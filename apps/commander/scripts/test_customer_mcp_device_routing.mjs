import assert from "node:assert/strict";
import { chooseCustomerTargetDevice } from "../src/device-targeting.mjs";

const base = {
  tenant_id: "TENANT-A",
  enrolled_by_subject_id: "SUBJECT-A",
  platform: "LINUX",
  architecture: "x86_64",
  agent_version: "0.3.14",
  tunnel_mode: "OUTBOUND_RELAY",
  state: "ACTIVE",
  revoked_at_utc: null,
};
const nucleo = { ...base, device_id: "D-NUCLEO", device_name: "nucleo-a", online: true };
const c = { ...base, device_id: "D-C", device_name: "sentinela-c", online: true };
const old = { ...base, device_id: "D-OLD", device_name: "offline-box", online: false };
const isOnline = (device) => device.online === true;
const choose = (devices, extra = {}) => chooseCustomerTargetDevice(devices, {
  tenantId: "TENANT-A",
  isOnline,
  ...extra,
});

assert.equal(choose([nucleo, old]).device_id, "D-NUCLEO");
assert.throws(() => choose([nucleo, c]), /COMPUTER_REQUIRED/);
assert.equal(choose([nucleo, c], { requestedComputer: "SENTINELA-C" }).device_id, "D-C");
assert.throws(() => choose([nucleo], { requestedComputer: "missing" }), /DEVICE_NOT_FOUND/);
assert.throws(() => choose([{ ...nucleo, device_name: "dup" }, { ...c, device_name: "DUP" }], { requestedComputer: "dup" }), /COMPUTER_NAME_AMBIGUOUS/);
assert.throws(() => choose([{ ...nucleo, tenant_id: "TENANT-B" }], { requestedDeviceId: "D-NUCLEO" }), /DEVICE_NOT_FOUND/);
assert.equal(choose([old], { requestedComputer: "offline-box" }).device_id, "D-OLD");
assert.throws(() => choose([old]), /DEVICE_OFFLINE/);
console.log("COMMANDER_MCP_SOLE_ONLINE_AUTO_ROUTE=PASS");
console.log("COMMANDER_MCP_MULTI_ONLINE_REQUIRES_COMPUTER=PASS");
console.log("COMMANDER_MCP_EXPLICIT_COMPUTER_ROUTE=PASS");
console.log("COMMANDER_MCP_EXPLICIT_OFFLINE_ROUTE_RESOLVES_FOR_IDEMPOTENCY=PASS");
console.log("COMMANDER_MCP_CROSS_TENANT_TARGET=DENIED");
