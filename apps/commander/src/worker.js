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

  status(periodKey, limit, expireReservations = true) {
    if (expireReservations) this.expireStaleReservations();
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

async function productUsageForPolicy(env, tenantId, periodKind, unitLimit) {
  const kind = String(periodKind || "").trim().toUpperCase();
  if (kind === "NONE") return unlimitedProductUsage();

  const periodKey = kind === "CALENDAR_MONTH" ? monthKey() : "LIFETIME";
  const limit = Number(unitLimit);
  const quota = env.TENANT_QUOTA.getByName(tenantId);
  return {
    ...(await quota.status(periodKey, limit)),
    metered: true,
  };
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

async function heartbeatDevice(env, request, body) {
  const device = await resolveDeviceCredential(env, request);
  const requestedId = body.device_id ? cleanId(body.device_id, 180) : device.device_id;
  if (requestedId !== device.device_id) throw new Error("DEVICE_ID_MISMATCH");

  const agentVersion = cleanAgentValue(body.agent_version, 80) || device.agent_version;
  const architecture = cleanAgentValue(body.architecture, 80) || device.architecture;
  const approvalMode = normalizeApprovalMode(body.approval_mode, normalizeApprovalMode(device.approval_mode, "ASK_EVERY_ACTION"));
  const seenAt = nowIso();

  const heartbeat = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?,
            agent_version = ?,
            architecture = ?,
            approval_mode = ?,
            tunnel_mode = 'OUTBOUND_RELAY'
      WHERE device_id = ? AND state = 'ACTIVE' AND revoked_at_utc IS NULL`
  ).bind(seenAt, agentVersion, architecture, approvalMode, device.device_id).run();
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
    `SELECT call_id, tenant_id, subject_id, device_id, tool_id, payload_json, state, expires_at_utc
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
    };
  };

  const existing = await readExisting();
  if (existing) return await existingResponse(existing);

  const device = await resolveCustomerTargetDevice(
    env, context, body.computer || null, requestedDeviceId
  );
  const deviceId = cleanId(device.device_id, 180);
  if (!deviceOnline(device.last_seen_at_utc, device.tunnel_mode)) throw new Error("DEVICE_OFFLINE");

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
       result_json, error_code)
     SELECT ?, ?, ?, ?, d.device_id, ?, ?, 'PENDING', ?, ?, NULL, NULL, NULL, NULL
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
        ) < ?`
  ).bind(
    callId, requestId, context.tenant_id, context.subject_id, toolId, payloadJson,
    createdAt, expiresAt, deviceId, context.tenant_id, eventV2Cutoff, onlineCutoff,
    createdAt, DEVICE_CALL_ACTIVE_QUEUE_LIMIT
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

async function portalActivity(env, session, limitValue=50, windowValue="7d") {
  const limit=Math.max(1,Math.min(100,Number(limitValue || 50)));
  const window=portalActivityWindow(windowValue);
  const privileged=["OWNER","ADMIN"].includes(String(session.role || "").toUpperCase());
  const clauses=["c.tenant_id = ?","c.created_at_utc >= ?"];
  const binds=[session.tenant_id,window.since_at_utc];
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

  return {
    schema:"hara.commander-portal-activity.v1",
    scope:privileged ? "TENANT" : "SUBJECT",
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

  let quota = null;
  let reservation = null;
  if (purposeFunctionId) {
    const functionId = cleanId(purposeFunctionId, 180);
    if (!functionId.startsWith("tool:") && !isDeviceFunctionAllowed(functionId)) throw new Error("POLICY_DENIED");
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
    if (quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, context.unit_limit)
        .catch(() => undefined);
    }
    throw error;
  }

  const status = await customerMcpWaitForCall(env, identity, call);
  if (status.state === "FAILED") {
    if (quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, context.unit_limit);
    }
    if (status.result && typeof status.result === "object") {
      return { ...projectCustomerToolResult(toolId, status.result), computer: targetComputer };
    }
    throw new Error(String(status.error_code || "DEVICE_EXECUTION_FAILED"));
  }
  if (status.state !== "COMPLETED") {
    if (quota && reservation?.state === "RESERVED") {
      await quota.release(requestId, context.subject_id, context.unit_limit);
    }
    throw new Error("DEVICE_CALL_" + String(status.state || "FAILED"));
  }

  const projected = {
    ...projectCustomerToolResult(toolId, status.result || {}),
    computer: targetComputer,
  };
  let usage = null;
  if (purposeFunctionId) {
    const receiptSha = String(projected.bridge_receipt_sha256 || "");
    if (
      projected.state === "PASS"
      && /^[0-9a-f]{64}$/.test(receiptSha)
    ) {
      usage = await quota.commit(
        requestId,
        context.subject_id,
        receiptSha,
        context.unit_limit,
      );
      if (!usage.ok) {
        throw new Error(String(usage.code || "PRODUCT_USAGE_COMMIT_DENIED"));
      }
    } else {
      usage = await quota.release(
        requestId,
        context.subject_id,
        context.unit_limit,
      );
    }
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
      RETURNING call_id, request_id, tool_id, payload_json, expires_at_utc`
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
  }
};
