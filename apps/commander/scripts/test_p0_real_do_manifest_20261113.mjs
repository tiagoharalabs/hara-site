// Real Commander TenantQuota/DeviceChannel/SecurityRateLimit in local workerd.
// QA-only explicit manifest; does NOT assert inventory of all hosted DOs.
import assert from "node:assert/strict";
import path from "node:path";
import { createRequire } from "node:module";
import { evaluateQaKnownManifest, QA_MANIFEST } from
  "../qa/p0-manifest-runtime/manifest-gate.mjs";
const require = createRequire(import.meta.url);
const { Miniflare } = require("/tmp_hara/commander-capability-suite-20261110/node_modules/miniflare");
process.env.MINIFLARE_WORKERD_PATH =
  "/home/sartorius/.npm/_npx/23be562fde961825/node_modules/workerd/bin/workerd";
const [bundle, storage] = process.argv.slice(2);
assert.ok(bundle && storage && path.resolve(storage).startsWith("/tmp_hara/commander-do-manifest-"));
const workerSha = "9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260";
const epoch = "QA_EXACT_DO_MANIFEST_EPOCH_20261113";
const subject = "QA_SYNTHETIC_SUBJECT_20261113";
const period = "2026-11";
const results = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const check = async (name, action) => {
  const details = (await action()) || {};
  results.push({ name, state: "PASS", ...details });
};
const namespaceNames = Object.freeze({
  "quota-alpha": "QA_MANIFEST_QUOTA_ALPHA_20261113",
  "quota-beta": "QA_MANIFEST_QUOTA_BETA_20261113",
  "channel-alpha": "QA_MANIFEST_CHANNEL_ALPHA_20261113",
  "rate-alpha": "QA_MANIFEST_RATE_ALPHA_20261113",
});
let mf;
let actors;
async function boot() {
  mf = new Miniflare({
    host: "127.0.0.1", port: 0, modules: true,
    modulesRoot: path.dirname(bundle), scriptPath: bundle,
    compatibilityDate: "2026-09-21",
    durableObjects: {
      TENANT_QUOTA: { className: "TenantQuota", useSQLite: true },
      DEVICE_CHANNEL: { className: "DeviceChannel", useSQLite: true },
      STRICT_RATE_LIMIT: { className: "SecurityRateLimit", useSQLite: true },
    },
    durableObjectsPersist: path.join(storage, "durable-objects"),
    d1Databases: ["PRODUCT_DB"], d1Persist: path.join(storage, "d1"),
    bindings: {
      ENVIRONMENT: "DEV", STORAGE_MODE: "ISOLATED_QA",
      CUSTOMER_MCP_EDGE_ENABLED: "false", DEVICE_EVENT_V2_ENABLED: "false",
      AUTH_ISSUER: "https://qa-manifest.invalid/",
      AUTH_CLIENT_ID: "synthetic-client",
      STRIPE_CHECKOUT_ENABLED: "false",
    },
    outboundService: async () => { throw Error("QA_EXTERNAL_EGRESS_DENIED"); },
  });
  const endpoint = await mf.ready;
  assert.equal(endpoint.hostname, "127.0.0.1");
  actors = new Map();
  for (const item of QA_MANIFEST) {
    const ns = await mf.getDurableObjectNamespace(item.binding);
    actors.set(item.alias, ns.get(ns.idFromName(namespaceNames[item.alias])));
  }
}
async function observe(index) {
  const observed = [];
  for (const item of QA_MANIFEST) {
    observed.push({
      alias: item.alias,
      witness: await actors.get(item.alias).cutoverFenceWitness(
        "QA_MANIFEST_W" + index + "_" + item.alias.replaceAll("-", "_") + "_NONCE_20261113"
      ),
    });
  }
  return { observed_at_ms: Date.now(), witnesses: observed };
}
const manifest = QA_MANIFEST.map(({alias,binding}) => ({alias,binding}));
const candidate = (windows) => ({manifest,epoch,windows,sourceSha256:workerSha});
let windows;
let decision;
try {
  await boot();
  await check("actual three DO classes expose their native witness method", async () => {
    for (const item of QA_MANIFEST) {
      const w = await actors.get(item.alias).cutoverFenceWitness(
        "QA_BEFORE_" + item.alias.replaceAll("-", "_") + "_NONCE"
      );
      assert.equal(w.valid, true);
      assert.equal(w.fenced, false);
      assert.equal(w.global_inventory_proven, false);
    }
    return { classes: 3, known_instances: 4 };
  });
  await check("two reserved quota units acquire protected reconciliation holds", async () => {
    const qa = actors.get("quota-alpha");
    for (const call of ["QA_CALL_UNCERTAIN_ONE", "QA_CALL_UNSTARTED_TWO", "QA_CALL_COMMITTED_THREE"]) {
      const x = await qa.reserve(call, subject, period, "tool:qa", 30);
      assert.equal(x.ok, true);
    }
    assert.equal((await qa.startDeviceCall("QA_CALL_UNCERTAIN_ONE", subject, period, 1)).ok, true);
    assert.equal((await qa.holdDeviceCall("QA_CALL_UNCERTAIN_ONE", subject, period, 1)).ok, true);
    assert.equal((await qa.commit("QA_CALL_COMMITTED_THREE", subject, "a".repeat(64), 30)).ok, true);
    const witness = await qa.cutoverFenceWitness("QA_PROTECTED_BEFORE_20261113");
    assert.equal(witness.protected_rows, 1);
    return { first_uncertain_protected: true };
  });
  await check("rate limit may mutate prior to its own fence", async () => {
    const rate = await actors.get("rate-alpha").limit(2, 60);
    assert.equal(rate.success, true);
  });
  await check("fencing only one real DO does not close the QA manifest", async () => {
    assert.equal((await actors.get("quota-alpha").enterCutoverFence(epoch)).ok, true);
    const partial = await observe(0);
    assert.equal(partial.witnesses.filter(x => x.witness.fenced).length, 1);
    assert.throws(() => evaluateQaKnownManifest(candidate([partial,partial])), /QA_DO_MANIFEST_/);
    const beta = await actors.get("quota-beta").reserve(
      "QA_BETA_PRE_FENCE", subject, period, "tool:qa", 30
    );
    assert.equal(beta.ok, true);
    assert.equal((await actors.get("quota-beta").release(
      "QA_BETA_PRE_FENCE", subject, 30
    )).ok, true);
    return { one_fenced: true, three_unfenced: true };
  });
  await check("all four known QA actor instances accept a pinned epoch", async () => {
    for (const item of QA_MANIFEST) {
      const response = await actors.get(item.alias).enterCutoverFence(epoch);
      assert.equal(response.ok, true);
      assert.equal(response.epoch, epoch);
    }
    return { scoped_fenced_instances: 4 };
  });
  await check("late hold stays monotonic, without quota release or settlement", async () => {
    const qa = actors.get("quota-alpha");
    const hold = await qa.holdDeviceCall("QA_CALL_UNSTARTED_TWO", subject, period, 1);
    assert.equal(hold.ok, true);
    const w = await qa.cutoverFenceWitness("QA_PROTECTED_AFTER_20261113");
    assert.equal(w.protected_rows, 2);
    assert.equal(w.protected_units, 2);
    assert.equal((await qa.reserve("QA_REJECTED_AFTER_FENCE",subject,period,"tool:qa",30)).code,
      "DO_CUTOVER_FENCED");
    return { protected_rows: 2, protected_units: 2 };
  });
  await check("rate and channel deny effects after individual fences", async () => {
    const rate = await actors.get("rate-alpha").limit(2, 60);
    assert.equal(rate.code,"DO_CUTOVER_FENCED");
    const channel = actors.get("channel-alpha");
    const res = await channel.fetch("https://qa.invalid/notify",{
      method:"POST",headers:{"x-hara-channel-authenticated":"1","content-type":"application/json"},
      body: JSON.stringify({call_id:"QA_NO_REAL_DELIVERY"})
    });
    assert.equal(res.status,503);
    const w=await channel.cutoverFenceWitness("QA_CHANNEL_POST_FENCE_20261113");
    assert.equal(w.local_drained,true);
  });
  await check("two scoped windows use distinct nonces and actual wall-clock separation", async () => {
    const first = await observe(1);
    await sleep(260);
    const second = await observe(2);
    windows = [first, second];
    decision = evaluateQaKnownManifest(candidate(windows));
    assert.equal(decision.state, "KNOWN_QA_DO_MANIFEST_TWO_OBSERVATIONS_PASS_GLOBAL_HOLD");
    assert.equal(decision.unique_nonces, 8);
    assert.equal(decision.all_live_commercial_instances_proven, false);
    assert.equal(decision.commercial_cutover_authorized, false);
    return { known_actors: 4, sample_interval_ms: second.observed_at_ms - first.observed_at_ms };
  });
  const negative = [
    ["missing actor", x => x.windows[0].witnesses.pop()],
    ["duplicate actor", x => x.windows[0].witnesses[3].alias = "quota-alpha"],
    ["manifest missing actor", x => x.manifest.pop()],
    ["manifest class mismatch", x => x.manifest[2].binding="TENANT_QUOTA"],
    ["source SHA drift", x => x.sourceSha256="0".repeat(64)],
    ["epoch drift", x => x.windows[0].witnesses[0].witness.epoch="QA_WRONG_EPOCH"],
    ["generation drift", x => x.windows[0].witnesses[0].witness.source_generation="UNPINNED"],
    ["witness unfenced", x => x.windows[0].witnesses[1].witness.fenced=false],
    ["nonce replay", x => x.windows[1].witnesses[0].witness.nonce=x.windows[0].witnesses[0].witness.nonce],
    ["clock gap zero", x => x.windows[1].observed_at_ms=x.windows[0].observed_at_ms],
    ["window missing", x => x.windows.pop()],
    ["global inventory overclaim",x=>x.windows[0].witnesses[0].witness.global_inventory_proven=true],
    ["provider convergence overclaim",x=>x.windows[0].witnesses[0].witness.provider_deployment_converged=true],
    ["approval overclaim",x=>x.windows[0].witnesses[0].witness.production_activation_authorized=true],
    ["inflight callback",x=>x.windows[0].witnesses[2].witness.callbacks_inflight=1],
    ["pending presence",x=>x.windows[0].witnesses[2].witness.presence_inflight=1],
    ["pending transient",x=>x.windows[0].witnesses[2].witness.transient_pending=1],
    ["open websocket",x=>x.windows[0].witnesses[2].witness.websockets=1],
    ["scheduled alarm",x=>x.windows[0].witnesses[2].witness.scheduled_alarm=true],
    ["local channel not drained",x=>x.windows[0].witnesses[2].witness.local_drained=false],
    ["lost protected row",x=>x.windows[1].witnesses[0].witness.protected_rows=1],
    ["changed quota units",x=>x.windows[1].witnesses[0].witness.protected_units=3],
  ];
  await check("corrupted DO witnesses or actor rosters fail closed", async () => {
    for (const [name, mutate] of negative) {
      const copy = JSON.parse(JSON.stringify(candidate(windows)));
      mutate(copy);
      assert.throws(() => evaluateQaKnownManifest(copy),
        /QA_DO_MANIFEST_/, "negative unexpectedly passed: "+name);
    }
    return { negatives_rejected: negative.length };
  });
  await check("an unregistered DO can remain mutable despite four known fences", async () => {
    const namespace = await mf.getDurableObjectNamespace("TENANT_QUOTA");
    const unseen = namespace.get(namespace.idFromName("QA_MANIFEST_UNREGISTERED_GAMMA"));
    const effect = await unseen.reserve(
      "QA_UNREGISTERED_EFFECT", subject, period, "tool:qa", 30
    );
    assert.equal(effect.ok,true);
    assert.equal((await unseen.cutoverFenceWitness("QA_UNREGISTERED_NONCE_20261113")).fenced,false);
    assert.equal(decision.all_live_commercial_instances_proven,false);
    return { unregistered_object_mutable: true, global_claim_denied: true };
  });
  await mf.dispose(); mf = undefined;
  await boot();
  await check("four fenced actors persist after workerd runtime restart", async () => {
    for (const {alias} of QA_MANIFEST) {
      const w = await actors.get(alias).cutoverFenceWitness(
        "QA_AFTER_RESTART_" + alias.replaceAll("-","_") + "_NONCE"
      );
      assert.equal(w.fenced,true);
      assert.equal(w.epoch,epoch);
    }
    const protectedRows = await actors.get("quota-alpha").cutoverFenceWitness(
      "QA_RESTART_PROTECTED_ROWS_20261113"
    );
    assert.equal(protectedRows.protected_rows,2);
    assert.equal(protectedRows.protected_units,2);
    return { persisted_known_fences: 4, protected_units: 2 };
  });
  console.log(JSON.stringify({
    schema:"hara.commander-qa-real-do-known-manifest.v1",
    state:"REAL_PRODUCT_DO_KNOWN_MANIFEST_WORKERD_PASS_GLOBAL_HOLD",
    source_worker_sha256:workerSha,
    cases:results,
    scoped_witness:decision,
    time_gap_ms:windows[1].observed_at_ms-windows[0].observed_at_ms,
    known_qa_actors:4,unregistered_qa_actor_observed:true,
    observer_scope:"LOCAL_WORKERD_KNOWN_SYNTHETIC_MANIFEST_ONLY",
    commercial_active_inventory_proven:false,
    two_global_quiescence_windows_proven:false,
    local_runtime_restart_proven:true,
    production_mutated:false,provider_called:false,
    commercial_cutover_authorized:false
  }));
} finally {
  if (mf) await mf.dispose();
}