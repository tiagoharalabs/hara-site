#!/usr/bin/env node
// Real rollup migration + Worker history/prune functions over isolated D1 SQL.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { DatabaseSync } from "node:sqlite";

const app=new URL("../",import.meta.url);
const worker=fs.readFileSync(new URL("src/worker.js",app),"utf8");
const migration="0039_device_call_history_rollup_retention.sql";
const db=new DatabaseSync(":memory:");
for (const name of fs.readdirSync(new URL("migrations/",app)).filter(x=>x.endsWith(".sql")&&x!==migration).sort()) {
  db.exec(fs.readFileSync(new URL(`migrations/${name}`,app),"utf8"));
}
const DAY=24*60*60*1000;
const nowMs=Date.now();
const iso=(offset)=>new Date(nowMs+offset).toISOString();
class ClockDate extends Date {
  constructor(...args){super(...(args.length?args:[nowMs]));}
  static now(){return nowMs;}
}
const now=new ClockDate().toISOString();
db.prepare("INSERT INTO tenants VALUES ('T1','History QA','ACTIVE','DEV',?)").run(now);
db.prepare("INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES ('S1','T1','https://fixture.invalid','subject','ACTIVE','OWNER',?)").run(now);
db.prepare("INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc) VALUES ('P1','HASH','T1','S1',?,?)").run(now,now);
db.prepare("INSERT INTO commander_devices (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,agent_version,tunnel_mode,credential_hash,state,created_at_utc) VALUES ('D1','P1','T1','S1','History QA','LINUX','0.3.43','OUTBOUND_RELAY','CREDENTIAL','ACTIVE',?)").run(now);
const seed=(id,created,{settled=true}={})=>{
  db.prepare("INSERT INTO commander_device_calls (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,created_at_utc,expires_at_utc,completed_at_utc,usage_mode,usage_units,usage_period_key,call_result_metadata_json,usage_settled_at_utc) VALUES (?,?,'T1','S1','D1','hara.files.read','{}','COMPLETED',?,?,?,'CLOUD_QUOTA',1,'2026-10','{}',?)")
    .run(id,id,created,created,created,settled?created:null);
};
seed("OLD-SETTLED",iso(-110*DAY));
seed("OLD-UNSETTLED",iso(-110*DAY+60*60*1000),{settled:false});
seed("RECENT",iso(-30*60*1000));
seed("BOUNDARY-IN",iso(-7*DAY+15*60*1000));
seed("BOUNDARY-OUT",iso(-7*DAY-15*60*1000));
const migrationSql=fs.readFileSync(new URL(`migrations/${migration}`,app),"utf8");
db.exec(migrationSql);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM commander_device_call_history_hourly WHERE hour_key<?").get(iso(-9*DAY).slice(0,13)).n,0);

const wrap=(sql,binds=[])=>({
  async first(){return db.prepare(sql).get(...binds)||null;},
  async run(){return {meta:{changes:Number(db.prepare(sql).run(...binds).changes)}};},
});
const env={PRODUCT_DB:{prepare(sql){return {bind(...binds){return wrap(sql,binds);}};}}};
function extract(name){
  const start=worker.indexOf(`async function ${name}(`);
  assert(start>=0,`missing ${name}`);
  const end=worker.indexOf("\n}",start);
  assert(end>start);
  return worker.slice(start,end+2);
}
const runtime=vm.createContext({Date:ClockDate,DEVICE_CALL_HISTORY_RETENTION_DAYS:90,
  DEVICE_CALL_HISTORY_PRUNE_BATCH:500,DEVICE_CALL_HISTORY_HOURLY_PRUNE_BATCH:5000});
vm.runInContext(extract("productTransactionHistory")+"\n"+extract("pruneDeviceCallHistory")+
  "\nglobalThis.history=productTransactionHistory;globalThis.prune=pruneDeviceCallHistory;",runtime);
const read=()=>runtime.history(env,"T1","S1");
let view=await read();
assert.equal(view.available,true);
assert.equal(view.calls_total,5);
assert.equal(view.calls_7d,2);
console.log("COMMANDER_HISTORY_BACKFILL_EXACT_SEVEN_DAY_BOUNDARY=PASS");

db.prepare("INSERT INTO commander_device_call_history_hourly VALUES ('T1','S1',?,1)").run(iso(-20*DAY).slice(0,13));
const pruned=await runtime.prune(env);
assert.equal(pruned.call_rows,1);
assert.equal(pruned.hour_rows,1);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM commander_device_calls WHERE call_id='OLD-SETTLED'").get().n,0);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM commander_device_calls WHERE call_id='OLD-UNSETTLED'").get().n,1);
view=await read();
assert.equal(view.calls_total,5);
assert.equal(view.calls_7d,2);
console.log("COMMANDER_HISTORY_PRUNE_PRESERVES_TOTAL_AND_UNSETTLED_PROOF=PASS");

seed("AFTER-MIGRATION",now);
view=await read();
assert.equal(view.calls_total,6);
assert.equal(view.calls_7d,3);
db.exec(migrationSql);
view=await read();
assert.equal(view.calls_total,6);
assert.equal(view.calls_7d,3);
assert.equal((await runtime.history(env,"T1","FOREIGN")).calls_total,0);
assert.equal(db.prepare("PRAGMA integrity_check").get()["integrity_check"],"ok");
console.log("COMMANDER_HISTORY_INSERT_TRIGGER_AND_MIGRATION_REPLAY_IDEMPOTENT=PASS");
db.close();
