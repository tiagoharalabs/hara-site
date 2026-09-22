import { DurableObject } from "cloudflare:workers";
import {
  authStatus,
  beginLogin,
  finishLogin,
  logout,
  resolvePortalSession,
} from "./auth.js";
import { normalizeIssuer } from "./oidc.js";

const DEMO_TENANT = "HARA-TENANT-DEMO-0001";
const MCP_METER_ID = "HARA_COMMANDER_GOVERNED_INVOKE";
const MCP_TOOL_GRANTS = Object.freeze({
  "hara.health": "COMMANDER_DISCOVERY",
  "hara.functions.list": "COMMANDER_DISCOVERY",
  "hara.functions.describe": "COMMANDER_DISCOVERY",
  "hara.functions.invoke": "COMMANDER_READ_ONLY_INVOKE",
  "hara.receipts.get": "COMMANDER_RECEIPT_READ",
});

function json(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type",
      "access-control-allow-methods": "GET,POST,OPTIONS"
    }
  });
}

function internalJson(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8"
    }
  });
}

function monthKey(now = new Date()) {
  return now.toISOString().slice(0, 7);
}

function requireDev(env) {
  if (env.ENVIRONMENT !== "DEV") {
    throw new Error("DEV_ENDPOINT_DISABLED");
  }
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

  status(periodKey, limit) {
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
      return { ok: existing.state !== "DENIED", existing: true, state: existing.state, ...this.status(periodKey, limit) };
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
    schema: "hara.commander-portal-dashboard-dev.v1",
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

async function mcpProductContext(env, issuer, oidcSubject) {
  const normalizedIssuer = normalizeIssuer(issuer);
  const subject = cleanOpaque(oidcSubject, 512);
  const row = await env.PRODUCT_DB.prepare(
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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: json({}).headers });

    const requestUrl = new URL(request.url);

    try {
      requireDev(env);
      const url = requestUrl;

      if (url.pathname === "/api/dev/health" && request.method === "GET") {
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

      if (url.pathname.startsWith("/api/internal/mcp/")) {
        requireMcpProductToken(request, env);
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

        const context = await mcpProductContext(env, body.issuer, body.subject);
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
      const code = error?.message || "INTERNAL_ERROR";
      const statusMap = {
        DEV_ACCESS_DENIED: 401,
        MCP_PRODUCT_ACCESS_DENIED: 401,
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
      };

      if (requestUrl.pathname === "/auth/callback") {
        const safeCode = /^[A-Z0-9_]{1,80}$/.test(code) ? code : "AUTH_CALLBACK_FAILED";
        return new Response(null, {
          status: 302,
          headers: {
            location: "/?auth_error=" + encodeURIComponent(safeCode) + "#login",
            "cache-control": "no-store",
          },
        });
      }

      return json({ ok: false, code }, statusMap[code] || 500);
    }
  }
};
