import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import {fileURLToPath} from "node:url";

const dir=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const worker=fs.readFileSync(path.join(dir,"src/worker.js"),"utf8");
const js=fs.readFileSync(path.join(dir,"public/app.js"),"utf8");
const html=fs.readFileSync(path.join(dir,"public/index.html"),"utf8");
const css=fs.readFileSync(path.join(dir,"public/layout-legibility-r7.css"),"utf8");
function segment(source,start,end) {
  const i=source.indexOf(start),j=source.indexOf(end,i+start.length);
  assert.ok(i>=0 && j>i,"MISSING_REGION:"+start);
  return source.slice(i,j);
}
const counters={n:0};
function ok(condition,label){assert.ok(condition,label);counters.n++;console.log(label+"=PASS")}
function eq(a,b,label){assert.deepEqual(a,b,label);counters.n++;console.log(label+"=PASS")}

ok(html.includes('data-confirm-history-clear>Limpar histórico'),"HISTORY_CONFIRM_BUTTON_EXISTS");
ok(html.includes('data-history-clear-error role="alert"'),"HISTORY_HAS_VISIBLE_ERROR");
ok(!html.includes("Mostrar ocultos")&&!html.includes("Restaurar todos"),"NO_ARCHIVE_RESTORE_UI");
ok(!html.includes("Limpar visualização"),"NO_VISUAL_ONLY_CLEAR");
ok(!js.includes("archivedRevokedDeviceIds")&&!js.includes("loadHiddenRevokedIds")&&!js.includes("showArchivedHistory"),"NO_LOCAL_HISTORY_HIDE");
ok(js.includes('/api/portal/devices/history/clear'),"FRONTEND_USES_SERVER_ENDPOINT");
ok(js.includes('data-confirm-revoke-device'),"EXPLICIT_REVOKE_CONTROL_RETAINED");
ok(worker.includes('requirePortalMutationOrigin(request)')&&worker.includes('clearPortalDeviceHistory(env, session, body)'),"ROUTE_PROTECTED");
ok(worker.includes("LEFT JOIN commander_device_history h"),"READ_FILTERS_WITH_SERVER_PROJECTION");
ok(!segment(worker,"async function clearPortalDeviceHistory","function isRedactedDeviceCallContent").includes("DELETE FROM commander_devices"),"AUDIT_TOMBSTONES_PROTECTED");
ok(css.includes("device-history-error"),"HISTORY_ERROR_STYLED");

const section=segment(worker,"async function clearPortalDeviceHistory","function isRedactedDeviceCallContent");
const dbEvents=[];
function makeDB(total,{failBatch=false}={}) {
  return {
    prepare(sql){
      return {sql, bind(...args){this.args=args;return this},
        async first(){ dbEvents.push({action:"count",sql,args:this.args});return {total}; }
      };
    },
    async batch(statements) {
      dbEvents.push({action:"batch",statements:statements.map(s=>({sql:s.sql,args:s.args}))});
      const count=statements[0].args[2];
      return [{meta:{changes:failBatch?0:count}},{meta:{changes:failBatch?0:1}}];
    },
  };
}
let context=vm.createContext({Number,Error,String,crypto:globalThis.crypto,
  nowIso:()=> "2026-10-23T18:00:00Z"});
vm.runInContext(section,context,{timeout:3500});
const session={tenant_id:"tenant-A",subject_id:"admin-A",role:"OWNER"};
await assert.rejects(()=>context.clearPortalDeviceHistory({PRODUCT_DB:makeDB(1)}, {...session,role:"MEMBER"},{expected_count:1}),/DEVICE_HISTORY_CLEAR_FORBIDDEN/);
ok(true,"MEMBER_CANNOT_PURGE_HISTORY");
await assert.rejects(()=>context.clearPortalDeviceHistory({PRODUCT_DB:makeDB(1)},session,{expected_count:"1"}),/DEVICE_HISTORY_CLEAR_COUNT_INVALID/);
ok(true,"COUNT_MUST_BE_INTEGER");
await assert.rejects(()=>context.clearPortalDeviceHistory({PRODUCT_DB:makeDB(2)},session,{expected_count:1}),/DEVICE_HISTORY_CHANGED/);
ok(true,"COUNT_CONFLICT_DENIED");
const db=makeDB(2);
const result=await context.clearPortalDeviceHistory({PRODUCT_DB:db},session,{expected_count:2});
eq({state:result.state,count:result.deleted_count},{state:"CLEARED",count:2},"SERVER_CLEAR_CONFIRMED");
const batch=dbEvents.filter(x=>x.action==="batch").at(-1);
ok(batch.statements[0].sql.includes("DELETE FROM commander_device_history"),"DELETE_PHYSICAL_HISTORY_ROWS");
ok(batch.statements[1].sql.includes("INSERT INTO commander_device_history_clears"),"CLEAR_AUDIT_INSERTED");
eq(batch.statements[0].args,["tenant-A","tenant-A",2],"TENANT_SQL_SCOPE");
await assert.rejects(()=>context.clearPortalDeviceHistory({PRODUCT_DB:makeDB(2,{failBatch:true})},session,{expected_count:2}),/DEVICE_HISTORY_CHANGED/);
ok(true,"CONCURRENT_DELETE_FAILS_CLOSED");

const activeId="HARA-DEVICE-aabbdccc-0000-4000-9000-001122334455";
const revokedId="HARA-DEVICE-abbbbbbb-0000-4000-9000-aaaaaaaabbbb";
const oldId="HARA-DEVICE-bbbbbbbb-0000-4000-9000-bbbbbbbbbbbb";
const devs=[{device_id:activeId,state:"ACTIVE",device_name:"Linux"},
  {device_id:revokedId,state:"REVOKED",device_name:"Old Windows"},
  {device_id:oldId,state:"REVOKED",device_name:"Old Linux"}];
let paths=[],messages=[],rerenders=0,readback=true, failClearStatus=0;
function browserResponse(body,status=200){return new Response(JSON.stringify(body),{status});}
const env={
  Number,String,Set,Array,JSON,Date,Error,Response,
  deviceTab:"history",historyClearConfirmation:true,historyClearPending:false,
  historyClearFailureMessage:"",currentRole:"OWNER",
  sessionAuthenticated:true,portalSessionGeneration:1,historyScope:"tenant-A:admin-A",
  devicesCache:{devices:devs},devicesCacheAt:0,
  showToast:s=>messages.push(s),
  renderDevices:()=>rerenders++,
  handlePortalAuthFailure:()=>false,
  portalFetch:async(p,opts={})=>{
    paths.push({p,opts});
    if(p==="/api/portal/devices/history/clear"){
      return failClearStatus?browserResponse({code:"DEVICE_HISTORY_CHANGED"},failClearStatus):
        browserResponse({ok:true,state:"CLEARED",deleted_count:2});
    }
    assert.equal(p,"/api/portal/devices");
    return browserResponse({devices: readback?[devs[0]]:devs});
  }
};
let browser=vm.createContext(env);
const historySource=segment(js,"  function requestHistoryClear() {","  function deviceApprovalLabel(mode) {");
vm.runInContext(historySource,browser,{timeout:3500});
await browser.confirmHistoryClear({isConnected:true,disabled:false});
eq(paths.map(x=>x.p),["/api/portal/devices/history/clear","/api/portal/devices"],"CLEAR_POST_THEN_SERVER_READBACK");
eq(JSON.parse(paths[0].opts.body),{expected_count:2},"CLEAR_EXPECTED_COUNT_SENT");
eq(browser.devicesCache.devices.map(d=>d.device_id),[activeId],"CLEAR_REMOVES_HISTORY_FROM_CACHE");
ok(messages.some(m=>m.includes("Histórico limpo")),"SERVER_CONFIRMED_CLEAR_TOAST");
eq(devs[0].state,"ACTIVE","ACTIVE_DEVICE_UNTOUCHED");
paths=[]; browser.historyClearConfirmation=true;browser.currentRole="MEMBER";
await browser.confirmHistoryClear({isConnected:true});
eq(paths.length,0,"MEMBER_CLIENT_WILL_NOT_CLEAR");
browser.currentRole="OWNER"; browser.devicesCache={devices:devs};browser.historyClearConfirmation=true;
failClearStatus=409;paths=[];messages=[];
await browser.confirmHistoryClear({isConnected:true});
eq(paths.length,1,"CONFLICT_MUST_NOT_TRIGGER_GET");
ok(browser.historyClearFailureMessage.includes("histórico mudou"),"CONFLICT_VISIBLE_IN_UI");
ok(browser.historyClearConfirmation,"CONFLICT_KEEP_CONFIRMATION");
console.log("R13_UI_AND_BACKEND_HISTORY_TESTS_PASS="+counters.n);


// R12 fix must remain functional after R13 history deletion.
const revokeSource=segment(js,"  async function confirmDeviceRevocation(deviceId, trigger = null) {","  function setInstallOs(");
const revokeActive={device_id:activeId,device_name:"Linux test",state:"ACTIVE"};
const revokeOther={device_id:oldId,device_name:"Other Linux",state:"ACTIVE"};
let revokeCalls=[],revokeToasts=[],revokeTab="",revokeLoad=0,revokeCode=200;
const revokeEnv={
  JSON,Error,Number,String,Response,
  pendingRevokeDeviceId:activeId,revokeRequestPending:false,revokeFailureMessage:"",
  devicesCache:{devices:[revokeActive,revokeOther]},
  handlePortalAuthFailure:()=>false,
  portalFetch:async(route,req)=>{
    assert.equal(route,"/api/portal/devices/revoke");
    assert.equal(req.method,"POST");
    const body=JSON.parse(req.body);
    revokeCalls.push(body.device_id);
    if(revokeCode!==200)return browserResponse({code:"DENIED"},revokeCode);
    revokeActive.state="REVOKED";
    return browserResponse({ok:true,state:"REVOKED",device_id:body.device_id});
  },
  setDeviceTab:t=>{revokeTab=t;},
  loadDevices:async()=>{revokeLoad++;},
  renderDevices:()=>{},
  showToast:t=>{revokeToasts.push(t);}
};
const rc=vm.createContext(revokeEnv);
vm.runInContext(revokeSource,rc,{timeout:3500});
const trigger={disabled:false,textContent:"",isConnected:true};
await rc.confirmDeviceRevocation(activeId,trigger);
eq(revokeCalls,[activeId],"REVOKE_EXACT_DEVICE_ID_SINGLE_POST");
eq(revokeTab,"history","REVOKE_OPENS_HISTORY");
eq(revokeOther.state,"ACTIVE","REVOKE_OTHER_DEVICE_NOT_TOUCHED");
eq(revokeLoad,1,"REVOKE_REQUESTS_READBACK");
ok(revokeToasts.some(t=>t.includes("revogado")),"REVOKE_SHOWS_SERVER_CONFIRMED_SUCCESS");
revokeCode=403;revokeCalls=[];revokeToasts=[];revokeEnv.pendingRevokeDeviceId=oldId;
await rc.confirmDeviceRevocation(oldId,{disabled:false,textContent:"",isConnected:true});
eq(revokeCalls,[oldId],"REVOKE_NEGATIVE_POST_ONE_DEVICE");
ok(String(revokeEnv.revokeFailureMessage).includes("Sem permissão"),"REVOKE_403_VISIBLE_ERROR");
eq(revokeOther.state,"ACTIVE","REVOKE_DENIED_FAILS_CLOSED");
console.log("R13_ALL_REVOKE_AND_HISTORY_SCENARIOS_PASS="+counters.n);
