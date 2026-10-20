import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
import {
  APPROVED_COMMERCIAL_TERMS,
  createBillingCheckout,
  createBillingPortal,
  stripeBillingConfigured,
  stripePlanForPrice,
  stripePriceForPlan,
  subscriptionEntitlementState,
  verifyStripeWebhookSignature,
} from "../src/billing.mjs";

const env = {
  STRIPE_SECRET_KEY: "fixture-secret-key",
  STRIPE_WEBHOOK_SECRET: "fixture-webhook-secret",
  STRIPE_PRICE_STANDARD: "price_standard_fixture",
  STRIPE_PRICE_SCALE: "price_scale_fixture",
};

assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.currency, "BRL");
assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.price_amount_cents, 8000);
assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.billing_interval, "month");
assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.usage_unlimited, false);
assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.functional_calls_per_month, 1_000_000);
assert.equal(APPROVED_COMMERCIAL_TERMS.TRIAL.functional_calls_total, 5_000);
assert.equal(stripeBillingConfigured(env), true);
assert.equal(stripeBillingConfigured({
  ENVIRONMENT:"PROD", STRIPE_SECRET_KEY:"sk_test_MustNotBeProd123",
  STRIPE_WEBHOOK_SECRET:"whsec_ValidFixture123",
}), false);
assert.equal(stripeBillingConfigured({
  ENVIRONMENT:"DEV", STRIPE_SECRET_KEY:"sk_live_MustNotBeDev123",
  STRIPE_WEBHOOK_SECRET:"whsec_ValidFixture123",
}), false);
assert.equal(stripeBillingConfigured({
  ENVIRONMENT:"DEV", STRIPE_SECRET_KEY:"sk_test_ValidFixture123",
  STRIPE_WEBHOOK_SECRET:"whsec_ValidFixture123",
}), true);
assert.equal(stripePriceForPlan(env, "STANDARD"), "price_standard_fixture");
assert.equal(stripePlanForPrice(env, "price_scale_fixture"), null);
assert.equal(stripePlanForPrice(env, "price_unknown"), null);

assert.equal(subscriptionEntitlementState("active"), "ACTIVE");
assert.equal(subscriptionEntitlementState("trialing"), "ACTIVE");
assert.equal(subscriptionEntitlementState("past_due"), "SUSPENDED");
assert.equal(subscriptionEntitlementState("unpaid"), "SUSPENDED");
assert.equal(subscriptionEntitlementState("canceled"), "REVOKED");

async function signatureFor(secret, timestamp, raw) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const bytes = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(String(timestamp) + "." + raw),
  );
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

const raw = JSON.stringify({ id: "evt_fixture", type: "ping", data: { object: {} } });
const timestamp = 1800000000;
const signature = await signatureFor(env.STRIPE_WEBHOOK_SECRET, timestamp, raw);
assert.equal(
  await verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${signature}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 10,
  ),
  true,
);

await assert.rejects(
  verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${"0".repeat(64)}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 10,
  ),
  /BILLING_WEBHOOK_SIGNATURE_INVALID/,
);

await assert.rejects(
  verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${signature}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 301,
  ),
  /BILLING_WEBHOOK_TIMESTAMP_INVALID/,
);

const queries = [];
const db = new DatabaseSync(":memory:");
const migrations = new URL("../migrations/", import.meta.url);
for (const file of ["0001_product.sql", "0003_plan_grants.sql", "0005_devices.sql",
  "0013_billing_v1.sql", "0014_founder_internal_entitlement.sql",
  "0021_commercial_terms_20261005.sql", "0036_commander_prelaunch_commercial_terms.sql",
  "0037_billing_recovery_and_checkout_attempts.sql"]) {
  db.exec(fs.readFileSync(new URL(file, migrations), "utf8"));
}
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)")
  .run("HARA-TENANT-FIXTURE", "Fixture", "ACTIVE", "DEV", "2026-10-10T00:00:00Z");
env.PRODUCT_DB = {
  prepare(sql) {
    queries.push(sql);
    const statement = db.prepare(sql);
    return {
      bind(...args) {
        return {
          async first() { return statement.get(...args) || null; },
          async run() { const result = statement.run(...args); return {meta:{changes:Number(result.changes)}}; },
        };
      },
    };
  },
};

let checkoutRequest = null;
const fakeFetch = async (url, options) => {
  checkoutRequest = { url, options };
  return new Response(JSON.stringify({
    id: "cs_test_fixture",
    url: "https://checkout.stripe.com/c/pay/cs_test_fixture",
    expires_at: Math.floor(Date.now()/1000)+3600,
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
};

const result = await createBillingCheckout(
  new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", {
    method: "POST",
  }),
  env,
  {
    tenant_id: "HARA-TENANT-FIXTURE",
    subject_id: "HARA-SUBJECT-FIXTURE",
    email: "fixture@example.invalid",
    role: "OWNER",
  },
  "STANDARD",
  fakeFetch,
);

assert.equal(result.plan_code, "STANDARD");
assert.equal(result.secret_material_exposed, false);
assert.equal(checkoutRequest.url, "https://api.stripe.com/v1/checkout/sessions");
const form = new URLSearchParams(checkoutRequest.options.body);
assert.equal(form.get("mode"), "subscription");
assert.equal(form.get("line_items[0][price]"), "price_standard_fixture");
assert.equal(form.get("metadata[tenant_id]"), "HARA-TENANT-FIXTURE");
assert.equal(form.get("subscription_data[metadata][plan_code]"), "STANDARD");
assert.equal(form.get("tax_id_collection[enabled]"), "true");
assert.equal(checkoutRequest.options.headers.authorization, "Bearer fixture-secret-key");
assert.match(checkoutRequest.options.headers["idempotency-key"], /^commander_checkout_/);

const evilFetch = async () => new Response(JSON.stringify({
  id: "cs_test_fixture",
  url: "https://evilstripe.com/not-allowed",
  expires_at: Math.floor(Date.now()/1000)+3600,
}), {
  status: 200,
  headers: { "content-type": "application/json" },
});
db.prepare("UPDATE billing_checkout_attempts SET expires_at_utc=? WHERE tenant_id=?")
  .run("2026-10-01T00:00:00.000Z", "HARA-TENANT-FIXTURE");
await assert.rejects(
  createBillingCheckout(
    new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", {
      method: "POST",
    }),
    env,
    {
      tenant_id: "HARA-TENANT-FIXTURE",
      subject_id: "HARA-SUBJECT-FIXTURE",
      email: "fixture@example.invalid",
      role: "OWNER",
    },
    "STANDARD",
    evilFetch,
  ),
  /BILLING_CHECKOUT_RESPONSE_INVALID/,
);

let portalRequest = null;
const portalEnv = {
  ...env,
  STRIPE_PORTAL_CONFIGURATION: "bpc_test_config123",
  PRODUCT_DB: {
    prepare() {
      return { bind() {
        return { async first() { return { external_customer_id: "cus_test_fixture" }; } };
      } };
    },
  },
};
const portalResult = await createBillingPortal(
  new Request("https://commander.haralabs.com.br/api/portal/billing/portal", {method:"POST"}),
  portalEnv,
  {tenant_id:"HARA-TENANT-FIXTURE",role:"OWNER"},
  async (url,options) => {
    portalRequest = {url,options};
    return new Response(JSON.stringify({url:"https://billing.stripe.com/p/session/test_fixture"}),{
      status:200,headers:{"content-type":"application/json"},
    });
  },
);
assert.equal(portalResult.secret_material_exposed,false);
assert.equal(portalRequest.url,"https://api.stripe.com/v1/billing_portal/sessions");
assert.equal(new URLSearchParams(portalRequest.options.body).get("configuration"),"bpc_test_config123");
assert.equal(new URLSearchParams(portalRequest.options.body).get("customer"),"cus_test_fixture");
console.log("COMMANDER_BILLING_PORTAL_EXPLICIT_CONFIGURATION=PASS");

console.log("COMMANDER_BILLING_V1_SIGNATURE=PASS");
console.log("COMMANDER_BILLING_V1_PLAN_MAPPING=PASS");
console.log("COMMANDER_BILLING_V1_CHECKOUT_CONTRACT=PASS");
console.log("COMMANDER_BILLING_V1_SECRET_COMMIT=ABSENT");
