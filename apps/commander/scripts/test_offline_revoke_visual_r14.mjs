import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import {fileURLToPath} from "node:url";
import {DatabaseSync} from "node:sqlite";

const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const read=p=>fs.readFileSync(path.join(base,p),"utf8");
const js=read("public/app.js"),html=read("public/index.html"),css=read("public/layout-legibility-r7.css"),worker=read("src/worker.js");
const offlineId="HARA-DEVICE-64adbd7a-02b1-4890-acdb-9543e8b48d00";
const onlineId="HARA-DEVICE-ccccccc0-0000-4000-9000-000000000001";
const otherTenantId="HARA-DEVICE-ddddddd0-0000-4000-9000-000000000002";
const checks=[];
function pass(name){checks.push(name);console.log(name+"=PASS")}
function segment(src,a,b) {
  const i=src.indexOf(a),j=src.indexOf(b,i+a.length);
  assert.ok(i>=0&&j>i,"SOURCE_NOT_FOUND:"+a);
  return src.slice(i,j);
}
const first=segment(js,"  function revokeDevice(deviceId) {","  function cancelDeviceRevocation(deviceId) {");
let renderCalls=0,focusCalls=0,scrollCalls=0,networkCalls=0;
const messages=[];
const panel={
  scrollIntoView(x){scrollCalls++;assert.equal(x.block,"center");},
  focus(x){focusCalls++;assert.equal(x.preventScroll,true);}
};
const ctx=vm.createContext({
  String,
  document:{querySelector:s=>s==="[data-revoke-confirm-panel]"?panel:null},
  devicesCache:{devices:[
    {device_id:offlineId,device_name:"HARA_WIN11",state:"ACTIVE",online:false},
    {device_id:onlineId,device_name:"test-online",state:"ACTIVE",online:true}
  ]},
  revokeRequestPending:false,pendingRevokeDeviceId:null,expandedDeviceId:null,
  revokeFailureMessage:"",
  showToast:t=>messages.push(t),renderDevices:()=>{renderCalls++},
  portalFetch:()=>{networkCalls++;throw Error("NOT_ALLOWED")}
});
vm.runInContext(first,ctx);
ctx.revokeDevice(offlineId);
assert.equal(ctx.pendingRevokeDeviceId,offlineId);
assert.equal(ctx.expandedDeviceId,offlineId);
assert.equal(networkCalls,0);pass("OFFLINE_ACTIVE_FIRST_CLICK_NO_POST");
assert.equal(renderCalls,1);assert.equal(focusCalls,1);assert.equal(scrollCalls,1);
assert.ok(messages.at(-1).includes("offline não impede"));pass("CONFIRMATION_VISIBLE_AND_FOCUSED");
assert.ok(js.includes("confirmation.dataset.revokeConfirmPanel"));
assert.ok(js.includes("confirmation.tabIndex = -1"));pass("NEUTRAL_FOCUS_NOT_DESTRUCTIVE_BUTTON");
ctx.pendingRevokeDeviceId=null;
ctx.revokeDevice(onlineId);
assert.equal(ctx.pendingRevokeDeviceId,onlineId);
assert.equal(networkCalls,0);pass("ONLINE_SAME_EXPLICIT_CONFIRM");
ctx.pendingRevokeDeviceId=null;
ctx.devicesCache.devices[0].state="REVOKED";
ctx.revokeDevice(offlineId);
assert.equal(ctx.pendingRevokeDeviceId,null);assert.equal(networkCalls,0);
pass("ALREADY_REVOKED_REFUSED");
assert.ok(css.includes(".devices-panel-compact .empty-state {\n  border-top: 0;"));
assert.ok(css.includes(".devices-section-tabs {\n  border-bottom: 0;"));
assert.ok(css.includes(".device-overflow-actions,\nhtml[data-theme=\"dark\"] [data-view=\"devices\"] .device-overflow-actions"));
pass("UNWANTED_HORIZONTAL_LINES_REMOVED");
assert.ok(html.includes("app.js?v=20261023-revoke-click-r15"));
assert.ok(html.includes("layout-legibility-r7.css?v=20261023-offline-revoke-r14"));
pass("R14_ASSET_VERSIONS_BUSTED");
assert.ok(html.includes("ux-auth-settings-r11.css?v=20261023-gold-luxe-r11"));
assert.ok(js.includes("/api/portal/devices/history/clear"));
assert.ok(!js.includes("archivedRevokedDeviceIds"));pass("R11_STYLE_R13_HISTORY_PRESERVED");

const func=segment(worker,"async function revokePortalDevice(env, session, body) {",
  "async function clearPortalDeviceHistory(env, session, body = {}) {");
const db=new DatabaseSync(":memory:");
db.exec([
 "CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,revoked_at_utc TEXT,enrolled_by_subject_id TEXT)",
 "CREATE TABLE commander_device_calls(tenant_id TEXT,device_id TEXT,state TEXT,completed_at_utc TEXT,error_code TEXT)",
 "CREATE TABLE commander_device_selections(tenant_id TEXT,device_id TEXT)",
 "CREATE TABLE commander_device_history(tenant_id TEXT,device_id TEXT,revoked_at_utc TEXT,PRIMARY KEY(tenant_id,device_id))"
].join(";")+";");
const addDevice=db.prepare("INSERT INTO commander_devices VALUES(?,?,?,?,?)");
addDevice.run(offlineId,"tenant-A","ACTIVE",null,"subject-A");
addDevice.run(onlineId,"tenant-A","ACTIVE",null,"subject-A");
addDevice.run(otherTenantId,"tenant-B","ACTIVE",null,"subject-B");
db.prepare("INSERT INTO commander_device_calls(tenant_id,device_id,state) VALUES(?,?,?)").run("tenant-A",offlineId,"PENDING");
db.prepare("INSERT INTO commander_device_selections VALUES(?,?)").run("tenant-A",offlineId);
const mockDb={
  prepare(sql){return {sql,bind(...args){return{sql,args}}}},
  async batch(items){
    db.exec("BEGIN");
    try {
      const results=items.map(st=>({meta:{changes:Number(db.prepare(st.sql).run(...st.args).changes)}}));
      db.exec("COMMIT");
      return results;
    }catch(e){db.exec("ROLLBACK");throw e;}
  }
};
const ctxt=vm.createContext({
  Error,String,crypto:globalThis.crypto,
  cleanId:x=>String(x||""),
  nowIso:()=>"2026-10-23T19:00:00.000Z"
});
vm.runInContext(func,ctxt);
const owner={tenant_id:"tenant-A",subject_id:"subject-A",role:"OWNER"};
const ret=await ctxt.revokePortalDevice({PRODUCT_DB:mockDb},owner,{device_id:offlineId});
assert.equal(ret.ok,true);assert.equal(ret.state,"REVOKED");assert.equal(ret.device_id,offlineId);
assert.equal(db.prepare("SELECT state FROM commander_devices WHERE device_id=?").get(offlineId).state,"REVOKED");
pass("OFFLINE_BACKEND_REVOKES_WITHOUT_HEARTBEAT");
assert.equal(db.prepare("SELECT state FROM commander_device_calls WHERE device_id=?").get(offlineId).state,"CANCELLED");
assert.equal(db.prepare("SELECT count(*) AS n FROM commander_device_selections WHERE device_id=?").get(offlineId).n,0);
assert.equal(db.prepare("SELECT count(*) AS n FROM commander_device_history WHERE device_id=?").get(offlineId).n,1);
pass("PENDING_CALLS_CANCELLED_HISTORY_WRITTEN");
assert.equal(db.prepare("SELECT state FROM commander_devices WHERE device_id=?").get(onlineId).state,"ACTIVE");
pass("OTHER_DEVICE_UNTOUCHED");
await assert.rejects(()=>ctxt.revokePortalDevice({PRODUCT_DB:mockDb},owner,{device_id:otherTenantId}),/DEVICE_NOT_FOUND/);
assert.equal(db.prepare("SELECT state FROM commander_devices WHERE device_id=?").get(otherTenantId).state,"ACTIVE");
pass("CROSS_TENANT_DENIED");
await assert.rejects(()=>ctxt.revokePortalDevice({PRODUCT_DB:mockDb},owner,{device_id:offlineId}),/DEVICE_NOT_FOUND/);
pass("DUPLICATE_REVOKE_FAILS_CLOSED");
console.log("R14_OFFLINE_REVOKE_LINE_REMOVE_PASS="+checks.length);
