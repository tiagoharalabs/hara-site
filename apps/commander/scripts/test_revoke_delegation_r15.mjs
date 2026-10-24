import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import {fileURLToPath} from "node:url";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const js=fs.readFileSync(path.join(root,"public/app.js"),"utf8");
const html=fs.readFileSync(path.join(root,"public/index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"public/layout-legibility-r7.css"),"utf8");
const worker=fs.readFileSync(path.join(root,"src/worker.js"),"utf8");
const test=(label,cond)=>{assert.ok(cond,label);console.log(label+"=PASS")};
const count=(source,s)=>source.split(s).length-1;

test("R15_TAB_DELEGATION_SCOPED_ALL_THREE",count(js,'.device-tabs button[data-device-tab]')===3);
test("R15_TAB_DELEGATION_NO_AMBIGUOUS_CLOSEST",!js.includes('event.target.closest("[data-device-tab]")'));
test("R15_LIST_NOT_TAB_BUTTON",js.includes("list.dataset.listTab = deviceTab")
  && !js.includes("list.dataset.deviceTab = deviceTab"));
test("R15_TAB_BUTTON_MARKUP_KEPT",count(html,'data-device-tab="active"')===1
  && count(html,'data-device-tab="history"')===1);
test("R15_ASSET_CACHE_BUST",html.includes('app.js?v=20261023-revoke-click-r15'));
test("R15_FIRST_CLICK_NO_API_WRITE",js.includes('function revokeDevice(deviceId) {')
  && js.includes('pendingRevokeDeviceId = id;')
  && js.includes('panel.scrollIntoView?.({ behavior: "smooth", block: "center" })'));
test("R15_CONFIRM_POST_STILL_EXPLICIT",js.includes('async function confirmDeviceRevocation')
  && js.includes('portalFetch("/api/portal/devices/revoke"')
  && js.includes('data-confirm-revoke-device'));
test("R15_OFFLINE_NOT_USED_AS_GATE",!js.slice(js.indexOf('  function revokeDevice(deviceId)'),js.indexOf('  function cancelDeviceRevocation')).includes('device.online'));
test("R15_BACKEND_REVOCATION_INDEPENDENT_OF_HEARTBEAT",
  worker.includes("async function revokePortalDevice") &&
  !worker.slice(worker.indexOf("async function revokePortalDevice"),worker.indexOf("async function clearPortalDeviceHistory")).includes("deviceOnline("));
test("R15_TOKEN_REJECTED_AFTER_REVOKE",worker.includes('device.state !== "ACTIVE" || device.revoked_at_utc'));
test("R15_HISTORY_CLEAR_PRESERVED",js.includes("/api/portal/devices/history/clear")
  && worker.includes("DELETE FROM commander_device_history"));
test("R15_R14_VISUAL_PRESERVED",css.includes(".devices-panel-compact .empty-state {\n  border-top: 0;")
  && css.includes(".device-overflow-actions,\nhtml[data-theme=\"dark\"] [data-view=\"devices\"] .device-overflow-actions"));
// Authenticating the old bearer after revocation must fail independently
// from whether the device can answer a heartbeat.
const verifySource=worker.slice(
  worker.indexOf("async function resolveDeviceCredential(env, request) {"),
  worker.indexOf("function activitySnapshotNumber("));
assert.ok(verifySource.startsWith("async function resolveDeviceCredential"));
const verifier=vm.createContext({
  Error,
  bearerToken:()=> "synthetic_test_token",
  sha256:async()=> "synthetic_hash"
});
vm.runInContext(verifySource,verifier,{timeout:1000});
const credentialDb=(state,revoked)=>({
  prepare(sql){
    assert.ok(sql.includes("WHERE credential_hash = ?"));
    return {bind(...args){
      assert.equal(args[0],"synthetic_hash");
      return {first:async()=>({
        device_id:"synthetic_offline_device", state, revoked_at_utc:revoked
      })};
    }};
  }
});
await assert.rejects(
  ()=>verifier.resolveDeviceCredential({PRODUCT_DB:credentialDb("REVOKED","2026-10-23T18:00:00Z")},{}),
  /DEVICE_AUTH_INVALID/);
console.log("R15_REVOKED_TOKEN_REJECTED_IN_BACKEND=PASS");
const valid=await verifier.resolveDeviceCredential({PRODUCT_DB:credentialDb("ACTIVE",null)},{});
assert.equal(valid.state,"ACTIVE");
console.log("R15_ACTIVE_TOKEN_STILL_VALID=PASS");
console.log("R15_DELEGATED_CLICK_REGRESSION_PASS=14");
