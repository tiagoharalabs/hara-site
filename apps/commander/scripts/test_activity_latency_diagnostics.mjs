import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";
import { summarizeRecentLatency } from "../src/activity-latency.mjs";

const base = dirname(fileURLToPath(import.meta.url));
const worker = readFileSync(resolve(base, "../src/worker.js"), "utf8");
assert.match(worker, /summarizeRecentLatency\(transactions,limit\)/);
assert.match(worker, /recent_latency:cloud\.diagnostics\?\.recent_latency/);

const rows = [
  { state:"COMPLETED", tool_id:"hara.files.read", computer:"Services", transport_mode:"EVENT_V2",
    queue_ms:100, execution_ms:500, total_ms:600 },
  { state:"COMPLETED", tool_id:"hara.files.read", computer:"Services", transport_mode:"EVENT_V2",
    queue_ms:200, execution_ms:600, total_ms:800 },
  { state:"COMPLETED", tool_id:"hara.files.read", computer:"Services", transport_mode:"EVENT_V2",
    queue_ms:4000, execution_ms:600, total_ms:4600 },
  { state:"COMPLETED", tool_id:"hara.process.run", computer:"C", transport_mode:"OUTBOUND_RELAY",
    queue_ms:null, execution_ms:700, total_ms:900 },
  { state:"FAILED", tool_id:"hara.files.read", computer:"Services", transport_mode:"EVENT_V2",
    queue_ms:9000, execution_ms:100, total_ms:9100 },
];

const result = summarizeRecentLatency(rows, 100);
assert.equal(result.source, "CLOUD_SERVER_TIMESTAMPS");
assert.equal(result.scope, "RECENT_RETURNED_CALLS");
assert.equal(result.returned_rows, 5);
assert.equal(result.completed_rows, 4);
assert.equal(result.requested_limit, 100);
assert.equal(result.metrics.queue_ms.sample_size, 3);
assert.equal(result.metrics.queue_ms.missing_count, 1);
assert.equal(result.metrics.queue_ms.p50, 200);
assert.equal(result.metrics.queue_ms.p95, 4000);
assert.equal(result.metrics.execution_ms.sample_size, 4);
assert.equal(result.by_tool[0].tool_id, "hara.files.read");
assert.equal(result.by_tool[0].metrics.queue_ms.p99, 4000);
assert.equal(result.by_device[0].computer, "Services");
assert.equal(result.by_transport[0].transport_mode, "EVENT_V2");
assert.equal(result.by_tool_device[0].tool_id, "hara.files.read");
assert.equal(result.by_tool_device[0].computer, "Services");
assert.equal(result.by_tool_device[0].transport_mode, "EVENT_V2");
assert.deepEqual(result.by_tool[1].metrics.queue_ms,
  { sample_size:0, missing_count:1, avg:null, p50:null, p95:null, p99:null });
console.log("COMMANDER_RECENT_LATENCY_SERVER_SAMPLE_GROUPS_AND_MISSING_VALUES=PASS");

const empty = summarizeRecentLatency([], 25);
assert.equal(empty.metrics.queue_ms.sample_size, 0);
assert.equal(empty.metrics.queue_ms.p95, null);
assert.deepEqual(empty.by_tool, []);
console.log("COMMANDER_RECENT_LATENCY_EMPTY_SAMPLE_NOT_ZERO=PASS");

const slice = (start, end) => {
  const from = worker.indexOf(start);
  const to = worker.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `${start} -> ${end}`);
  return worker.slice(from, to);
};
const source = [
  slice("function portalActivitySource(", "function elapsedMs("),
  slice("function elapsedMs(", "function portalActivityWindow("),
  slice("function portalActivityWindow(", "function betaAccessCanManage("),
  slice("async function portalActivity(", "async function executeCustomerMcpTool("),
].join("\n");
const activity = vm.runInNewContext(`${source}\nportalActivity`, {
  Date,
  summarizeRecentLatency,
  portalActivityFromLocalSnapshots:async () => null,
  mergePortalActivity:(_local, cloud) => cloud,
});
const callRows = [
  { call_id:"1", request_id:"HARA-QA-1", tool_id:"hara.files.read", state:"COMPLETED",
    created_at_utc:"2026-10-20T22:00:00.000Z", claimed_at_utc:"2026-10-20T22:00:00.100Z",
    completed_at_utc:"2026-10-20T22:00:00.600Z", device_name:"Services", tunnel_mode:"EVENT_V2" },
  { call_id:"2", request_id:"HARA-QA-2", tool_id:"hara.files.read", state:"COMPLETED",
    created_at_utc:"2026-10-20T22:00:01.000Z", claimed_at_utc:"2026-10-20T22:00:01.200Z",
    completed_at_utc:"2026-10-20T22:00:01.800Z", device_name:"Services", tunnel_mode:"EVENT_V2" },
  { call_id:"3", request_id:"HARA-QA-3", tool_id:"hara.files.read", state:"COMPLETED",
    created_at_utc:"2026-10-20T22:00:02.000Z", claimed_at_utc:null,
    completed_at_utc:"2026-10-20T22:00:03.000Z", device_name:"Services", tunnel_mode:"EVENT_V2" },
];
const sqlSeen = [];
const env = { PRODUCT_DB:{ prepare(sql) {
  sqlSeen.push(sql);
  return { bind() { return {
    first:async () => ({ total_calls:3, completed:3, device_count:1, transport_modes:"EVENT_V2" }),
    all:async () => ({ results:sql.includes("SELECT c.call_id") ? callRows : [] }),
  }; } };
} } };
const projected = await activity(env, {tenant_id:"T-QA", subject_id:"S-QA", role:"MEMBER"}, 100, "24h");
assert.equal(sqlSeen.length, 4);
assert.equal(projected.transactions.length, 3);
assert.equal(projected.transactions[2].queue_ms, null);
assert.equal(projected.diagnostics.recent_latency.metrics.queue_ms.sample_size, 2);
assert.equal(projected.diagnostics.recent_latency.metrics.queue_ms.missing_count, 1);
assert.equal(projected.diagnostics.recent_latency.metrics.queue_ms.p95, 200);
assert.equal(projected.diagnostics.recent_latency.by_tool[0].tool_id, "hara.files.read");
console.log("COMMANDER_ACTIVITY_WORKER_PUBLIC_PROJECTION_EXACT_TIMESTAMPS=PASS");
