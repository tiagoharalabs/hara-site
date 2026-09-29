const STRIPE_API = "https://api.stripe.com/v1";
const WEBHOOK_TOLERANCE_SECONDS = 300;
const WEBHOOK_MAX_BYTES = 512 * 1024;
const PAID_PLANS = Object.freeze(["STANDARD", "SCALE"]);
const ACTIVE_SUBSCRIPTION_STATES = new Set(["active", "trialing"]);
const SUSPENDED_SUBSCRIPTION_STATES = new Set(["incomplete", "past_due", "unpaid", "paused"]);
const REVOKED_SUBSCRIPTION_STATES = new Set(["canceled", "incomplete_expired"]);

function nowIso() {
  return new Date().toISOString();
}

function cleanText(value, max = 240) {
  const text = String(value || "").trim();
  return text && text.length <= max ? text : null;
}

function cleanStripeId(value, prefixes = []) {
  const text = cleanText(value, 255);
  if (!text || !/^[A-Za-z0-9_]+$/.test(text)) return null;
  if (prefixes.length && !prefixes.some((prefix) => text.startsWith(prefix))) return null;
  return text;
}

function cleanPlanCode(value) {
  const plan = String(value || "").trim().toUpperCase();
  return PAID_PLANS.includes(plan) ? plan : null;
}

function boolInt(value) {
  return value === true ? 1 : 0;
}

function stripeHttpsUrl(value) {
  const text = cleanText(value, 2048);
  if (!text) return null;
  let parsed;
  try {
    parsed = new URL(text);
  } catch (_error) {
    return null;
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "https:") return null;
  if (host !== "stripe.com" && !host.endsWith(".stripe.com")) return null;
  return parsed.toString();
}

function epochToIso(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return new Date(seconds * 1000).toISOString();
}

function priceMap(env) {
  return {
    STANDARD: cleanStripeId(env.STRIPE_PRICE_STANDARD, ["price_"]),
    SCALE: cleanStripeId(env.STRIPE_PRICE_SCALE, ["price_"]),
  };
}

export function stripeBillingConfigured(env) {
  return Boolean(
    cleanText(env.STRIPE_SECRET_KEY, 512)
    && cleanText(env.STRIPE_WEBHOOK_SECRET, 512)
  );
}

export function stripePriceForPlan(env, planCode) {
  const plan = cleanPlanCode(planCode);
  if (!plan) return null;
  return priceMap(env)[plan] || null;
}

export function stripePlanForPrice(env, priceId) {
  const price = cleanStripeId(priceId, ["price_"]);
  if (!price) return null;
  const prices = priceMap(env);
  for (const plan of PAID_PLANS) {
    if (prices[plan] === price) return plan;
  }
  return null;
}

export function subscriptionEntitlementState(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (ACTIVE_SUBSCRIPTION_STATES.has(normalized)) return "ACTIVE";
  if (SUSPENDED_SUBSCRIPTION_STATES.has(normalized)) return "SUSPENDED";
  if (REVOKED_SUBSCRIPTION_STATES.has(normalized)) return "REVOKED";
  return "SUSPENDED";
}

function requireBillingConfigured(env) {
  if (!stripeBillingConfigured(env)) throw new Error("BILLING_NOT_CONFIGURED");
}

function requireBillingAdmin(session) {
  if (!session || !["OWNER", "ADMIN"].includes(String(session.role || ""))) {
    throw new Error("BILLING_ADMIN_REQUIRED");
  }
}

async function stripePost(env, path, fields, fetcher = fetch) {
  requireBillingConfigured(env);
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(fields || {})) {
    if (value === undefined || value === null || value === "") continue;
    body.set(key, String(value));
  }

  const headers = {
    authorization: "Bearer " + String(env.STRIPE_SECRET_KEY),
    accept: "application/json",
    "content-type": "application/x-www-form-urlencoded",
  };
  const apiVersion = cleanText(env.STRIPE_API_VERSION, 64);
  if (apiVersion) headers["stripe-version"] = apiVersion;

  let response;
  try {
    response = await fetcher(STRIPE_API + path, {
      method: "POST",
      headers,
      body: body.toString(),
      redirect: "error",
    });
  } catch (_error) {
    throw new Error("BILLING_PROVIDER_UNREACHABLE");
  }

  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    throw new Error("BILLING_PROVIDER_RESPONSE_INVALID");
  }
  if (!response.ok) {
    const type = String(payload?.error?.type || "").toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    throw new Error(type ? "BILLING_PROVIDER_" + type.slice(0, 80) : "BILLING_PROVIDER_ERROR");
  }
  return payload;
}

async function activePlan(env, planCode) {
  return env.PRODUCT_DB.prepare(
    `SELECT plan_code, display_name, meter_id, period_kind, unit_limit, state
       FROM plans
      WHERE plan_code = ? AND state = 'ACTIVE'
      LIMIT 1`
  ).bind(planCode).first();
}

async function billingConnection(env, tenantId) {
  return env.PRODUCT_DB.prepare(
    `SELECT billing_connection_id, tenant_id, provider,
            external_customer_id, external_subscription_id,
            plan_code, subscription_status, current_period_end_utc,
            cancel_at_period_end, state, created_at_utc, updated_at_utc
       FROM billing_connections
      WHERE billing_connection_id = ?
      LIMIT 1`
  ).bind("STRIPE:" + tenantId).first();
}

export async function billingStatus(env, session) {
  const prices = priceMap(env);
  const plans = {};
  for (const planCode of PAID_PLANS) {
    const plan = await activePlan(env, planCode);
    plans[planCode] = {
      plan_code: planCode,
      catalog_active: Boolean(plan),
      checkout_ready: Boolean(
        stripeBillingConfigured(env) && plan && prices[planCode]
      ),
      unit_limit: plan?.unit_limit == null ? null : Number(plan.unit_limit),
      period_kind: plan ? plan.period_kind : null,
    };
  }

  const connection = await billingConnection(env, session.tenant_id);
  return {
    schema: "hara.commander-billing-status.v1",
    provider: "STRIPE",
    configured: stripeBillingConfigured(env),
    can_manage: ["OWNER", "ADMIN"].includes(String(session.role || "")),
    plans,
    connection: connection ? {
      state: connection.state,
      plan_code: connection.plan_code,
      subscription_status: connection.subscription_status,
      current_period_end_utc: connection.current_period_end_utc,
      cancel_at_period_end: Boolean(connection.cancel_at_period_end),
      customer_portal_ready: Boolean(connection.external_customer_id),
      subscription_present: Boolean(connection.external_subscription_id),
    } : null,
    secret_material_exposed: false,
  };
}
export async function createBillingCheckout(request, env, session, planCode, fetcher = fetch) {
  requireBillingAdmin(session);
  requireBillingConfigured(env);

  const plan = cleanPlanCode(planCode);
  if (!plan) throw new Error("BILLING_PLAN_INVALID");
  const catalog = await activePlan(env, plan);
  if (!catalog) throw new Error("BILLING_PLAN_UNAVAILABLE");

  const priceId = stripePriceForPlan(env, plan);
  if (!priceId) throw new Error("BILLING_PRICE_NOT_CONFIGURED");

  const existing = await billingConnection(env, session.tenant_id);
  if (
    existing?.external_subscription_id
    && ["active", "trialing", "past_due", "unpaid", "paused"].includes(
      String(existing.subscription_status || "").toLowerCase()
    )
  ) {
    throw new Error("BILLING_SUBSCRIPTION_ALREADY_EXISTS");
  }

  const origin = new URL(request.url).origin;
  const fields = {
    mode: "subscription",
    "line_items[0][price]": priceId,
    "line_items[0][quantity]": "1",
    success_url: origin + "/?billing=success#plans",
    cancel_url: origin + "/?billing=cancelled#plans",
    client_reference_id: session.tenant_id,
    "metadata[tenant_id]": session.tenant_id,
    "metadata[subject_id]": session.subject_id,
    "metadata[plan_code]": plan,
    "subscription_data[metadata][tenant_id]": session.tenant_id,
    "subscription_data[metadata][plan_code]": plan,
    "subscription_data[metadata][source]": "HARA_COMMANDER",
    "tax_id_collection[enabled]": "true",
  };

  if (existing?.external_customer_id) {
    fields.customer = existing.external_customer_id;
  } else if (session.email) {
    fields.customer_email = String(session.email).slice(0, 320);
  }

  const checkout = await stripePost(env, "/checkout/sessions", fields, fetcher);
  const checkoutId = cleanStripeId(checkout.id, ["cs_"]);
  const checkoutUrl = stripeHttpsUrl(checkout.url);
  if (!checkoutId || !checkoutUrl) throw new Error("BILLING_CHECKOUT_RESPONSE_INVALID");

  return {
    schema: "hara.commander-billing-checkout.v1",
    plan_code: plan,
    checkout_session_id: checkoutId,
    url: checkoutUrl,
    secret_material_exposed: false,
  };
}

export async function createBillingPortal(request, env, session, fetcher = fetch) {
  requireBillingAdmin(session);
  requireBillingConfigured(env);
  const connection = await billingConnection(env, session.tenant_id);
  const customerId = cleanStripeId(connection?.external_customer_id, ["cus_"]);
  if (!customerId) throw new Error("BILLING_CUSTOMER_NOT_READY");

  const origin = new URL(request.url).origin;
  const portal = await stripePost(env, "/billing_portal/sessions", {
    customer: customerId,
    return_url: origin + "/#plans",
  }, fetcher);

  const url = stripeHttpsUrl(portal.url);
  if (!url) throw new Error("BILLING_PORTAL_RESPONSE_INVALID");

  return {
    schema: "hara.commander-billing-portal.v1",
    url,
    secret_material_exposed: false,
  };
}

function hex(bytes) {
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function timingSafeHexEqual(left, right) {
  const a = String(left || "").toLowerCase();
  const b = String(right || "").toLowerCase();
  if (a.length !== b.length || !/^[0-9a-f]+$/.test(a) || !/^[0-9a-f]+$/.test(b)) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function hmacSha256Hex(secret, text) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(await crypto.subtle.sign("HMAC", key, encoder.encode(text)));
}

export async function verifyStripeWebhookSignature(rawBody, signatureHeader, secret, nowSeconds = Date.now() / 1000) {
  const header = String(signatureHeader || "");
  const parts = header.split(",").map((item) => item.trim()).filter(Boolean);
  let timestamp = null;
  const signatures = [];
  for (const part of parts) {
    const [key, value] = part.split("=", 2);
    if (key === "t" && /^\d+$/.test(value || "")) timestamp = Number(value);
    if (key === "v1" && /^[0-9a-f]{64}$/i.test(value || "")) signatures.push(value);
  }
  if (!timestamp || signatures.length < 1) throw new Error("BILLING_WEBHOOK_SIGNATURE_INVALID");
  if (Math.abs(Number(nowSeconds) - timestamp) > WEBHOOK_TOLERANCE_SECONDS) {
    throw new Error("BILLING_WEBHOOK_TIMESTAMP_INVALID");
  }
  const expected = await hmacSha256Hex(secret, String(timestamp) + "." + rawBody);
  if (!signatures.some((candidate) => timingSafeHexEqual(candidate, expected))) {
    throw new Error("BILLING_WEBHOOK_SIGNATURE_INVALID");
  }
  return true;
}
async function beginWebhookEvent(env, eventId, eventType) {
  const now = nowIso();
  await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO billing_webhook_events
      (event_id, provider, event_type, state, received_at_utc, processed_at_utc, result_code)
     VALUES (?, 'STRIPE', ?, 'RECEIVED', ?, NULL, NULL)`
  ).bind(eventId, eventType, now).run();

  return env.PRODUCT_DB.prepare(
    `SELECT event_id, event_type, state, result_code
       FROM billing_webhook_events
      WHERE event_id = ?
      LIMIT 1`
  ).bind(eventId).first();
}

async function claimWebhookEvent(env, eventId) {
  const claimed = await env.PRODUCT_DB.prepare(
    `UPDATE billing_webhook_events
        SET state = 'PROCESSING', processed_at_utc = NULL, result_code = NULL
      WHERE event_id = ? AND state IN ('RECEIVED','FAILED')`
  ).bind(eventId).run();
  return Boolean(claimed.meta?.changes);
}

async function finishWebhookEvent(env, eventId, state, resultCode) {
  await env.PRODUCT_DB.prepare(
    `UPDATE billing_webhook_events
        SET state = ?, processed_at_utc = ?, result_code = ?
      WHERE event_id = ?`
  ).bind(state, nowIso(), resultCode, eventId).run();
}

async function tenantExists(env, tenantId) {
  if (!cleanText(tenantId, 180)) return false;
  const row = await env.PRODUCT_DB.prepare(
    "SELECT tenant_id FROM tenants WHERE tenant_id = ? LIMIT 1"
  ).bind(tenantId).first();
  return Boolean(row);
}

async function resolveTenantForObject(env, object) {
  const metadataTenant = cleanText(object?.metadata?.tenant_id, 180);
  if (metadataTenant && await tenantExists(env, metadataTenant)) return metadataTenant;

  const subscriptionId = cleanStripeId(object?.id, ["sub_"])
    || cleanStripeId(object?.subscription, ["sub_"]);
  if (subscriptionId) {
    const row = await env.PRODUCT_DB.prepare(
      `SELECT tenant_id FROM billing_connections
        WHERE provider = 'STRIPE' AND external_subscription_id = ?
        LIMIT 1`
    ).bind(subscriptionId).first();
    if (row?.tenant_id) return row.tenant_id;
  }

  const customerId = cleanStripeId(object?.customer, ["cus_"]);
  if (customerId) {
    const row = await env.PRODUCT_DB.prepare(
      `SELECT tenant_id FROM billing_connections
        WHERE provider = 'STRIPE' AND external_customer_id = ?
        LIMIT 1`
    ).bind(customerId).first();
    if (row?.tenant_id) return row.tenant_id;
  }
  return null;
}

async function upsertBillingConnection(env, tenantId, {
  customerId = null,
  subscriptionId = null,
  planCode = null,
  subscriptionStatus = null,
  currentPeriodEndUtc = null,
  cancelAtPeriodEnd = false,
  state = "ACTIVE",
} = {}) {
  const id = "STRIPE:" + tenantId;
  const now = nowIso();
  await env.PRODUCT_DB.prepare(
    `INSERT INTO billing_connections
      (billing_connection_id, tenant_id, provider, external_customer_id,
       external_subscription_id, state, created_at_utc, updated_at_utc,
       plan_code, subscription_status, current_period_end_utc, cancel_at_period_end)
     VALUES (?, ?, 'STRIPE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(billing_connection_id) DO UPDATE SET
       external_customer_id = COALESCE(excluded.external_customer_id, billing_connections.external_customer_id),
       external_subscription_id = COALESCE(excluded.external_subscription_id, billing_connections.external_subscription_id),
       state = excluded.state,
       updated_at_utc = excluded.updated_at_utc,
       plan_code = COALESCE(excluded.plan_code, billing_connections.plan_code),
       subscription_status = COALESCE(excluded.subscription_status, billing_connections.subscription_status),
       current_period_end_utc = COALESCE(excluded.current_period_end_utc, billing_connections.current_period_end_utc),
       cancel_at_period_end = excluded.cancel_at_period_end`
  ).bind(
    id, tenantId, customerId, subscriptionId, state, now, now,
    planCode, subscriptionStatus, currentPeriodEndUtc, boolInt(cancelAtPeriodEnd),
  ).run();
}

async function syncPaidEntitlement(env, tenantId, planCode, entitlementState) {
  const entitlementId = "BILLING:" + tenantId;
  const now = nowIso();

  if (entitlementState === "ACTIVE") {
    const plan = await activePlan(env, planCode);
    if (!plan) throw new Error("BILLING_PLAN_UNAVAILABLE");

    await env.PRODUCT_DB.batch([
      env.PRODUCT_DB.prepare(
        `UPDATE entitlements
            SET state = 'EXPIRED', valid_until_utc = ?
          WHERE tenant_id = ?
            AND entitlement_id <> ?
            AND state = 'ACTIVE'`
      ).bind(now, tenantId, entitlementId),
      env.PRODUCT_DB.prepare(
        `INSERT INTO entitlements
          (entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc)
         VALUES (?, ?, NULL, ?, 'ACTIVE', ?, NULL)
         ON CONFLICT(entitlement_id) DO UPDATE SET
           plan_code = excluded.plan_code,
           state = 'ACTIVE',
           valid_from_utc = excluded.valid_from_utc,
           valid_until_utc = NULL`
      ).bind(entitlementId, tenantId, planCode, now),
    ]);
    return;
  }

  if (entitlementState === "SUSPENDED") {
    await env.PRODUCT_DB.prepare(
      `UPDATE entitlements
          SET state = 'SUSPENDED'
        WHERE entitlement_id = ? AND tenant_id = ?`
    ).bind(entitlementId, tenantId).run();
    return;
  }

  await env.PRODUCT_DB.prepare(
    `UPDATE entitlements
        SET state = 'REVOKED', valid_until_utc = ?
      WHERE entitlement_id = ? AND tenant_id = ?`
  ).bind(now, entitlementId, tenantId).run();
}
async function processCheckoutCompleted(env, object) {
  const tenantId = cleanText(object?.metadata?.tenant_id || object?.client_reference_id, 180);
  if (!tenantId || !await tenantExists(env, tenantId)) throw new Error("BILLING_TENANT_INVALID");

  const customerId = cleanStripeId(object?.customer, ["cus_"]);
  const subscriptionId = cleanStripeId(object?.subscription, ["sub_"]);
  const planCode = cleanPlanCode(object?.metadata?.plan_code);
  await upsertBillingConnection(env, tenantId, {
    customerId,
    subscriptionId,
    planCode,
    state: "CHECKOUT_COMPLETED",
  });
  return "CHECKOUT_LINKED";
}

async function processSubscription(env, eventType, object) {
  const tenantId = await resolveTenantForObject(env, object);
  if (!tenantId) throw new Error("BILLING_TENANT_NOT_FOUND");

  const customerId = cleanStripeId(object?.customer, ["cus_"]);
  const subscriptionId = cleanStripeId(object?.id, ["sub_"]);
  const status = String(object?.status || "").trim().toLowerCase();
  if (!subscriptionId || !status) throw new Error("BILLING_SUBSCRIPTION_INVALID");

  const priceId = cleanStripeId(object?.items?.data?.[0]?.price?.id, ["price_"]);
  const planCode = stripePlanForPrice(env, priceId)
    || cleanPlanCode(object?.metadata?.plan_code);
  if (!planCode) throw new Error("BILLING_PRICE_UNKNOWN");

  const configuredPrice = stripePriceForPlan(env, planCode);
  if (!configuredPrice || priceId !== configuredPrice) throw new Error("BILLING_PRICE_MISMATCH");

  const entitlementState = eventType === "customer.subscription.deleted"
    ? "REVOKED"
    : subscriptionEntitlementState(status);

  await upsertBillingConnection(env, tenantId, {
    customerId,
    subscriptionId,
    planCode,
    subscriptionStatus: status,
    currentPeriodEndUtc: epochToIso(object?.current_period_end),
    cancelAtPeriodEnd: Boolean(object?.cancel_at_period_end || object?.cancel_at),
    state: entitlementState === "ACTIVE" ? "ACTIVE" : entitlementState,
  });
  await syncPaidEntitlement(env, tenantId, planCode, entitlementState);
  return "SUBSCRIPTION_" + entitlementState;
}

async function processInvoicePaymentFailed(env, object) {
  const tenantId = await resolveTenantForObject(env, object);
  if (!tenantId) return "INVOICE_TENANT_NOT_FOUND";
  await upsertBillingConnection(env, tenantId, {
    customerId: cleanStripeId(object?.customer, ["cus_"]),
    subscriptionId: cleanStripeId(object?.subscription, ["sub_"]),
    subscriptionStatus: "past_due",
    state: "SUSPENDED",
  });
  await env.PRODUCT_DB.prepare(
    `UPDATE entitlements
        SET state = 'SUSPENDED'
      WHERE entitlement_id = ? AND tenant_id = ?`
  ).bind("BILLING:" + tenantId, tenantId).run();
  return "INVOICE_PAYMENT_FAILED";
}

async function processStripeEvent(env, event) {
  const type = String(event?.type || "");
  const object = event?.data?.object;
  if (!object || typeof object !== "object") throw new Error("BILLING_EVENT_OBJECT_INVALID");

  if (type === "checkout.session.completed") return processCheckoutCompleted(env, object);
  if (
    type === "customer.subscription.created"
    || type === "customer.subscription.updated"
    || type === "customer.subscription.deleted"
  ) {
    return processSubscription(env, type, object);
  }
  if (type === "invoice.payment_failed") return processInvoicePaymentFailed(env, object);
  return null;
}

export async function handleStripeWebhook(request, env) {
  requireBillingConfigured(env);
  const declaredLength = Number(request.headers.get("content-length") || "0");
  if (Number.isFinite(declaredLength) && declaredLength > WEBHOOK_MAX_BYTES) {
    throw new Error("BILLING_WEBHOOK_PAYLOAD_TOO_LARGE");
  }
  const rawBody = await request.text();
  if (new TextEncoder().encode(rawBody).byteLength > WEBHOOK_MAX_BYTES) {
    throw new Error("BILLING_WEBHOOK_PAYLOAD_TOO_LARGE");
  }
  const signature = request.headers.get("stripe-signature");
  await verifyStripeWebhookSignature(
    rawBody,
    signature,
    String(env.STRIPE_WEBHOOK_SECRET),
  );

  let event;
  try {
    event = JSON.parse(rawBody);
  } catch (_error) {
    throw new Error("BILLING_WEBHOOK_JSON_INVALID");
  }

  const eventId = cleanStripeId(event?.id, ["evt_"]);
  const eventType = cleanText(event?.type, 180);
  if (!eventId || !eventType) throw new Error("BILLING_WEBHOOK_EVENT_INVALID");

  const existing = await beginWebhookEvent(env, eventId, eventType);
  if (existing?.state === "PROCESSED" || existing?.state === "IGNORED") {
    return {
      schema: "hara.commander-billing-webhook.v1",
      ok: true,
      duplicate: true,
      event_id: eventId,
      result_code: existing.result_code,
    };
  }

  const claimed = await claimWebhookEvent(env, eventId);
  if (!claimed) {
    return {
      schema: "hara.commander-billing-webhook.v1",
      ok: true,
      duplicate: true,
      event_id: eventId,
      result_code: "EVENT_IN_PROGRESS",
    };
  }

  try {
    const resultCode = await processStripeEvent(env, event);
    if (!resultCode) {
      await finishWebhookEvent(env, eventId, "IGNORED", "EVENT_IGNORED");
      return {
        schema: "hara.commander-billing-webhook.v1",
        ok: true,
        duplicate: false,
        event_id: eventId,
        result_code: "EVENT_IGNORED",
      };
    }

    await finishWebhookEvent(env, eventId, "PROCESSED", resultCode);
    return {
      schema: "hara.commander-billing-webhook.v1",
      ok: true,
      duplicate: false,
      event_id: eventId,
      result_code: resultCode,
    };
  } catch (error) {
    const raw = String(error?.message || "BILLING_WEBHOOK_PROCESSING_FAILED");
    const code = /^[A-Z0-9_]{1,120}$/.test(raw) ? raw : "BILLING_WEBHOOK_PROCESSING_FAILED";
    await finishWebhookEvent(env, eventId, "FAILED", code).catch(() => null);
    throw error;
  }
}
