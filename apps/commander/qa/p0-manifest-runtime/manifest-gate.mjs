// QA-only witness coverage verifier over the EXISTING Commander DO classes.
// No API routes, queue, Agent RPC, new orchestrator, production or cloud writes.
export const QA_MANIFEST = Object.freeze([
  Object.freeze({ alias: "quota-alpha", binding: "TENANT_QUOTA" }),
  Object.freeze({ alias: "quota-beta", binding: "TENANT_QUOTA" }),
  Object.freeze({ alias: "channel-alpha", binding: "DEVICE_CHANNEL" }),
  Object.freeze({ alias: "rate-alpha", binding: "STRICT_RATE_LIMIT" }),
]);
export const SOURCE_GENERATION = "HARA_CANDIDATE_P0_FENCE_20261112";
const names = new Set(QA_MANIFEST.map(({ alias }) => alias));
const fail = code => { throw new Error("QA_DO_MANIFEST_" + code); };
const integer = x => Number.isSafeInteger(x) && x >= 0;
const exactName = (value, expected) => {
  if (!Array.isArray(value) || value.length !== expected.length) fail("COUNT_INVALID");
  const supplied = value.map(x => x?.alias);
  if (new Set(supplied).size !== expected.length) fail("DUPLICATE_OR_MISSING");
  if (supplied.some(x => !expected.includes(x))) fail("UNREGISTERED_INSTANCE");
};
function witnessFor(alias, value, epoch, nonces) {
  if (!value || typeof value !== "object" || value.valid !== true ||
      value.source_generation !== SOURCE_GENERATION ||
      value.fenced !== true || value.epoch !== epoch) fail("WITNESS_SOURCE_EPOCH_INVALID");
  const nonce = value.nonce;
  if (typeof nonce !== "string" || !/^[A-Za-z0-9_-]{8,100}$/.test(nonce) ||
      nonces.has(nonce)) fail("WITNESS_NONCE_REPLAY");
  nonces.add(nonce);
  if (value.global_inventory_proven !== false ||
      value.provider_deployment_converged !== false ||
      value.production_activation_authorized !== false) fail("WITNESS_OVERCLAIM");
  if (alias === "channel-alpha") {
    if (value.local_drained !== true || !integer(value.websockets) ||
        !integer(value.callbacks_inflight) || !integer(value.presence_inflight) ||
        !integer(value.transient_pending) ||
        value.websockets !== 0 || value.callbacks_inflight !== 0 ||
        value.presence_inflight !== 0 || value.transient_pending !== 0 ||
        value.scheduled_alarm !== false) fail("CHANNEL_NOT_DRAINED");
  }
  if (alias === "quota-alpha" || alias === "quota-beta") {
    if (!integer(value.protected_rows) || !integer(value.protected_units))
      fail("QUOTA_PROTECTION_UNPROVEN");
  }
}
export function evaluateQaKnownManifest({ manifest, epoch, windows, sourceSha256 } = {}) {
  if (typeof epoch !== "string" || !/^[A-Za-z0-9_-]{8,100}$/.test(epoch))
    fail("EPOCH_INVALID");
  if (typeof sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(sourceSha256) ||
      sourceSha256 !== "9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260")
    fail("EXACT_WORKER_SOURCE_UNPROVEN");
  exactName(manifest, QA_MANIFEST.map(x => x.alias));
  for (const [i, entry] of QA_MANIFEST.entries()) {
    const row = manifest[i];
    if (row.alias !== entry.alias || row.binding !== entry.binding)
      fail("CLASS_MANIFEST_DRIFT");
  }
  if (!Array.isArray(windows) || windows.length !== 2) fail("WINDOW_COUNT_INVALID");
  const nonces = new Set();
  let previous;
  const quotaCounts = new Map();
  for (const window of windows) {
    if (!integer(window?.observed_at_ms)) fail("WINDOW_TIMESTAMP_INVALID");
    if (previous !== undefined &&
        (window.observed_at_ms - previous < 200 ||
         window.observed_at_ms - previous > 30000)) fail("WINDOW_GAP_INVALID");
    previous = window.observed_at_ms;
    if (!Array.isArray(window.witnesses)) fail("WITNESS_LIST_MISSING");
    exactName(window.witnesses, [...names]);
    const present = new Map(window.witnesses.map(x => [x.alias, x.witness]));
    for (const { alias } of QA_MANIFEST) {
      const w = present.get(alias);
      witnessFor(alias, w, epoch, nonces);
      if (alias.startsWith("quota-")) {
        const old = quotaCounts.get(alias);
        if (old && (old.rows !== w.protected_rows || old.units !== w.protected_units))
          fail("PROTECTED_QUOTA_CHANGED");
        quotaCounts.set(alias, { rows: w.protected_rows, units: w.protected_units });
      }
    }
  }
  if (quotaCounts.get("quota-alpha")?.rows !== 2 ||
      quotaCounts.get("quota-alpha")?.units !== 2 ||
      quotaCounts.get("quota-beta")?.rows !== 0 ||
      quotaCounts.get("quota-beta")?.units !== 0)
    fail("QA_PROTECTED_RESERVATION_EXPECTATIONS");
  return {
    schema: "hara.commander-qa-known-do-manifest-witness.v1",
    state: "KNOWN_QA_DO_MANIFEST_TWO_OBSERVATIONS_PASS_GLOBAL_HOLD",
    source_worker_sha256: sourceSha256,
    known_qa_instances: QA_MANIFEST.length,
    samples: windows.length,
    unique_nonces: nonces.size,
    quota_protected_units: 2,
    websocket_drained_in_known_channel: true,
    known_actor_manifest_complete: true,
    all_live_commercial_instances_proven: false,
    unregistered_DO_instances_excluded: true,
    global_two_quiescence_windows_proven: false,
    commercial_queue_consumer_proven: false,
    commercial_cutover_authorized: false,
    agent_dispatched: false,
    production_mutated: false,
    hosted_cloudflare_qa_run: false,
  };
}