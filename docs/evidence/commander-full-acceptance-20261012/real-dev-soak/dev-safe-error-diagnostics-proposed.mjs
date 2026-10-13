// Proposed DEV-only diagnostics; no raw message, payload, headers, cookies or paths.
const ERROR_NAMES = new Set(["Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "AggregateError", "DOMException", "D1Error"]);
const FUNCTIONS = new Set(["fetch", "dispatchTransientDeviceCall", "mcpTransientProductContext", "mcpProductContext", "resolveCustomerTargetDevice", "resolveSelectedDevice", "resolveOrBootstrapContext", "requireMcpProductToken", "recordLearningSignal", "dispatchTransient", "webSocketMessage", "alarm", "getByName", "first", "all"]);
const ROUTES = new Map([["/api/internal/device/transient-call", "TRANSIENT_CALL"], ["/api/internal/mcp/authorize", "MCP_AUTHORIZE"], ["/api/internal/mcp/commit", "MCP_COMMIT"], ["/api/internal/mcp/release", "MCP_RELEASE"]]);

export function safeCauseClass(message) {
  const value = String(message || "");
  if (/D1_ERROR.*(?:constraint|UNIQUE|FOREIGN KEY)/i.test(value)) return "D1_CONSTRAINT";
  if (/D1_ERROR.*(?:timeout|timed out)/i.test(value)) return "D1_TIMEOUT";
  if (/D1_ERROR.*(?:read|write).*limit/i.test(value)) return "D1_LIMIT";
  if (/(?:Durable Object|DO).*?(?:reset|restart)/i.test(value)) return "DO_RESET";
  if (/(?:Durable Object|DO).*?(?:timeout|timed out)/i.test(value)) return "DO_RPC_TIMEOUT";
  if (/(?:Durable Object|DO).*?(?:storage|sqlite).*?(?:limit|full|capacity)/i.test(value)) return "DO_STORAGE_LIMIT";
  if (/WebSocket.*?(?:closed|not open|closing)/i.test(value)) return "WEBSOCKET_STATE";
  return "UNKNOWN";
}

export function safeStackFrames(stack) {
  const frames = [];
  for (const line of String(stack || "").split("\n").slice(0, 24)) {
    const match = line.match(/^\s*at\s+(?:async\s+)?(?:Object\.)?([A-Za-z_$][\w$]*)\s+\([^\n]*:(\d+):(\d+)\)\s*$/);
    if (!match || !FUNCTIONS.has(match[1])) continue;
    const lineNumber = Number(match[2]);
    const column = Number(match[3]);
    if (!Number.isSafeInteger(lineNumber) || lineNumber < 1 || lineNumber > 1_000_000) continue;
    if (!Number.isSafeInteger(column) || column < 1 || column > 1_000_000) continue;
    frames.push({ function: match[1], line: lineNumber, column });
    if (frames.length === 4) break;
  }
  return frames;
}

export async function buildDevSafeIncident(error, env, pathname) {
  if (String(env?.ENVIRONMENT || "") !== "DEV"
      || String(env?.DEV_SAFE_ERROR_DIAGNOSTICS_ENABLED || "").toLowerCase() !== "true") return null;
  const message = String(error?.message || "").slice(0, 32_768);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(message)));
  const name = String(error?.name || "");
  return {
    schema: "hara.dev-safe-error-incident.v1",
    incident_id: crypto.randomUUID(),
    at_utc: new Date().toISOString(),
    environment: "DEV",
    route: ROUTES.get(String(pathname || "")) || "OTHER",
    exception_class: ERROR_NAMES.has(name) ? name : "Error",
    safe_cause_class: safeCauseClass(message),
    message_sha256: Array.from(digest, b => b.toString(16).padStart(2, "0")).join(""),
    message_digest_truncated: String(error?.message || "").length > 32_768,
    stack_frames: safeStackFrames(error?.stack),
  };
}

export async function emitDevSafeIncident(error, env, pathname, sink = console.error) {
  try {
    const incident = await buildDevSafeIncident(error, env, pathname);
    if (incident) sink(JSON.stringify(incident));
    return incident?.incident_id || null;
  } catch {
    // Diagnostics cannot change the public error contract.
    return null;
  }
}
