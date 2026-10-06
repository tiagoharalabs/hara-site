import { DurableObject } from "cloudflare:workers";
import {
  authCallbackFailureResponse,
  authStatus,
  beginLogin,
  finishLogin,
  logout,
  resolvePortalSession,
  runAuthRetentionMaintenance,
} from "./auth.js";
import { normalizeIssuer, randomToken, sha256 } from "./oidc.js";
import {
  billingStatus,
  createBillingCheckout,
  createBillingPortal,
  handleStripeWebhook,
} from "./billing.mjs";
import {
  haraIdentityMcpDevEnabled,
  haraIdentityMcpDevProtectedResourceMetadata,
  haraIdentityMcpDevUnauthorized,
  verifyHaraIdentityMcpDevBearer,
} from "./mcp-hara-identity-dev.mjs";
import {
  haraIdentityCustomerMcpEnabled,
  haraIdentityCustomerMcpProtectedResourceMetadata,
  haraIdentityCustomerMcpUnauthorized,
  verifyHaraIdentityCustomerMcpBearer,
} from "./mcp-hara-identity-customer.mjs";
import { handleCustomerMcpRequest } from "./customer-mcp.mjs";
import { handleSimpleCustomerMcpRequest } from "./customer-mcp-simple.mjs";
import {
  DEVICE_FUNCTION_ID,
  DEVICE_TOOL_FUNCTION_MAP,
  deviceFunctionForTool,
  isDeviceFunctionAllowed,
  isDeviceMutationTool,
  isDeviceProcessTool,
  isDeviceProcessMutationTool,
  canonicalDeviceToolPayload,
} from "./device-tool-contract.mjs";
import { chooseCustomerTargetDevice } from "./device-targeting.mjs";
import { DeviceChannel, deviceChannelName } from "./device-channel.mjs";
import { SecurityRateLimit } from "./security-rate-limit-do.mjs";
import {
  enforceLayeredRateLimit,
  rateLimitActorKey,
  rateLimitClientKey,
  rateLimitSecretKey,
} from "./security-rate-limit.mjs";
import { signProductLease } from "./product-lease.mjs";
export { DeviceChannel };
export { SecurityRateLimit };

const DEMO_TENANT = "HARA-TENANT-DEMO-0001";
const MCP_METER_ID = "HARA_COMMANDER_GOVERNED_INVOKE";
const MCP_SECONDARY_PROVIDER = "CLOUDFLARE_ACCESS";
const DEVICE_CALL_TTL_SECONDS = 50;
const DEVICE_CALL_ACTIVE_QUEUE_LIMIT = 16;
const DEVICE_CALL_EXPIRY_MAINTENANCE_BATCH = 5000;
const DEVICE_CALL_CONTENT_REDACTION_BATCH = 64;
const DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES = 8;
const DEVICE_CALL_REDACTED_PREFIX = "HARA_REDACTED_SHA256:";
const EVENT_V2_TERMINAL_FAST_PATH_WAIT_MS = 500;
const LOCAL_BUDGET_MIN_LINUX_PATCH = 36;
const LOCAL_BUDGET_BLOCK_UNITS = 100;
const PRODUCT_LEASE_TTL_SECONDS = 6 * 60 * 60;
const SLO_ALERT_PROFILE = "INTERNAL_BETA_V1";
const SLO_ALERT_BREACH_STREAK = 2;
const SLO_ALERT_RECOVERY_STREAK = 2;
const SLO_ALERT_ONLINE_GRACE_SECONDS = 120;
const SLO_ALERT_SNAPSHOT_GRACE_SECONDS = 180;
const SLO_ALERT_INCIDENT_RETENTION_SECONDS = 90 * 24 * 60 * 60;
const TRANSIENT_EXECUTE_OR_REPLAY = "EXECUTE_OR_REPLAY";
const TRANSIENT_REPLAY_ONLY = "REPLAY_ONLY";
const TRANSIENT_SAFE_PREEXEC_RELEASE_CODES = new Set([
  "CHANNEL_TRANSIENT_OFFLINE",
  "CHANNEL_TRANSIENT_BUSY",
]);

function transientPublicErrorCode(code) {
  return code === "CHANNEL_TRANSIENT_OFFLINE" ? "DEVICE_OFFLINE" : code;
}
const QUOTA_RESERVATION_TTL_SECONDS = 10 * 60;
const PAIRING_RETENTION_SECONDS = 30 * 24 * 60 * 60;
const PAIRING_RETENTION_BATCH = 100;
const MCP_TOOL_GRANTS = Object.freeze({
  "hara.devices.list": "COMMANDER_DISCOVERY",
  "hara.capabilities": "COMMANDER_DISCOVERY",
  "hara.usage": "COMMANDER_RECEIPT_READ",
  "hara.activity": "COMMANDER_RECEIPT_READ",
  "hara.health": "COMMANDER_DISCOVERY",
  "hara.ping": "COMMANDER_DISCOVERY",
  "hara.device.info": "COMMANDER_READ_ONLY_INVOKE",
  "hara.system.uptime": "COMMANDER_READ_ONLY_INVOKE",
  "hara.system.resources": "COMMANDER_READ_ONLY_INVOKE",
  "hara.workspace.inspect": "COMMANDER_READ_ONLY_INVOKE",
  "hara.processes.list": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.info": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.hash": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.diff": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.search": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.list": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.read": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.read_many": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.create_directory": "COMMANDER_MUTATION_INVOKE",
  "hara.files.write": "COMMANDER_MUTATION_INVOKE",
  "hara.files.edit": "COMMANDER_MUTATION_INVOKE",
  "hara.files.move": "COMMANDER_MUTATION_INVOKE",
  "hara.files.copy": "COMMANDER_MUTATION_INVOKE",
  "hara.files.delete": "COMMANDER_MUTATION_INVOKE",
  "hara.files.preimages.list": "COMMANDER_READ_ONLY_INVOKE",
  "hara.files.rollback": "COMMANDER_MUTATION_INVOKE",
  "hara.process.sessions": "COMMANDER_READ_ONLY_INVOKE",
  "hara.process.run": "COMMANDER_PROCESS_EXECUTION",
  "hara.process.start": "COMMANDER_PROCESS_EXECUTION",
  "hara.process.output": "COMMANDER_READ_ONLY_INVOKE",
  "hara.process.interact": "COMMANDER_PROCESS_EXECUTION",
  "hara.process.kill": "COMMANDER_PROCESS_EXECUTION",
  "hara.functions.list": "COMMANDER_DISCOVERY",
  "hara.functions.describe": "COMMANDER_DISCOVERY",
  "hara.functions.invoke": "COMMANDER_READ_ONLY_INVOKE",
  "hara.receipts.get": "COMMANDER_RECEIPT_READ",
  "hara.calls.recent": "COMMANDER_RECEIPT_READ",
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

function rateLimitedJson(code) {
  const response = json({ ok: false, code }, 429);
  response.headers.set("retry-after", "60");
  return response;
}

function monthKey(now = new Date()) {
  return now.toISOString().slice(0, 7);
}

function monthEndUtc(periodKey) {
  const match=/^([0-9]{4})-([0-9]{2})$/.exec(String(periodKey || ""));
  if (!match) throw new Error("PERIOD_KEY_INVALID");
  const year=Number(match[1]);
  const month=Number(match[2]);
  if (month < 1 || month > 12) throw new Error("PERIOD_KEY_INVALID");
  return new Date(Date.UTC(year, month, 1)).toISOString();
}

function localBudgetEligibleDevice(device) {
  return String(device?.platform || "").toUpperCase() === "LINUX"
    && semverAtLeast(device?.agent_version, LOCAL_BUDGET_MIN_LINUX_PATCH)
    && !String(device?.tunnel_mode || "").toUpperCase().startsWith("EVENT_V2");
}

function callUsageMode(context, device, purposeFunctionId) {
  if (!purposeFunctionId || context.period_kind === "NONE") return "UNMETERED";
  if (context.period_kind === "CALENDAR_MONTH" && localBudgetEligibleDevice(device)) {
    return "LOCAL_BUDGET";
  }
  return "CLOUD_QUOTA";
}

async function resolveCallUsageMode(env, context, device, purposeFunctionId) {
  const preferred = callUsageMode(context, device, purposeFunctionId);
  if (preferred !== "LOCAL_BUDGET") return preferred;
  const periodKey = mcpPeriodKey(context);
  const row = await env.PRODUCT_DB.prepare(
    `SELECT budget_id
       FROM commander_device_budget_blocks
      WHERE tenant_id = ?
        AND device_id = ?
        AND period_key = ?
        AND state = 'ACTIVE'
        AND expires_at_utc > ?
        AND units_issued < units_allocated
      ORDER BY allocation_sequence ASC
      LIMIT 1`
  ).bind(context.tenant_id, device.device_id, periodKey, nowIso()).first();
  return row ? "LOCAL_BUDGET" : "CLOUD_QUOTA";
}

async function localBudgetAllocatedUnits(env, tenantId, periodKey) {
  const row = await env.PRODUCT_DB.prepare(
    `SELECT COALESCE(SUM(units_allocated),0) AS allocated
       FROM commander_device_budget_blocks
      WHERE tenant_id = ?
        AND period_key = ?`
  ).bind(tenantId, periodKey).first().catch(() => null);
  return Math.max(0, Number(row?.allocated || 0));
}

async function effectiveCloudQuotaLimit(env, context, periodKey) {
  if (context.period_kind === "NONE") return null;
  const configured = Number(context.unit_limit);
  if (context.period_kind !== "CALENDAR_MONTH") return configured;
  const localAllocated = await localBudgetAllocatedUnits(
    env,
    context.tenant_id,
    periodKey,
  );
  return Math.max(configured - localAllocated, 0);
}

async function tenantFullyLocalBudgetCapable(env, tenantId) {
  const result = await env.PRODUCT_DB.prepare(
    `SELECT platform,agent_version,tunnel_mode
       FROM commander_devices
      WHERE tenant_id = ?
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(tenantId).all();
  const rows = result.results || [];
  return rows.length > 0 && rows.every((row) => localBudgetEligibleDevice(row));
}

async function freshLocalBudgetBaseline(
  env,
  tenantId,
  periodKey,
  meterId,
  { createIfEligible = false } = {},
) {
  const existing = await env.PRODUCT_DB.prepare(
    `SELECT tenant_id,period_key,meter_id,legacy_consumed_units,source,state,
            established_at_utc,invalidated_at_utc,invalidation_reason
       FROM commander_tenant_budget_baselines
      WHERE tenant_id = ?
        AND period_key = ?
        AND meter_id = ?
      LIMIT 1`
  ).bind(tenantId, periodKey, meterId).first().catch(() => null);

  const compatible = await tenantFullyLocalBudgetCapable(env, tenantId);
  if (existing) {
    if (existing.state === "ACTIVE" && compatible) return existing;
    if (existing.state === "ACTIVE" && !compatible) {
      await env.PRODUCT_DB.prepare(
        `UPDATE commander_tenant_budget_baselines
            SET state = 'INVALIDATED',
                invalidated_at_utc = ?,
                invalidation_reason = 'MIXED_OR_INCOMPATIBLE_FLEET'
          WHERE tenant_id = ?
            AND period_key = ?
            AND meter_id = ?
            AND state = 'ACTIVE'`
      ).bind(nowIso(), tenantId, periodKey, meterId).run();
    }
    return null;
  }

  if (!createIfEligible || !compatible) return null;

  const periodStart = periodKey + "-01T00:00:00.000Z";
  const periodEnd = monthEndUtc(periodKey);
  const [history, blocks] = await Promise.all([
    env.PRODUCT_DB.prepare(
      `SELECT COUNT(*) AS prior_calls
         FROM commander_device_calls
        WHERE tenant_id = ?
          AND created_at_utc >= ?
          AND created_at_utc < ?`
    ).bind(tenantId, periodStart, periodEnd).first(),
    env.PRODUCT_DB.prepare(
      `SELECT COUNT(*) AS prior_blocks
         FROM commander_device_budget_blocks
        WHERE tenant_id = ?
          AND period_key = ?`
    ).bind(tenantId, periodKey).first(),
  ]);

  if (
    Number(history?.prior_calls || 0) !== 0
    || Number(blocks?.prior_blocks || 0) !== 0
  ) {
    return null;
  }

  const establishedAt = nowIso();
  await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO commander_tenant_budget_baselines
       (tenant_id,period_key,meter_id,legacy_consumed_units,source,state,
        established_at_utc,invalidated_at_utc,invalidation_reason)
     VALUES (?, ?, ?, 0, 'FRESH_TENANT_ZERO', 'ACTIVE', ?, NULL, NULL)`
  ).bind(tenantId, periodKey, meterId, establishedAt).run();

  return env.PRODUCT_DB.prepare(
    `SELECT tenant_id,period_key,meter_id,legacy_consumed_units,source,state,
            established_at_utc,invalidated_at_utc,invalidation_reason
       FROM commander_tenant_budget_baselines
      WHERE tenant_id = ?
        AND period_key = ?
        AND meter_id = ?
        AND state = 'ACTIVE'
      LIMIT 1`
  ).bind(tenantId, periodKey, meterId).first();
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

async function requireMcpProductToken(request, env) {
  const supplied = request.headers.get("x-hara-mcp-product-token");
  if (secretMatches(env.MCP_PRODUCT_TOKEN, supplied)) return;
  if (
    env.ENVIRONMENT === "DEV"
    && secretMatches(env.MCP_PRODUCT_CANARY_TOKEN, supplied)
  ) {
    return;
  }

  await enforceLayeredRateLimit(
    env.RATE_LIMIT_MCP_AUTH_FAILURE,
    env.STRICT_RATE_LIMIT,
    await rateLimitClientKey(request, "mcp-auth-failure-client"),
    20,
    60,
    "MCP_AUTH_RATE_LIMITED",
    { allowStrictUnavailableFallback: true },
  );
  if (supplied) {
    await enforceLayeredRateLimit(
      env.RATE_LIMIT_MCP_AUTH_FAILURE,
      env.STRICT_RATE_LIMIT,
      await rateLimitSecretKey("mcp-auth-failure-token", supplied),
      20,
      60,
      "MCP_AUTH_RATE_LIMITED",
      { allowStrictUnavailableFallback: true },
    );
  }
  throw new Error("MCP_PRODUCT_ACCESS_DENIED");
}

async function enforceLoginInitiationRateLimit(request, env) {
  await enforceLayeredRateLimit(
    env.RATE_LIMIT_LOGIN,
    env.STRICT_RATE_LIMIT,
    await rateLimitClientKey(request, "auth-login"),
    30,
    60,
    "AUTH_RATE_LIMITED",
    { allowStrictUnavailableFallback: true },
  );
}

async function enforceDeviceEnrollClientRateLimit(request, env) {
  await enforceLayeredRateLimit(
    env.RATE_LIMIT_DEVICE_ENROLL_CLIENT,
    env.STRICT_RATE_LIMIT,
    await rateLimitClientKey(request, "device-enroll-client"),
    60,
    60,
    "DEVICE_ENROLL_RATE_LIMITED",
    { allowStrictUnavailableFallback: true },
  );
}

async function enforceDeviceEnrollTokenRateLimit(body, env) {
  const supplied = String(body?.pairing_token || "");
  if (!supplied) return;
  await enforceLayeredRateLimit(
    env.RATE_LIMIT_DEVICE_ENROLL_TOKEN,
    env.STRICT_RATE_LIMIT,
    await rateLimitSecretKey("device-enroll-token", supplied),
    10,
    60,
    "DEVICE_ENROLL_RATE_LIMITED",
    { allowStrictUnavailableFallback: true },
  );
}

async function enforcePortalMutationRateLimit(env, session) {
  await enforceLayeredRateLimit(
    env.RATE_LIMIT_PORTAL_MUTATION,
    env.STRICT_RATE_LIMIT,
    await rateLimitActorKey("portal-mutation", session.tenant_id, session.subject_id),
    60,
    60,
    "PORTAL_MUTATION_RATE_LIMITED",
    { allowStrictUnavailableFallback: true },
  );
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

function normalizeApprovalMode(value, fallback = "ASK_EVERY_ACTION") {
  const raw = String(value || "").trim().toUpperCase();
  const aliases = {
    "ASK": "ASK_EVERY_ACTION",
    "ASK_EVERY_ACTION": "ASK_EVERY_ACTION",
    "SESSION": "SESSION_TRUSTED",
    "SESSION_TRUSTED": "SESSION_TRUSTED",
    "AUTO": "PERSISTENT_TRUSTED",
    "ALWAYS": "PERSISTENT_TRUSTED",
    "PERSISTENT": "PERSISTENT_TRUSTED",
    "PERSISTENT_TRUSTED": "PERSISTENT_TRUSTED",
  };
  const mode = raw ? aliases[raw] : fallback;
  if (!["ASK_EVERY_ACTION","SESSION_TRUSTED","PERSISTENT_TRUSTED"].includes(mode)) {
    throw new Error("DEVICE_APPROVAL_MODE_INVALID");
  }
  return mode;
}

function deviceCallRetryAfterMs(state, source = "status") {
  const normalized = String(state || "").trim().toUpperCase();
  if (normalized === "PENDING") return source === "enqueue" ? 350 : 750;
  if (normalized === "EXECUTING") return 250;
  return 0;
}

function deviceOnline(lastSeenAtUtc, tunnelMode = "OUTBOUND_RELAY", now = Date.now()) {
  const mode = String(tunnelMode || "");
  if (mode === "EVENT_V2_OFFLINE" || mode === "OUTBOUND_RELAY_OFFLINE") return false;
  if (!lastSeenAtUtc) return false;
  const seen = Date.parse(String(lastSeenAtUtc));
  if (!Number.isFinite(seen)) return false;
  const onlineWindowMs = mode === "EVENT_V2"
    ? 7 * 60 * 60 * 1000
    : 90_000;
  return now - seen <= onlineWindowMs;
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

function eventV2Enabled(env) {
  return String(env.DEVICE_EVENT_V2_ENABLED || "").trim().toLowerCase() === "true";
}

function transientRpcEnabled(env) {
  return env.ENVIRONMENT === "DEV"
    && eventV2Enabled(env)
    && String(env.DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED || "").trim().toLowerCase() === "true";
}

async function openDeviceEventChannel(env, request) {
  if (!eventV2Enabled(env)) throw new Error("DEVICE_EVENT_V2_DISABLED");
  if (!env.DEVICE_CHANNEL) throw new Error("DEVICE_EVENT_V2_BINDING_MISSING");
  if (String(request.headers.get("upgrade") || "").toLowerCase() !== "websocket") {
    return json({ ok: false, code: "DEVICE_EVENT_V2_UPGRADE_REQUIRED" }, 426);
  }

  const device = await resolveDeviceCredential(env, request);
  const stub = env.DEVICE_CHANNEL.getByName(
    deviceChannelName(device.tenant_id, device.device_id)
  );
  const headers = new Headers();
  headers.set("Upgrade", "websocket");
  headers.set("x-hara-channel-authenticated", "1");
  headers.set("x-hara-tenant-id", device.tenant_id);
  headers.set("x-hara-device-id", device.device_id);

  return stub.fetch(new Request("https://device-channel/connect", {
    method: "GET",
    headers,
  }));
}

async function notifyDeviceEventChannel(env, tenantId, deviceId, callId) {
  if (!eventV2Enabled(env) || !env.DEVICE_CHANNEL) {
    return { attempted: false, delivered: 0 };
  }

  try {
    const stub = env.DEVICE_CHANNEL.getByName(deviceChannelName(tenantId, deviceId));
    const response = await stub.fetch(new Request("https://device-channel/notify", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-hara-channel-authenticated": "1",
      },
      body: JSON.stringify({ call_id: callId }),
    }));
    if (!response.ok) {
      return { attempted: true, delivered: 0 };
    }
    const payload = await response.json().catch(() => ({}));
    return {
      attempted: true,
      delivered: Number(payload.delivered || 0),
    };
  } catch (_error) {
    // D1 call state remains authoritative. Event delivery is an accelerator only.
    return { attempted: true, delivered: 0 };
  }
}


const LEARNING_SIGNAL_KEYS = Object.freeze([
  "schema",
  "tool_id",
  "tool_family",
  "outcome",
  "latency_bucket",
  "result_bytes_bucket",
  "platform",
  "agent_version",
  "transport_mode",
  "privileged_attempt",
  "customer_content_collected",
]);

function recordLearningSignal(env, signal) {
  if (!env.LEARNING_ANALYTICS) return { attempted: false, recorded: false };
  try {
    if (!signal || typeof signal !== "object" || Array.isArray(signal)) {
      return { attempted: true, recorded: false };
    }
    const keys = Object.keys(signal).sort();
    if (keys.join(",") !== [...LEARNING_SIGNAL_KEYS].sort().join(",")) {
      return { attempted: true, recorded: false };
    }
    if (
      signal.schema !== "hara.commander-learning-signal.v1"
      || signal.privileged_attempt !== false
      || signal.customer_content_collected !== false
    ) {
      return { attempted: true, recorded: false };
    }

    const toolId = cleanId(signal.tool_id, 120);
    const toolFamily = cleanId(signal.tool_family, 80);
    const outcome = cleanId(signal.outcome, 40);
    const latencyBucket = cleanId(signal.latency_bucket, 40);
    const resultBytesBucket = cleanId(signal.result_bytes_bucket, 40);
    const platform = cleanId(signal.platform, 40);
    const agentVersion = cleanId(signal.agent_version, 80);
    const transportMode = cleanId(signal.transport_mode, 40);

    env.LEARNING_ANALYTICS.writeDataPoint({
      indexes: [toolFamily],
      blobs: [
        toolId,
        toolFamily,
        outcome,
        latencyBucket,
        resultBytesBucket,
        platform,
        agentVersion,
        transportMode,
      ],
      doubles: [1],
    });
    return { attempted: true, recorded: true };
  } catch (_error) {
    // Analytics must never delay or fail a customer call.
    return { attempted: true, recorded: false };
  }
}

async function dispatchTransientDeviceCall(env, body) {
  if (!transientRpcEnabled(env)) throw new Error("DEVICE_TRANSIENT_RPC_DISABLED");
  if (!env.DEVICE_CHANNEL) throw new Error("DEVICE_EVENT_V2_BINDING_MISSING");

  const requestId = cleanId(body.request_id, 220);
  const toolId = cleanId(body.tool_id, 120);
  const requiredGrant = MCP_TOOL_GRANTS[toolId];
  if (!requiredGrant) throw new Error("DEVICE_CALL_TOOL_DENIED");

  const context = await mcpTransientProductContext(
    env,
    body.issuer,
    body.subject,
    mcpBootstrapHints(body),
  );
  if (!context.ok) throw new Error(context.code);
  if (!context.grants.includes(requiredGrant)) throw new Error("GRANT_MISSING");

  const requestedDeviceId = body.device_id ? cleanId(body.device_id, 180) : null;
  const canonicalPayload = canonicalDeviceToolPayload(toolId, body.payload);
  boundedJson(canonicalPayload, 128 * 1024, "DEVICE_CALL_PAYLOAD_INVALID");

  const device = await resolveCustomerTargetDevice(
    env, context, body.computer || null, requestedDeviceId
  );
  const deviceId = cleanId(device.device_id, 180);
  if (!deviceOnline(device.last_seen_at_utc, device.tunnel_mode)) {
    throw new Error("DEVICE_OFFLINE");
  }
  if (String(device.tunnel_mode || "") !== "EVENT_V2") {
    throw new Error("DEVICE_TRANSIENT_REQUIRES_EVENT_V2");
  }

  let quota = null;
  let reservation = null;
  let committedReplayReceipt = null;
  let executionMode = TRANSIENT_EXECUTE_OR_REPLAY;
  if (toolId === "hara.functions.invoke") {
    const functionId = cleanId(canonicalPayload.function_id, 180);
    if (!isDeviceFunctionAllowed(functionId)) throw new Error("POLICY_DENIED");
    quota = env.TENANT_QUOTA.getByName(context.tenant_id);
    reservation = await quota.reserve(
      requestId,
      context.subject_id,
      mcpPeriodKey(context),
      functionId,
      context.unit_limit,
    );
    if (!reservation.ok) {
      throw new Error(String(reservation.code || "QUOTA_DENIED"));
    }
    if (reservation.existing && reservation.state === "RELEASED") {
      throw new Error("REQUEST_USAGE_TERMINAL");
    }
    if (reservation.state === "COMMITTED") {
      committedReplayReceipt = String(
        reservation.receipt_sha256 || "",
      ).trim().toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(committedReplayReceipt)) {
        throw new Error("TRANSIENT_COMMITTED_RECEIPT_INVALID");
      }
      executionMode = TRANSIENT_REPLAY_ONLY;
    } else if (reservation.state !== "RESERVED") {
      throw new Error("TRANSIENT_QUOTA_STATE_INVALID");
    }
  }

  const callId = "HARA-TRANSIENT-" + crypto.randomUUID();
  const stub = env.DEVICE_CHANNEL.getByName(
    deviceChannelName(context.tenant_id, deviceId),
  );

  let response;
  try {
    response = await stub.fetch(new Request("https://device-channel/dispatch", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-hara-channel-authenticated": "1",
      },
      body: JSON.stringify({
        call_id: callId,
        request_id: requestId,
        tool_id: toolId,
        execution_mode: executionMode,
        payload: canonicalPayload,
      }),
    }));
  } catch (error) {
    // Transport exceptions after dispatch are ambiguous: the Agent may have
    // executed and persisted a local replay result. Keep RESERVED so retry can
    // reconcile through the same request_id instead of allowing a free replay.
    throw error;
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const rawCode = String(payload.code || "DEVICE_TRANSIENT_RPC_FAILED");
    if (
      quota
      && reservation?.state === "RESERVED"
      && TRANSIENT_SAFE_PREEXEC_RELEASE_CODES.has(rawCode)
    ) {
      await quota.release(requestId, context.subject_id, context.unit_limit);
    }
    throw new Error(transientPublicErrorCode(rawCode));
  }

  let usage = null;
  let receiptSha256 = null;
  if (toolId === "hara.functions.invoke") {
    if (payload.state === "FAILED") {
      if (reservation?.state === "RESERVED") {
        usage = await quota.release(
          requestId,
          context.subject_id,
          context.unit_limit,
        );
      } else {
        usage = reservation;
      }
    } else if (payload.state === "COMPLETED") {
      receiptSha256 = String(
        payload.result?.bridge_receipt_sha256 || "",
      ).trim().toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(receiptSha256)) {
        // Do not release an ambiguous successful execution. The reservation
        // expires fail-closed unless a retry can recover the local receipt.
        throw new Error("DEVICE_CALL_RECEIPT_INVALID");
      }
      if (executionMode === TRANSIENT_REPLAY_ONLY) {
        if (receiptSha256 !== committedReplayReceipt) {
          throw new Error("TRANSIENT_REPLAY_RECEIPT_MISMATCH");
        }
        // reserve() already proved this request_id is COMMITTED for the same
        // subject/period/function and returned the canonical committed receipt.
        // A local Agent replay only needs to match that receipt; a second
        // TenantQuota commit RPC would repeat the same state/receipt checks.
        usage = reservation;
      } else {
        usage = await quota.commit(
          requestId,
          context.subject_id,
          receiptSha256,
          context.unit_limit,
        );
        if (!usage.ok) {
          throw new Error(String(usage.code || "TRANSIENT_QUOTA_COMMIT_FAILED"));
        }
      }
    } else {
      throw new Error("CHANNEL_TRANSIENT_RESULT_INVALID");
    }
  }

  recordLearningSignal(env, payload.learning_signal);

  return {
    schema: "hara.commander-device-transient-call.v1",
    transport_mode: "EVENT_V2_TRANSIENT_RPC",
    execution_mode: executionMode,
    persisted_customer_payload: false,
    persisted_customer_result: false,
    request_id: requestId,
    device_id: deviceId,
    tool_id: toolId,
    call_id: callId,
    state: payload.state,
    result: payload.result ?? {},
    error_code: payload.error_code || null,
    receipt_sha256: receiptSha256,
    usage,
    learning_signal: payload.learning_signal,
  };
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

        CREATE INDEX IF NOT EXISTS idx_request_state_expiry
          ON request_state(state, updated_at_utc);

        CREATE TABLE IF NOT EXISTS period_usage (
          period_key TEXT PRIMARY KEY,
          consumed_units INTEGER NOT NULL DEFAULT 0 CHECK (consumed_units >= 0)
        );

        CREATE TABLE IF NOT EXISTS quota_meta (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          usage_schema_version INTEGER NOT NULL DEFAULT 0
        );

        INSERT OR IGNORE INTO quota_meta (id, usage_schema_version)
        VALUES (1, 0);

        CREATE TRIGGER IF NOT EXISTS trg_request_state_usage_insert
        AFTER INSERT ON request_state
        WHEN NEW.state IN ('RESERVED', 'COMMITTED') AND NEW.units <> 0
        BEGIN
          INSERT INTO period_usage (period_key, consumed_units)
          VALUES (NEW.period_key, NEW.units)
          ON CONFLICT(period_key) DO UPDATE SET
            consumed_units = consumed_units + excluded.consumed_units;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_request_state_usage_update_same_period
        AFTER UPDATE OF period_key, state, units ON request_state
        WHEN OLD.period_key = NEW.period_key
          AND (OLD.state <> NEW.state OR OLD.units <> NEW.units)
        BEGIN
          UPDATE period_usage
             SET consumed_units = consumed_units
               - CASE
                   WHEN OLD.state IN ('RESERVED', 'COMMITTED') THEN OLD.units
                   ELSE 0
                 END
               + CASE
                   WHEN NEW.state IN ('RESERVED', 'COMMITTED') THEN NEW.units
                   ELSE 0
                 END
           WHERE period_key = NEW.period_key;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_request_state_usage_update_period
        AFTER UPDATE OF period_key, state, units ON request_state
        WHEN OLD.period_key <> NEW.period_key
        BEGIN
          UPDATE period_usage
             SET consumed_units = consumed_units
               - CASE
                   WHEN OLD.state IN ('RESERVED', 'COMMITTED') THEN OLD.units
                   ELSE 0
                 END
           WHERE period_key = OLD.period_key;

          INSERT INTO period_usage (period_key, consumed_units)
          VALUES (
            NEW.period_key,
            CASE
              WHEN NEW.state IN ('RESERVED', 'COMMITTED') THEN NEW.units
              ELSE 0
            END
          )
          ON CONFLICT(period_key) DO UPDATE SET
            consumed_units = consumed_units + excluded.consumed_units;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_request_state_usage_delete
        AFTER DELETE ON request_state
        WHEN OLD.state IN ('RESERVED', 'COMMITTED') AND OLD.units <> 0
        BEGIN
          UPDATE period_usage
             SET consumed_units = consumed_units - OLD.units
           WHERE period_key = OLD.period_key;
        END;
      `);

      const columns = [...this.ctx.storage.sql.exec("PRAGMA table_info(request_state)")];
      if (!columns.some((column) => column.name === "subject_id")) {
        this.ctx.storage.sql.exec(
          "ALTER TABLE request_state ADD COLUMN subject_id TEXT NOT NULL DEFAULT 'LEGACY'"
        );
      }

      const usageMeta = [...this.ctx.storage.sql.exec(
        "SELECT usage_schema_version FROM quota_meta WHERE id = 1"
      )][0] || { usage_schema_version: 0 };
      if (Number(usageMeta.usage_schema_version || 0) < 1) {
        this.ctx.storage.sql.exec(`
          DELETE FROM period_usage;

          INSERT INTO period_usage (period_key, consumed_units)
          SELECT period_key, COALESCE(SUM(units), 0)
            FROM request_state
           WHERE state IN ('RESERVED', 'COMMITTED')
           GROUP BY period_key;

          UPDATE quota_meta
             SET usage_schema_version = 1
           WHERE id = 1;
        `);
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

  status(periodKey, limit, expireReservations = true) {
    if (expireReservations) this.expireStaleReservations();
    const row = [...this.ctx.storage.sql.exec(
      `SELECT consumed_units AS consumed
         FROM period_usage
        WHERE period_key = ?`,
      periodKey
    )][0] || { consumed: 0 };

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
        ...this.status(periodKey, limit, false)
      };
    }

    const balance = this.status(periodKey, limit, false);
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

    const consumedUnits = balance.consumed_units + 1;
    return {
      ok: true,
      existing: false,
      state: "RESERVED",
      ...balance,
      consumed_units: consumedUnits,
      remaining_units: limit == null ? null : Math.max(limit - consumedUnits, 0),
    };
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
      return { ok: true, existing: true, state: "COMMITTED", ...this.status(row.period_key, limit, false) };
    }
    if (row.state !== "RESERVED") return { ok: false, code: "RESERVATION_NOT_ACTIVE", state: row.state };

    this.ctx.storage.sql.exec(
      `UPDATE request_state
          SET state = 'COMMITTED', receipt_sha256 = ?, updated_at_utc = ?
        WHERE request_id = ?`,
      receiptSha256, new Date().toISOString(), requestId
    );
    return { ok: true, existing: false, state: "COMMITTED", ...this.status(row.period_key, limit, false) };
  }

  release(requestId, subjectId, limit) {
    this.expireStaleReservations();
    const row = [...this.ctx.storage.sql.exec(
      `SELECT request_id, subject_id, period_key, state FROM request_state WHERE request_id = ?`,
      requestId
    )][0];

    if (!row) return { ok: false, code: "RESERVATION_NOT_FOUND" };
    if (row.subject_id !== subjectId) return { ok: false, code: "IDEMPOTENCY_CONFLICT" };
    if (row.state === "RELEASED") return { ok: true, existing: true, state: "RELEASED", ...this.status(row.period_key, limit, false) };
    if (row.state !== "RESERVED") return { ok: false, code: "RESERVATION_NOT_ACTIVE", state: row.state };

    this.ctx.storage.sql.exec(
      `UPDATE request_state SET state = 'RELEASED', units = 0, updated_at_utc = ? WHERE request_id = ?`,
      new Date().toISOString(), requestId
    );
    return { ok: true, existing: false, state: "RELEASED", ...this.status(row.period_key, limit, false) };
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

function unlimitedProductUsage() {
  return {
    period_key: "UNLIMITED",
    limit: null,
    consumed_units: null,
    remaining_units: null,
    metered: false,
  };
}

async function productUsageForPolicy(
  env,
  tenantId,
  periodKind,
  unitLimit,
  meterId = MCP_METER_ID,
) {
  const kind = String(periodKind || "").trim().toUpperCase();
  if (kind === "NONE") return { ...unlimitedProductUsage(), available: true };

  const periodKey = kind === "CALENDAR_MONTH" ? monthKey() : "LIFETIME";
  const limit = Number(unitLimit);
  try {
    const [freshBaseline, localBudget] = await Promise.all([
      kind === "CALENDAR_MONTH"
        ? freshLocalBudgetBaseline(
            env,
            tenantId,
            periodKey,
            meterId,
            { createIfEligible: false },
          )
        : Promise.resolve(null),
      env.PRODUCT_DB.prepare(
        `SELECT COALESCE(SUM(units_allocated),0) AS allocated,
                COALESCE(SUM(units_reported),0) AS reported
           FROM commander_device_budget_blocks
          WHERE tenant_id = ?
            AND period_key = ?`
      ).bind(tenantId, periodKey).first().catch(() => null),
    ]);

    let legacyConsumed;
    let baselineSource;
    if (freshBaseline) {
      legacyConsumed = Number(freshBaseline.legacy_consumed_units || 0);
      baselineSource = String(freshBaseline.source || "FRESH_TENANT_ZERO");
    } else {
      const legacy = await env.TENANT_QUOTA.getByName(tenantId).status(periodKey, limit);
      legacyConsumed = Number(legacy?.consumed_units || 0);
      baselineSource = "TENANT_QUOTA_LIVE";
    }

    const localAllocated = Number(localBudget?.allocated || 0);
    const localReported = Number(localBudget?.reported || 0);
    const consumed = legacyConsumed + localReported;
    return {
      period_key: periodKey,
      limit,
      consumed_units: consumed,
      remaining_units: Math.max(limit - consumed, 0),
      metered: true,
      available: true,
      consistency: localAllocated > 0 ? "EVENTUAL_LOCAL_BUDGET" : "CLOUD_AUTHORITATIVE",
      cloud_legacy_consumed_units: legacyConsumed,
      legacy_baseline_source: baselineSource,
      local_budget_allocated_units: localAllocated,
      local_budget_reported_units: localReported,
      local_budget_unreported_capacity_units: Math.max(localAllocated - localReported, 0),
    };
  } catch (_error) {
    // Read-only product surfaces degrade independently from execution authority.
    // Quota reserve/commit/release paths remain fail-closed.
    return {
      period_key: periodKey,
      limit,
      consumed_units: null,
      remaining_units: null,
      metered: true,
      available: false,
      error_code: "USAGE_TEMPORARILY_UNAVAILABLE",
    };
  }
}

async function dashboard(env, tenantId) {
  const ent = await entitlementForTenant(env, tenantId);
  if (!ent) return null;

  const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
  const usage = await productUsageForPolicy(
    env,
    tenantId,
    ent.period_kind,
    ent.unit_limit,
    ent.meter_id,
  );

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
  const limit = ent.period_kind === "NONE" ? null : Number(ent.unit_limit);
  const usage = await productUsageForPolicy(
    env,
    tenantId,
    ent.period_kind,
    ent.unit_limit,
    ent.meter_id,
  );

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

function productLeaseForContext(context, device, grants, now = new Date()) {
  const issuedAt = now.toISOString();
  const leaseEnd = new Date(now.getTime() + PRODUCT_LEASE_TTL_SECONDS * 1000);
  const periodEnd = context.period_kind === "CALENDAR_MONTH"
    ? new Date(monthEndUtc(monthKey(now)))
    : null;
  const validUntil = periodEnd && periodEnd < leaseEnd ? periodEnd : leaseEnd;
  const usageMode = context.period_kind === "NONE"
    ? "UNMETERED"
    : (localBudgetEligibleDevice(device) && context.period_kind === "CALENDAR_MONTH"
      ? "LOCAL_BUDGET"
      : "CLOUD_QUOTA");
  return {
    schema: "hara.commander-device-product-lease.v1",
    lease_id: "HARA-PRODUCT-LEASE-" + crypto.randomUUID(),
    authority: "HARA_COMMANDER_CLOUD",
    device_id: device.device_id,
    tenant_id: context.tenant_id,
    entitlement_id: context.entitlement_id,
    plan_code: context.plan_code,
    plan_name: context.plan_name,
    grants: [...grants].sort(),
    meter_id: context.meter_id,
    period_kind: context.period_kind,
    unit_limit: context.unit_limit,
    usage_mode: usageMode,
    issued_at_utc: issuedAt,
    valid_until_utc: validUntil.toISOString(),
  };
}

async function reconcileDeviceBudgetReport(env, device, periodKey, report) {
  if (!report) return null;
  if (!report || typeof report !== "object") throw new Error("LOCAL_BUDGET_REPORT_INVALID");
  const budgetId = cleanId(report.budget_id, 180);
  const leaseToken = cleanOpaque(report.lease_token, 512);
  const committed = Number(report.committed_units);
  if (!Number.isInteger(committed) || committed < 0) throw new Error("LOCAL_BUDGET_REPORT_INVALID");

  const row = await env.PRODUCT_DB.prepare(
    `SELECT budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
            allocation_sequence,units_allocated,units_issued,units_reported,lease_token_hash,state,issued_at_utc,expires_at_utc
       FROM commander_device_budget_blocks
      WHERE budget_id = ?
        AND tenant_id = ?
        AND device_id = ?
      LIMIT 1`
  ).bind(budgetId, device.tenant_id, device.device_id).first();

  if (!row || String(row.period_key) !== String(periodKey)) {
    throw new Error("LOCAL_BUDGET_REPORT_INVALID");
  }
  const suppliedHash = await sha256(leaseToken);
  if (!secretMatches(row.lease_token_hash, suppliedHash)) {
    throw new Error("LOCAL_BUDGET_TOKEN_INVALID");
  }
  const allocated = Number(row.units_allocated);
  const prior = Number(row.units_reported);
  if (committed < prior || committed > allocated) {
    throw new Error("LOCAL_BUDGET_REPORT_NON_MONOTONIC");
  }
  const nextState = committed >= allocated ? "EXHAUSTED" : "ACTIVE";
  const reportedAt = nowIso();
  await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_budget_blocks
        SET units_reported = ?,
            state = ?,
            last_reported_at_utc = ?
      WHERE budget_id = ?
        AND tenant_id = ?
        AND device_id = ?`
  ).bind(
    committed, nextState, reportedAt,
    budgetId, device.tenant_id, device.device_id
  ).run();

  return {
    ...row,
    units_allocated: allocated,
    units_reported: committed,
    state: nextState,
    lease_token: leaseToken,
  };
}

function publicBudgetBlock(row, leaseToken) {
  if (!row) return null;
  return {
    schema: "hara.commander-local-budget-block.v1",
    budget_id: row.budget_id,
    device_id: row.device_id,
    tenant_id: row.tenant_id,
    entitlement_id: row.entitlement_id,
    plan_code: row.plan_code,
    meter_id: row.meter_id,
    period_key: row.period_key,
    allocation_sequence: Number(row.allocation_sequence),
    allocated_units: Number(row.units_allocated),
    cloud_issued_units: Number(row.units_issued || 0),
    committed_units: Number(row.units_reported || 0),
    lease_token: leaseToken,
    issued_at_utc: row.issued_at_utc,
    expires_at_utc: row.expires_at_utc,
    cloud_authoritative: true,
  };
}

async function issueDeviceBudgetBlock(env, device, entitlement, report = null) {
  const periodKey = monthKey();
  const now = nowIso();
  const expiresAt = monthEndUtc(periodKey);
  const reconciled = await reconcileDeviceBudgetReport(
    env, device, periodKey, report
  );

  if (
    reconciled
    && reconciled.state === "ACTIVE"
    && reconciled.units_reported < reconciled.units_allocated
    && String(reconciled.expires_at_utc) > now
  ) {
    return {
      exhausted: false,
      block: publicBudgetBlock(reconciled, reconciled.lease_token),
    };
  }

  const staleActive = await env.PRODUCT_DB.prepare(
    `SELECT budget_id
       FROM commander_device_budget_blocks
      WHERE tenant_id = ?
        AND device_id = ?
        AND period_key = ?
        AND state = 'ACTIVE'
      ORDER BY issued_at_utc DESC
      LIMIT 1`
  ).bind(device.tenant_id, device.device_id, periodKey).first();

  if (staleActive && !reconciled) {
    await env.PRODUCT_DB.prepare(
      `UPDATE commander_device_budget_blocks
          SET state = 'EXPIRED',
              last_reported_at_utc = ?
        WHERE budget_id = ?
          AND tenant_id = ?
          AND device_id = ?
          AND state = 'ACTIVE'`
    ).bind(now, staleActive.budget_id, device.tenant_id, device.device_id).run();
  }

  const totals = await env.PRODUCT_DB.prepare(
    `SELECT COALESCE(SUM(units_allocated),0) AS allocated,
            COUNT(*) AS block_count
       FROM commander_device_budget_blocks
      WHERE tenant_id = ?
        AND period_key = ?`
  ).bind(device.tenant_id, periodKey).first();

  const limit = Number(entitlement.unit_limit);
  const freshBaseline = await freshLocalBudgetBaseline(
    env,
    device.tenant_id,
    periodKey,
    entitlement.meter_id,
    { createIfEligible: true },
  );
  let legacyConsumed;
  let legacyBaselineSource;
  if (freshBaseline) {
    legacyConsumed = Number(freshBaseline.legacy_consumed_units || 0);
    legacyBaselineSource = String(freshBaseline.source || "FRESH_TENANT_ZERO");
  } else {
    const legacyUsage = await env.TENANT_QUOTA
      .getByName(device.tenant_id)
      .status(periodKey, limit);
    legacyConsumed = Number(legacyUsage?.consumed_units || 0);
    legacyBaselineSource = "TENANT_QUOTA_LIVE";
  }
  const allocated = Number(totals?.allocated || 0);
  const allocationSequence = Number(totals?.block_count || 0) + 1;
  const remaining = Math.max(limit - legacyConsumed - allocated, 0);
  if (remaining < 1) {
    return {
      exhausted: true,
      block: null,
      legacy_consumed_units: legacyConsumed,
      legacy_baseline_source: legacyBaselineSource,
      locally_allocated_units: allocated,
    };
  }

  const units = Math.min(LOCAL_BUDGET_BLOCK_UNITS, remaining);
  const budgetId = "HARA-BUDGET-" + crypto.randomUUID();
  const leaseToken = randomToken(32);
  const leaseTokenHash = await sha256(leaseToken);
  const issuedAt = nowIso();

  try {
    await env.PRODUCT_DB.prepare(
      `INSERT INTO commander_device_budget_blocks
         (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
          allocation_sequence,units_allocated,units_issued,units_reported,lease_token_hash,state,
          issued_at_utc,expires_at_utc,last_reported_at_utc)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 'ACTIVE', ?, ?, NULL)`
    ).bind(
      budgetId,
      device.tenant_id,
      device.device_id,
      entitlement.entitlement_id,
      entitlement.plan_code,
      entitlement.meter_id,
      periodKey,
      allocationSequence,
      units,
      leaseTokenHash,
      issuedAt,
      expiresAt,
    ).run();
  } catch (_error) {
    throw new Error("LOCAL_BUDGET_ALLOCATION_CONFLICT");
  }

  return {
    exhausted: false,
    legacy_consumed_units: legacyConsumed,
    legacy_baseline_source: legacyBaselineSource,
    locally_allocated_units: allocated + units,
    block: publicBudgetBlock({
      budget_id: budgetId,
      tenant_id: device.tenant_id,
      device_id: device.device_id,
      entitlement_id: entitlement.entitlement_id,
      plan_code: entitlement.plan_code,
      meter_id: entitlement.meter_id,
      period_key: periodKey,
      allocation_sequence: allocationSequence,
      units_allocated: units,
      units_issued: 0,
      units_reported: 0,
      issued_at_utc: issuedAt,
      expires_at_utc: expiresAt,
    }, leaseToken),
  };
}

async function deviceProductLease(env, request, body = {}) {
  const device = await resolveDeviceCredential(env, request);
  const entitlement = await entitlementForTenant(env, device.tenant_id);
  if (!entitlement) throw new Error("ENTITLEMENT_NOT_FOUND");
  const grants = await grantsForPlan(env, entitlement.plan_code);
  const context = {
    tenant_id: entitlement.tenant_id,
    entitlement_id: entitlement.entitlement_id,
    plan_code: entitlement.plan_code,
    plan_name: entitlement.plan_name,
    meter_id: entitlement.meter_id,
    period_kind: entitlement.period_kind,
    unit_limit: entitlement.period_kind === "NONE" ? null : Number(entitlement.unit_limit),
  };
  const productLease = productLeaseForContext(context, device, grants);
  let budget = null;

  if (productLease.usage_mode === "LOCAL_BUDGET") {
    try {
      budget = await issueDeviceBudgetBlock(
        env,
        device,
        context,
        body?.budget_report || null,
      );
    } catch (error) {
      productLease.usage_mode = "CLOUD_QUOTA";
      productLease.local_budget_degraded = true;
      productLease.local_budget_degraded_code = sanitizeErrorCode(error);
      budget = null;
    }
  }

  const productLeaseToken = await signProductLease(
    env,
    productLease,
    new URL(request.url).origin,
  );

  return {
    schema: "hara.commander-device-product-lease-response.v1",
    ok: true,
    product_lease: productLease,
    product_lease_token: productLeaseToken,
    product_lease_signature: {
      alg: "RS256",
      kid: "commander-lease-v1",
    },
    budget,
  };
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

function mcpBootstrapHints(body) {
  const providerCode = String(body?.provider_code || "").trim();
  const email = String(body?.email || "").trim();
  if (!providerCode && !email) return null;
  return {
    provider_code: body.provider_code,
    email: body.email,
  };
}

function finalizeMcpProductContext(row, normalizedIssuer, subject, grants) {
  if (!row) return { ok: false, code: "IDENTITY_NOT_PROVISIONED" };
  if (row.subject_state !== "ACTIVE") return { ok: false, code: "SUBJECT_INACTIVE" };
  if (row.tenant_state !== "ACTIVE") return { ok: false, code: "TENANT_INACTIVE" };
  if (row.entitlement_state !== "ACTIVE" || row.plan_state !== "ACTIVE") {
    return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  }

  const now = Date.now();
  const validFrom = Date.parse(row.valid_from_utc);
  const validUntil = row.valid_until_utc == null ? null : Date.parse(row.valid_until_utc);
  if (!Number.isFinite(validFrom) || now < validFrom) {
    return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  }
  if (validUntil != null && (!Number.isFinite(validUntil) || now >= validUntil)) {
    return { ok: false, code: "ENTITLEMENT_INACTIVE" };
  }

  if (row.meter_id !== MCP_METER_ID) return { ok: false, code: "METER_INVALID" };
  if (!["CALENDAR_MONTH", "LIFETIME", "NONE"].includes(row.period_kind)) {
    return { ok: false, code: "PERIOD_KIND_INVALID" };
  }
  if (!Array.isArray(grants) || grants.some((grant) => typeof grant !== "string" || !grant)) {
    return { ok: false, code: "USAGE_POLICY_INVALID" };
  }

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
  const grants = await grantsForPlan(env, row.plan_code);
  return finalizeMcpProductContext(row, normalizedIssuer, subject, grants);
}

async function mcpTransientProductContext(
  env,
  issuer,
  oidcSubject,
  bootstrap = null,
) {
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
       p.state AS plan_state,
       (
         SELECT json_group_array(pg.grant_code)
           FROM plan_grants pg
          WHERE pg.plan_code = p.plan_code
       ) AS grants_json,
       (
         SELECT json_object(
           'device_id', d.device_id,
           'tenant_id', d.tenant_id,
           'state', d.state,
           'tunnel_mode', d.tunnel_mode,
           'last_seen_at_utc', d.last_seen_at_utc,
           'revoked_at_utc', d.revoked_at_utc
         )
           FROM commander_device_selections s
           JOIN commander_devices d ON d.device_id = s.device_id
          WHERE s.tenant_id = u.tenant_id
            AND s.subject_id = u.subject_id
            AND d.tenant_id = s.tenant_id
            AND d.state = 'ACTIVE'
            AND d.revoked_at_utc IS NULL
          LIMIT 1
       ) AS selected_device_json
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
    return mcpTransientProductContext(env, normalizedIssuer, subject, null);
  }
  if (!row) return { ok: false, code: "IDENTITY_NOT_PROVISIONED" };

  let grants;
  let selectedDevice = null;
  try {
    grants = JSON.parse(String(row.grants_json || "[]"));
    if (row.selected_device_json) {
      selectedDevice = JSON.parse(String(row.selected_device_json));
    }
  } catch (_error) {
    return { ok: false, code: "PRODUCT_CONTEXT_INVALID" };
  }

  const context = finalizeMcpProductContext(
    row,
    normalizedIssuer,
    subject,
    grants,
  );
  if (!context.ok) return context;
  return {
    ...context,
    selected_device: selectedDevice,
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
    `SELECT d.device_id, d.tenant_id, d.state, d.tunnel_mode,
            d.last_seen_at_utc, d.revoked_at_utc
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

export async function resolveCustomerTargetDevice(env, context, requestedComputer = null, requestedDeviceId = null) {
  const explicitDeviceId = requestedDeviceId ? cleanId(requestedDeviceId, 180) : null;
  const explicitComputer = requestedComputer ? cleanDeviceName(requestedComputer) : null;
  const result = await env.PRODUCT_DB.prepare(
    `SELECT device_id, tenant_id, enrolled_by_subject_id, device_name, platform, architecture,
            agent_version, tunnel_mode, state, last_seen_at_utc, revoked_at_utc
       FROM commander_devices
      WHERE tenant_id = ?
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL
      ORDER BY created_at_utc DESC`
  ).bind(context.tenant_id).all();
  return chooseCustomerTargetDevice(result.results || [], {
    tenantId: context.tenant_id,
    requestedComputer: explicitComputer,
    requestedDeviceId: explicitDeviceId,
    isOnline: (device) => deviceOnline(device.last_seen_at_utc, device.tunnel_mode),
  });
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
            d.revoked_at_utc, d.approval_mode
       FROM commander_devices d
      WHERE d.tenant_id = ?
      ORDER BY d.created_at_utc DESC`
  ).bind(session.tenant_id).all();

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
    online: row.state === "ACTIVE" && deviceOnline(row.last_seen_at_utc, row.tunnel_mode, now),
    created_at_utc: row.created_at_utc,
    last_seen_at_utc: row.last_seen_at_utc,
    revoked_at_utc: row.revoked_at_utc,
    approval_mode: normalizeApprovalMode(row.approval_mode, "ASK_EVERY_ACTION"),
  }));
}

async function enrollDevice(env, body) {
  const pairingToken = cleanOpaque(body.pairing_token, 512);
  const tokenHash = await sha256(pairingToken);
  const deviceName = cleanDeviceName(body.device_name);
  const platform = normalizeDevicePlatform(body.platform);
  const architecture = cleanAgentValue(body.architecture, 80);
  const agentVersion = cleanAgentValue(body.agent_version, 80) || "0.1.0";
  const approvalMode = normalizeApprovalMode(body.approval_mode, "ASK_EVERY_ACTION");
  const deviceId = "HARA-DEVICE-" + crypto.randomUUID();
  const deviceSecret = randomToken(48);
  const credentialHash = await sha256(deviceSecret);
  const createdAt = nowIso();

  const insert = env.PRODUCT_DB.prepare(
    `INSERT INTO commander_devices
      (device_id, pairing_id, tenant_id, enrolled_by_subject_id, device_name, platform,
       architecture, agent_version, tunnel_mode, credential_hash, state,
       created_at_utc, last_seen_at_utc, revoked_at_utc, approval_mode)
     SELECT ?, pairing_id, tenant_id, subject_id, ?, ?, ?, ?, 'OUTBOUND_RELAY', ?,
            'ACTIVE', ?, ?, NULL, ?
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
    approvalMode,
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
    approval_mode: approvalMode,
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
            last_seen_at_utc, revoked_at_utc, approval_mode
       FROM commander_devices
      WHERE credential_hash = ?
      LIMIT 1`
  ).bind(credentialHash).first();

  if (!device || device.state !== "ACTIVE" || device.revoked_at_utc) {
    throw new Error("DEVICE_AUTH_INVALID");
  }
  return device;
}

function activitySnapshotNumber(value, max = 1_000_000_000) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return 0;
  return Math.min(max, Math.round(num * 10) / 10);
}

function cleanAgentActivityWindow(value, key) {
  if (!value || typeof value !== "object") return null;
  const summary = value.summary || {};
  const diagnostics = value.diagnostics || {};
  const topTools = Array.isArray(diagnostics.top_tools) ? diagnostics.top_tools.slice(0, 6) : [];
  const topErrors = Array.isArray(diagnostics.top_errors) ? diagnostics.top_errors.slice(0, 6) : [];
  const transports = Array.isArray(summary.transport_modes)
    ? summary.transport_modes.slice(0, 8).map((item) => cleanAgentValue(item, 80)).filter(Boolean)
    : [];
  const rawSlo = value.slo && typeof value.slo === "object" ? value.slo : {};
  const sloStatus = ["PASS","DEGRADED","INSUFFICIENT_DATA"].includes(String(rawSlo.status || ""))
    ? String(rawSlo.status)
    : "INSUFFICIENT_DATA";
  const slo = {
    profile:"INTERNAL_BETA_V1",
    status:sloStatus,
    evaluable:rawSlo.evaluable === true,
    targets:{
      min_success_rate_percent:activitySnapshotNumber(rawSlo.targets?.min_success_rate_percent ?? 99,100),
      p50_max_ms:activitySnapshotNumber(rawSlo.targets?.p50_max_ms ?? 1000),
      p95_max_ms:activitySnapshotNumber(rawSlo.targets?.p95_max_ms ?? 6000),
      p99_max_ms:activitySnapshotNumber(rawSlo.targets?.p99_max_ms ?? 12000),
      min_latency_samples:activitySnapshotNumber(rawSlo.targets?.min_latency_samples ?? 20,100000),
    },
    checks:{
      success_rate:typeof rawSlo.checks?.success_rate === "boolean" ? rawSlo.checks.success_rate : null,
      p50:typeof rawSlo.checks?.p50 === "boolean" ? rawSlo.checks.p50 : null,
      p95:typeof rawSlo.checks?.p95 === "boolean" ? rawSlo.checks.p95 : null,
      p99:typeof rawSlo.checks?.p99 === "boolean" ? rawSlo.checks.p99 : null,
    },
  };
  return {
    schema: "hara.commander-device-activity-window.v1",
    window_key: key,
    summary: {
      total_calls: activitySnapshotNumber(summary.total_calls),
      completed: activitySnapshotNumber(summary.completed),
      failed: activitySnapshotNumber(summary.failed),
      pending: activitySnapshotNumber(summary.pending),
      executing: activitySnapshotNumber(summary.executing),
      expired: activitySnapshotNumber(summary.expired),
      cancelled: activitySnapshotNumber(summary.cancelled),
      success_rate_percent: summary.success_rate_percent == null ? null : activitySnapshotNumber(summary.success_rate_percent, 100),
      under_3s_percent: summary.under_3s_percent == null ? null : activitySnapshotNumber(summary.under_3s_percent, 100),
      avg_queue_ms: summary.avg_queue_ms == null ? null : activitySnapshotNumber(summary.avg_queue_ms),
      avg_execution_ms: summary.avg_execution_ms == null ? null : activitySnapshotNumber(summary.avg_execution_ms),
      avg_total_ms: summary.avg_total_ms == null ? null : activitySnapshotNumber(summary.avg_total_ms),
      latency_p50_ms: summary.latency_p50_ms == null ? null : activitySnapshotNumber(summary.latency_p50_ms),
      latency_p95_ms: summary.latency_p95_ms == null ? null : activitySnapshotNumber(summary.latency_p95_ms),
      latency_p99_ms: summary.latency_p99_ms == null ? null : activitySnapshotNumber(summary.latency_p99_ms),
      latency_sample_size: activitySnapshotNumber(summary.latency_sample_size,100000),
      latency_population_size: activitySnapshotNumber(summary.latency_population_size,100000000),
      latency_sample_capped: summary.latency_sample_capped === true,
      transport_modes: [...new Set(transports)],
    },
    slo,
    diagnostics: {
      top_tools: topTools.map((row) => ({
        tool_id: cleanAgentValue(row?.tool_id, 120) || "unknown",
        calls: activitySnapshotNumber(row?.calls),
      })),
      top_errors: topErrors.map((row) => ({
        error_code: cleanAgentValue(row?.error_code, 120) || "UNKNOWN",
        calls: activitySnapshotNumber(row?.calls),
      })),
    },
  };
}

function cleanAgentActivitySnapshots(value) {
  if (!value || typeof value !== "object") return null;
  if (value.schema !== "hara.commander-local-activity-snapshots.v1") return null;
  const windows = {};
  for (const key of ["24h", "7d", "30d"]) {
    const cleaned = cleanAgentActivityWindow(value.windows?.[key], key);
    if (cleaned) windows[key] = cleaned;
  }
  if (!Object.keys(windows).length) return null;
  const raw = JSON.stringify({
    schema: "hara.commander-device-activity-snapshots.v1",
    windows,
    detail_location: "LOCAL_DEVICE",
    customer_content_synced: false,
  });
  return raw.length <= 32 * 1024 ? raw : null;
}

async function heartbeatDevice(env, request, body) {
  const device = await resolveDeviceCredential(env, request);
  const requestedId = body.device_id ? cleanId(body.device_id, 180) : device.device_id;
  if (requestedId !== device.device_id) throw new Error("DEVICE_ID_MISMATCH");

  const agentVersion = cleanAgentValue(body.agent_version, 80) || device.agent_version;
  const architecture = cleanAgentValue(body.architecture, 80) || device.architecture;
  const approvalMode = normalizeApprovalMode(body.approval_mode, normalizeApprovalMode(device.approval_mode, "ASK_EVERY_ACTION"));
  const activitySummaryJson = cleanAgentActivitySnapshots(body.activity_snapshots);
  const seenAt = nowIso();

  const heartbeat = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?,
            agent_version = ?,
            architecture = ?,
            approval_mode = ?,
            tunnel_mode = 'OUTBOUND_RELAY',
            activity_summary_json = CASE WHEN ? IS NULL THEN activity_summary_json ELSE ? END,
            activity_summary_at_utc = CASE WHEN ? IS NULL THEN activity_summary_at_utc ELSE ? END
      WHERE device_id = ? AND state = 'ACTIVE' AND revoked_at_utc IS NULL`
  ).bind(
    seenAt, agentVersion, architecture, approvalMode,
    activitySummaryJson, activitySummaryJson,
    activitySummaryJson, seenAt,
    device.device_id
  ).run();
  if (!heartbeat.meta?.changes) throw new Error("DEVICE_AUTH_INVALID");

  return {
    schema: "hara.commander-device-heartbeat.v1",
    ok: true,
    device_id: device.device_id,
    state: "ACTIVE",
    server_time_utc: seenAt,
    heartbeat_after_seconds: 30,
    local_activity_snapshot_accepted: Boolean(activitySummaryJson),
  };
}

async function markDeviceOffline(env, request, body) {
  const device = await resolveDeviceCredential(env, request);
  const requestedId = body.device_id ? cleanId(body.device_id, 180) : device.device_id;
  if (requestedId !== device.device_id) throw new Error("DEVICE_ID_MISMATCH");
  const seenAt = nowIso();
  const agentVersion = cleanAgentValue(body.agent_version, 80) || device.agent_version;
  const architecture = cleanAgentValue(body.architecture, 80) || device.architecture;
  const approvalMode = normalizeApprovalMode(body.approval_mode, normalizeApprovalMode(device.approval_mode, "ASK_EVERY_ACTION"));
  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?,
            agent_version = ?,
            architecture = ?,
            approval_mode = ?,
            tunnel_mode = 'OUTBOUND_RELAY_OFFLINE'
      WHERE device_id = ? AND state = 'ACTIVE' AND revoked_at_utc IS NULL`
  ).bind(seenAt, agentVersion, architecture, approvalMode, device.device_id).run();
  if (!result.meta?.changes) throw new Error("DEVICE_AUTH_INVALID");
  return {
    schema: "hara.commander-device-offline.v1",
    ok: true,
    device_id: device.device_id,
    state: "OFFLINE",
    server_time_utc: seenAt,
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

function isRedactedDeviceCallContent(value) {
  return typeof value === "string" && value.startsWith(DEVICE_CALL_REDACTED_PREFIX);
}

async function redactedDeviceCallContent(value) {
  if (value == null || isRedactedDeviceCallContent(value)) return value;
  return DEVICE_CALL_REDACTED_PREFIX + await sha256(String(value));
}

async function deviceCallStoredContentMatches(storedValue, candidateValue) {
  if (storedValue === candidateValue) return true;
  if (!isRedactedDeviceCallContent(storedValue)) return false;
  return storedValue === await redactedDeviceCallContent(candidateValue);
}

async function redactExpiredDeviceCallContent(env, cutoff) {
  let redacted = 0;
  for (
    let batch = 0;
    batch < DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES;
    batch += 1
  ) {
    const result = await env.PRODUCT_DB.prepare(
      `SELECT call_id, payload_json, result_json
         FROM commander_device_calls INDEXED BY idx_device_calls_expiry
        WHERE state IN ('COMPLETED','FAILED','CANCELLED','EXPIRED')
          AND expires_at_utc <= ?
          AND (
            payload_json NOT LIKE ?
            OR (result_json IS NOT NULL AND result_json NOT LIKE ?)
          )
        ORDER BY expires_at_utc ASC
        LIMIT ?`
    ).bind(
      cutoff,
      DEVICE_CALL_REDACTED_PREFIX + "%",
      DEVICE_CALL_REDACTED_PREFIX + "%",
      DEVICE_CALL_CONTENT_REDACTION_BATCH,
    ).all();

    const rows = result.results || [];
    if (rows.length < 1) break;

    const updates = [];
    for (const row of rows) {
      const payloadMarker = await redactedDeviceCallContent(row.payload_json);
      const resultMarker = row.result_json == null
        ? null
        : await redactedDeviceCallContent(row.result_json);
      updates.push(
        env.PRODUCT_DB.prepare(
          `UPDATE commander_device_calls
              SET payload_json = ?, result_json = ?
            WHERE call_id = ?
              AND state IN ('COMPLETED','FAILED','CANCELLED','EXPIRED')
              AND expires_at_utc <= ?`
        ).bind(payloadMarker, resultMarker, row.call_id, cutoff)
      );
    }
    await env.PRODUCT_DB.batch(updates);
    redacted += updates.length;
    if (rows.length < DEVICE_CALL_CONTENT_REDACTION_BATCH) break;
  }
  return { redacted };
}

async function cleanupExpiredDeviceCalls(env) {
  const expiredAt = nowIso();
  const expiry = await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_calls
        SET state = 'EXPIRED', completed_at_utc = ?, error_code = 'DEVICE_CALL_EXPIRED'
      WHERE call_id IN (
        SELECT call_id
          FROM commander_device_calls INDEXED BY idx_device_calls_expiry
         WHERE state IN ('PENDING','EXECUTING')
           AND expires_at_utc <= ?
         ORDER BY expires_at_utc ASC
         LIMIT ?
      )`
  ).bind(expiredAt, expiredAt, DEVICE_CALL_EXPIRY_MAINTENANCE_BATCH).run();
  const redaction = await redactExpiredDeviceCallContent(env, expiredAt);
  return {
    expired: Number(expiry.meta?.changes || 0),
    redacted: Number(redaction.redacted || 0),
  };
}

async function enqueueDeviceCall(env, body) {
  const requestId = cleanId(body.request_id, 220);
  const toolId = cleanId(body.tool_id, 120);
  const requiredGrant = MCP_TOOL_GRANTS[toolId];
  if (!requiredGrant) throw new Error("DEVICE_CALL_TOOL_DENIED");

  const context = await mcpProductContext(env, body.issuer, body.subject, mcpBootstrapHints(body));
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
    `SELECT call_id, tenant_id, subject_id, device_id, tool_id, payload_json, state, expires_at_utc,
            usage_mode, usage_units, usage_period_key, usage_budget_id
       FROM commander_device_calls WHERE request_id = ? LIMIT 1`
  ).bind(requestId).first();
  const existingResponse = async (existing) => {
    const payloadMatches = await deviceCallStoredContentMatches(
      existing.payload_json,
      payloadJson,
    );
    if (
      existing.tenant_id !== context.tenant_id
      || existing.subject_id !== context.subject_id
      || existing.tool_id !== toolId
      || !payloadMatches
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
      retry_after_ms: deviceCallRetryAfterMs(existing.state, "enqueue"),
      usage_mode: existing.usage_mode || "CLOUD_QUOTA",
      usage_units: Number(existing.usage_units || 0),
      usage_period_key: existing.usage_period_key || null,
      usage_budget_id: existing.usage_budget_id || null,
    };
  };

  const existing = await readExisting();
  if (existing) return await existingResponse(existing);

  const device = await resolveCustomerTargetDevice(
    env, context, body.computer || null, requestedDeviceId
  );
  const deviceId = cleanId(device.device_id, 180);
  if (!deviceOnline(device.last_seen_at_utc, device.tunnel_mode)) throw new Error("DEVICE_OFFLINE");

  const usageFunctionId = quotaFunctionIdForTool(toolId, canonicalPayload);
  const usageMode = await resolveCallUsageMode(env, context, device, usageFunctionId);
  const usageUnits = usageFunctionId ? 1 : 0;
  const usagePeriodKey = usageUnits ? mcpPeriodKey(context) : null;
  const enqueueAt = nowIso();

  const callId = "HARA-CALL-" + crypto.randomUUID();
  const createdAt = nowIso();
  const expiresAt = nowIso(DEVICE_CALL_TTL_SECONDS);
  const onlineCutoff = new Date(Date.now() - 90_000).toISOString();
  const eventV2Cutoff = new Date(Date.now() - 7 * 60 * 60 * 1000).toISOString();
  const inserted = await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO commander_device_calls
      (call_id, request_id, tenant_id, subject_id, device_id, tool_id, payload_json,
       state, created_at_utc, expires_at_utc, claimed_at_utc, completed_at_utc,
       result_json, error_code, usage_mode, usage_units, usage_period_key, usage_budget_id)
     SELECT ?, ?, ?, ?, d.device_id, ?, ?, 'PENDING', ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?,
            CASE WHEN ? = 'LOCAL_BUDGET' THEN (
              SELECT b.budget_id
                FROM commander_device_budget_blocks b
               WHERE b.tenant_id = d.tenant_id
                 AND b.device_id = d.device_id
                 AND b.period_key = ?
                 AND b.state = 'ACTIVE'
                 AND b.expires_at_utc > ?
                 AND b.units_issued + ? <= b.units_allocated
               ORDER BY b.allocation_sequence ASC
               LIMIT 1
            ) ELSE NULL END
       FROM commander_devices d
      WHERE d.device_id = ?
        AND d.tenant_id = ?
        AND d.state = 'ACTIVE'
        AND d.revoked_at_utc IS NULL
        AND (
          (d.tunnel_mode = 'EVENT_V2' AND d.last_seen_at_utc >= ?)
          OR
          (d.tunnel_mode NOT IN ('EVENT_V2','EVENT_V2_OFFLINE','OUTBOUND_RELAY_OFFLINE') AND d.last_seen_at_utc >= ?)
        )
        AND (
          SELECT COUNT(*)
            FROM commander_device_calls q INDEXED BY idx_device_calls_poll
           WHERE q.device_id = d.device_id
             AND q.tenant_id = d.tenant_id
             AND q.state IN ('PENDING','EXECUTING')
             AND q.expires_at_utc > ?
        ) < ?
        AND (
          ? <> 'LOCAL_BUDGET'
          OR EXISTS (
            SELECT 1
              FROM commander_device_budget_blocks b
             WHERE b.tenant_id = d.tenant_id
               AND b.device_id = d.device_id
               AND b.period_key = ?
               AND b.state = 'ACTIVE'
               AND b.expires_at_utc > ?
               AND b.units_issued + ? <= b.units_allocated
          )
        )`
  ).bind(
    callId, requestId, context.tenant_id, context.subject_id, toolId, payloadJson,
    createdAt, expiresAt, usageMode, usageUnits, usagePeriodKey,
    usageMode, usagePeriodKey, createdAt, usageUnits,
    deviceId, context.tenant_id, eventV2Cutoff, onlineCutoff,
    createdAt, DEVICE_CALL_ACTIVE_QUEUE_LIMIT,
    usageMode, usagePeriodKey, createdAt, usageUnits
  ).run();

  if (!inserted.meta?.changes) {
    const concurrent = await readExisting();
    if (concurrent) return await existingResponse(concurrent);

    const currentDevice = await resolveCustomerTargetDevice(
      env, context, null, deviceId
    );
    if (!deviceOnline(currentDevice.last_seen_at_utc, currentDevice.tunnel_mode)) {
      throw new Error("DEVICE_OFFLINE");
    }

    if (usageMode === "LOCAL_BUDGET") {
      const block = await env.PRODUCT_DB.prepare(
        `SELECT budget_id,units_allocated,units_issued
           FROM commander_device_budget_blocks
          WHERE tenant_id = ?
            AND device_id = ?
            AND period_key = ?
            AND state = 'ACTIVE'
            AND expires_at_utc > ?
          ORDER BY allocation_sequence ASC
          LIMIT 1`
      ).bind(context.tenant_id, deviceId, usagePeriodKey, nowIso()).first();
      if (!block || Number(block.units_issued || 0) + usageUnits > Number(block.units_allocated || 0)) {
        throw new Error("LOCAL_BUDGET_CAPACITY_EXHAUSTED");
      }
    }

    const activeQueue = await env.PRODUCT_DB.prepare(
      `SELECT COUNT(*) AS active_count
         FROM commander_device_calls INDEXED BY idx_device_calls_poll
        WHERE device_id = ?
          AND tenant_id = ?
          AND state IN ('PENDING','EXECUTING')
          AND expires_at_utc > ?`
    ).bind(deviceId, context.tenant_id, nowIso()).first();
    if (Number(activeQueue?.active_count || 0) >= DEVICE_CALL_ACTIVE_QUEUE_LIMIT) {
      throw new Error("DEVICE_BUSY");
    }

    throw new Error("DEVICE_CALL_ENQUEUE_CONFLICT");
  }

  const useEventV2 = String(device.tunnel_mode || "") === "EVENT_V2";
  const notification = useEventV2
    ? await notifyDeviceEventChannel(
        env,
        context.tenant_id,
        deviceId,
        callId,
      )
    : { attempted: false, delivered: 0 };
  if (
    useEventV2
    && eventV2Enabled(env)
    && notification.attempted
    && notification.delivered < 1
  ) {
    const cancelledAt = nowIso();
    await env.PRODUCT_DB.prepare(
      `UPDATE commander_device_calls
          SET state = 'CANCELLED',
              completed_at_utc = ?,
              error_code = 'DEVICE_EVENT_UNDELIVERED'
        WHERE call_id = ?
          AND tenant_id = ?
          AND device_id = ?
          AND state = 'PENDING'`
    ).bind(
      cancelledAt,
      callId,
      context.tenant_id,
      deviceId,
    ).run();
    throw new Error("DEVICE_OFFLINE");
  }

  let postNotify = null;
  if (
    eventV2Enabled(env)
    && notification.attempted
    && notification.delivered >= 1
  ) {
    await scheduler.wait(EVENT_V2_TERMINAL_FAST_PATH_WAIT_MS);
    postNotify = await env.PRODUCT_DB.prepare(
      `SELECT state, claimed_at_utc, completed_at_utc, result_json, error_code
         FROM commander_device_calls
        WHERE call_id = ?
          AND tenant_id = ?
          AND subject_id = ?
        LIMIT 1`
    ).bind(callId, context.tenant_id, context.subject_id).first();
  }

  const responseState = String(postNotify?.state || "PENDING");
  const response = {
    schema: "hara.commander-device-call.v1",
    existing: false,
    call_id: callId,
    request_id: requestId,
    device_id: deviceId,
    tool_id: toolId,
    state: responseState,
    expires_at_utc: expiresAt,
    retry_after_ms: deviceCallRetryAfterMs(responseState, "enqueue"),
    usage_mode: usageMode,
    usage_units: usageUnits,
    usage_period_key: usagePeriodKey,
    usage_budget_id: usageMode === "LOCAL_BUDGET"
      ? await env.PRODUCT_DB.prepare(
          `SELECT usage_budget_id FROM commander_device_calls WHERE call_id = ? LIMIT 1`
        ).bind(callId).first().then((row) => row?.usage_budget_id || null)
      : null,
  };

  if (postNotify) {
    response.claimed_at_utc = postNotify.claimed_at_utc || null;
    response.completed_at_utc = postNotify.completed_at_utc || null;
    response.result = postNotify.result_json ? JSON.parse(postNotify.result_json) : null;
    response.error_code = postNotify.error_code || null;
  }

  return response;
}

async function customerMcpRequestId(identity, toolId, args, mcpRequestId, transportRequestId) {
  const digest = await sha256(JSON.stringify({
    issuer: identity.issuer,
    subject: identity.subject,
    client_id: identity.client_id,
    tool_id: toolId,
    mcp_request_id: mcpRequestId,
    transport_request_id: String(transportRequestId || ""),
    arguments: args || {},
  }));
  return "HARA-CUSTOMER-MCP-" + digest;
}

function trimPublicText(value, limit = 65536) {
  if (typeof value !== "string") return null;
  return value.length <= limit
    ? value
    : value.slice(0, limit) + "\n[HARA_COMMANDER_OUTPUT_TRUNCATED]";
}

function projectCustomerToolResult(toolId, response) {
  const value = response && typeof response === "object" ? response : {};
  const result = value.result && typeof value.result === "object" ? value.result : {};
  const projectedResult = {};

  if (toolId === "hara.health") {
    for (const key of [
      "registered_function_count",
      "executable_function_count",
    ]) {
      if (key in result) projectedResult[key] = result[key];
    }
    if (result.device && typeof result.device === "object") {
      const device = {};
      for (const key of [
        "device_id",
        "hostname",
        "platform",
        "platform_release",
        "architecture",
        "python_version",
        "agent_version",
        "tunnel_mode",
      ]) {
        if (typeof result.device[key] === "string") device[key] = result.device[key];
      }
      if (Object.keys(device).length) projectedResult.device = device;
    }
  } else if (toolId === "hara.functions.list") {
    for (const key of [
      "registered_function_count",
      "executable_function_count",
      "active_function_count",
    ]) {
      if (Number.isInteger(result[key])) projectedResult[key] = result[key];
    }
    if (Array.isArray(result.domains)) {
      projectedResult.domains = result.domains.filter((entry) => typeof entry === "string");
    }
    if (Array.isArray(result.functions)) {
      projectedResult.functions = result.functions
        .filter((entry) => entry && typeof entry.function_id === "string")
        .map((entry) => ({
          function_id: entry.function_id,
          ...(typeof entry.state === "string" ? { state: entry.state } : {}),
        }));
    }
  } else if (toolId === "hara.functions.describe") {
    for (const key of ["function_id", "state", "pending_domain_binding"]) {
      if (key in result) projectedResult[key] = result[key];
    }
    if (typeof result.IDENTITY?.domain === "string") {
      projectedResult.domain = result.IDENTITY.domain;
    }
    if (typeof result.PURPOSE?.description_pt_br === "string") {
      projectedResult.description = result.PURPOSE.description_pt_br;
    }
    const execution = result.EXECUTION_SEMANTICS;
    const authority = result.AUTHORITY;
    const risk = execution?.risk_class ?? authority?.risk_class;
    const changeIntent = execution?.change_intent_required
      ?? authority?.change_intent_required;
    const failClosed = authority?.fail_closed ?? result.FAILURE_ROLLBACK?.fail_closed;
    if (typeof risk === "string") projectedResult.risk_class = risk;
    if (typeof changeIntent === "boolean") {
      projectedResult.change_intent_required = changeIntent;
    }
    if (typeof failClosed === "boolean") projectedResult.fail_closed = failClosed;
  } else if (toolId === "hara.functions.invoke" || deviceFunctionForTool(toolId) || isDeviceMutationTool(toolId) || isDeviceProcessTool(toolId) || toolId === "hara.files.preimages.list") {
    for (const key of [
      "function_id",
      "risk_class",
      "process_exit_code",
      "domain_success_inferred",
    ]) {
      if (key in result) projectedResult[key] = result[key];
    }
    const stdout = trimPublicText(result.stdout);
    const stderr = trimPublicText(result.stderr);
    if (stdout !== null) projectedResult.stdout = stdout;
    if (stderr) projectedResult.stderr = stderr;
    for (const key of ["human_approval_state","local_authorization_mode","authorization_source","preimage_sha256","preimage_id","rollback_preimage_id"]) {
      if (typeof result[key] === "string") projectedResult[key] = result[key];
    }
  } else if (toolId === "hara.receipts.get") {
    for (const key of [
      "tool_id",
      "function_id_if_any",
      "transport_mode",
      "operational_authority",
      "execution_authority",
      "mutation_class",
      "state",
      "payload_values_persisted",
      "human_approval_required",
      "human_approval_state",
      "local_authorization_mode",
      "authorization_source",
      "preimage_sha256",
      "preimage_id",
      "rollback_preimage_id",
    ]) {
      if (key in result) projectedResult[key] = result[key];
    }
  }

  const projected = {
    state: value.state || null,
    operational_authority: value.operational_authority || null,
    execution_authority: "HARA_COMMANDER_AGENT",
    runtime_authority_from_chatgpt: value.runtime_authority_from_chatgpt === true,
    mutation_performed: value.mutation_performed === true,
    result: projectedResult,
    customer_services_relay: false,
  };

  const receiptSha = String(value.bridge_receipt_sha256 || "").trim().toLowerCase();
  if (/^[0-9a-f]{64}$/.test(receiptSha)) {
    projected.bridge_receipt_sha256 = receiptSha;
  }
  if (value.blocker && typeof value.blocker === "object") {
    const blocker = {};
    if (typeof value.blocker.code === "string") blocker.code = value.blocker.code;
    if (typeof value.blocker.details?.risk_class === "string") {
      blocker.details = { risk_class: value.blocker.details.risk_class };
    }
    if (Object.keys(blocker).length) projected.blocker = blocker;
  }
  return projected;
}

function customerMcpDevicePayload(toolId, args) {
  if (["hara.health","hara.ping","hara.device.info","hara.system.uptime","hara.system.resources","hara.functions.list"].includes(toolId)) return {};
  if (toolId === "hara.workspace.inspect") {
    return {path:String(args.path || ""),...(args.max_entries === undefined ? {} : {max_entries:Number(args.max_entries)})};
  }
  if (toolId === "hara.processes.list") {
    return args.limit === undefined ? {} : { limit: Number(args.limit) };
  }
  if (toolId === "hara.files.info") return { path: String(args.path || "") };
  if (toolId === "hara.files.hash") return {path:String(args.path || "")};
  if (toolId === "hara.files.diff") return {left:String(args.left || ""),right:String(args.right || ""),max_lines:args.max_lines===undefined ? 200 : Number(args.max_lines)};
  if (toolId === "hara.files.search") {
    return {
      path:String(args.path || ""), search_type:String(args.search_type || ""), pattern:String(args.pattern || ""),
      max_results:args.max_results === undefined ? 50 : Number(args.max_results),
      include_hidden:args.include_hidden === true, ignore_case:args.ignore_case !== false,
      ...(args.file_glob === undefined ? {} : {file_glob:String(args.file_glob)}),
    };
  }
  if (toolId === "hara.files.list") {
    return {
      path:String(args.path || ""),
      ...(args.limit === undefined ? {} : {limit:Number(args.limit)}),
      ...(args.depth === undefined ? {} : {depth:Number(args.depth)}),
    };
  }
  if (toolId === "hara.files.read") {
    return {
      path: String(args.path || ""),
      ...(args.offset === undefined ? {} : {offset:Number(args.offset)}),
      ...(args.length === undefined ? {} : {length:Number(args.length)}),
    };
  }
  if (toolId === "hara.files.read_many") {
    return {
      paths:Array.isArray(args.paths) ? args.paths.map((v)=>String(v)) : [],
      offset:args.offset === undefined ? 0 : Number(args.offset),
      length:args.length === undefined ? 100 : Number(args.length),
    };
  }
  if (toolId === "hara.files.preimages.list") return {limit:args.limit === undefined ? 50 : Number(args.limit),...(args.path === undefined ? {} : {path:String(args.path)})};
  if (toolId === "hara.files.rollback") return {preimage_id:String(args.preimage_id || "")};
  if (toolId === "hara.process.sessions") return {};
  if (toolId === "hara.process.run") return {command:String(args.command ?? ""),...(args.cwd === undefined ? {} : {cwd:String(args.cwd)}),timeout_ms:args.timeout_ms === undefined ? 3000 : Number(args.timeout_ms),max_lines:args.max_lines === undefined ? 200 : Number(args.max_lines)};
  if (toolId === "hara.process.start") return {command:String(args.command ?? ""),...(args.cwd === undefined ? {} : {cwd:String(args.cwd)}),timeout_ms:args.timeout_ms === undefined ? 1000 : Number(args.timeout_ms)};
  if (toolId === "hara.process.output") return {session_id:String(args.session_id || ""),...(args.offset === undefined ? {} : {offset:Number(args.offset)}),length:args.length === undefined ? 200 : Number(args.length),timeout_ms:args.timeout_ms === undefined ? 500 : Number(args.timeout_ms)};
  if (toolId === "hara.process.interact") return {session_id:String(args.session_id || ""),input:String(args.input ?? ""),timeout_ms:args.timeout_ms === undefined ? 1000 : Number(args.timeout_ms)};
  if (toolId === "hara.process.kill") return {session_id:String(args.session_id || ""),force:args.force === true};
  if (toolId === "hara.files.create_directory") return {path:String(args.path || ""),parents:args.parents !== false};
  if (toolId === "hara.files.write") return {path:String(args.path || ""),content:String(args.content ?? ""),mode:String(args.mode || "rewrite")};
  if (toolId === "hara.files.edit") return {path:String(args.path || ""),old_text:String(args.old_text ?? ""),new_text:String(args.new_text ?? ""),replace_all:args.replace_all === true};
  if (toolId === "hara.files.move") return {source:String(args.source || ""),destination:String(args.destination || "")};
  if (toolId === "hara.files.copy") return {source:String(args.source || ""),destination:String(args.destination || "")};
  if (toolId === "hara.files.delete") return {path:String(args.path || "")};
  if (toolId === "hara.functions.describe") return { function_id: cleanId(args.function_id, 180) };
  if (toolId === "hara.functions.invoke") {
    return {
      function_id: cleanId(args.function_id, 180),
      arguments: { argv: Array.isArray(args.argv) ? args.argv.map((value) => String(value)) : [] },
    };
  }
  if (toolId === "hara.receipts.get") return { receipt_id_or_sha256: cleanId(args.receipt_id_or_sha256, 256) };
  throw new Error("DEVICE_CALL_TOOL_DENIED");
}

function quotaFunctionIdForTool(toolId, payload) {
  if (toolId === "hara.functions.invoke") return cleanId(payload.function_id, 180);
  if (["hara.ping","hara.health","hara.functions.list","hara.functions.describe","hara.receipts.get"].includes(toolId)) return null;
  const functionId=deviceFunctionForTool(toolId);
  if (functionId) return functionId;
  if (isDeviceMutationTool(toolId) || isDeviceProcessTool(toolId) || toolId === "hara.files.preimages.list") return "tool:"+toolId;
  return null;
}

function legacyInvokePayload(toolId, payload) {
  const functionId = deviceFunctionForTool(toolId);
  if (!functionId) return null;
  if (["device.info","device.ping","system.uptime","system.resources"].includes(functionId)) return {function_id:functionId,arguments:{argv:[]}};
  if (functionId === "workspace.inspect") return {function_id:functionId,arguments:{argv:[payload.path,...(payload.max_entries === undefined ? [] : [String(payload.max_entries)])]}};
  if (functionId === "process.list") return {function_id:functionId,arguments:{argv:payload.limit === undefined ? [] : [String(payload.limit)]}};
  if (functionId === "filesystem.info") return {function_id:functionId,arguments:{argv:[payload.path]}};
  if (functionId === "filesystem.hash") return {function_id:functionId,arguments:{argv:[payload.path]}};
  if (functionId === "filesystem.diff") return {function_id:functionId,arguments:{argv:[payload.left,payload.right,String(payload.max_lines ?? 200)]}};
  if (functionId === "filesystem.search") return {function_id:functionId,arguments:{argv:[
    payload.path, payload.search_type, payload.pattern, String(payload.max_results ?? 50),
    payload.include_hidden ? "1" : "0", payload.ignore_case === false ? "0" : "1", payload.file_glob ?? "",
  ]}};
  if (functionId === "filesystem.list") {
    const argv=[payload.path];
    if (payload.limit !== undefined || payload.depth !== undefined) argv.push(String(payload.limit ?? 100));
    if (payload.depth !== undefined) argv.push(String(payload.depth));
    return {function_id:functionId,arguments:{argv}};
  }
  if (functionId === "filesystem.read_many") return {function_id:functionId,arguments:{argv:[String(payload.offset ?? 0),String(payload.length ?? 100),...(payload.paths||[])]}};
  if (functionId === "filesystem.read") {
    const argv=[payload.path];
    if (payload.offset !== undefined || payload.length !== undefined) argv.push(String(payload.offset ?? 0));
    if (payload.length !== undefined) argv.push(String(payload.length));
    return {function_id:functionId,arguments:{argv}};
  }
  return null;
}

function agentPurposeToolReady(device, toolId) {
  const platform=String(device?.platform || "").toUpperCase();
  if (platform === "WINDOWS") {
    const starter=[
      "hara.ping","hara.device.info","hara.processes.list",
      "hara.files.info","hara.files.list","hara.files.read",
      "hara.files.create_directory","hara.files.write","hara.process.run",
    ];
    return starter.includes(toolId) && semverAtLeast(device.agent_version,32);
  }
  if (platform !== "LINUX") return false;
  const parts=String(device?.agent_version || "0.0.0").split(".").map((v)=>Number(v));
  const [a=0,b=0,c=0]=parts;
  const minPatch =
    toolId === "hara.process.run" ? 25
    : ["hara.system.resources","hara.workspace.inspect"].includes(toolId) ? 24
    : ["hara.files.hash","hara.files.diff","hara.files.copy","hara.files.delete"].includes(toolId) ? 23
    : ["hara.files.preimages.list","hara.files.rollback"].includes(toolId) ? 21
    : isDeviceProcessTool(toolId) ? 20
    : isDeviceMutationTool(toolId) ? 19
    : toolId === "hara.files.read_many" ? 18
    : toolId === "hara.files.search" ? 17
    : 16;
  return a > 0 || b > 3 || (b === 3 && c >= minPatch);
}

async function customerMcpWaitForCall(env, identity, call) {
  let status = call;
  const deadline = Date.now() + 45_000;
  while (!["COMPLETED", "FAILED", "EXPIRED", "CANCELLED"].includes(String(status.state))) {
    if (Date.now() >= deadline) {
      throw new Error("DEVICE_CALL_TIMEOUT");
    }
    const retryMs = Math.max(
      100,
      Math.min(500, Number(status.retry_after_ms || 250)),
    );
    if (globalThis.scheduler?.wait) {
      await globalThis.scheduler.wait(retryMs);
    } else {
      await new Promise((resolve) => setTimeout(resolve, retryMs));
    }
    status = await deviceCallStatus(env, {
      issuer: identity.issuer,
      subject: identity.subject,
      call_id: call.call_id,
    });
  }
  return status;
}

function semverAtLeast(version, wantedPatch) {
  const parts=String(version || "0.0.0").split(".").map((v)=>Number(v));
  const [major=0,minor=0,patch=0]=parts;
  return major > 0 || minor > 3 || (minor === 3 && patch >= wantedPatch);
}

function capabilityToolDetail(toolId, approvalMode = "ASK_EVERY_ACTION") {
  const id=String(toolId || "");
  const processExecution=isDeviceProcessMutationTool(id);
  const filesystemMutation=isDeviceMutationTool(id);
  const mutable=processExecution || filesystemMutation;
  const mode=normalizeApprovalMode(approvalMode, "ASK_EVERY_ACTION");
  return {
    tool_id:id,
    risk_class:processExecution ? "PROCESS_EXECUTION" : (filesystemMutation ? "FILESYSTEM_MUTATION" : "READ_ONLY"),
    local_approval_required:mutable && mode === "ASK_EVERY_ACTION",
    local_session_authorization_sufficient:mutable && mode === "SESSION_TRUSTED",
    persistent_device_authorization_sufficient:mutable && mode === "PERSISTENT_TRUSTED",
    required_grant:MCP_TOOL_GRANTS[id] || null,
    preferred_interface:id !== "hara.functions.invoke",
  };
}

function capabilitiesForDevice(device, grants) {
  const platform=String(device.platform || "").toUpperCase();
  const linux=platform === "LINUX";
  const tools=["hara.health","hara.functions.list","hara.functions.describe","hara.receipts.get"];
  if (platform === "WINDOWS") {
    tools.push("hara.device.info","hara.functions.invoke");
    if (semverAtLeast(device.agent_version,32)) {
      tools.push("hara.ping","hara.processes.list","hara.files.info","hara.files.list","hara.files.read");
      if (grants.includes("COMMANDER_MUTATION_INVOKE")) {
        tools.push("hara.files.create_directory","hara.files.write");
      }
      if (grants.includes("COMMANDER_PROCESS_EXECUTION")) {
        tools.push("hara.process.run");
      }
    }
  }
  if (linux && semverAtLeast(device.agent_version,16)) {
    tools.push("hara.ping","hara.device.info","hara.system.uptime","hara.processes.list","hara.files.info","hara.files.list","hara.files.read");
  }
  if (linux && semverAtLeast(device.agent_version,17)) tools.push("hara.files.search");
  if (linux && semverAtLeast(device.agent_version,18)) tools.push("hara.files.read_many");
  if (linux && semverAtLeast(device.agent_version,19) && grants.includes("COMMANDER_MUTATION_INVOKE")) {
    tools.push("hara.files.create_directory","hara.files.write","hara.files.edit","hara.files.move");
  }
  if (linux && semverAtLeast(device.agent_version,20) && grants.includes("COMMANDER_PROCESS_EXECUTION")) {
    tools.push("hara.process.sessions","hara.process.start","hara.process.output","hara.process.interact","hara.process.kill");
  }
  if (linux && semverAtLeast(device.agent_version,21)) {
    tools.push("hara.files.preimages.list");
    if (grants.includes("COMMANDER_MUTATION_INVOKE")) tools.push("hara.files.rollback");
  }
  if (linux && semverAtLeast(device.agent_version,23)) {
    tools.push("hara.files.hash","hara.files.diff");
    if (grants.includes("COMMANDER_MUTATION_INVOKE")) tools.push("hara.files.copy","hara.files.delete");
  }
  if (linux && semverAtLeast(device.agent_version,24)) {
    tools.push("hara.system.resources","hara.workspace.inspect");
  }
  if (linux && semverAtLeast(device.agent_version,25) && grants.includes("COMMANDER_PROCESS_EXECUTION")) {
    tools.push("hara.process.run");
  }
  const availableTools=[...new Set(tools)].sort();
  const approvalMode=normalizeApprovalMode(device.approval_mode, "ASK_EVERY_ACTION");
  return {
    computer:device.device_name,
    device_id:device.device_id,
    platform:device.platform,
    architecture:device.architecture,
    agent_version:device.agent_version,
    state:device.revoked_at_utc ? "REVOKED" : (device.online ? "ONLINE" : "OFFLINE"),
    tools:availableTools,
    tool_details:availableTools.map((toolId)=>capabilityToolDetail(toolId,approvalMode)),
    capability_detail_schema:"hara.commander-capability-tool.v2",
    approval_mode:approvalMode,
    operator_session_required:approvalMode !== "PERSISTENT_TRUSTED",
    mutation_requires_local_approval:approvalMode === "ASK_EVERY_ACTION",
    process_execution_requires_local_approval:approvalMode === "ASK_EVERY_ACTION",
    local_session_authorizes_governed_mutations:approvalMode === "SESSION_TRUSTED",
    persistent_device_authorizes_governed_mutations:approvalMode === "PERSISTENT_TRUSTED",
    process_sessions_revoked_with_operator_session:true,
    payload_hot_path_redaction:true,
    receipt_binding:true,
  };
}

function resolveNamedCustomerDevice(devices, computer) {
  const wanted=String(computer || "").trim().toLowerCase();
  const matches=devices.filter((d)=>String(d.device_name||"").toLowerCase()===wanted);
  if (!matches.length) throw new Error("DEVICE_NOT_FOUND");

  const active=matches.filter((d)=>!d.revoked_at_utc);
  if (active.length===1) return active[0];
  if (active.length>1) {
    const online=active.filter((d)=>d.online);
    if (online.length===1) return online[0];
    throw new Error("COMPUTER_NAME_AMBIGUOUS");
  }

  if (matches.length===1) return matches[0];
  throw new Error("COMPUTER_NAME_AMBIGUOUS");
}

async function customerCapabilities(env, context, args) {
  let devices=await listDevices(env,{tenant_id:context.tenant_id});
  if (args?.computer) {
    devices=[resolveNamedCustomerDevice(devices,args.computer)];
  }
  return devices.map((d)=>capabilitiesForDevice(d,context.grants));
}

async function customerUsage(env, context) {
  const usage=await productUsageForPolicy(
    env,
    context.tenant_id,
    context.period_kind,
    context.unit_limit,
    context.meter_id,
  );
  return {
    plan_code:context.plan_code,
    plan_name:context.plan_name,
    entitlement_id:context.entitlement_id,
    period_kind:context.period_kind,
    grants:[...context.grants].sort(),
    usage,
  };
}

async function recentCustomerCalls(env, context, args) {
  const limit=Math.max(1,Math.min(100,Number(args?.limit || 50)));
  const tool=String(args?.tool || "").trim();
  let deviceId=null;
  if (args?.computer) {
    const devices=await listDevices(env,{tenant_id:context.tenant_id});
    deviceId=resolveNamedCustomerDevice(devices,args.computer).device_id;
  }
  const clauses=["c.tenant_id = ?","c.subject_id = ?"];
  const binds=[context.tenant_id,context.subject_id];
  if (deviceId) { clauses.push("c.device_id = ?"); binds.push(deviceId); }
  if (tool) { clauses.push("c.tool_id = ?"); binds.push(cleanId(tool,120)); }
  binds.push(limit);
  const result=await env.PRODUCT_DB.prepare(`
    SELECT c.call_id,c.request_id,c.device_id,c.tool_id,c.state,c.created_at_utc,c.claimed_at_utc,
           c.completed_at_utc,c.error_code,d.device_name
      FROM commander_device_calls c
      JOIN commander_devices d ON d.device_id = c.device_id
     WHERE ${clauses.join(" AND ")}
     ORDER BY c.created_at_utc DESC
     LIMIT ?`).bind(...binds).all();
  return (result.results||[]).map((row)=>( {
    call_id:row.call_id, request_id:row.request_id, computer:row.device_name, tool_id:row.tool_id,
    state:row.state, created_at_utc:row.created_at_utc, claimed_at_utc:row.claimed_at_utc,
    completed_at_utc:row.completed_at_utc, error_code:row.error_code || null,
  }));
}

function portalActivitySource(requestId) {
  const value=String(requestId || "");
  if (value.startsWith("HARA-CUSTOMER-MCP-")) return "CUSTOMER_MCP";
  if (value.startsWith("HARA-QA-")) return "QA";
  if (value.startsWith("HARA-E2E-")) return "E2E";
  if (value.startsWith("manual-")) return "MANUAL";
  return "OTHER";
}

function elapsedMs(start,end) {
  const a=Date.parse(String(start || ""));
  const b=Date.parse(String(end || ""));
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return null;
  return Math.round(b-a);
}

function portalActivityWindow(value) {
  const raw=String(value || "7d").trim().toLowerCase();
  const windows={
    "24h":{ key:"24h", label:"24 horas", hours:24 },
    "7d":{ key:"7d", label:"7 dias", hours:7*24 },
    "30d":{ key:"30d", label:"30 dias", hours:30*24 },
  };
  const selected=windows[raw] || windows["7d"];
  return {
    key:selected.key,
    label:selected.label,
    since_at_utc:new Date(Date.now()-(selected.hours*60*60*1000)).toISOString(),
  };
}

function betaAccessCanManage(session) {
  return ["OWNER","ADMIN"].includes(String(session?.role || "").toUpperCase());
}

async function portalBetaAccessStatus(env, session) {
  const row=await env.PRODUCT_DB.prepare(
    `SELECT plan_code,state,requested_at_utc,updated_at_utc
       FROM commander_beta_access_requests
      WHERE tenant_id = ? AND subject_id = ? AND plan_code = 'STANDARD'
      LIMIT 1`
  ).bind(session.tenant_id,session.subject_id).first();

  return {
    schema:"hara.commander-beta-access.v1",
    plan_code:"STANDARD",
    can_request:betaAccessCanManage(session),
    request:row ? {
      plan_code:String(row.plan_code || "STANDARD"),
      state:String(row.state || "REQUESTED"),
      requested_at_utc:row.requested_at_utc,
      updated_at_utc:row.updated_at_utc,
    } : null,
  };
}

async function requestPortalBetaAccess(env, session) {
  if (!betaAccessCanManage(session)) throw new Error("BETA_ACCESS_ADMIN_REQUIRED");
  const plan=await env.PRODUCT_DB.prepare(
    `SELECT plan_code,state FROM plans WHERE plan_code = 'STANDARD' LIMIT 1`
  ).first();
  if (!plan || String(plan.state || "").toUpperCase() !== "ACTIVE") {
    throw new Error("BETA_ACCESS_PLAN_UNAVAILABLE");
  }
  const now=nowIso();
  const requestId="HARA-BETA-"+crypto.randomUUID();
  await env.PRODUCT_DB.prepare(
    `INSERT INTO commander_beta_access_requests
       (request_id,tenant_id,subject_id,plan_code,state,requested_at_utc,updated_at_utc)
     VALUES (?, ?, ?, 'STANDARD', 'REQUESTED', ?, ?)
     ON CONFLICT(tenant_id,subject_id,plan_code)
     DO UPDATE SET state='REQUESTED',updated_at_utc=excluded.updated_at_utc`
  ).bind(requestId,session.tenant_id,session.subject_id,now,now).run();
  return await portalBetaAccessStatus(env,session);
}


function sloAlertTime(value) {
  const ms=Date.parse(String(value || ""));
  return Number.isFinite(ms) ? ms : null;
}

function sloAlertNumber(value) {
  const num=Number(value);
  return Number.isFinite(num) && num >= 0 ? num : null;
}

function evaluateTenantSloRows(rows, nowMs=Date.now()) {
  const onlineCutoff=nowMs-(SLO_ALERT_ONLINE_GRACE_SECONDS*1000);
  const snapshotCutoff=nowMs-(SLO_ALERT_SNAPSHOT_GRACE_SECONDS*1000);
  const online=(rows || []).filter((row)=>{
    const seen=sloAlertTime(row.last_seen_at_utc);
    return seen != null && seen >= onlineCutoff;
  });
  if (!online.length) return null;
  let pass=0, degraded=0, insufficient=0, missing=0, stale=0, completed=0, failed=0;
  let latestSnapshot=null;
  const p50=[],p95=[],p99=[];
  for (const row of online) {
    const snapAt=sloAlertTime(row.activity_summary_at_utc);
    if (!row.activity_summary_json) { missing+=1; continue; }
    if (snapAt == null || snapAt < snapshotCutoff) stale+=1;
    if (snapAt != null && (latestSnapshot == null || snapAt > latestSnapshot)) latestSnapshot=snapAt;
    let parsed;
    try { parsed=JSON.parse(String(row.activity_summary_json)); }
    catch (_error) { missing+=1; continue; }
    const selected=parsed?.windows?.["24h"] || {};
    const summary=selected.summary || {};
    const status=String(selected.slo?.status || "INSUFFICIENT_DATA");
    if (status === "PASS") pass+=1;
    else if (status === "DEGRADED") degraded+=1;
    else insufficient+=1;
    completed+=Number(summary.completed || 0);
    failed+=Number(summary.failed || 0);
    for (const [target,field] of [[p50,"latency_p50_ms"],[p95,"latency_p95_ms"],[p99,"latency_p99_ms"]]) {
      const value=sloAlertNumber(summary[field]);
      if (value != null) target.push(value);
    }
  }
  const terminal=completed+failed;
  const state=(missing || stale || degraded) ? "DEGRADED" : (pass ? "PASS" : "INSUFFICIENT_DATA");
  return {
    profile:SLO_ALERT_PROFILE,
    state,
    online_devices:online.length,
    pass_devices:pass,
    degraded_devices:degraded,
    insufficient_devices:insufficient,
    missing_snapshot_devices:missing,
    stale_snapshot_devices:stale,
    weighted_success_rate_percent:terminal ? Number(((completed/terminal)*100).toFixed(3)) : null,
    worst_device_p50_ms:p50.length ? Math.max(...p50) : null,
    worst_device_p95_ms:p95.length ? Math.max(...p95) : null,
    worst_device_p99_ms:p99.length ? Math.max(...p99) : null,
    last_snapshot_at_utc:latestSnapshot == null ? null : new Date(latestSnapshot).toISOString(),
  };
}

async function portalSloStatus(env, session) {
  if (!betaAccessCanManage(session)) throw new Error("SLO_STATUS_ADMIN_REQUIRED");
  const state=await env.PRODUCT_DB.prepare(
    "SELECT tenant_id,profile,state,breach_streak,recovery_streak,current_incident_id,last_evaluated_at_utc,last_snapshot_at_utc,summary_json,updated_at_utc FROM commander_slo_state WHERE tenant_id = ? LIMIT 1"
  ).bind(session.tenant_id).first();
  const incidentRows=await env.PRODUCT_DB.prepare(
    "SELECT incident_id,state,opened_at_utc,resolved_at_utc,first_breach_at_utc,last_breach_at_utc,last_seen_at_utc,summary_json,resolution_json FROM commander_slo_incidents WHERE tenant_id = ? ORDER BY opened_at_utc DESC LIMIT 10"
  ).bind(session.tenant_id).all();
  const parse=(value)=>{ try { return value ? JSON.parse(String(value)) : null; } catch (_error) { return null; } };
  return {
    schema:"hara.commander-portal-slo.v1",
    profile:SLO_ALERT_PROFILE,
    state:state ? {
      state:String(state.state),
      breach_streak:Number(state.breach_streak || 0),
      recovery_streak:Number(state.recovery_streak || 0),
      current_incident_id:state.current_incident_id || null,
      last_evaluated_at_utc:state.last_evaluated_at_utc || null,
      last_snapshot_at_utc:state.last_snapshot_at_utc || null,
      summary:parse(state.summary_json),
      updated_at_utc:state.updated_at_utc || null,
    } : null,
    incidents:(incidentRows.results || []).map((row)=>({
      incident_id:String(row.incident_id),
      state:String(row.state),
      opened_at_utc:row.opened_at_utc,
      resolved_at_utc:row.resolved_at_utc || null,
      first_breach_at_utc:row.first_breach_at_utc,
      last_breach_at_utc:row.last_breach_at_utc || null,
      last_seen_at_utc:row.last_seen_at_utc,
      summary:parse(row.summary_json),
      resolution:parse(row.resolution_json),
    })),
  };
}

async function runSloAlertMaintenance(env) {
  const now=nowIso();
  const result=await env.PRODUCT_DB.prepare(
    "SELECT tenant_id,device_id,device_name,agent_version,last_seen_at_utc,activity_summary_at_utc,activity_summary_json FROM commander_devices WHERE state='ACTIVE' AND revoked_at_utc IS NULL ORDER BY tenant_id,device_name"
  ).all();
  const byTenant=new Map();
  for (const row of result.results || []) {
    const tenant=String(row.tenant_id || "");
    if (!tenant) continue;
    if (!byTenant.has(tenant)) byTenant.set(tenant,[]);
    byTenant.get(tenant).push(row);
  }
  for (const [tenantId,rows] of byTenant.entries()) {
    const summary=evaluateTenantSloRows(rows);
    if (!summary) continue;
    const prior=await env.PRODUCT_DB.prepare(
      "SELECT state,breach_streak,recovery_streak,current_incident_id FROM commander_slo_state WHERE tenant_id = ? LIMIT 1"
    ).bind(tenantId).first();
    let breach=0, recovery=0;
    let incidentId=prior?.current_incident_id || null;
    if (summary.state === "DEGRADED") {
      breach=String(prior?.state || "") === "DEGRADED" ? Number(prior?.breach_streak || 0)+1 : 1;
      recovery=0;
      if (!incidentId && breach >= SLO_ALERT_BREACH_STREAK) {
        incidentId="HARA-SLO-INC-"+crypto.randomUUID();
        await env.PRODUCT_DB.prepare(
          "INSERT INTO commander_slo_incidents (incident_id,tenant_id,profile,state,opened_at_utc,resolved_at_utc,first_breach_at_utc,last_breach_at_utc,last_seen_at_utc,summary_json,resolution_json,updated_at_utc) VALUES (?, ?, ?, 'OPEN', ?, NULL, ?, ?, ?, ?, NULL, ?)"
        ).bind(incidentId,tenantId,SLO_ALERT_PROFILE,now,now,now,now,JSON.stringify(summary),now).run();
      } else if (incidentId) {
        await env.PRODUCT_DB.prepare(
          "UPDATE commander_slo_incidents SET last_breach_at_utc=?,last_seen_at_utc=?,summary_json=?,updated_at_utc=? WHERE incident_id=? AND state='OPEN'"
        ).bind(now,now,JSON.stringify(summary),now,incidentId).run();
      }
    } else if (summary.state === "PASS") {
      breach=0;
      recovery=incidentId ? Number(prior?.recovery_streak || 0)+1 : 0;
      if (incidentId && recovery >= SLO_ALERT_RECOVERY_STREAK) {
        const resolution={state:"PASS",recovered_at_utc:now,recovery_streak:recovery,summary};
        await env.PRODUCT_DB.prepare(
          "UPDATE commander_slo_incidents SET state='RESOLVED',resolved_at_utc=?,last_seen_at_utc=?,resolution_json=?,updated_at_utc=? WHERE incident_id=? AND state='OPEN'"
        ).bind(now,now,JSON.stringify(resolution),now,incidentId).run();
        incidentId=null;
        recovery=0;
      } else if (incidentId) {
        await env.PRODUCT_DB.prepare(
          "UPDATE commander_slo_incidents SET last_seen_at_utc=?,updated_at_utc=? WHERE incident_id=? AND state='OPEN'"
        ).bind(now,now,incidentId).run();
      }
    } else {
      breach=0;
      recovery=0;
    }
    await env.PRODUCT_DB.prepare(
      "INSERT INTO commander_slo_state (tenant_id,profile,state,breach_streak,recovery_streak,current_incident_id,last_evaluated_at_utc,last_snapshot_at_utc,summary_json,updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(tenant_id) DO UPDATE SET profile=excluded.profile,state=excluded.state,breach_streak=excluded.breach_streak,recovery_streak=excluded.recovery_streak,current_incident_id=excluded.current_incident_id,last_evaluated_at_utc=excluded.last_evaluated_at_utc,last_snapshot_at_utc=excluded.last_snapshot_at_utc,summary_json=excluded.summary_json,updated_at_utc=excluded.updated_at_utc"
    ).bind(tenantId,SLO_ALERT_PROFILE,summary.state,breach,recovery,incidentId,now,summary.last_snapshot_at_utc,JSON.stringify(summary),now).run();
  }
  const cutoff=new Date(Date.now()-(SLO_ALERT_INCIDENT_RETENTION_SECONDS*1000)).toISOString();
  await env.PRODUCT_DB.prepare(
    "DELETE FROM commander_slo_incidents WHERE incident_id IN (SELECT incident_id FROM commander_slo_incidents WHERE state='RESOLVED' AND resolved_at_utc IS NOT NULL AND resolved_at_utc < ? ORDER BY resolved_at_utc LIMIT 500)"
  ).bind(cutoff).run();
}

async function portalActivityFromLocalSnapshots(env, session, window) {
  if (!["OWNER","ADMIN"].includes(String(session.role || "").toUpperCase())) return null;
  const result=await env.PRODUCT_DB.prepare(
    `SELECT device_id,device_name,tunnel_mode,agent_version,
            activity_summary_json,activity_summary_at_utc
       FROM commander_devices
      WHERE tenant_id = ?
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL
      ORDER BY device_name`
  ).bind(session.tenant_id).all();

  const deviceRows=result.results || [];
  const snapshots=[];
  for (const row of deviceRows) {
    try {
      const parsed=JSON.parse(String(row.activity_summary_json || ""));
      const selected=parsed?.windows?.[window.key];
      if (!selected?.summary) continue;
      snapshots.push({row, selected});
    } catch (_error) {}
  }
  if (!snapshots.length) return null;

  const totals={
    total_calls:0,completed:0,failed:0,pending:0,executing:0,expired:0,cancelled:0,
    under3_weighted:0,total_ms_weighted:0,queue_ms_weighted:0,exec_ms_weighted:0,
    duration_weight:0,
  };
  const tools=new Map();
  const errors=new Map();
  const transports=new Set();
  const percentileValues={p50:[],p95:[],p99:[]};
  let latencySampleSize=0;
  let latencyPopulationSize=0;
  let latencySampleCapped=false;
  let sloPass=0;
  let sloDegraded=0;
  let sloInsufficient=0;

  for (const item of snapshots) {
    const summary=item.selected.summary || {};
    const total=Number(summary.total_calls || 0);
    const completed=Number(summary.completed || 0);
    totals.total_calls+=total;
    totals.completed+=completed;
    totals.failed+=Number(summary.failed || 0);
    totals.pending+=Number(summary.pending || 0);
    totals.executing+=Number(summary.executing || 0);
    totals.expired+=Number(summary.expired || 0);
    totals.cancelled+=Number(summary.cancelled || 0);
    if (summary.under_3s_percent != null) {
      totals.under3_weighted+=(Number(summary.under_3s_percent || 0)/100)*completed;
    }
    if (total > 0) {
      totals.duration_weight+=total;
      if (summary.avg_total_ms != null) totals.total_ms_weighted+=Number(summary.avg_total_ms)*total;
      if (summary.avg_queue_ms != null) totals.queue_ms_weighted+=Number(summary.avg_queue_ms)*total;
      if (summary.avg_execution_ms != null) totals.exec_ms_weighted+=Number(summary.avg_execution_ms)*total;
    }
    for (const [key,field] of [["p50","latency_p50_ms"],["p95","latency_p95_ms"],["p99","latency_p99_ms"]]) {
      if (summary[field] != null) percentileValues[key].push(Number(summary[field]));
    }
    latencySampleSize+=Number(summary.latency_sample_size || 0);
    latencyPopulationSize+=Number(summary.latency_population_size || 0);
    latencySampleCapped=latencySampleCapped || summary.latency_sample_capped === true;
    const deviceSlo=String(item.selected.slo?.status || "INSUFFICIENT_DATA");
    if (deviceSlo === "PASS") sloPass+=1;
    else if (deviceSlo === "DEGRADED") sloDegraded+=1;
    else sloInsufficient+=1;
    for (const mode of summary.transport_modes || []) transports.add(String(mode));
    for (const row of item.selected.diagnostics?.top_tools || []) {
      const key=String(row.tool_id || "unknown");
      tools.set(key,(tools.get(key)||0)+Number(row.calls || 0));
    }
    for (const row of item.selected.diagnostics?.top_errors || []) {
      const key=String(row.error_code || "UNKNOWN");
      errors.set(key,(errors.get(key)||0)+Number(row.calls || 0));
    }
  }

  const terminal=totals.completed+totals.failed+totals.expired+totals.cancelled;
  const top=(map,key)=>[...map.entries()]
    .map(([name,calls])=>({[key]:name,calls}))
    .sort((a,b)=>b.calls-a.calls || String(a[key]).localeCompare(String(b[key])))
    .slice(0,6);

  const aggregateSloStatus=sloDegraded
    ? "DEGRADED"
    : (sloPass ? "PASS" : "INSUFFICIENT_DATA");
  const payload={
    schema:"hara.commander-portal-activity.v2",
    scope:"TENANT",
    source:"LOCAL_DEVICE_SNAPSHOTS",
    detail_location:"LOCAL_DEVICE",
    cloud_history_scanned:false,
    snapshot_device_count:snapshots.length,
    active_device_count:deviceRows.length,
    snapshot_coverage_percent:deviceRows.length
      ? Number(((snapshots.length/deviceRows.length)*100).toFixed(1))
      : 100,
    snapshot_updated_at_utc:snapshots
      .map((item)=>String(item.row.activity_summary_at_utc || ""))
      .filter(Boolean).sort().at(-1) || null,
    window,
    privacy:{
      payload_values_exposed:false,
      result_values_exposed:false,
      request_id_exposed:false,
      command_text_exposed:false,
      argument_values_exposed:false,
      historical_command_text_persisted:false,
      detailed_history_location:"LOCAL_DEVICE",
      customer_content_synced:false,
      metadata_only:true,
    },
    diagnostics:{
      top_tools:top(tools,"tool_id"),
      top_errors:top(errors,"error_code"),
    },
    summary:{
      total_calls:totals.total_calls,
      completed:totals.completed,
      failed:totals.failed,
      pending:totals.pending,
      executing:totals.executing,
      expired:totals.expired,
      cancelled:totals.cancelled,
      success_rate_percent:terminal ? Number(((totals.completed/terminal)*100).toFixed(1)) : null,
      under_3s_percent:totals.completed ? Number(((totals.under3_weighted/totals.completed)*100).toFixed(1)) : null,
      avg_queue_ms:totals.duration_weight ? Number((totals.queue_ms_weighted/totals.duration_weight).toFixed(1)) : null,
      avg_execution_ms:totals.duration_weight ? Number((totals.exec_ms_weighted/totals.duration_weight).toFixed(1)) : null,
      avg_total_ms:totals.duration_weight ? Number((totals.total_ms_weighted/totals.duration_weight).toFixed(1)) : null,
      latency_p50_ms:percentileValues.p50.length ? Math.max(...percentileValues.p50) : null,
      latency_p95_ms:percentileValues.p95.length ? Math.max(...percentileValues.p95) : null,
      latency_p99_ms:percentileValues.p99.length ? Math.max(...percentileValues.p99) : null,
      latency_sample_size:latencySampleSize,
      latency_population_size:latencyPopulationSize,
      latency_sample_capped:latencySampleCapped,
      device_count:snapshots.length,
      transport_modes:[...transports],
    },
    slo:{
      profile:"INTERNAL_BETA_V1",
      status:aggregateSloStatus,
      evaluable_devices:sloPass+sloDegraded,
      pass_devices:sloPass,
      degraded_devices:sloDegraded,
      insufficient_devices:sloInsufficient,
    },
    transactions:[],
  };
  Object.defineProperty(payload, "_covered_device_ids", {
    value:snapshots.map((item)=>String(item.row.device_id || "")).filter(Boolean),
    enumerable:false,
  });
  return payload;
}

function mergeActivityBreakdown(localItems, cloudItems, key) {
  const combined=new Map();
  for (const item of [...(localItems || []), ...(cloudItems || [])]) {
    const name=String(item?.[key] || (key === "tool_id" ? "unknown" : "UNKNOWN"));
    combined.set(name,(combined.get(name)||0)+Number(item?.calls || 0));
  }
  return [...combined.entries()]
    .map(([name,calls])=>({[key]:name,calls}))
    .sort((a,b)=>b.calls-a.calls || String(a[key]).localeCompare(String(b[key])))
    .slice(0,6);
}

function mergePortalActivity(local, cloud) {
  if (!local) return cloud;
  const a=local.summary || {};
  const b=cloud.summary || {};
  const localTotal=Number(a.total_calls || 0);
  const cloudTotal=Number(b.total_calls || 0);
  const total=localTotal+cloudTotal;
  const completed=Number(a.completed || 0)+Number(b.completed || 0);
  const failed=Number(a.failed || 0)+Number(b.failed || 0);
  const expired=Number(a.expired || 0)+Number(b.expired || 0);
  const cancelled=Number(a.cancelled || 0)+Number(b.cancelled || 0);
  const terminal=completed+failed+expired+cancelled;
  const weighted=(field)=>{
    const values=[];
    if (a[field] != null && localTotal) values.push([Number(a[field]),localTotal]);
    if (b[field] != null && cloudTotal) values.push([Number(b[field]),cloudTotal]);
    const weight=values.reduce((sum,item)=>sum+item[1],0);
    return weight ? Number((values.reduce((sum,item)=>sum+(item[0]*item[1]),0)/weight).toFixed(1)) : null;
  };
  const under3Count=
    (a.under_3s_percent == null ? 0 : (Number(a.under_3s_percent)/100)*Number(a.completed || 0))
    +(b.under_3s_percent == null ? 0 : (Number(b.under_3s_percent)/100)*Number(b.completed || 0));
  const percentileMax=(field)=>{
    const values=[a[field],b[field]].filter((value)=>value != null).map(Number);
    return values.length ? Math.max(...values) : null;
  };
  return {
    ...cloud,
    schema:"hara.commander-portal-activity.v2",
    source:cloudTotal ? "LOCAL_DEVICE_SNAPSHOTS_WITH_CLOUD_FALLBACK" : "LOCAL_DEVICE_SNAPSHOTS",
    detail_location:cloudTotal ? "LOCAL_DEVICE_WITH_CLOUD_FALLBACK" : "LOCAL_DEVICE",
    cloud_history_scanned:Boolean(cloud.cloud_history_scanned),
    snapshot_device_count:local.snapshot_device_count,
    active_device_count:local.active_device_count,
    snapshot_coverage_percent:local.snapshot_coverage_percent,
    snapshot_updated_at_utc:local.snapshot_updated_at_utc,
    privacy:{
      ...cloud.privacy,
      detailed_history_location:cloudTotal ? "LOCAL_DEVICE_AND_LEGACY_CLOUD_FALLBACK" : "LOCAL_DEVICE",
      customer_content_synced:false,
      metadata_only:true,
    },
    diagnostics:{
      top_tools:mergeActivityBreakdown(local.diagnostics?.top_tools,cloud.diagnostics?.top_tools,"tool_id"),
      top_errors:mergeActivityBreakdown(local.diagnostics?.top_errors,cloud.diagnostics?.top_errors,"error_code"),
    },
    slo:local.slo || cloud.slo || {profile:"INTERNAL_BETA_V1",status:"INSUFFICIENT_DATA"},
    summary:{
      total_calls:total,
      completed,
      failed,
      pending:Number(a.pending || 0)+Number(b.pending || 0),
      executing:Number(a.executing || 0)+Number(b.executing || 0),
      expired,
      cancelled,
      success_rate_percent:terminal ? Number(((completed/terminal)*100).toFixed(1)) : null,
      under_3s_percent:completed ? Number(((under3Count/completed)*100).toFixed(1)) : null,
      avg_queue_ms:weighted("avg_queue_ms"),
      avg_execution_ms:weighted("avg_execution_ms"),
      avg_total_ms:weighted("avg_total_ms"),
      latency_p50_ms:percentileMax("latency_p50_ms"),
      latency_p95_ms:percentileMax("latency_p95_ms"),
      latency_p99_ms:percentileMax("latency_p99_ms"),
      latency_sample_size:Number(a.latency_sample_size || 0)+Number(b.latency_sample_size || 0),
      latency_population_size:Number(a.latency_population_size || 0)+Number(b.latency_population_size || 0),
      latency_sample_capped:a.latency_sample_capped === true || b.latency_sample_capped === true,
      device_count:Number(local.snapshot_device_count || 0)+Number(b.device_count || 0),
      transport_modes:[...new Set([
        ...(a.transport_modes || []),
        ...(b.transport_modes || []),
      ])],
    },
    transactions:cloud.transactions || [],
  };
}

async function portalActivity(env, session, limitValue=50, windowValue="7d") {
  const limit=Math.max(1,Math.min(100,Number(limitValue || 50)));
  const window=portalActivityWindow(windowValue);
  const privileged=["OWNER","ADMIN"].includes(String(session.role || "").toUpperCase());
  const local=privileged
    ? await portalActivityFromLocalSnapshots(env,session,window)
    : null;
  if (
    local
    && Number(local.active_device_count || 0) > 0
    && Number(local.snapshot_device_count || 0) === Number(local.active_device_count || 0)
  ) {
    return local;
  }
  const clauses=["c.tenant_id = ?","c.created_at_utc >= ?"];
  const binds=[session.tenant_id,window.since_at_utc];
  if (local?._covered_device_ids?.length) {
    const placeholders=local._covered_device_ids.map(()=>"?").join(",");
    clauses.push(`c.device_id NOT IN (${placeholders})`);
    binds.push(...local._covered_device_ids);
  }
  if (!privileged) {
    clauses.push("c.subject_id = ?");
    binds.push(session.subject_id);
  }
  const where=clauses.join(" AND ");

  const summarySql=`
    SELECT
      COUNT(*) AS total_calls,
      SUM(CASE WHEN c.state='COMPLETED' THEN 1 ELSE 0 END) AS completed,
      SUM(CASE WHEN c.state='FAILED' THEN 1 ELSE 0 END) AS failed,
      SUM(CASE WHEN c.state='PENDING' THEN 1 ELSE 0 END) AS pending,
      SUM(CASE WHEN c.state='EXECUTING' THEN 1 ELSE 0 END) AS executing,
      SUM(CASE WHEN c.state='EXPIRED' THEN 1 ELSE 0 END) AS expired,
      SUM(CASE WHEN c.state='CANCELLED' THEN 1 ELSE 0 END) AS cancelled,
      COUNT(DISTINCT c.device_id) AS device_count,
      GROUP_CONCAT(DISTINCT d.tunnel_mode) AS transport_modes,
      ROUND(AVG(CASE WHEN c.state='COMPLETED' AND c.claimed_at_utc IS NOT NULL
        THEN (julianday(c.claimed_at_utc)-julianday(c.created_at_utc))*86400000 END),1) AS avg_queue_ms,
      ROUND(AVG(CASE WHEN c.state='COMPLETED' AND c.claimed_at_utc IS NOT NULL AND c.completed_at_utc IS NOT NULL
        THEN (julianday(c.completed_at_utc)-julianday(c.claimed_at_utc))*86400000 END),1) AS avg_exec_ms,
      ROUND(AVG(CASE WHEN c.state='COMPLETED' AND c.completed_at_utc IS NOT NULL
        THEN (julianday(c.completed_at_utc)-julianday(c.created_at_utc))*86400000 END),1) AS avg_total_ms,
      SUM(CASE WHEN c.state='COMPLETED' AND c.completed_at_utc IS NOT NULL
        AND (julianday(c.completed_at_utc)-julianday(c.created_at_utc))*86400000 < 3000 THEN 1 ELSE 0 END) AS under_3s
    FROM commander_device_calls c
    JOIN commander_devices d ON d.device_id=c.device_id
    WHERE ${where}`;

  const recentSql=`
    SELECT c.call_id,c.request_id,c.tool_id,c.state,c.created_at_utc,c.claimed_at_utc,
           c.completed_at_utc,c.error_code,d.device_name,d.tunnel_mode,d.agent_version
      FROM commander_device_calls c
      JOIN commander_devices d ON d.device_id=c.device_id
     WHERE ${where}
     ORDER BY c.created_at_utc DESC
     LIMIT ?`;

  const topToolsSql=`
    SELECT c.tool_id,COUNT(*) AS calls
      FROM commander_device_calls c
     WHERE ${where}
     GROUP BY c.tool_id
     ORDER BY calls DESC,c.tool_id
     LIMIT 6`;

  const topErrorsSql=`
    SELECT COALESCE(c.error_code,'UNKNOWN') AS error_code,COUNT(*) AS calls
      FROM commander_device_calls c
     WHERE ${where}
       AND c.state='FAILED'
     GROUP BY COALESCE(c.error_code,'UNKNOWN')
     ORDER BY calls DESC,error_code
     LIMIT 6`;

  const [summaryRow,recentResult,topToolsResult,topErrorsResult]=await Promise.all([
    env.PRODUCT_DB.prepare(summarySql).bind(...binds).first(),
    env.PRODUCT_DB.prepare(recentSql).bind(...binds,limit).all(),
    env.PRODUCT_DB.prepare(topToolsSql).bind(...binds).all(),
    env.PRODUCT_DB.prepare(topErrorsSql).bind(...binds).all(),
  ]);

  const summary=summaryRow || {};
  const total=Number(summary.total_calls || 0);
  const completed=Number(summary.completed || 0);
  const failed=Number(summary.failed || 0);
  const expired=Number(summary.expired || 0);
  const cancelled=Number(summary.cancelled || 0);
  const terminal=completed+failed+expired+cancelled;
  const transportModes=String(summary.transport_modes || "")
    .split(",").map((value)=>value.trim()).filter(Boolean);

  const transactions=(recentResult.results || []).map((row)=>({
    trace_id:String(row.call_id || ""),
    source:portalActivitySource(row.request_id),
    tool_id:String(row.tool_id || ""),
    computer:String(row.device_name || ""),
    transport_mode:String(row.tunnel_mode || ""),
    agent_version:String(row.agent_version || ""),
    state:String(row.state || ""),
    created_at_utc:row.created_at_utc,
    claimed_at_utc:row.claimed_at_utc,
    completed_at_utc:row.completed_at_utc,
    queue_ms:elapsedMs(row.created_at_utc,row.claimed_at_utc),
    execution_ms:elapsedMs(row.claimed_at_utc,row.completed_at_utc),
    total_ms:elapsedMs(row.created_at_utc,row.completed_at_utc),
    error_code:row.error_code || null,
  }));

  const cloud={
    schema:"hara.commander-portal-activity.v1",
    scope:privileged ? "TENANT" : "SUBJECT",
    source:"CLOUD_CALL_HISTORY",
    detail_location:"CLOUD_LEGACY",
    cloud_history_scanned:true,
    window,
    privacy:{
      payload_values_exposed:false,
      result_values_exposed:false,
      request_id_exposed:false,
      command_text_exposed:false,
      argument_values_exposed:false,
      historical_command_text_persisted:false,
      payload_hot_path_transient:true,
      metadata_only:true,
    },
    diagnostics:{
      top_tools:(topToolsResult.results || []).map((row)=>({
        tool_id:String(row.tool_id || ""),
        calls:Number(row.calls || 0),
      })),
      top_errors:(topErrorsResult.results || []).map((row)=>({
        error_code:String(row.error_code || "UNKNOWN"),
        calls:Number(row.calls || 0),
      })),
    },
    summary:{
      total_calls:total,
      completed,
      failed,
      pending:Number(summary.pending || 0),
      executing:Number(summary.executing || 0),
      expired,
      cancelled,
      success_rate_percent:terminal ? Number(((completed/terminal)*100).toFixed(1)) : null,
      under_3s_percent:completed ? Number(((Number(summary.under_3s || 0)/completed)*100).toFixed(1)) : null,
      avg_queue_ms:summary.avg_queue_ms == null ? null : Number(summary.avg_queue_ms),
      avg_execution_ms:summary.avg_exec_ms == null ? null : Number(summary.avg_exec_ms),
      avg_total_ms:summary.avg_total_ms == null ? null : Number(summary.avg_total_ms),
      device_count:Number(summary.device_count || 0),
      transport_modes:transportModes,
    },
    transactions,
  };
  return mergePortalActivity(local,cloud);
}

async function executeCustomerMcpTool(
  env,
  identity,
  toolId,
  args,
  mcpRequestId,
  transportRequestId,
) {
  const requiredGrant = MCP_TOOL_GRANTS[toolId];
  if (!requiredGrant) throw new Error("POLICY_DENIED");

  const context = await mcpProductContext(env, identity.issuer, identity.subject);
  if (!context.ok) throw new Error(context.code);
  if (!context.grants.includes(requiredGrant)) throw new Error("GRANT_MISSING");

  if (toolId === "hara.devices.list") {
    const devices = await listDevices(env, { tenant_id: context.tenant_id });
    return {
      state: "PASS", operational_authority: "HARA_SERVICES", execution_authority: "HARA_SERVICES",
      runtime_authority_from_chatgpt: false, mutation_performed: false, customer_services_relay: false,
      result: {
        count: devices.length,
        computers: devices.map((d) => ({
          device_id: d.device_id, computer: d.device_name, platform: d.platform, architecture: d.architecture,
          agent_version: d.agent_version, state: d.revoked_at_utc ? "REVOKED" : (d.online ? "ONLINE" : "OFFLINE"),
          last_seen_at_utc: d.last_seen_at_utc,
        })),
      },
      product: { plan_code: context.plan_code, entitlement_id: context.entitlement_id, quota: null },
    };
  }

  if (toolId === "hara.capabilities") {
    const capabilities=await customerCapabilities(env,context,args);
    return {state:"PASS",operational_authority:"HARA_SERVICES",execution_authority:"HARA_SERVICES",runtime_authority_from_chatgpt:false,mutation_performed:false,customer_services_relay:false,result:{count:capabilities.length,computers:capabilities},product:{plan_code:context.plan_code,entitlement_id:context.entitlement_id,quota:null}};
  }

  if (toolId === "hara.usage") {
    const usage=await customerUsage(env,context);
    return {state:"PASS",operational_authority:"HARA_SERVICES",execution_authority:"HARA_SERVICES",runtime_authority_from_chatgpt:false,mutation_performed:false,customer_services_relay:false,result:usage,product:{plan_code:context.plan_code,entitlement_id:context.entitlement_id,quota:usage.usage}};
  }

  if (toolId === "hara.activity") {
    const activity=await portalActivity(
      env,
      {tenant_id:context.tenant_id,subject_id:context.subject_id,role:"MEMBER"},
      args?.limit || 50,
      args?.window || "7d",
    );
    return {
      state:"PASS", operational_authority:"HARA_SERVICES", execution_authority:"HARA_SERVICES",
      runtime_authority_from_chatgpt:false, mutation_performed:false, customer_services_relay:false,
      result:activity,
      product:{plan_code:context.plan_code,entitlement_id:context.entitlement_id,quota:null},
    };
  }

  if (toolId === "hara.calls.recent") {
    const calls = await recentCustomerCalls(env, context, args);
    return {
      state:"PASS", operational_authority:"HARA_SERVICES", execution_authority:"HARA_SERVICES",
      runtime_authority_from_chatgpt:false, mutation_performed:false, customer_services_relay:false,
      result:{count:calls.length,calls},
      product:{plan_code:context.plan_code,entitlement_id:context.entitlement_id,quota:null},
    };
  }

  const targetDevice = await resolveCustomerTargetDevice(
    env, context, args?.computer || null, null
  );
  const targetDeviceId = cleanId(targetDevice.device_id, 180);
  const targetComputer = String(targetDevice.device_name || "");
  const payload = customerMcpDevicePayload(toolId, args);
  const requestId = await customerMcpRequestId(
    identity,
    toolId,
    { device_id: targetDeviceId, payload },
    mcpRequestId,
    transportRequestId,
  );
  if ((isDeviceMutationTool(toolId) || isDeviceProcessTool(toolId) || toolId === "hara.files.preimages.list") && !agentPurposeToolReady(targetDevice, toolId)) {
    throw new Error("AGENT_UPGRADE_REQUIRED");
  }
  const purposeFunctionId = quotaFunctionIdForTool(toolId, payload);
  const legacyPayload = legacyInvokePayload(toolId, payload);
  const dispatchAsLegacyInvoke = Boolean(legacyPayload) && !agentPurposeToolReady(targetDevice, toolId);
  const dispatchToolId = dispatchAsLegacyInvoke ? "hara.functions.invoke" : toolId;
  const dispatchPayload = dispatchAsLegacyInvoke ? legacyPayload : payload;

  const usageMode = await resolveCallUsageMode(env, context, targetDevice, purposeFunctionId);
  let quota = null;
  let reservation = null;
  let cloudQuotaLimit = context.unit_limit;
  if (purposeFunctionId && usageMode === "CLOUD_QUOTA") {
    const functionId = cleanId(purposeFunctionId, 180);
    if (!functionId.startsWith("tool:") && !isDeviceFunctionAllowed(functionId)) throw new Error("POLICY_DENIED");
    const cloudPeriodKey = mcpPeriodKey(context);
    cloudQuotaLimit = await effectiveCloudQuotaLimit(env, context, cloudPeriodKey);
    quota = env.TENANT_QUOTA.getByName(context.tenant_id);
    reservation = await quota.reserve(
      requestId,
      context.subject_id,
      cloudPeriodKey,
      functionId,
      cloudQuotaLimit,
    );
    if (!reservation.ok) {
      throw new Error(String(reservation.code || "QUOTA_DENIED"));
    }
    if (reservation.existing && reservation.state === "RELEASED") {
      throw new Error("REQUEST_USAGE_TERMINAL");
    }
    if (reservation.state === "COMMITTED") {
      const committedReceiptSha = String(
        reservation.receipt_sha256 || "",
      ).trim().toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(committedReceiptSha)) {
        throw new Error("CUSTOMER_MCP_COMMITTED_RECEIPT_INVALID");
      }
      return {
        state: "PASS",
        operational_authority: null,
        execution_authority: "HARA_COMMANDER_AGENT",
        runtime_authority_from_chatgpt: false,
        mutation_performed: false,
        replayed: true,
        result: { replayed: true },
        bridge_receipt_sha256: committedReceiptSha,
        customer_services_relay: false,
        computer: targetComputer,
        product: {
          plan_code: context.plan_code,
          entitlement_id: context.entitlement_id,
          quota: reservation,
        },
      };
    }
    if (reservation.state !== "RESERVED") {
      throw new Error("CUSTOMER_MCP_QUOTA_STATE_INVALID");
    }
  } else if (purposeFunctionId && usageMode === "LOCAL_BUDGET") {
    reservation = {
      ok: true,
      state: "LOCAL_BUDGET",
      mode: "LOCAL_BUDGET",
      period_key: mcpPeriodKey(context),
      units: 1,
      cloud_quota_transaction: false,
    };
  } else if (purposeFunctionId && usageMode === "UNMETERED") {
    reservation = {
      ok: true,
      state: "UNMETERED",
      mode: "UNMETERED",
      units: 0,
      cloud_quota_transaction: false,
    };
  }

  let call;
  try {
    call = await enqueueDeviceCall(env, {
      issuer: identity.issuer,
      subject: identity.subject,
      request_id: requestId,
      tool_id: dispatchToolId,
      device_id: targetDeviceId,
      payload: dispatchPayload,
    });
  } catch (error) {
    if (usageMode === "CLOUD_QUOTA" && quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, cloudQuotaLimit)
        .catch(() => undefined);
    }
    throw error;
  }

  const status = await customerMcpWaitForCall(env, identity, call);
  if (status.state === "FAILED") {
    if (usageMode === "CLOUD_QUOTA" && quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, cloudQuotaLimit);
    }
    if (status.result && typeof status.result === "object") {
      return { ...projectCustomerToolResult(toolId, status.result), computer: targetComputer };
    }
    throw new Error(String(status.error_code || "DEVICE_EXECUTION_FAILED"));
  }
  if (status.state !== "COMPLETED") {
    if (usageMode === "CLOUD_QUOTA" && quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, cloudQuotaLimit);
    }
    throw new Error("DEVICE_CALL_" + String(status.state || "FAILED"));
  }

  const projected = {
    ...projectCustomerToolResult(toolId, status.result || {}),
    computer: targetComputer,
  };
  let usage = null;
  if (purposeFunctionId && usageMode === "CLOUD_QUOTA") {
    const receiptSha = String(projected.bridge_receipt_sha256 || "");
    if (
      projected.state === "PASS"
      && /^[0-9a-f]{64}$/.test(receiptSha)
    ) {
      usage = await quota.commit(
        requestId,
        context.subject_id,
        receiptSha,
        cloudQuotaLimit,
      );
      if (!usage.ok) {
        throw new Error(String(usage.code || "PRODUCT_USAGE_COMMIT_DENIED"));
      }
    } else {
      usage = await quota.release(
        requestId,
        context.subject_id,
        cloudQuotaLimit,
      );
    }
  } else if (purposeFunctionId && usageMode === "LOCAL_BUDGET") {
    usage = {
      ok: true,
      state: "LOCAL_BUDGET",
      mode: "LOCAL_BUDGET",
      period_key: mcpPeriodKey(context),
      units: 1,
      cloud_quota_transaction: false,
      local_enforced: true,
    };
  } else if (purposeFunctionId && usageMode === "UNMETERED") {
    usage = {
      ok: true,
      state: "UNMETERED",
      mode: "UNMETERED",
      units: 0,
      cloud_quota_transaction: false,
    };
  }

  return {
    ...projected,
    product: {
      plan_code: context.plan_code,
      entitlement_id: context.entitlement_id,
      quota: usage,
    },
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
          FROM commander_device_calls c INDEXED BY idx_device_calls_poll
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
      RETURNING call_id, request_id, tool_id, payload_json, expires_at_utc,
                usage_mode, usage_units, usage_period_key, usage_budget_id`
  ).bind(now, device.device_id, now).all();

  const row = (result.results || [])[0];
  if (!row) return null;

  const rawPayloadJson = String(row.payload_json || "{}");
  const rawPayload = JSON.parse(rawPayloadJson);
  const payloadMarker = await redactedDeviceCallContent(rawPayloadJson);
  await env.PRODUCT_DB.prepare(
    `UPDATE commander_device_calls
        SET payload_json = ?
      WHERE call_id = ?
        AND tenant_id = ?
        AND device_id = ?
        AND state = 'EXECUTING'`
  ).bind(payloadMarker, row.call_id, device.tenant_id, device.device_id).run();

  return {
    schema: "hara.commander-device-call-claim.v1",
    call_id: row.call_id,
    request_id: row.request_id,
    tool_id: row.tool_id,
    payload: rawPayload,
    expires_at_utc: row.expires_at_utc,
    usage: {
      mode: String(row.usage_mode || "CLOUD_QUOTA"),
      units: Number(row.usage_units || 0),
      period_key: row.usage_period_key || null,
      budget_id: row.usage_budget_id || null,
    },
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
      const resultMatches = await deviceCallStoredContentMatches(
        existing.result_json,
        resultJson,
      );
      if (
        !resultMatches
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
  const context = await mcpProductContext(env, body.issuer, body.subject, mcpBootstrapHints(body));
  if (!context.ok) throw new Error(context.code);

  const now = nowIso();
  const readCall = () => env.PRODUCT_DB.prepare(
    `SELECT call_id, request_id, device_id, tool_id, state, created_at_utc,
            expires_at_utc, claimed_at_utc, completed_at_utc, payload_json, result_json, error_code
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
                  expires_at_utc, claimed_at_utc, completed_at_utc, payload_json, result_json, error_code`
    ).bind(now, callId, context.tenant_id, context.subject_id, now).all();
    const updated = (expired.results || [])[0];
    if (updated) {
      row = updated;
    } else {
      row = await readCall();
      if (!row) throw new Error("DEVICE_CALL_NOT_FOUND");
    }
  }

  const rawResultJson = row.result_json && !isRedactedDeviceCallContent(row.result_json)
    ? String(row.result_json)
    : null;
  const publicResult = rawResultJson ? JSON.parse(rawResultJson) : null;
  let contentRedacted = isRedactedDeviceCallContent(row.payload_json)
    || isRedactedDeviceCallContent(row.result_json);
  if (["COMPLETED","FAILED","CANCELLED","EXPIRED"].includes(String(row.state)) && rawResultJson) {
    const resultMarker = await redactedDeviceCallContent(rawResultJson);
    await env.PRODUCT_DB.prepare(
      `UPDATE commander_device_calls
          SET result_json = ?
        WHERE call_id = ?
          AND tenant_id = ?
          AND subject_id = ?
          AND result_json = ?`
    ).bind(resultMarker, row.call_id, context.tenant_id, context.subject_id, rawResultJson).run();
    contentRedacted = true;
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
    result: publicResult,
    content_redacted: contentRedacted,
    error_code: row.error_code || null,
    retry_after_ms: deviceCallRetryAfterMs(row.state, "status"),
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

      if (url.pathname === "/api/dev/slo-maintenance" && request.method === "POST") {
        await requireMcpProductToken(request, env);
        await runSloAlertMaintenance(env);
        return json({ ok:true, schema:"hara.commander-slo-maintenance.v1", environment:"DEV" });
      }

      if (url.pathname === "/api/portal/auth-config" && request.method === "GET") {
        return json({ configured: authStatus(env).configured });
      }

      if (url.pathname === "/api/billing/stripe/webhook" && request.method === "POST") {
        return json(await handleStripeWebhook(request, env));
      }

      if (
        [
          "/.well-known/oauth-protected-resource",
          "/.well-known/oauth-protected-resource/api/mcp",
        ].includes(url.pathname)
        && request.method === "GET"
      ) {
        if (!haraIdentityCustomerMcpEnabled(env)) {
          return json({ ok: false, code: "NOT_FOUND" }, 404);
        }
        return json(haraIdentityCustomerMcpProtectedResourceMetadata(request, env));
      }

      if (url.pathname === "/api/mcp" && ["GET", "POST"].includes(request.method)) {
        if (!haraIdentityCustomerMcpEnabled(env)) {
          return json({ ok: false, code: "NOT_FOUND" }, 404);
        }
        let identity;
        try {
          identity = await verifyHaraIdentityCustomerMcpBearer(request, env);
        } catch (_error) {
          return haraIdentityCustomerMcpUnauthorized(request);
        }

        const profile=String(url.searchParams.get("profile") || "full").trim().toLowerCase();
        if (!["full","simple"].includes(profile)) {
          return json({ ok:false, code:"MCP_PROFILE_INVALID" }, 400);
        }
        const handler=profile === "simple" ? handleSimpleCustomerMcpRequest : handleCustomerMcpRequest;
        return handler(request, {
          authInfo: {
            token: "HARA_IDENTITY_VALIDATED",
            clientId: identity.client_id,
            scopes: identity.scopes,
          },
          allowedHosts: ["commander.haralabs.com.br"],
          executeTool: async ({
            tool_id,
            arguments: toolArguments,
            mcp_request_id,
            transport_request_id,
          }) => executeCustomerMcpTool(
            env,
            identity,
            tool_id,
            toolArguments,
            mcp_request_id,
            transport_request_id,
          ),
        });
      }

      if (
        url.pathname === "/.well-known/oauth-protected-resource/api/dev/mcp"
        && request.method === "GET"
      ) {
        requireDev(env);
        if (!haraIdentityMcpDevEnabled(env)) {
          return json({ ok: false, code: "NOT_FOUND" }, 404);
        }
        return json(haraIdentityMcpDevProtectedResourceMetadata(request, env));
      }

      if (
        ["/api/dev/mcp", "/api/dev/mcp/proof"].includes(url.pathname)
        && ["GET", "POST"].includes(request.method)
      ) {
        requireDev(env);
        if (!haraIdentityMcpDevEnabled(env)) {
          return json({ ok: false, code: "NOT_FOUND" }, 404);
        }

        let identity;
        try {
          identity = await verifyHaraIdentityMcpDevBearer(request, env);
        } catch (_error) {
          return haraIdentityMcpDevUnauthorized(request);
        }

        const context = await mcpProductContext(env, identity.issuer, identity.subject);
        if (!context.ok) {
          return json({ ok: false, code: context.code }, 403);
        }
        if (!context.grants.includes("COMMANDER_DISCOVERY")) {
          return json({ ok: false, code: "GRANT_MISSING" }, 403);
        }

        if (url.pathname === "/api/dev/mcp/proof") {
          const periodKey = mcpPeriodKey(context);
          const usage = await env.TENANT_QUOTA
            .getByName(context.tenant_id)
            .status(periodKey, context.unit_limit);

          return json({
            schema: "hara.commander-mcp-hara-identity-dev-proof.v2",
            ok: true,
            environment: "DEV",
            token_binding: {
              issuer: identity.issuer,
              client_id: identity.client_id,
              binding_claim: identity.client_binding,
              audience_count: identity.audience_count,
              scopes: identity.scopes,
            },
            subject: {
              subject_id: context.subject_id,
              tenant_id: context.tenant_id,
            },
            entitlement: {
              entitlement_id: context.entitlement_id,
              plan_code: context.plan_code,
              grants: context.grants,
            },
            quota: {
              meter_id: context.meter_id,
              period_kind: context.period_kind,
              unit_limit: context.unit_limit,
              status: usage,
            },
            customer_services_relay: false,
            event_v2_mutation: false,
          });
        }

        return handleCustomerMcpRequest(request, {
          authInfo: {
            token: "HARA_IDENTITY_VALIDATED",
            clientId: identity.client_id,
            scopes: identity.scopes,
          },
          allowedHosts: ["hara-commander-dev-v2.tiago-sartori.workers.dev"],
          executeTool: async ({
            tool_id,
            arguments: toolArguments,
            mcp_request_id,
          }) => executeCustomerMcpTool(
            env,
            identity,
            tool_id,
            toolArguments,
            mcp_request_id,
          ),
        });
      }

      if (url.pathname === "/auth/login" && request.method === "GET") {
        await enforceLoginInitiationRateLimit(request, env);
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

      if (url.pathname === "/api/portal/bootstrap" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);

        const [payload, devices] = await Promise.all([
          dashboardForSubject(env, session.subject_id, session.tenant_id),
          listDevices(env, session),
        ]);

        const subject = {
          subject_id: session.subject_id,
          display_name: session.display_name,
          role: session.role
        };
        if (!payload) {
          return json({
            ok: false,
            code: "ENTITLEMENT_NOT_FOUND",
            subject,
            tenant: {
              tenant_id: session.tenant_id,
              display_name: session.tenant_name
            }
          }, 403);
        }

        return json({
          schema: "hara.commander-portal-bootstrap.v1",
          subject,
          tenant: payload.tenant,
          entitlement: payload.entitlement,
          usage: payload.usage,
          device_state: {
            schema: "hara.commander-device-list.v1",
            devices,
            active_count: devices.filter((device) => device.state === "ACTIVE").length,
            online_count: devices.filter((device) => device.online).length,
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

      if (url.pathname === "/api/portal/activity" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        const limit=Number(url.searchParams.get("limit") || 50);
        const window=url.searchParams.get("window") || "7d";
        return json(await portalActivity(env,session,limit,window));
      }

      if (url.pathname === "/api/portal/slo" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok:false, code:"AUTH_REQUIRED" },401);
        return json(await portalSloStatus(env,session));
      }

      if (url.pathname === "/api/portal/beta-access" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok:false, code:"AUTH_REQUIRED" },401);
        return json(await portalBetaAccessStatus(env,session));
      }

      if (url.pathname === "/api/portal/beta-access" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok:false, code:"AUTH_REQUIRED" },401);
        await enforcePortalMutationRateLimit(env,session);
        return json(await requestPortalBetaAccess(env,session),201);
      }

      if (url.pathname === "/api/portal/billing" && request.method === "GET") {
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        return json(await billingStatus(env, session));
      }

      if (url.pathname === "/api/portal/billing/checkout" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        await enforcePortalMutationRateLimit(env, session);
        const body = await request.json();
        return json(await createBillingCheckout(request, env, session, body?.plan_code), 201);
      }

      if (url.pathname === "/api/portal/billing/portal" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        await enforcePortalMutationRateLimit(env, session);
        return json(await createBillingPortal(request, env, session), 201);
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
        await enforcePortalMutationRateLimit(env, session);
        return json(await createDevicePairing(env, session), 201);
      }

      if (url.pathname === "/api/portal/devices/revoke" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        await enforcePortalMutationRateLimit(env, session);
        const body = await request.json();
        return json(await revokePortalDevice(env, session, body));
      }

      if (url.pathname === "/api/portal/devices/select" && request.method === "POST") {
        requirePortalMutationOrigin(request);
        const session = await resolvePortalSession(request, env);
        if (!session) return json({ ok: false, code: "AUTH_REQUIRED" }, 401);
        await enforcePortalMutationRateLimit(env, session);
        const body = await request.json();
        return json(await selectPortalDevice(env, session, body));
      }

      if (url.pathname === "/api/device/channel" && request.method === "GET") {
        return await openDeviceEventChannel(env, request);
      }

      if (url.pathname === "/api/device/enroll" && request.method === "POST") {
        await enforceDeviceEnrollClientRateLimit(request, env);
        const body = await request.json();
        await enforceDeviceEnrollTokenRateLimit(body, env);
        return json(await enrollDevice(env, body), 201);
      }

      if (url.pathname === "/api/device/heartbeat" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        return json(await heartbeatDevice(env, request, body));
      }

      if (url.pathname === "/api/device/product-lease" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        return json(await deviceProductLease(env, request, body));
      }

      if (url.pathname === "/api/device/offline" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        return json(await markDeviceOffline(env, request, body));
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
        await requireMcpProductToken(request, env);
      }

      if (url.pathname === "/api/internal/device/transient-call" && request.method === "POST") {
        const body = await request.json();
        return internalJson(await dispatchTransientDeviceCall(env, body));
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

        const context = await mcpProductContext(env, body.issuer, body.subject, mcpBootstrapHints(body));
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
        if (!isDeviceFunctionAllowed(functionId)) {
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
        const reservation = context.period_kind === "NONE"
          ? {
              ok: true,
              state: "UNMETERED",
              mode: "UNMETERED",
              period_key: periodKey,
              units: 0,
              cloud_quota_transaction: false,
            }
          : await env.TENANT_QUOTA
              .getByName(context.tenant_id)
              .reserve(
                requestId,
                context.subject_id,
                periodKey,
                functionId,
                await effectiveCloudQuotaLimit(env, context, periodKey),
              );

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

        const context = await mcpProductContext(env, body.issuer, body.subject);
        if (!context.ok) return internalJson({ ok: false, code: context.code }, 403);

        const usage = context.period_kind === "NONE"
          ? {
              ok: true,
              state: "UNMETERED",
              mode: "UNMETERED",
              units: 0,
              cloud_quota_transaction: false,
            }
          : await env.TENANT_QUOTA
              .getByName(context.tenant_id)
              .commit(
                requestId,
                context.subject_id,
                receiptSha256,
                await effectiveCloudQuotaLimit(env, context, mcpPeriodKey(context)),
              );

        return internalJson({
          schema: "hara.commander-mcp-usage-transition.v1",
          transition: "COMMIT",
          subject_id: context.subject_id,
          tenant_id: context.tenant_id,
          request_id: requestId,
          receipt_sha256: receiptSha256,
          usage,
        });
      }

      if (url.pathname === "/api/internal/mcp/release" && request.method === "POST") {
        const body = await request.json();
        const requestId = cleanId(body.request_id, 220);
        const context = await mcpProductContext(env, body.issuer, body.subject);
        if (!context.ok) return internalJson({ ok: false, code: context.code }, 403);

        const usage = context.period_kind === "NONE"
          ? {
              ok: true,
              state: "UNMETERED",
              mode: "UNMETERED",
              units: 0,
              cloud_quota_transaction: false,
            }
          : await env.TENANT_QUOTA
              .getByName(context.tenant_id)
              .release(
                requestId,
                context.subject_id,
                await effectiveCloudQuotaLimit(env, context, mcpPeriodKey(context)),
              );

        return internalJson({
          schema: "hara.commander-mcp-usage-transition.v1",
          transition: "RELEASE",
          subject_id: context.subject_id,
          tenant_id: context.tenant_id,
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
        RATE_LIMIT_BINDING_MISSING: 503,
        RATE_LIMIT_CHECK_FAILED: 503,
        STRICT_RATE_LIMIT_BINDING_MISSING: 503,
        STRICT_RATE_LIMIT_CHECK_FAILED: 503,
        AUTH_RATE_LIMITED: 429,
        DEVICE_ENROLL_RATE_LIMITED: 429,
        PORTAL_MUTATION_RATE_LIMITED: 429,
        MCP_AUTH_RATE_LIMITED: 429,
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
        BETA_ACCESS_ADMIN_REQUIRED: 403,
        BETA_ACCESS_PLAN_UNAVAILABLE: 409,
        SLO_STATUS_ADMIN_REQUIRED: 403,
        BILLING_NOT_CONFIGURED: 503,
        BILLING_ADMIN_REQUIRED: 403,
        BILLING_PLAN_INVALID: 400,
        BILLING_PLAN_UNAVAILABLE: 409,
        BILLING_PRICE_NOT_CONFIGURED: 503,
        BILLING_SUBSCRIPTION_ALREADY_EXISTS: 409,
        BILLING_CUSTOMER_NOT_READY: 409,
        BILLING_CHECKOUT_RESPONSE_INVALID: 502,
        BILLING_CHECKOUT_URL_INVALID: 502,
        BILLING_PORTAL_RESPONSE_INVALID: 502,
        BILLING_PORTAL_URL_INVALID: 502,
        BILLING_PROVIDER_UNREACHABLE: 502,
        BILLING_PROVIDER_RESPONSE_INVALID: 502,
        BILLING_PROVIDER_ERROR: 502,
        BILLING_WEBHOOK_SIGNATURE_INVALID: 400,
        BILLING_WEBHOOK_TIMESTAMP_INVALID: 400,
        BILLING_WEBHOOK_JSON_INVALID: 400,
        BILLING_WEBHOOK_EVENT_INVALID: 400,
        BILLING_WEBHOOK_PAYLOAD_TOO_LARGE: 413,
        BILLING_EVENT_OBJECT_INVALID: 400,
        BILLING_TENANT_INVALID: 400,
        BILLING_TENANT_NOT_FOUND: 409,
        BILLING_SUBSCRIPTION_INVALID: 400,
        BILLING_PRICE_UNKNOWN: 409,
        BILLING_PRICE_MISMATCH: 409,
        DEVICE_PAIRING_INVALID: 401,
        DEVICE_PAIRING_CREATE_FAILED: 503,
        DEVICE_AUTH_REQUIRED: 401,
        DEVICE_AUTH_INVALID: 401,
        DEVICE_EVENT_V2_DISABLED: 404,
        DEVICE_EVENT_V2_BINDING_MISSING: 503,
        DEVICE_TRANSIENT_RPC_DISABLED: 404,
        DEVICE_TRANSIENT_REQUIRES_EVENT_V2: 409,
        CHANNEL_TRANSIENT_OFFLINE: 409,
        CHANNEL_TRANSIENT_DISCONNECTED: 409,
        CHANNEL_TRANSIENT_BUSY: 429,
        CHANNEL_TRANSIENT_TIMEOUT: 504,
        CHANNEL_TRANSIENT_PAYLOAD_INVALID: 400,
        CHANNEL_TRANSIENT_RESULT_INVALID: 502,
        CHANNEL_LEARNING_SIGNAL_INVALID: 502,
        DEVICE_TRANSIENT_RPC_FAILED: 502,
        TRANSIENT_QUOTA_STATE_INVALID: 409,
        TRANSIENT_QUOTA_COMMIT_FAILED: 502,
        TRANSIENT_COMMITTED_RECEIPT_INVALID: 409,
        TRANSIENT_REPLAY_RECEIPT_MISMATCH: 409,
        PRODUCT_CONTEXT_INVALID: 500,
        REQUEST_USAGE_TERMINAL: 409,
        QUOTA_DENIED: 429,
        QUOTA_EXCEEDED: 429,
        DEVICE_ID_MISMATCH: 403,
        DEVICE_NOT_FOUND: 404,
        DEVICE_SELECTION_REQUIRED: 409,
        DEVICE_NOT_SELECTED: 403,
        DEVICE_NAME_INVALID: 400,
        DEVICE_PLATFORM_INVALID: 400,
        DEVICE_METADATA_INVALID: 400,
        DEVICE_OFFLINE: 409,
        DEVICE_BUSY: 429,
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

      if (statusMap[code] === 429 && code !== "DEVICE_BUSY") {
        return rateLimitedJson(code);
      }
      const errorPayload = { ok: false, code };
      if (code === "DEVICE_BUSY") errorPayload.retry_after_ms = 1000;
      return json(errorPayload, statusMap[code] || 500);
    }
  },
  async scheduled(_event, env, ctx) {
    requireRuntime(env);
    ctx.waitUntil(runAuthRetentionMaintenance(env));
    ctx.waitUntil(cleanupExpiredDeviceCalls(env));
    ctx.waitUntil(runSloAlertMaintenance(env));
  }
};
