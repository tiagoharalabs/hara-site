#!/usr/bin/env node
// Execute the real production WebSocket device gate in an isolated context.
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../src/worker.js", import.meta.url), "utf8");
const start = source.indexOf("async function openDeviceEventChannel(env, request)");
const end = source.indexOf("\nasync function notifyDeviceEventChannel(", start);
if (start < 0 || end <= start) throw Error("EVENT_V2_FLEET_SOURCE_NOT_FOUND");
const founder = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62";
const sentinelaC = "HARA-DEVICE-11bbcaed-a0d5-4540-9d5a-40b84f1bdf74";
const stranger = "HARA-DEVICE-00000000-0000-0000-0000-000000000001";
let device;
let doCalls = 0;
const context = {
  eventV2Enabled: (env) => env.DEVICE_EVENT_V2_ENABLED === "true",
  resolveDeviceCredential: async () => device,
  deviceChannelName: (tenant, id) => tenant + ":" + id,
  json: (payload, status) => ({ payload, status }),
  Headers,
  Request,
};
const open = vm.runInNewContext(source.slice(start, end) +
  "\nopenDeviceEventChannel", context);
const makeEnv = (extras) => ({
  ENVIRONMENT: "PROD",
  DEVICE_EVENT_V2_ENABLED: "true",
  DEVICE_EVENT_V2_CANARY_DEVICE_ID: founder,
  DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS: extras,
  DEVICE_CHANNEL: {
    getByName: () => ({ fetch: async () => { doCalls++; return { status: 101 }; } }),
  },
});
const request = { headers: { get: () => "websocket" } };
async function shouldAllow(id, extras) {
  device = { tenant_id: "founder-tenant", device_id: id };
  doCalls = 0;
  const result = await open(makeEnv(extras), request);
  if (result.status !== 101 || doCalls !== 1) throw Error("ALLOW_FAILED:" + id);
}
async function shouldDeny(id, extras) {
  device = { tenant_id: "founder-tenant", device_id: id };
  doCalls = 0;
  try {
    await open(makeEnv(extras), request);
    throw Error("UNEXPECTED_ALLOWED:" + id);
  } catch (err) {
    if (String(err?.message) !== "DEVICE_EVENT_V2_CANARY_DENIED") throw err;
  }
  if (doCalls !== 0) throw Error("UNAUTHORIZED_DURABLE_OBJECT_ACCESS");
}
await shouldAllow(founder, sentinelaC);
await shouldAllow(sentinelaC, sentinelaC);
await shouldDeny(stranger, sentinelaC);
await shouldDeny(sentinelaC, "");
await shouldDeny(sentinelaC, "*");
await shouldDeny(sentinelaC, sentinelaC + "," + sentinelaC);
await shouldDeny(sentinelaC, founder + "," + sentinelaC);
await shouldDeny(sentinelaC, sentinelaC + ",garbage");
await shouldDeny(sentinelaC, [sentinelaC, ...Array(9).fill(stranger)].join(","));
console.log("EVENT_V2_FOUNDER_FLEET_CANARY_ALLOW=PASS");
console.log("EVENT_V2_UNLISTED_AUTHENTICATED_DEVICE_DENIED=PASS");
console.log("EVENT_V2_INVALID_WILDCARD_DUPLICATE_ALLOWLIST_DENIED=PASS");
console.log("EVENT_V2_UNAUTHORIZED_DO_ACCESS=DENIED");
