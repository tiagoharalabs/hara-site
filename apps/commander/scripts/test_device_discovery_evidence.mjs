import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const source = fs.readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/worker.js"),
  "utf8",
);

function section(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `FUNCTION_BOUNDARY_${start}`);
  return source.slice(first, last);
}

const scope = vm.createContext({
  Date,
  DEVICE_ONLINE_GRACE_SECONDS: 240,
  normalizeApprovalMode: (value) => value || "ASK_EVERY_ACTION",
});
vm.runInContext(
  section("function deviceOnline(", "function boundedJson(")
  + section("async function listDevices(", "async function enrollDevice("),
  scope,
  { timeout: 2000 },
);

const now = Date.now();
const ago = (seconds) => new Date(now - seconds * 1000).toISOString();
const rows = [
  { device_id: "event-recent", device_name: "event-recent", state: "ACTIVE", tunnel_mode: "EVENT_V2", last_seen_at_utc: ago(5 * 3600) },
  { device_id: "event-stale", device_name: "event-stale", state: "ACTIVE", tunnel_mode: "EVENT_V2", last_seen_at_utc: ago(8 * 3600) },
  { device_id: "relay-recent", device_name: "relay-recent", state: "ACTIVE", tunnel_mode: "OUTBOUND_RELAY", last_seen_at_utc: ago(120) },
  { device_id: "no-checkpoint", device_name: "no-checkpoint", state: "ACTIVE", tunnel_mode: "OUTBOUND_RELAY", last_seen_at_utc: null },
  { device_id: "invalid-checkpoint", device_name: "invalid-checkpoint", state: "ACTIVE", tunnel_mode: "OUTBOUND_RELAY", last_seen_at_utc: "not-a-time" },
  { device_id: "local", device_name: "local", state: "ACTIVE", tunnel_mode: "LOCAL_TUNNEL", last_seen_at_utc: ago(60) },
  { device_id: "declared-offline", device_name: "declared-offline", state: "ACTIVE", tunnel_mode: "EVENT_V2_OFFLINE", last_seen_at_utc: ago(60) },
  { device_id: "revoked", device_name: "revoked", state: "ACTIVE", tunnel_mode: "EVENT_V2", last_seen_at_utc: ago(60), revoked_at_utc: ago(30) },
];
const env = { PRODUCT_DB: { prepare: () => ({ bind: () => ({ all: async () => ({ results: rows }) }) }) } };
scope.env = env;
const devices = JSON.parse(JSON.stringify(await vm.runInContext(
  'listDevices(env, { tenant_id: "tenant-a" })', scope, { timeout: 2000 },
)));
const byId = Object.fromEntries(devices.map((device) => [device.device_id, device]));

assert.equal(byId["event-recent"].online, true);
assert.equal(byId["event-recent"].checkpoint_state, "RECENT");
assert.equal(byId["event-recent"].checkpoint_window_seconds, 7 * 3600);
assert.equal(byId["event-stale"].online, false);
assert.equal(byId["event-stale"].checkpoint_state, "STALE");
assert.equal(byId["relay-recent"].checkpoint_window_seconds, 240);
assert.equal(byId["no-checkpoint"].checkpoint_state, "NONE");
assert.equal(byId["invalid-checkpoint"].checkpoint_state, "NONE");
assert.equal(byId.local.checkpoint_state, "LOCAL_ONLY");
assert.equal(byId["declared-offline"].checkpoint_state, "TRANSPORT_OFFLINE");
assert.equal(byId.revoked.online, false);
assert.equal(byId.revoked.state, "ACTIVE");

scope.devices = devices;
const publicRows = JSON.parse(JSON.stringify(await vm.runInContext(
  "devices.map((device) => publicDeviceSummary(device))", scope, { timeout: 2000 },
)));
const publicById = Object.fromEntries(publicRows.map((device) => [device.device_id, device]));
assert.equal(publicById["event-recent"].registration_state, "ACTIVE");
assert.equal(publicById["event-recent"].state, "ONLINE");
assert.equal(publicById["event-recent"].checkpoint_state, "RECENT");
assert.equal(publicById["event-recent"].reachability_state, "NOT_PROBED");
assert.equal(publicById["event-recent"].last_seen_at_utc, byId["event-recent"].last_seen_at_utc);
assert.equal(publicById["event-stale"].state, "OFFLINE");
assert.equal(publicById.revoked.registration_state, "REVOKED");
assert.equal(publicById.revoked.state, "REVOKED");
assert.match(source, /devices\.map\(\(d\) => publicDeviceSummary\(d\)\)/);
console.log("COMMANDER_DEVICE_DISCOVERY_REGISTRATION_CHECKPOINT_REACHABILITY_DISTINCT=PASS");
