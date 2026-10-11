// Reconcile self-reported Agent metadata from an already authenticated, accepted
// device.info/ping result. This is NOT release-signature attestation. Do not
// inspect arbitrary command output, add polling, or rewrite transport/presence.
const INFO_FUNCTIONS = new Map([
  ["hara.device.info", "device.info"],
  ["hara.ping", "device.ping"],
]);
const RELEASE_VERSION = /^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})$/;
const MAX_INFO_BYTES = 8192;

export const VERSION_OBSERVATION_SQL = `UPDATE commander_devices
   SET agent_version = ?
 WHERE tenant_id = ? AND device_id = ?
   AND state = 'ACTIVE' AND revoked_at_utc IS NULL
   AND agent_version IS ?`;

export function observedAgentVersion(device, acceptedCall, result) {
  if (!device || device.state !== "ACTIVE" || device.revoked_at_utc != null
      || !device.tenant_id || !device.device_id
      || acceptedCall?.state !== "COMPLETED") return null;
  // The live Agent wraps function output in its canonical PASS envelope.
  // Accept only a successful, non-mutating self-info envelope; retain support
  // for the flat output contract. Device/tenant validation remains below.
  if (result && typeof result === "object" && !Array.isArray(result)
      && Object.prototype.hasOwnProperty.call(result, "result")) {
    if (result.state !== "PASS" || result.runtime_authority_from_chatgpt !== false
        || result.mutation_performed !== false || result.blocker != null) return null;
    result = result.result;
  }
  const expectedFunction = INFO_FUNCTIONS.get(acceptedCall.tool_id);
  if (!expectedFunction || !result || Array.isArray(result)
      || result.function_id !== expectedFunction || result.process_exit_code !== 0
      || typeof result.stdout !== "string"
      || result.stdout.length > MAX_INFO_BYTES
      || new TextEncoder().encode(result.stdout).byteLength > MAX_INFO_BYTES) return null;
  let info;
  try { info = JSON.parse(result.stdout); } catch { return null; }
  if (!info || typeof info !== "object" || Array.isArray(info)
      || info.device_id !== device.device_id
      || typeof info.agent_version !== "string"
      || info.agent_version.trim() !== info.agent_version
      || !RELEASE_VERSION.test(info.agent_version)) return null;
  return info.agent_version;
}

export async function reconcileAgentVersion(env, device, acceptedCall, result) {
  const observed = observedAgentVersion(device, acceptedCall, result);
  if (observed === null) return { state: "NOT_APPLICABLE", queries: 0 };
  const previous = device.agent_version ?? null;
  if (observed === previous) return { state: "UNCHANGED", queries: 0 };
  // Compare-and-set protects against a concurrent metadata refresh. A genuine
  // rollback is allowed; numerically highest version is not necessarily live.
  const update = await env.PRODUCT_DB.prepare(VERSION_OBSERVATION_SQL)
    .bind(observed, device.tenant_id, device.device_id, previous).run();
  if (update?.success === false || !Number.isInteger(update?.meta?.changes)) {
    throw new Error("DEVICE_VERSION_OBSERVATION_PERSIST_FAILED");
  }
  return { state: update.meta.changes === 1 ? "UPDATED" : "CONCURRENT_CHANGE", queries: 1 };
}
