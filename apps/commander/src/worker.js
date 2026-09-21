import { DurableObject } from "cloudflare:workers";
import {
  authStatus,
  beginLogin,
  finishLogin,
  logout,
  resolvePortalSession,
} from "./auth.js";

const DEMO_TENANT = "HARA-TENANT-DEMO-0001";

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

function monthKey(now = new Date()) {
  return now.toISOString().slice(0, 7);
}

function requireDev(env) {
  if (env.ENVIRONMENT !== "DEV") {
    throw new Error("DEV_ENDPOINT_DISABLED");
  }
}

function requireRemoteDevToken(request, env) {
  if (env.STORAGE_MODE !== "REMOTE_DEV") return;
  const expected = String(env.DEV_ACCESS_TOKEN || "");
  const supplied = String(request.headers.get("x-hara-dev-token") || "");
  if (!expected || supplied.length !== expected.length) {
    throw new Error("DEV_ACCESS_DENIED");
  }
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) {
    diff |= expected.charCodeAt(i) ^ supplied.charCodeAt(i);
  }
  if (diff !== 0) throw new Error("DEV_ACCESS_DENIED");
}

function cleanId(value, max = 180) {
  const text = String(value || "").trim();
  if (!text || text.length > max || !/^[A-Za-z0-9_.:-]+$/.test(text)) {
    throw new Error("INVALID_IDENTIFIER");
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

  reserve(requestId, periodKey, functionId, limit) {
    const existing = [...this.ctx.storage.sql.exec(
      `SELECT request_id, period_key, function_id, state, units, receipt_sha256
         FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (existing) {
      if (existing.period_key !== periodKey || existing.function_id !== functionId) {
        return { ok: false, code: "IDEMPOTENCY_CONFLICT", existing: true, state: existing.state };
      }
      return { ok: existing.state !== "DENIED", existing: true, state: existing.state, ...this.status(periodKey, limit) };
    }

    const balance = this.status(periodKey, limit);
    if (limit != null && balance.consumed_units >= limit) {
      this.ctx.storage.sql.exec(
        `INSERT INTO request_state
          (request_id, period_key, function_id, state, units, updated_at_utc)
         VALUES (?, ?, ?, 'DENIED', 0, ?)`,
        requestId, periodKey, functionId, new Date().toISOString()
      );
      return { ok: false, code: "QUOTA_EXCEEDED", existing: false, state: "DENIED", ...balance };
    }

    this.ctx.storage.sql.exec(
      `INSERT INTO request_state
        (request_id, period_key, function_id, state, units, updated_at_utc)
       VALUES (?, ?, ?, 'RESERVED', 1, ?)`,
      requestId, periodKey, functionId, new Date().toISOString()
    );

    return { ok: true, existing: false, state: "RESERVED", ...this.status(periodKey, limit) };
  }

  commit(requestId, receiptSha256, limit) {
    const row = [...this.ctx.storage.sql.exec(
      `SELECT request_id, period_key, function_id, state, receipt_sha256
         FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (!row) return { ok: false, code: "RESERVATION_NOT_FOUND" };
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

  release(requestId, limit) {
    const row = [...this.ctx.storage.sql.exec(
      `SELECT request_id, period_key, state FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (!row) return { ok: false, code: "RESERVATION_NOT_FOUND" };
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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: json({}).headers });

    try {
      requireDev(env);
      const url = new URL(request.url);

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
        return json(await stub.reserve(requestId, periodKey, functionId, limit));
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
        return json(await env.TENANT_QUOTA.getByName(tenantId).commit(requestId, receiptSha256, limit));
      }

      if (url.pathname === "/api/dev/quota/release" && request.method === "POST") {
        const body = await request.json();
        const tenantId = cleanId(body.tenant_id || DEMO_TENANT);
        const requestId = cleanId(body.request_id);
        const ent = await entitlementForTenant(env, tenantId);
        if (!ent) return json({ ok: false, code: "ENTITLEMENT_NOT_FOUND" }, 404);
        const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
        return json(await env.TENANT_QUOTA.getByName(tenantId).release(requestId, limit));
      }

      return json({ ok: false, code: "NOT_FOUND" }, 404);
    } catch (error) {
      const code = error?.message || "INTERNAL_ERROR";
      const statusMap = {
        DEV_ACCESS_DENIED: 401,
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

      if (url?.pathname === "/auth/callback") {
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
