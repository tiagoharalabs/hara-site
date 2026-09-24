import { DurableObject } from "cloudflare:workers";
import {
  authCallbackFailureResponse,
  authStatus,
  beginLogin,
  finishLogin,
  logout,
  resolvePortalSession,
} from "./auth.js";
import { normalizeIssuer, randomToken, sha256 } from "./oidc.js";
import {
  DEVICE_FUNCTION_ID,
  canonicalDeviceToolPayload,
} from "./device-tool-contract.mjs";

const DEMO_TENANT = "HARA-TENANT-DEMO-0001";
const MCP_METER_ID = "HARA_COMMANDER_GOVERNED_INVOKE";
const MCP_SECONDARY_PROVIDER = "CLOUDFLARE_ACCESS";
const DEVICE_CALL_TTL_SECONDS = 50;
const QUOTA_RESERVATION_TTL_SECONDS = 10 * 60;
const PAIRING_RETENTION_SECONDS = 30 * 24 * 60 * 60;
const PAIRING_RETENTION_BATCH = 100;
const MCP_TOOL_GRANTS = Object.freeze({
  "hara.health": "COMMANDER_DISCOVERY",
  "hara.functions.list": "COMMANDER_DISCOVERY",
  "hara.functions.describe": "COMMANDER_DISCOVERY",
  "hara.functions.invoke": "COMMANDER_READ_ONLY_INVOKE",
  "hara.receipts.get": "COMMANDER_RECEIPT_READ",
});

const SECURITY_HEADERS = Object.freeze({
  "strict-transport-security": "max-age=31536000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "no-referrer",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "x-robots-tag": "noindex, nofollow",
});

function json(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      ...SECURITY_HEADERS,
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type,authorization",
      "access-control-allow-methods": "GET,POST,OPTIONS"
    }
  });
}

function internalJson(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      ...SECURITY_HEADERS,
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8"
    }
  });
}

function monthKey(now = new Date()) {
  return now.toISOString().slice(0, 7);
}

function requireRuntime(env) {
  if (!["DEV", "PROD"].includes(String(env.ENVIRONMENT || ""))) {
    throw new Error("RUNTIME_ENV_INVALID");
  }
}

function requireDev(env) {
  if (env.ENVIRONMENT !== "DEV") {
    throw new Error("DEV_ENDPOINT_DISABLED");
  }
}

function sanitizeErrorCode(error) {
  if (error instanceof SyntaxError) return "INVALID_JSON";
  const raw = String(error?.message || "INTERNAL_ERROR");
  return /^[A-Z][A-Z0-9_]{0,119}$/.test(raw) ? raw : "INTERNAL_ERROR";
}

function secretMatches(expectedValue, suppliedValue) {
  const expected = String(expectedValue || "");
  const supplied = String(suppliedValue || "");
  if (!expected || supplied.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) {
    diff |= expected.charCodeAt(i) ^ supplied.charCodeAt(i);
  }
  return diff === 0;
}

function requireRemoteDevToken(request, env) {
  if (env.STORAGE_MODE !== "REMOTE_DEV") return;
  if (!secretMatches(env.DEV_ACCESS_TOKEN, request.headers.get("x-hara-dev-token"))) {
    throw new Error("DEV_ACCESS_DENIED");
  }
}

function requireMcpProductToken(request, env) {
  if (!secretMatches(env.MCP_PRODUCT_TOKEN, request.headers.get("x-hara-mcp-product-token"))) {
    throw new Error("MCP_PRODUCT_ACCESS_DENIED");
  }
}

function requirePortalMutationOrigin(request) {
  const expectedOrigin = new URL(request.url).origin;
  const origin = request.headers.get("origin");
  const fetchSite = String(request.headers.get("sec-fetch-site") || "").toLowerCase();
  if (!origin || origin !== expectedOrigin) throw new Error("PORTAL_ORIGIN_DENIED");
  if (fetchSite && fetchSite !== "same-origin") throw new Error("PORTAL_ORIGIN_DENIED");
}

function cleanId(value, max = 180) {
  const text = String(value || "").trim();
  if (!text || text.length > max || !/^[A-Za-z0-9_.:-]+$/.test(text)) {
    throw new Error("INVALID_IDENTIFIER");
  }
  return text;
}

function cleanOpaque(value, max = 512) {
  const text = String(value || "");
  if (!text || text.length > max || /[\u0000-\u001f\u007f]/.test(text)) {
    throw new Error("INVALID_OPAQUE_VALUE");
  }
  return text;
}

function normalizeEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  if (!email || email.length > 320 || !email.includes("@")) return null;
  return email;
}

function nowIso(offsetSeconds = 0) {
  return new Date(Date.now() + offsetSeconds * 1000).toISOString();
}

function bearerToken(request) {
  const header = String(request.headers.get("authorization") || "");
  if (!header.toLowerCase().startsWith("bearer ")) return null;
  const token = header.slice(7).trim();
  return token || null;
}

function cleanDeviceName(value) {
  const text = String(value || "").trim().replace(/\s+/g, " ");
  if (!text || text.length > 120 || /[\u0000-\u001f\u007f]/.test(text)) {
    throw new Error("DEVICE_NAME_INVALID");
  }
  return text;
}

function normalizeDevicePlatform(value) {
  const platform = String(value || "").trim().toUpperCase();
  if (!["LINUX", "WINDOWS"].includes(platform)) throw new Error("DEVICE_PLATFORM_INVALID");
  return platform;
}

function cleanAgentValue(value, max = 80) {
  const text = String(value || "").trim();
  if (!text) return null;
  if (text.length > max || /[\u0000-\u001f\u007f]/.test(text)) {
    throw new Error("DEVICE_METADATA_INVALID");
  }
  return text;
}

function deviceOnline(lastSeenAtUtc, now = Date.now()) {
  if (!lastSeenAtUtc) return false;
  const seen = Date.parse(String(lastSeenAtUtc));
  return Number.isFinite(seen) && now - seen <= 90_000;
}

function boundedJson(value, maxBytes, code) {
  let text;
  try {
    text = JSON.stringify(value == null ? {} : value);
  } catch (_error) {
    throw new Error(code);
  }
  if (new TextEncoder().encode(text).byteLength > maxBytes) {
    throw new Error(code);
  }
  return text;
}

export class TenantQuota extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS request_state (
          request_id TEXT PRIMARY KEY,
          subject_id TEXT NOT NULL DEFAULT 'LEGACY',
          period_key TEXT NOT NULL,
          function_id TEXT NOT NULL,
          state TEXT NOT NULL,
          units INTEGER NOT NULL,
          receipt_sha256 TEXT,
          updated_at_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_request_period
          ON request_state(period_key, state);
      `);

      const columns = [...this.ctx.storage.sql.exec("PRAGMA table_info(request_state)")];
      if (!columns.some((column) => column.name === "subject_id")) {
        this.ctx.storage.sql.exec(
          "ALTER TABLE request_state ADD COLUMN subject_id TEXT NOT NULL DEFAULT 'LEGACY'"
        );
      }
    });
  }

  expireStaleReservations() {
    const now = new Date().toISOString();
    const cutoff = new Date(
      Date.now() - QUOTA_RESERVATION_TTL_SECONDS * 1000
    ).toISOString();
    this.ctx.storage.sql.exec(
      `UPDATE request_state
          SET state = 'RELEASED', units = 0, updated_at_utc = ?
        WHERE state = 'RESERVED'
          AND updated_at_utc <= ?`,
      now,
      cutoff
    );
  }

  status(periodKey, limit) {
    this.expireStaleReservations();
    const row = this.ctx.storage.sql.exec(
      `SELECT COALESCE(SUM(units), 0) AS consumed
         FROM request_state
        WHERE period_key = ?
          AND state IN ('RESERVED', 'COMMITTED')`,
      periodKey
    ).one();

    const consumed = Number(row.consumed || 0);
    return {
      period_key: periodKey,
      limit,
      consumed_units: consumed,
      remaining_units: limit == null ? null : Math.max(limit - consumed, 0)
    };
  }

  reserve(requestId, subjectId, periodKey, functionId, limit) {
    this.expireStaleReservations();
    const existing = [...this.ctx.storage.sql.exec(
      `SELECT request_id, subject_id, period_key, function_id, state, units, receipt_sha256
         FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (existing) {
      if (
        existing.subject_id !== subjectId
        || existing.period_key !== periodKey
        || existing.function_id !== functionId
      ) {
        return { ok: false, code: "IDEMPOTENCY_CONFLICT", existing: true, state: existing.state };
      }
      return {
        ok: existing.state !== "DENIED",
        existing: true,
        state: existing.state,
        receipt_sha256: existing.receipt_sha256 || null,
        ...this.status(periodKey, limit)
      };
    }

    const balance = this.status(periodKey, limit);
    if (limit != null && balance.consumed_units >= limit) {
      this.ctx.storage.sql.exec(
        `INSERT INTO request_state
          (request_id, subject_id, period_key, function_id, state, units, updated_at_utc)
         VALUES (?, ?, ?, ?, 'DENIED', 0, ?)`,
        requestId, subjectId, periodKey, functionId, new Date().toISOString()
      );
      return { ok: false, code: "QUOTA_EXCEEDED", existing: false, state: "DENIED", ...balance };
    }

    this.ctx.storage.sql.exec(
      `INSERT INTO request_state
        (request_id, subject_id, period_key, function_id, state, units, updated_at_utc)
       VALUES (?, ?, ?, ?, 'RESERVED', 1, ?)`,
      requestId, subjectId, periodKey, functionId, new Date().toISOString()
    );

    return { ok: true, existing: false, state: "RESERVED", ...this.status(periodKey, limit) };
  }

  commit(requestId, subjectId, receiptSha256, limit) {
    this.expireStaleReservations();
    const row = [...this.ctx.storage.sql.exec(
      `SELECT request_id, subject_id, period_key, function_id, state, receipt_sha256
         FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (!row) return { ok: false, code: "RESERVATION_NOT_FOUND" };
    if (row.subject_id !== subjectId) return { ok: false, code: "IDEMPOTENCY_CONFLICT" };
    if (row.state === "COMMITTED") {
      if (row.receipt_sha256 !== receiptSha256) return { ok: false, code: "IDEMPOTENCY_CONFLICT" };
      return { ok: true, existing: true, state: "COMMITTED", ...this.status(row.period_key, limit) };
    }
    if (row.state !== "RESERVED") return { ok: false, code: "RESERVATION_NOT_ACTIVE", state: row.state };

    this.ctx.storage.sql.exec(
      `UPDATE request_state
          SET state = 'COMMITTED', receipt_sha256 = ?, updated_at_utc = ?
        WHERE request_id = ?`,
      receiptSha256, new Date().toISOString(), requestId
    );
    return { ok: true, existing: false, state: "COMMITTED", ...this.status(row.period_key, limit) };
  }

  release(requestId, subjectId, limit) {
    this.expireStaleReservations();
    const row = [...this.ctx.storage.sql.exec(
      `SELECT request_id, subject_id, period_key, state FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (!row) return { ok: false, code: "RESERVATION_NOT_FOUND" };
    if (row.subject_id !== subjectId) return { ok: false, code: "IDEMPOTENCY_CONFLICT" };
    if (row.state === "RELEASED") return { ok: true, existing: true, state: "RELEASED", ...this.status(row.period_key, limit) };
    if (row.state !== "RESERVED") return { ok: false, code: "RESERVATION_NOT_ACTIVE", state: row.state };

    this.ctx.storage.sql.exec(
      `UPDATE request_state SET state = 'RELEASED', units = 0, updated_at_utc = ? WHERE request_id = ?`,
      new Date().toISOString(), requestId
    );
    return { ok: true, existing: false, state: "RELEASED", ...this.status(row.period_key, limit) };
  }
}

async function entitlementForTenant(env, tenantId) {
  return env.PRODUCT_DB.prepare(
    `SELECT
       t.tenant_id,
       t.display_name AS tenant_name,
       t.state AS tenant_state,
       e.entitlement_id,
       e.state AS entitlement_state,
       p.plan_code,
       p.display_name AS plan_name,
       p.meter_id,
       p.period_kind,
       p.unit_limit
     FROM tenants t
     JOIN entitlements e ON e.tenant_id = t.tenant_id
     JOIN plans p ON p.plan_code = e.plan_code
    WHERE t.tenant_id = ?
      AND t.state = 'ACTIVE'
      AND e.state = 'ACTIVE'
      AND p.state = 'ACTIVE'
    LIMIT 1`
  ).bind(tenantId).first();
}

async function dashboard(env, tenantId) {
  const ent = await entitlementForTenant(env, tenantId);
  if (!ent) return null;

  const quota = env.TENANT_QUOTA.getByName(tenantId);
  const periodKey = ent.period_kind === "CALENDAR_MONTH" ? monthKey() : "LIFETIME";
  const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
  const usage = await quota.status(periodKey, limit);

  return {
    schema: "hara.commander-dashboard-dev.v1",
    tenant: {
      tenant_id: ent.tenant_id,
      display_name: ent.tenant_name,
      state: ent.tenant_state
    },
    entitlement: {
      entitlement_id: ent.entitlement_id,
      state: ent.entitlement_state,
      plan_code: ent.plan_code,
      plan_name: ent.plan_name,
      meter_id: ent.meter_id,
      period_kind: ent.period_kind,
      unit_limit: limit
    },
    usage
  };
}

async function dashboardForSubject(env, subjectId, tenantId) {
  const ent = await env.PRODUCT_DB.prepare(
    `SELECT
       t.tenant_id,
       t.display_name AS tenant_name,
       t.state AS tenant_state,
       e.entitlement_id,
       e.state AS entitlement_state,
       e.subject_id AS entitlement_subject_id,
       p.plan_code,
       p.display_name AS plan_name,
       p.meter_id,
       p.period_kind,
       p.unit_limit
     FROM tenants t
     JOIN entitlements e ON e.tenant_id = t.tenant_id
     JOIN plans p ON p.plan_code = e.plan_code
    WHERE t.tenant_id = ?
      AND t.state = 'ACTIVE'
      AND e.state = 'ACTIVE'
      AND p.state = 'ACTIVE'
      AND (e.subject_id IS NULL OR e.subject_id = ?)
    ORDER BY CASE WHEN e.subject_id = ? THEN 0 ELSE 1 END
    LIMIT 1`
  ).bind(tenantId, subjectId, subjectId).first();

  if (!ent) return null;
  const quota = env.TENANT_QUOTA.getByName(tenantId);
  const periodKey = ent.period_kind === "CALENDAR_MONTH" ? monthKey() : "LIFETIME";
  const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
  const usage = await quota.status(periodKey, limit);

  return {
    schema: "hara.commander-portal-dashboard.v1",
    tenant: {
      tenant_id: ent.tenant_id,
      display_name: ent.tenant_name,
      state: ent.tenant_state
    },
    entitlement: {
      entitlement_id: ent.entitlement_id,
      state: ent.entitlement_state,
      plan_code: ent.plan_code,
      plan_name: ent.plan_name,
      meter_id: ent.meter_id,
      period_kind: ent.period_kind,
      unit_limit: limit
    },
    usage
  };
}

async function grantsForPlan(env, planCode) {
  const result = await env.PRODUCT_DB.prepare(
    `SELECT grant_code
       FROM plan_grants
      WHERE plan_code = ?
      ORDER BY grant_code`
  ).bind(planCode).all();
  return (result.results || []).map((row) => String(row.grant_code));
}

async function ensureSecondaryMcpBinding(env, {
  issuer,
  oidcSubject,
  providerCode,
  email,
}) {
  const provider = cleanId(providerCode, 80);
  if (provider !== MCP_SECONDARY_PROVIDER) {
    return { ok: false, code: "SECONDARY_PROVIDER_INVALID" };
  }

  const configuredIssuerRaw = String(env.MCP_ACCESS_ISSUER || "").trim();
  if (!configuredIssuerRaw) {
    return { ok: false, code: "MCP_ACCESS_ISSUER_NOT_CONFIGURED" };
  }

  const normalizedIssuer = normalizeIssuer(issuer);
  const configuredIssuer = normalizeIssuer(configuredIssuerRaw);
  if (normalizedIssuer !== configuredIssuer) {
    return { ok: false, code: "SECONDARY_ISSUER_MISMATCH" };
  }

  const subject = cleanOpaque(oidcSubject, 512);
  const normalizedEmail = normalizeEmail(email);
  if (!normalizedEmail) {
    return { ok: false, code: "SECONDARY_EMAIL_REQUIRED" };
  }

  const candidates = await env.PRODUCT_DB.prepare(
    `SELECT DISTINCT u.subject_id
       FROM users u
       JOIN identity_bindings primary_binding
         ON primary_binding.subject_id = u.subject_id
        AND primary_binding.provider_code = 'PRIMARY_OIDC'
        AND primary_binding.state = 'ACTIVE'
      WHERE lower(u.email) = ?
        AND u.state = 'ACTIVE'
      LIMIT 2`
  ).bind(normalizedEmail).all();

  const rows = candidates.results || [];
  if (rows.length === 0) return { ok: false, code: "IDENTITY_NOT_PROVISIONED" };
  if (rows.length !== 1) return { ok: false, code: "SECONDARY_IDENTITY_AMBIGUOUS" };
  const targetSubjectId = String(rows[0].subject_id);

  const providerBindings = await env.PRODUCT_DB.prepare(
    `SELECT issuer, external_subject
       FROM identity_bindings
      WHERE subject_id = ?
        AND provider_code = ?
        AND state = 'ACTIVE'
      LIMIT 2`
  ).bind(targetSubjectId, provider).all();

  const activeProviderBindings = providerBindings.results || [];
  if (activeProviderBindings.length > 0) {
    const exact = activeProviderBindings.some(
      (row) => row.issuer === normalizedIssuer && row.external_subject === subject
    );
    return exact
      ? { ok: true, subject_id: targetSubjectId, existing: true }
      : { ok: false, code: "SECONDARY_IDENTITY_CONFLICT" };
  }

  const createdAt = new Date().toISOString();
  await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO identity_bindings
      (identity_binding_id, subject_id, provider_code, issuer, external_subject, state, created_at_utc, revoked_at_utc)
     VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, NULL)`
  ).bind(
    "CLOUDFLARE_ACCESS:" + targetSubjectId,
    targetSubjectId,
    provider,
    normalizedIssuer,
    subject,
    createdAt,
  ).run();

  const bound = await env.PRODUCT_DB.prepare(
    `SELECT subject_id
       FROM identity_bindings
      WHERE issuer = ?
        AND external_subject = ?
        AND provider_code = ?
        AND state = 'ACTIVE'
      LIMIT 1`
  ).bind(normalizedIssuer, subject, provider).first();

  if (!bound || String(bound.subject_id) !== targetSubjectId) {
    return { ok: false, code: "SECONDARY_IDENTITY_BINDING_FAILED" };
  }

  return { ok: true, subject_id: targetSubjectId, existing: false };
}

async function mcpProductContext(env, issuer, oidcSubject, bootstrap = null) {
  const normalizedIssuer = normalizeIssuer(issuer);
  const subject = cleanOpaque(oidcSubject, 512);
  let row = await env.PRODUCT_DB.prepare(
    `SELECT
       u.subject_id,
       u.tenant_id,
       u.state AS subject_state,
       u.role,
       b.provider_code,
       t.display_name AS tenant_name,
       t.state AS tenant_state,
       e.entitlement_id,
       e.subject_id AS entitlement_subject_id,
       e.state AS entitlement_state,
       e.valid_from_utc,
       e.valid_until_utc,
       p.plan_code,
       p.display_name AS plan_name,
       p.meter_id,
       p.period_kind,
       p.unit_limit,
       p.state AS plan_state
     FROM identity_bindings b
     JOIN users u ON u.subject_id = b.subject_id
     JOIN tenants t ON t.tenant_id = u.tenant_id
     JOIN entitlements e
       ON e.tenant_id = u.tenant_id
      AND (e.subject_id IS NULL OR e.subject_id = u.subject_id)
     JOIN plans p ON p.plan_code = e.plan_code
    WHERE b.issuer = ?
      AND b.external_subject = ?
      AND b.state = 'ACTIVE'
    ORDER BY CASE WHEN e.subject_id = u.subject_id THEN 0 ELSE 1 END
    LIMIT 1`
  ).bind(normalizedIssuer, subject).first();

  if (!row && bootstrap) {
    const binding = await ensureSecondaryMcpBinding(env, {
      issuer: normalizedIssuer,
      oidcSubject: subject,
      providerCode: bootstrap.provider_code,
      email: bootstrap.email,
    });
    if (!binding.ok) return binding;
    return mcpProductContext(env, normalizedIssuer, subject, null);
  }
  if (!row) return { ok: false, code: "IDENTITY_NOT_PROVISIONED" };
  if (row.subject_state !== "ACTIVE") return { ok: false, code: "SUBJECT_INACTIVE" };
  if (row.tenant_state !== "ACTIVE") return { ok: false, code: "TENANT_INACTIVE" };
  if (row.entitlement_state !== "ACTIVE" || row.plan_state !== "ACTIVE") {
    return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  }

  const now = Date.now();
  const validFrom = Date.parse(row.valid_from_utc);
  const validUntil = row.valid_until_utc == null ? null : Date.parse(row.valid_until_utc);
  if (!Number.isFinite(validFrom) || now < validFrom) return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  if (validUntil != null && (!Number.isFinite(validUntil) || now >= validUntil)) {
    return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  }

  if (row.meter_id !== MCP_METER_ID) return { ok: false, code: "METER_INVALID" };
  if (!["CALENDAR_MONTH", "LIFETIME", "NONE"].includes(row.period_kind)) {
    return { ok: false, code: "PERIOD_KIND_INVALID" };
  }

  const grants = await grantsForPlan(env, row.plan_code);
  const limit = row.period_kind === "NONE" ? null : Number(row.unit_limit);
  if (limit != null && (!Number.isInteger(limit) || limit < 1)) {
    return { ok: false, code: "USAGE_POLICY_INVALID" };
  }

  return {
    ok: true,
    issuer: normalizedIssuer,
    oidc_subject: subject,
    subject_id: row.subject_id,
    tenant_id: row.tenant_id,
    role: row.role,
    tenant_name: row.tenant_name,
    entitlement_id: row.entitlement_id,
    plan_code: row.plan_code,
    plan_name: row.plan_name,
    meter_id: row.meter_id,
    period_kind: row.period_kind,
    unit_limit: limit,
    grants,
  };
}

async function mcpIdentityBinding(env, issuer, oidcSubject) {
  const normalizedIssuer = normalizeIssuer(issuer);
  const subject = cleanOpaque(oidcSubject, 512);
  const row = await env.PRODUCT_DB.prepare(
    `SELECT u.subject_id, u.tenant_id, u.state, b.provider_code
       FROM identity_bindings b
       JOIN users u ON u.subject_id = b.subject_id
      WHERE b.issuer = ?
        AND b.external_subject = ?
        AND b.state = 'ACTIVE'
      LIMIT 1`
  ).bind(normalizedIssuer, subject).first();

  if (!row) return { ok: false, code: "IDENTITY_NOT_PROVISIONED" };
  return {
    ok: true,
    issuer: normalizedIssuer,
    oidc_subject: subject,
    provider_code: row.provider_code,
    subject_id: row.subject_id,
    tenant_id: row.tenant_id,
    subject_state: row.state,
  };
}

function mcpPeriodKey(context) {
  if (context.period_kind === "CALENDAR_MONTH") return monthKey();
  return "LIFETIME";
}

function mcpDecisionPayload(context, toolId, requiredGrant, extra = {}) {
  return {
    schema: "hara.commander-mcp-product-decision.v1",
    allowed: true,
    code: "ALLOW",
    tool_id: toolId,
    required_grant: requiredGrant,
    subject: {
      subject_id: context.subject_id,
      tenant_id: context.tenant_id,
      role: context.role,
      oidc_issuer: context.issuer,
      oidc_subject: context.oidc_subject,
      provider_code: context.provider_code,
    },
    tenant: {
      tenant_id: context.tenant_id,
      display_name: context.tenant_name,
    },
    entitlement: {
      entitlement_id: context.entitlement_id,
      plan_code: context.plan_code,
      plan_name: context.plan_name,
      grants: context.grants,
    },
    usage_policy: {
      meter_id: context.meter_id,
      period_kind: context.period_kind,
      unit_limit: context.unit_limit,
      units: toolId === "hara.functions.invoke" ? 1 : 0,
    },
    ...extra,
  };
}

async function selectedDeviceForSubject(env, tenantId, subjectId) {
  return env.PRODUCT_DB.prepare(
    `SELECT s.device_id
       FROM commander_device_selections s
       JOIN commander_devices d ON d.device_id = s.device_id
      WHERE s.tenant_id = ?
        AND s.subject_id = ?
        AND d.tenant_id = s.tenant_id
        AND d.state = 'ACTIVE'
        AND d.revoked_at_utc IS NULL
      LIMIT 1`
  ).bind(tenantId, subjectId).first();
}

async function selectDevice(env, tenantId, subjectId, deviceId) {
  const selectedAt = nowIso();
  const result = await env.PRODUCT_DB.prepare(
    `INSERT INTO commander_device_selections
      (tenant_id, subject_id, device_id, selected_at_utc)
     SELECT ?, ?, d.device_id, ?
       FROM commander_devices d
      WHERE d.device_id = ?
        AND d.tenant_id = ?
        AND d.state = 'ACTIVE'
        AND d.revoked_at_utc IS NULL
     ON CONFLICT(tenant_id, subject_id)
     DO UPDATE SET device_id = excluded.device_id, selected_at_utc = excluded.selected_at_utc`
  ).bind(tenantId, subjectId, selectedAt, deviceId, tenantId).run();
  if (!result.meta?.changes) throw new Error("DEVICE_NOT_FOUND");
  return deviceId;
}

async function selectPortalDevice(env, session, body) {
  const deviceId = cleanId(body.device_id, 180);
  await selectDevice(env, session.tenant_id, session.subject_id, deviceId);
  return {
    schema: "hara.commander-device-selection.v1",
    ok: true,
    device_id: deviceId,
    selected: true,
  };
}

async function cleanupTerminalPairingTokens(env) {
  const cutoff = nowIso(-PAIRING_RETENTION_SECONDS);
  return env.PRODUCT_DB.prepare(
    `DELETE FROM device_pairing_tokens
      WHERE pairing_id IN (
        SELECT p.pairing_id
          FROM device_pairing_tokens p
         WHERE p.consumed_at_utc IS NULL
           AND NOT EXISTS (
             SELECT 1
               FROM commander_devices d
              WHERE d.pairing_id = p.pairing_id
           )
           AND (
             (p.superseded_at_utc IS NOT NULL AND p.superseded_at_utc <= ?)
             OR (
               p.superseded_at_utc IS NULL
               AND p.expires_at_utc <= ?
             )
           )
         ORDER BY COALESCE(p.superseded_at_utc, p.expires_at_utc) ASC
         LIMIT ?
      )`
  ).bind(cutoff, cutoff, PAIRING_RETENTION_BATCH).run();
}

async function createDevicePairing(env, session) {
  await cleanupTerminalPairingTokens(env).catch(() => null);

  const token = randomToken(32);
  const tokenHash = await sha256(token);
  const pairingId = "HARA-PAIR-" + crypto.randomUUID();
  const createdAt = nowIso();
  const expiresAt = nowIso(10 * 60);

  const supersede = env.PRODUCT_DB.prepare(
    `UPDATE device_pairing_tokens
        SET superseded_at_utc = ?
      WHERE tenant_id = ?
        AND subject_id = ?
        AND consumed_at_utc IS NULL
        AND superseded_at_utc IS NULL`
  ).bind(createdAt, session.tenant_id, session.subject_id);

  const insert = env.PRODUCT_DB.prepare(
    `INSERT INTO device_pairing_tokens
      (pairing_id, token_hash, tenant_id, subject_id, created_at_utc, expires_at_utc,
       consumed_at_utc, superseded_at_utc)
     VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)`
  ).bind(
    pairingId,
    tokenHash,
    session.tenant_id,
    session.subject_id,
    createdAt,
    expiresAt,
  );

  try {
    await env.PRODUCT_DB.batch([supersede, insert]);
  } catch (_error) {
    throw new Error("DEVICE_PAIRING_CREATE_FAILED");
  }

  return {
    schema: "hara.commander-device-pairing.v1",
    pairing_id: pairingId,
    pairing_token: token,
    expires_at_utc: expiresAt,
    one_time: true,
  };
}

async function listDevices(env, session) {
  const result = await env.PRODUCT_DB.prepare(
    `SELECT d.device_id, d.enrolled_by_subject_id, d.device_name, d.platform, d.architecture,
            d.agent_version, d.tunnel_mode, d.state, d.created_at_utc, d.last_seen_at_utc,
            d.revoked_at_utc,
            CASE WHEN s.device_id = d.device_id THEN 1 ELSE 0 END AS selected
       FROM commander_devices d
       LEFT JOIN commander_device_selections s
         ON s.tenant_id = d.tenant_id
        AND s.subject_id = ?
      WHERE d.tenant_id = ?
      ORDER BY d.created_at_utc DESC`
  ).bind(session.subject_id, session.tenant_id).all();

  const now = Date.now();
  return (result.results || []).map((row) => ({
    device_id: row.device_id,
    enrolled_by_subject_id: row.enrolled_by_subject_id,
    device_name: row.device_name,
    platform: row.platform,
    architecture: row.architecture,
    agent_version: row.agent_version,
    tunnel_mode: row.tunnel_mode,
    state: row.state,
    online: row.state === "ACTIVE" && deviceOnline(row.last_seen_at_utc, now),
    selected: Boolean(row.selected) && row.state === "ACTIVE" && !row.revoked_at_utc,
    created_at_utc: row.created_at_utc,
    last_seen_at_utc: row.last_seen_at_utc,
    revoked_at_utc: row.revoked_at_utc,
  }));
}

async function enrollDevice(env, body) {
  const pairingToken = cleanOpaque(body.pairing_token, 512);
  const tokenHash = await sha256(pairingToken);
  const deviceName = cleanDeviceName(body.device_name);
  const platform = normalizeDevicePlatform(body.platform);
  const architecture = cleanAgentValue(body.architecture, 80);
  const agentVersion = cleanAgentValue(body.agent_version, 80) || "0.1.0";
  const deviceId = "HARA-DEVICE-" + crypto.randomUUID();
  const deviceSecret = randomToken(48);
  const credentialHash = await sha256(deviceSecret);
  const createdAt = nowIso();

  const insert = env.PRODUCT_DB.prepare(
    `INSERT INTO commander_devices
      (device_id, pairing_id, tenant_id, enrolled_by_subject_id, device_name, platform,
       architecture, agent_version, tunnel_mode, credential_hash, state,
       created_at_utc, last_seen_at_utc, revoked_at_utc)
     SELECT ?, pairing_id, tenant_id, subject_id, ?, ?, ?, ?, 'OUTBOUND_RELAY', ?,
            'ACTIVE', ?, ?, NULL
       FROM device_pairing_tokens
      WHERE token_hash = ?
        AND consumed_at_utc IS NULL
        AND superseded_at_utc IS NULL
        AND expires_at_utc > ?`
  ).bind(
    deviceId,
    deviceName,
    platform,
    architecture,
    agentVersion,
    credentialHash,
    createdAt,
    createdAt,
    tokenHash,
    createdAt,
  );

  const consume = env.PRODUCT_DB.prepare(
    `UPDATE device_pairing_tokens
        SET consumed_at_utc = ?
      WHERE token_hash = ?
        AND consumed_at_utc IS NULL
        AND superseded_at_utc IS NULL
        AND expires_at_utc > ?`
  ).bind(createdAt, tokenHash, createdAt);

  let results;
  try {
    results = await env.PRODUCT_DB.batch([insert, consume]);
  } catch (_error) {
    throw new Error("DEVICE_PAIRING_INVALID");
  }

  if (!results?.[0]?.meta?.changes || !results?.[1]?.meta?.changes) {
    throw new Error("DEVICE_PAIRING_INVALID");
  }

  const enrolled = await env.PRODUCT_DB.prepare(
    `SELECT tenant_id, enrolled_by_subject_id
       FROM commander_devices WHERE device_id = ? LIMIT 1`
  ).bind(deviceId).first();
  if (!enrolled) throw new Error("DEVICE_PAIRING_INVALID");
  await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO commander_device_selections
      (tenant_id, subject_id, device_id, selected_at_utc)
     SELECT ?, ?, d.device_id, ?
       FROM commander_devices d
      WHERE d.device_id = ?
        AND d.tenant_id = ?
        AND d.state = 'ACTIVE'
        AND d.revoked_at_utc IS NULL`
  ).bind(
    enrolled.tenant_id, enrolled.enrolled_by_subject_id, createdAt, deviceId, enrolled.tenant_id
  ).run();

  return {
    schema: "hara.commander-device-enrollment.v1",
    device_id: deviceId,
    device_token: deviceSecret,
    device_name: deviceName,
    platform,
    architecture,
    agent_version: agentVersion,
    tunnel_mode: "OUTBOUND_RELAY",
    state: "ACTIVE",
    enrolled_at_utc: createdAt,
  };
}

async function resolveDeviceCredential(env, request) {
  const token = bearerToken(request);
  if (!token) throw new Error("DEVICE_AUTH_REQUIRED");
  const credentialHash = await sha256(token);
  const device = await env.PRODUCT_DB.prepare(
    `SELECT device_id, tenant_id, enrolled_by_subject_id, device_name, platform,
            architecture, agent_version, tunnel_mode, state, created_at_utc,
            last_seen_at_utc, revoked_at_utc
       FROM commander_devices
      WHERE credential_hash = ?
      LIMIT 1`
  ).bind(credentialHash).first();

  if (!device || device.state !== "ACTIVE" || device.revoked_at_utc) {
    throw new Error("DEVICE_AUTH_INVALID");
  }
  return device;
}

async function heartbeatDevice(env, request, body) {
  const device = await resolveDeviceCredential(env, request);
  const requestedId = body.device_id ? cleanId(body.device_id, 180) : device.device_id;
  if (requestedId !== device.device_id) throw new Error("DEVICE_ID_MISMATCH");

  const agentVersion = cleanAgentValue(body.agent_version, 80) || device.agent_version;
  const architecture = cleanAgentValue(body.architecture, 80) || device.architecture;
  const seenAt = nowIso();

  const heartbeat = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?, agent_version = ?, architecture = ?
      WHERE device_id = ? AND state = 'ACTIVE' AND revoked_at_utc IS NULL`
  ).bind(seenAt, agentVersion, architecture, device.device_id).run();
  if (!heartbeat.meta?.changes) throw new Error("DEVICE_AUTH_INVALID");

  return {
    schema: "hara.commander-device-heartbeat.v1",
    ok: true,
    device_id: device.device_id,
    state: "ACTIVE",
    server_time_utc: seenAt,
    heartbeat_after_seconds: 30,
  };
}

async function revokeDeviceSelf(env, request) {
  const device = await resolveDeviceCredential(env, request);
  const revokedAt = nowIso();
  await env.PRODUCT_DB.batch([
    env.PRODUCT_DB.prepare(
      `UPDATE commander_devices
          SET state = 'REVOKED', revoked_at_utc = ?
        WHERE device_id = ? AND tenant_id = ? AND state = 'ACTIVE'`
    ).bind(revokedAt, device.device_id, device.tenant_id),
    env.PRODUCT_DB.prepare(
      `DELETE FROM commander_device_selections
        WHERE tenant_id = ? AND device_id = ?`
    ).bind(device.tenant_id, device.device_id),
    env.PRODUCT_DB.prepare(
      `UPDATE commander_device_calls
          SET state = 'CANCELLED', completed_at_utc = ?, error_code = 'DEVICE_REVOKED'
        WHERE tenant_id = ? AND device_id = ? AND state IN ('PENDING','EXECUTING')`
    ).bind(revokedAt, device.tenant_id, device.device_id),
  ]);
  return {
    schema: "hara.commander-device-self-revocation.v1",
    ok: true,
    device_id: device.device_id,
    state: "REVOKED",
    revoked_at_utc: revokedAt,
    pending_calls_cancelled: true,
  };
}

async function revokePortalDevice(env, session, body) {
  const deviceId = cleanId(body.device_id, 180);
  const revokedAt = nowIso();
  const privileged = ["OWNER", "ADMIN"].includes(String(session.role));
  const statement = privileged
    ? env.PRODUCT_DB.prepare(
        `UPDATE commander_devices
            SET state = 'REVOKED', revoked_at_utc = ?
          WHERE device_id = ? AND tenant_id = ? AND state = 'ACTIVE'`
      ).bind(revokedAt, deviceId, session.tenant_id)
    : env.PRODUCT_DB.prepare(
        `UPDATE commander_devices
            SET state = 'REVOKED', revoked_at_utc = ?
          WHERE device_id = ? AND tenant_id = ? AND enrolled_by_subject_id = ? AND state = 'ACTIVE'`
      ).bind(revokedAt, deviceId, session.tenant_id, session.subject_id);

  const results = await env.PRODUCT_DB.batch([
    statement,
    env.PRODUCT_DB.prepare(
      `DELETE FROM commander_device_selections
        WHERE tenant_id = ?
          AND device_id = ?
          AND EXISTS (
            SELECT 1
              FROM commander_devices d
             WHERE d.device_id = ?
               AND d.tenant_id = ?
               AND d.state = 'REVOKED'
               AND d.revoked_at_utc = ?
          )`
    ).bind(session.tenant_id, deviceId, deviceId, session.tenant_id, revokedAt),
    env.PRODUCT_DB.prepare(
      `UPDATE commander_device_calls
          SET state = 'CANCELLED', completed_at_utc = ?, error_code = 'DEVICE_REVOKED'
        WHERE tenant_id = ?
          AND device_id = ?
          AND state IN ('PENDING','EXECUTING')
          AND EXISTS (
            SELECT 1
              FROM commander_devices d
             WHERE d.device_id = commander_device_calls.device_id
               AND d.tenant_id = commander_device_calls.tenant_id
               AND d.state = 'REVOKED'
               AND d.revoked_at_utc = ?
          )`
    ).bind(revokedAt, session.tenant_id, deviceId, revokedAt),
  ]);
  if (!results?.[0]?.meta?.changes) throw new Error("DEVICE_NOT_FOUND");
  return {
    schema: "hara.commander-device-revocation.v1",
    ok: true,
    device_id: deviceId,
    state: "REVOKED",
    revoked_at_utc: revokedAt,
    pending_calls_cancelled: true,
  };
}

async function enqueueDeviceCall(env, body) {
  const requestId = cleanId(body.request_id, 220);
  const toolId = cleanId(body.tool_id, 120);
  const requiredGrant = MCP_TOOL_GRANTS[toolId];
  if (!requiredGrant) throw new Error("DEVICE_CALL_TOOL_DENIED");

  const context = await mcpProductContext(env, body.issuer, body.subject, {
    provider_code: body.provider_code,
    email: body.email,
  });
  if (!context.ok) throw new Error(context.code);
  if (!context.grants.includes(requiredGrant)) throw new Error("GRANT_MISSING");

  const requestedDeviceId = body.device_id ? cleanId(body.device_id, 180) : null;
  const canonicalPayload = canonicalDeviceToolPayload(toolId, body.payload);
  const payloadJson = boundedJson(
    canonicalPayload,
    128 * 1024,
    "DEVICE_CALL_PAYLOAD_INVALID",
  );
  const readExisting = () => env.PRODUCT_DB.prepare(
    `SELECT call_id, tenant_id, subject_id, device_id, tool_id, payload_json, state, expires_at_utc
       FROM commander_device_calls WHERE request_id = ? LIMIT 1`
  ).bind(requestId).first();
  const existingResponse = (existing) => {
    if (
      existing.tenant_id !== context.tenant_id
      || existing.subject_id !== context.subject_id
      || existing.tool_id !== toolId
      || existing.payload_json !== payloadJson
      || (requestedDeviceId && existing.device_id !== requestedDeviceId)
    ) {
      throw new Error("IDEMPOTENCY_CONFLICT");
    }
    return {
      schema: "hara.commander-device-call.v1",
      existing: true,
      call_id: existing.call_id,
      request_id: requestId,
      device_id: existing.device_id,
      tool_id: toolId,
      state: existing.state,
      expires_at_utc: existing.expires_at_utc,
    };
  };

  const existing = await readExisting();
  if (existing) return existingResponse(existing);

  const selection = await selectedDeviceForSubject(
    env, context.tenant_id, context.subject_id
  );
  if (!selection) throw new Error("DEVICE_SELECTION_REQUIRED");
  const deviceId = cleanId(selection.device_id, 180);
  if (requestedDeviceId && requestedDeviceId !== deviceId) {
    throw new Error("DEVICE_NOT_SELECTED");
  }

  const device = await env.PRODUCT_DB.prepare(
    `SELECT device_id, tenant_id, state, last_seen_at_utc, revoked_at_utc
       FROM commander_devices
      WHERE device_id = ? AND tenant_id = ?
      LIMIT 1`
  ).bind(deviceId, context.tenant_id).first();
  if (!device || device.state !== "ACTIVE" || device.revoked_at_utc) {
    throw new Error("DEVICE_NOT_FOUND");
  }
  if (!deviceOnline(device.last_seen_at_utc)) throw new Error("DEVICE_OFFLINE");

  const enqueueAt = nowIso();
  await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_calls
        SET state = 'EXPIRED', completed_at_utc = ?, error_code = 'DEVICE_CALL_EXPIRED'
      WHERE tenant_id = ? AND subject_id = ? AND device_id = ?
        AND state IN ('PENDING','EXECUTING')
        AND expires_at_utc <= ?`
  ).bind(enqueueAt, context.tenant_id, context.subject_id, deviceId, enqueueAt).run();

  const callId = "HARA-CALL-" + crypto.randomUUID();
  const createdAt = nowIso();
  const expiresAt = nowIso(DEVICE_CALL_TTL_SECONDS);
  const onlineCutoff = new Date(Date.now() - 90_000).toISOString();
  const inserted = await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO commander_device_calls
      (call_id, request_id, tenant_id, subject_id, device_id, tool_id, payload_json,
       state, created_at_utc, expires_at_utc, claimed_at_utc, completed_at_utc,
       result_json, error_code)
     SELECT ?, ?, ?, ?, d.device_id, ?, ?, 'PENDING', ?, ?, NULL, NULL, NULL, NULL
       FROM commander_devices d
       JOIN commander_device_selections s
         ON s.tenant_id = d.tenant_id
        AND s.device_id = d.device_id
      WHERE d.device_id = ?
        AND d.tenant_id = ?
        AND d.state = 'ACTIVE'
        AND d.revoked_at_utc IS NULL
        AND d.last_seen_at_utc >= ?
        AND s.subject_id = ?`
  ).bind(
    callId, requestId, context.tenant_id, context.subject_id, toolId, payloadJson,
    createdAt, expiresAt, deviceId, context.tenant_id, onlineCutoff, context.subject_id
  ).run();

  if (!inserted.meta?.changes) {
    const concurrent = await readExisting();
    if (concurrent) return existingResponse(concurrent);

    const currentSelection = await selectedDeviceForSubject(
      env, context.tenant_id, context.subject_id
    );
    if (!currentSelection) throw new Error("DEVICE_SELECTION_REQUIRED");
    if (cleanId(currentSelection.device_id, 180) !== deviceId) {
      throw new Error("DEVICE_NOT_SELECTED");
    }

    const currentDevice = await env.PRODUCT_DB.prepare(
      `SELECT state, last_seen_at_utc, revoked_at_utc
         FROM commander_devices
        WHERE device_id = ? AND tenant_id = ?
        LIMIT 1`
    ).bind(deviceId, context.tenant_id).first();
    if (!currentDevice || currentDevice.state !== "ACTIVE" || currentDevice.revoked_at_utc) {
      throw new Error("DEVICE_NOT_FOUND");
    }
    if (!deviceOnline(currentDevice.last_seen_at_utc)) throw new Error("DEVICE_OFFLINE");
    throw new Error("DEVICE_CALL_ENQUEUE_CONFLICT");
  }

  return {
    schema: "hara.commander-device-call.v1",
    existing: false,
    call_id: callId,
    request_id: requestId,
    device_id: deviceId,
    tool_id: toolId,
    state: "PENDING",
    expires_at_utc: expiresAt,
  };
}

async function claimNextDeviceCall(env, request) {
  const device = await resolveDeviceCredential(env, request);
  const now = nowIso();

  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_calls
        SET state = 'EXECUTING', claimed_at_utc = ?
      WHERE call_id = (
        SELECT c.call_id
          FROM commander_device_calls c
          JOIN commander_devices d
            ON d.device_id = c.device_id
           AND d.tenant_id = c.tenant_id
         WHERE c.device_id = ?
           AND c.state = 'PENDING'
           AND c.expires_at_utc > ?
           AND d.state = 'ACTIVE'
           AND d.revoked_at_utc IS NULL
         ORDER BY c.created_at_utc
         LIMIT 1
      )
      RETURNING call_id, request_id, tool_id, payload_json, expires_at_utc`
  ).bind(now, device.device_id, now).all();

  const row = (result.results || [])[0];
  if (!row) return null;

  return {
    schema: "hara.commander-device-call-claim.v1",
    call_id: row.call_id,
    request_id: row.request_id,
    tool_id: row.tool_id,
    payload: JSON.parse(row.payload_json || "{}"),
    expires_at_utc: row.expires_at_utc,
  };
}

async function completeDeviceCall(env, request, body) {
  const device = await resolveDeviceCredential(env, request);
  const callId = cleanId(body.call_id, 180);
  const state = String(body.state || "").trim().toUpperCase();
  if (!["COMPLETED", "FAILED"].includes(state)) {
    throw new Error("DEVICE_CALL_RESULT_STATE_INVALID");
  }

  const resultJson = boundedJson(body.result || {}, 256 * 1024, "DEVICE_CALL_RESULT_INVALID");
  const errorCode = state === "FAILED"
    ? cleanId(body.error_code || "DEVICE_EXECUTION_FAILED", 120)
    : null;
  const completedAt = nowIso();

  const update = await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_calls
        SET state = ?, completed_at_utc = ?, result_json = ?, error_code = ?
      WHERE call_id = ?
        AND tenant_id = ?
        AND device_id = ?
        AND state = 'EXECUTING'
        AND expires_at_utc > ?
      RETURNING call_id, request_id, tool_id, state, completed_at_utc`
  ).bind(
    state, completedAt, resultJson, errorCode, callId, device.tenant_id, device.device_id,
    completedAt
  ).all();

  const row = (update.results || [])[0];
  if (!row) {
    const existing = await env.PRODUCT_DB.prepare(
      `SELECT state, expires_at_utc, result_json, error_code FROM commander_device_calls
        WHERE call_id = ? AND tenant_id = ? AND device_id = ? LIMIT 1`
    ).bind(callId, device.tenant_id, device.device_id).first();
    if (existing && existing.state === state) {
      if (
        existing.result_json !== resultJson
        || (state === "FAILED" && String(existing.error_code || "") !== String(errorCode || ""))
      ) {
        throw new Error("IDEMPOTENCY_CONFLICT");
      }
      return { schema: "hara.commander-device-call-result.v1", ok: true, existing: true, call_id: callId, state };
    }
    if (
      existing
      && existing.state === "EXECUTING"
      && String(existing.expires_at_utc) <= completedAt
    ) {
      await env.PRODUCT_DB.prepare(
        `UPDATE commander_device_calls
            SET state = 'EXPIRED', completed_at_utc = ?, error_code = 'DEVICE_CALL_EXPIRED'
          WHERE call_id = ?
            AND tenant_id = ?
            AND device_id = ?
            AND state = 'EXECUTING'
            AND expires_at_utc <= ?`
      ).bind(
        completedAt, callId, device.tenant_id, device.device_id, completedAt
      ).run();
      throw new Error("DEVICE_CALL_EXPIRED");
    }
    throw new Error("DEVICE_CALL_NOT_EXECUTING");
  }

  return {
    schema: "hara.commander-device-call-result.v1",
    ok: true,
    existing: false,
    call_id: row.call_id,
    request_id: row.request_id,
    tool_id: row.tool_id,
    state: row.state,
    completed_at_utc: row.completed_at_utc,
  };
}

async function deviceCallStatus(env, body) {
  const callId = cleanId(body.call_id, 180);
  const context = await mcpProductContext(env, body.issuer, body.subject, {
    provider_code: body.provider_code,
    email: body.email,
  });
  if (!context.ok) throw new Error(context.code);

  const now = nowIso();
  const readCall = () => env.PRODUCT_DB.prepare(
    `SELECT call_id, request_id, device_id, tool_id, state, created_at_utc,
            expires_at_utc, claimed_at_utc, completed_at_utc, result_json, error_code
       FROM commander_device_calls
      WHERE call_id = ? AND tenant_id = ? AND subject_id = ?
      LIMIT 1`
  ).bind(callId, context.tenant_id, context.subject_id).first();

  let row = await readCall();
  if (!row) throw new Error("DEVICE_CALL_NOT_FOUND");

  if (
    ["PENDING", "EXECUTING"].includes(String(row.state))
    && String(row.expires_at_utc) <= now
  ) {
    const expired = await env.PRODUCT_DB.prepare(
      `UPDATE commander_device_calls
          SET state = 'EXPIRED', completed_at_utc = ?, error_code = 'DEVICE_CALL_EXPIRED'
        WHERE call_id = ?
          AND tenant_id = ?
          AND subject_id = ?
          AND state IN ('PENDING','EXECUTING')
          AND expires_at_utc <= ?
        RETURNING call_id, request_id, device_id, tool_id, state, created_at_utc,
                  expires_at_utc, claimed_at_utc, completed_at_utc, result_json, error_code`
    ).bind(now, callId, context.tenant_id, context.subject_id, now).all();
    const updated = (expired.results || [])[0];
    if (updated) {
      row = updated;
    } else {
      row = await readCall();
      if (!row) throw new Error("DEVICE_CALL_NOT_FOUND");
    }
  }

  return {
    schema: "hara.commander-device-call-status.v1",
    call_id: row.call_id,
    request_id: row.request_id,
    device_id: row.device_id,
    tool_id: row.tool_id,
    state: row.state,
    created_at_utc: row.created_at_utc,
    expires_at_utc: row.expires_at_utc,
    claimed_at_utc: row.claimed_at_utc,
    completed_at_utc: row.completed_at_utc,
    result: row.result_json ? JSON.parse(row.result_json) : null,
    error_code: row.error_code || null,
  };
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: json({}).headers });

    const requestUrl = new URL(request.url);

    try {
      requireRuntime(env);
      const url = requestUrl;
      if (url.pathname.startsWith("/api/dev/")) requireDev(env);

      if (url.pathname === "/api/health" && request.method === "GET") {
        return json({
          ok: true,
          service: "hara-commander",
          environment: env.ENVIRONMENT,
          storage_mode: env.STORAGE_MODE,
          auth: authStatus(env),
        });
      }

      if (url.pathname === "/api/dev/health" && request.method === "GET") {
        requireRemoteDevToken(request, env);
        return json({
          ok: true,
          service: "hara-commander-product-dev",
          environment: env.ENVIRONMENT,
          product_db: env.STORAGE_MODE === "REMOTE_DEV" ? "D1_REMOTE_DEV" : "D1_LOCAL",
          quota_store: env.STORAGE_MODE === "REMOTE_DEV" ? "DURABLE_OBJECT_SQLITE_REMOTE_DEV" : "DURABLE_OBJECT_SQLITE_LOCAL",
          auth: authStatus(env),
          production_mutation: false
        });
      }

      if (url.pathname === "/api/portal/auth-config" && request.method === "GET") {
        return json(authStatus(env));
      }

      if (url.pathname === "/auth/login" && request.method === "GET") {
        return await beginLogin(request, env);
      }

      if (url.pathname === "/auth/callback" && request.method === "GET") {
        return await finishLogin(request, env);
      }

      if (url.pathname === "/auth/logout" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        return await logout(request, env);
      }

      if (url.pathname === "/api/portal/session" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        return json({
          ok: true,
          subject: {
            subject_id: session.subject_id,
            display_name: session.display_name,
            role: session.role
          },
          tenant: {
            tenant_id: session.tenant_id,
            display_name: session.tenant_name
          }
        });
      }

      if (url.pathname === "/api/portal/dashboard" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        const payload = await dashboardForSubject(env, session.subject_id, session.tenant_id);
        if (!payload) return json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 403);
        payload.subject = {
          subject_id: session.subject_id,
          display_name: session.display_name,
          role: session.role
        };
        return json(payload);
      }

      if (url.pathname === "/api/portal/devices" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        const devices = await listDevices(env, session);
        return json({
          schema: "hara.commander-device-list.v1",
          devices,
          active_count: devices.filter((device) => device.state === "ACTIVE").length,
          online_count: devices.filter((device) => device.online).length,
        });
      }

      if (url.pathname === "/api/portal/devices/pairing" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        return json(await createDevicePairing(env, session), 201);
      }

      if (url.pathname === "/api/portal/devices/revoke" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        const body = await request.json();
        return json(await revokePortalDevice(env, session, body));
      }

      if (url.pathname === "/api/portal/devices/select" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        const body = await request.json();
        return json(await selectPortalDevice(env, session, body));
      }

      if (url.pathname === "/api/device/enroll" && request.method === "POST") {
        const body = await request.json();
        return json(await enrollDevice(env, body), 201);
      }

      if (url.pathname === "/api/device/heartbeat" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        return json(await heartbeatDevice(env, request, body));
      }

      if (url.pathname === "/api/device/revoke-self" && request.method === "POST") {
        return json(await revokeDeviceSelf(env, request));
      }

      if (url.pathname === "/api/device/calls/next" && request.method === "POST") {
        const call = await claimNextDeviceCall(env, request);
        if (!call) {
          return new Response(null, {
            status: 204,
            headers: { ...SECURITY_HEADERS, "cache-control": "no-store" }
          });
        }
        return json(call);
      }

      if (url.pathname === "/api/device/calls/complete" && request.method === "POST") {
        const body = await request.json();
        return json(await completeDeviceCall(env, request, body));
      }

      if (
        url.pathname.startsWith("/api/internal/mcp/")
        || url.pathname.startsWith("/api/internal/device/")
      ) {
        requireMcpProductToken(request, env);
      }

      if (url.pathname === "/api/internal/device/calls" && request.method === "POST") {
        const body = await request.json();
        return internalJson(await enqueueDeviceCall(env, body), 201);
      }

      if (url.pathname === "/api/internal/device/calls/status" && request.method === "POST") {
        const body = await request.json();
        return internalJson(await deviceCallStatus(env, body));
      }

      if (url.pathname === "/api/internal/mcp/authorize" && request.method === "POST") {
        const body = await request.json();
        const toolId = cleanId(body.tool_id, 120);
        const requestId = cleanId(body.request_id, 220);
        const requiredGrant = MCP_TOOL_GRANTS[toolId];
        if (!requiredGrant) {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: "POLICY_DENIED",
            tool_id: toolId,
            request_id: requestId,
          });
        }

        const context = await mcpProductContext(env, body.issuer, body.subject, {
          provider_code: body.provider_code,
          email: body.email,
        });
        if (!context.ok) {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: context.code,
            tool_id: toolId,
            request_id: requestId,
          });
        }

        if (!context.grants.includes(requiredGrant)) {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: "GRANT_MISSING",
            tool_id: toolId,
            request_id: requestId,
            required_grant: requiredGrant,
          });
        }

        if (toolId !== "hara.functions.invoke") {
          return internalJson(mcpDecisionPayload(context, toolId, requiredGrant, {
            request_id: requestId,
          }));
        }

        const functionId = cleanId(body.function_id, 180);
        if (functionId !== DEVICE_FUNCTION_ID) {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: "POLICY_DENIED",
            tool_id: toolId,
            request_id: requestId,
            function_id: functionId,
            required_grant: requiredGrant,
          });
        }
        const periodKey = mcpPeriodKey(context);
        const reservation = await env.TENANT_QUOTA
          .getByName(context.tenant_id)
          .reserve(requestId, context.subject_id, periodKey, functionId, context.unit_limit);

        if (!reservation.ok) {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: reservation.code || "QUOTA_DENIED",
            tool_id: toolId,
            request_id: requestId,
            function_id: functionId,
            required_grant: requiredGrant,
            usage: reservation,
          });
        }

        if (reservation.existing && reservation.state === "RELEASED") {
          return internalJson({
            schema: "hara.commander-mcp-product-decision.v1",
            allowed: false,
            code: "REQUEST_USAGE_TERMINAL",
            tool_id: toolId,
            request_id: requestId,
            function_id: functionId,
            required_grant: requiredGrant,
            usage: reservation,
          });
        }

        return internalJson(mcpDecisionPayload(context, toolId, requiredGrant, {
          request_id: requestId,
          function_id: functionId,
          usage: reservation,
        }));
      }

      if (url.pathname === "/api/internal/mcp/commit" && request.method === "POST") {
        const body = await request.json();
        const requestId = cleanId(body.request_id, 220);
        const receiptSha256 = String(body.receipt_sha256 || "").trim().toLowerCase();
        if (!/^[0-9a-f]{64}$/.test(receiptSha256)) {
          return internalJson({ ok: false, code: "INVALID_RECEIPT_SHA256" }, 400);
        }

        const identity = await mcpIdentityBinding(env, body.issuer, body.subject);
        if (!identity.ok) return internalJson({ ok: false, code: identity.code }, 403);

        const usage = await env.TENANT_QUOTA
          .getByName(identity.tenant_id)
          .commit(requestId, identity.subject_id, receiptSha256, null);

        return internalJson({
          schema: "hara.commander-mcp-usage-transition.v1",
          transition: "COMMIT",
          subject_id: identity.subject_id,
          tenant_id: identity.tenant_id,
          request_id: requestId,
          receipt_sha256: receiptSha256,
          usage,
        });
      }

      if (url.pathname === "/api/internal/mcp/release" && request.method === "POST") {
        const body = await request.json();
        const requestId = cleanId(body.request_id, 220);
        const identity = await mcpIdentityBinding(env, body.issuer, body.subject);
        if (!identity.ok) return internalJson({ ok: false, code: identity.code }, 403);

        const usage = await env.TENANT_QUOTA
          .getByName(identity.tenant_id)
          .release(requestId, identity.subject_id, null);

        return internalJson({
          schema: "hara.commander-mcp-usage-transition.v1",
          transition: "RELEASE",
          subject_id: identity.subject_id,
          tenant_id: identity.tenant_id,
          request_id: requestId,
          usage,
        });
      }

      if (url.pathname.startsWith("/api/dev/")) requireRemoteDevToken(request, env);

      if (url.pathname === "/api/dev/dashboard" && request.method === "GET") {
        const tenantId = cleanId(url.searchParams.get("tenant_id") || DEMO_TENANT);
        const payload = await dashboard(env, tenantId);
        return payload ? json(payload) : json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 404);
      }

      if (url.pathname === "/api/dev/quota/reserve" && request.method === "POST") {
        const body = await request.json();
        const tenantId = cleanId(body.tenant_id || DEMO_TENANT);
        const requestId = cleanId(body.request_id);
        const functionId = cleanId(body.function_id || "fleet.list");
        const ent = await entitlementForTenant(env, tenantId);
        if (!ent) return json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 404);

        const periodKey = ent.period_kind === "CALENDAR_MONTH" ? monthKey() : "LIFETIME";
        const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
        const stub = env.TENANT_QUOTA.getByName(tenantId);
        return json(await stub.reserve(requestId, "LEGACY", periodKey, functionId, limit));
      }

      if (url.pathname === "/api/dev/quota/commit" && request.method === "POST") {
        const body = await request.json();
        const tenantId = cleanId(body.tenant_id || DEMO_TENANT);
        const requestId = cleanId(body.request_id);
        const receiptSha256 = String(body.receipt_sha256 || "").trim().toLowerCase();
        if (!/^[0-9a-f]{64}$/.test(receiptSha256)) return json({ ok: false, code: "INVALID_RECEIPT_SHA256" }, 400);
        const ent = await entitlementForTenant(env, tenantId);
        if (!ent) return json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 404);
        const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
        return json(await env.TENANT_QUOTA.getByName(tenantId).commit(requestId, "LEGACY", receiptSha256, limit));
      }

      if (url.pathname === "/api/dev/quota/release" && request.method === "POST") {
        const body = await request.json();
        const tenantId = cleanId(body.tenant_id || DEMO_TENANT);
        const requestId = cleanId(body.request_id);
        const ent = await entitlementForTenant(env, tenantId);
        if (!ent) return json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 404);
        const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
        return json(await env.TENANT_QUOTA.getByName(tenantId).release(requestId, "LEGACY", limit));
      }

      return json({ ok: false, code: "NOT_FOUND" }, 404);
    } catch (error) {
      const code = sanitizeErrorCode(error);
      const statusMap = {
        RUNTIME_ENV_INVALID: 500,
        INVALID_JSON: 400,
        INVALID_IDENTIFIER: 400,
        INVALID_OPAQUE_VALUE: 400,
        DEV_ENDPOINT_DISABLED: 404,
        DEV_ACCESS_DENIED: 401,
        MCP_PRODUCT_ACCESS_DENIED: 401,
        PORTAL_ORIGIN_DENIED: 403,
        AUTH_REQUIRED: 401,
        OIDC_NOT_CONFIGURED: 503,
        IDENTITY_NOT_PROVISIONED: 403,
        IDENTITY_INACTIVE: 403,
        IDENTITY_INVITE_EXPIRED: 403,
        OIDC_CALLBACK_INVALID: 400,
        OIDC_STATE_INVALID: 400,
        OIDC_STATE_REPLAYED: 400,
        OIDC_STATE_EXPIRED: 400,
        OIDC_PROVIDER_ERROR: 400,
        DEVICE_PAIRING_INVALID: 401,
        DEVICE_PAIRING_CREATE_FAILED: 503,
        DEVICE_AUTH_REQUIRED: 401,
        DEVICE_AUTH_INVALID: 401,
        DEVICE_ID_MISMATCH: 403,
        DEVICE_NOT_FOUND: 404,
        DEVICE_SELECTION_REQUIRED: 409,
        DEVICE_NOT_SELECTED: 403,
        DEVICE_NAME_INVALID: 400,
        DEVICE_PLATFORM_INVALID: 400,
        DEVICE_METADATA_INVALID: 400,
        DEVICE_OFFLINE: 409,
        DEVICE_CALL_TOOL_DENIED: 403,
        DEVICE_CALL_FUNCTION_DENIED: 403,
        DEVICE_CALL_PAYLOAD_INVALID: 400,
        DEVICE_CALL_RECEIPT_INVALID: 400,
        DEVICE_CALL_RESULT_STATE_INVALID: 400,
        DEVICE_CALL_RESULT_INVALID: 400,
        DEVICE_CALL_NOT_EXECUTING: 409,
        DEVICE_CALL_EXPIRED: 409,
        DEVICE_CALL_ENQUEUE_CONFLICT: 409,
        DEVICE_CALL_NOT_FOUND: 404,
        GRANT_MISSING: 403,
        IDEMPOTENCY_CONFLICT: 409,
      };

      if (requestUrl.pathname === "/auth/callback") {
        return authCallbackFailureResponse(error);
      }

      return json({ ok: false, code }, statusMap[code] || 500);
    }
  }
};
