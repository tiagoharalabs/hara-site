import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { DatabaseSync } from "node:sqlite";
import { createHash } from "node:crypto";

// Exercise the actual production TenantQuota class against real SQLite,
// including its schema migration and accounting triggers. All state is in
// memory. The clock advances directly; no service, credentials or sleeps.
const workerPath=process.argv[2] || new URL("../src/worker.js",import.meta.url);
const source=fs.readFileSync(workerPath,"utf8");
const start=source.indexOf("export class TenantQuota extends DurableObject {");
const end=source.indexOf("\nasync function entitlementForTenant",start);
assert.ok(start>=0 && end>start,"production TenantQuota class missing");
const classSource=source.slice(start,end).replace("export class TenantQuota","class TenantQuota");
const defaultTtlExpression=source.match(/const QUOTA_RESERVATION_TTL_SECONDS\s*=\s*([\d\s*]+)\s*;/)?.[1];
assert.ok(defaultTtlExpression,"legacy reservation TTL expression missing");
const defaultTtl=Number(vm.runInNewContext(defaultTtlExpression));
assert.equal(defaultTtl,600,"legacy reservation TTL changed");
const approvalSource=fs.readFileSync(new URL("../src/approval-async-relay.mjs",new URL(`file://${fs.realpathSync(workerPath)}`)),"utf8");
const approvalTtl=Number(approvalSource.match(/const ASYNC_APPROVAL_RESERVATION_TTL_SECONDS\s*=\s*(\d+)\s*;/)?.[1]);
assert.equal(approvalTtl,1800,"approval reservation TTL changed");
const records=[];
const plain=(value)=>JSON.parse(JSON.stringify(value));
const iso=(value)=>new Date(value).toISOString();
const baseline=Date.parse("2026-10-31T23:45:00.000Z");
const receipt="a".repeat(64);
async function fixture({legacy=false}={}) {
  const db=new DatabaseSync(":memory:");
  let now=baseline;
  const statements=[];
  if (legacy) {
    db.exec(`CREATE TABLE request_state (
      request_id TEXT PRIMARY KEY, period_key TEXT NOT NULL,
      function_id TEXT NOT NULL, state TEXT NOT NULL, units INTEGER NOT NULL,
      receipt_sha256 TEXT, updated_at_utc TEXT NOT NULL
    );`);
    db.prepare("INSERT INTO request_state VALUES (?,?,?,?,?,?,?)").run(
      "legacy","2026-10","process.run","RESERVED",1,null,iso(now),
    );
  }
  class ClockDate extends Date {
    constructor(...args){super(...(args.length ? args : [now]));}
    static now(){return now;}
  }
  const pending=[];
  const ctx={
    blockConcurrencyWhile(callback){const p=callback();pending.push(p);return p;},
    storage:{sql:{exec(sql,...binds){
      statements.push({sql,binds:[...binds]});
      if (!binds.length && (/CREATE TABLE IF NOT EXISTS/.test(sql) || /DELETE FROM period_usage;/.test(sql) || /DROP TRIGGER IF EXISTS/.test(sql))) {
        db.exec(sql);return [];
      }
      return db.prepare(sql).all(...binds);
    }}},
  };
  class DurableObject {constructor(context){this.ctx=context;}}
  const runtime=vm.createContext({DurableObject,Date:ClockDate,
    QUOTA_RESERVATION_TTL_SECONDS:defaultTtl,
    ASYNC_APPROVAL_RESERVATION_TTL_SECONDS:approvalTtl});
  vm.runInContext(classSource+"\nglobalThis.QuotaClass=TenantQuota;",runtime);
  const quota=new runtime.QuotaClass(ctx,{});
  await Promise.all(pending);
  return {
    db,quota,statements,
    at(milliseconds){now=baseline+milliseconds;},
    row(id){return plain(db.prepare("SELECT * FROM request_state WHERE request_id = ?").get(id));},
    balance(period="2026-10"){return plain(quota.status(period,10,false));},
    reserve(id="R1",ttl=undefined,subject="S1",period="2026-10",fn="process.run",limit=10){
      return plain(quota.reserve(id,subject,period,fn,limit,ttl));
    },
    close(){db.close();},
  };
}
async function check(name,callback,options){
  const f=await fixture(options);
  try {await callback(f);records.push(name);} finally {f.close();}
}

await check("fresh-schema-real-accounting-triggers",(f)=>{
  const columns=f.db.prepare("PRAGMA table_info(request_state)").all();
  assert.ok(columns.some((column)=>column.name==="reservation_expires_at_utc"));
  assert.equal(f.reserve().state,"RESERVED");
  assert.equal(f.balance().consumed_units,1);
  assert.equal(f.quota.commit("R1","S1",receipt,10).state,"COMMITTED");
  assert.equal(f.balance().consumed_units,1,"commit must not charge twice");
});
await check("default-600-exact-expiry",(f)=>{
  f.reserve();
  assert.equal(f.row("R1").reservation_expires_at_utc,iso(baseline+600000));
  f.at(599999);f.quota.status("2026-10",10);
  assert.equal(f.row("R1").state,"RESERVED");
  f.at(600000);f.quota.status("2026-10",10);
  assert.equal(f.row("R1").state,"RELEASED");
  assert.equal(f.balance().consumed_units,0);
});
await check("approval-1800-survives-legacy-expiry",(f)=>{
  f.reserve("R1",1800);
  assert.equal(f.row("R1").reservation_expires_at_utc,iso(baseline+1800000));
  for (const offset of [600000,900000,1799999]) {
    f.at(offset);f.quota.status("2026-10",10);
    assert.equal(f.row("R1").state,"RESERVED");
    assert.equal(f.balance().consumed_units,1);
  }
  f.at(1800000);f.quota.status("2026-10",10);
  assert.equal(f.row("R1").state,"RELEASED");
  assert.equal(f.balance().consumed_units,0);
});
await check("pending-replay-cannot-extend-original-600",(f)=>{
  f.reserve();const expires=f.row("R1").reservation_expires_at_utc;
  f.at(500000);
  const repeated=f.reserve("R1",1800);
  assert.equal(repeated.existing,true);assert.equal(repeated.state,"RESERVED");
  assert.equal(f.row("R1").reservation_expires_at_utc,expires);
  assert.equal(f.balance().consumed_units,1);
  f.at(600000);
  assert.equal(f.reserve("R1",1800).state,"RELEASED");
  assert.equal(f.row("R1").reservation_expires_at_utc,expires);
});
await check("pending-replay-cannot-shorten-original-1800",(f)=>{
  f.reserve("R1",1800);const expires=f.row("R1").reservation_expires_at_utc;
  f.at(600000);assert.equal(f.reserve("R1",600).state,"RESERVED");
  assert.equal(f.row("R1").reservation_expires_at_utc,expires);
});
await check("internal-ttl-enumeration-rejects-invalid-input-before-write",(f)=>{
  for (const ttl of [null,0,30,900,1799,1801,"600","1800",NaN,Infinity,{},[]]) {
    const count=f.statements.length;
    assert.throws(()=>f.reserve("INVALID",ttl),/QUOTA_RESERVATION_TTL_INVALID/);
    assert.equal(f.statements.length,count,"invalid TTL reached storage");
  }
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM request_state").get().n,0);
});
await check("identity-function-period-replay-scoping",(f)=>{
  f.reserve("R1",1800);const before=f.row("R1");
  for (const [subject,period,fn] of [
    ["FOREIGN","2026-10","process.run"],
    ["S1","2026-11","process.run"],
    ["S1","2026-10","filesystem.write"],
  ]) {
    assert.equal(f.reserve("R1",1800,subject,period,fn).code,"IDEMPOTENCY_CONFLICT");
  }
  assert.deepEqual(f.row("R1"),before);
  assert.equal(f.balance().consumed_units,1);
});
await check("quota-capacity-and-denial-remain-unchanged",(f)=>{
  assert.equal(f.reserve("R1",1800,"S1","2026-10","process.run",1).state,"RESERVED");
  assert.equal(f.reserve("R2",1800,"S1","2026-10","process.run",1).code,"QUOTA_EXCEEDED");
  assert.equal(f.row("R2").state,"DENIED");assert.equal(f.row("R2").units,0);
  assert.equal(f.balance().consumed_units,1);
});
await check("lost-commit-response-safe-terminal-replay",(f)=>{
  f.reserve("R1",1800);f.at(900000);
  // Discard the first successful result to model a lost RPC response.
  f.quota.commit("R1","S1",receipt,10);
  const repeated=plain(f.quota.commit("R1","S1",receipt,10));
  assert.equal(repeated.ok,true);assert.equal(repeated.existing,true);
  assert.equal(repeated.state,"COMMITTED");assert.equal(f.balance().consumed_units,1);
  assert.equal(f.quota.commit("R1","S1","b".repeat(64),10).code,"IDEMPOTENCY_CONFLICT");
  assert.equal(f.quota.commit("R1","FOREIGN",receipt,10).code,"IDEMPOTENCY_CONFLICT");
  assert.equal(f.balance().consumed_units,1);
});
await check("committed-reservation-does-not-expire",(f)=>{
  f.reserve("R1",1800);f.quota.commit("R1","S1",receipt,10);
  f.at(7200000);f.quota.status("2026-10",10);
  assert.equal(f.row("R1").state,"COMMITTED");
  assert.equal(f.reserve("R1",600).state,"COMMITTED");
  assert.equal(f.balance().consumed_units,1);
});
await check("release-replay-refunds-once",(f)=>{
  f.reserve("R1",1800);f.quota.release("R1","S1",10);
  assert.equal(f.quota.release("R1","S1",10).existing,true);
  assert.equal(f.balance().consumed_units,0);
  assert.equal(f.reserve("R1",1800).state,"RELEASED");
  assert.equal(f.balance().consumed_units,0);
});
await check("legacy-schema-migration-preserves-default-600",(f)=>{
  const row=f.row("legacy");
  assert.equal(row.subject_id,"LEGACY");assert.equal(row.reservation_expires_at_utc,null);
  assert.equal(f.balance().consumed_units,1,"migration lost historical usage");
  f.at(599999);f.quota.status("2026-10",10);
  assert.equal(f.row("legacy").state,"RESERVED");
  f.at(600000);f.quota.status("2026-10",10);
  assert.equal(f.row("legacy").state,"RELEASED");assert.equal(f.balance().consumed_units,0);
},{legacy:true});
await check("mixed-legacy-and-profile-expiry-use-own-deadlines",(f)=>{
  f.reserve("R1",1800);
  f.at(600000);f.quota.status("2026-10",10);
  assert.equal(f.row("legacy").state,"RELEASED");assert.equal(f.row("R1").state,"RESERVED");
  assert.equal(f.balance().consumed_units,1);
},{legacy:true});
await check("completion-cross-month-settles-original-request-period",(f)=>{
  f.reserve("R1",1800);
  f.at(1000000); // November begins 900 seconds after the reservation.
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-11",1,receipt).code,"CALL_USAGE_BINDING_INVALID");
  assert.equal(f.quota.settleDeviceCall("R1","FOREIGN","2026-10",1,receipt).code,"CALL_USAGE_BINDING_INVALID");
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",2,receipt).code,"CALL_USAGE_BINDING_INVALID");
  assert.equal(f.quota.settleDeviceCall("MISSING","S1","2026-10",1,receipt).code,"CALL_USAGE_BINDING_INVALID");
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,receipt).state,"COMMITTED");
  assert.equal(f.row("R1").period_key,"2026-10");
  assert.equal(f.balance("2026-10").consumed_units,1);
  assert.equal(f.balance("2026-11").consumed_units,0);
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,receipt).existing,true);
});
await check("completion-cross-month-denial-refunds-original-period",(f)=>{
  f.reserve("R1",1800);f.at(1000000);
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,null).state,"RELEASED");
  assert.equal(f.balance("2026-10").consumed_units,0);
  assert.equal(f.balance("2026-11").consumed_units,0);
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,null).existing,true);
});
await check("proven-late-completion-restores-expired-reservation",(f)=>{
  f.reserve("R1",1800);f.at(1800000);
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,receipt).state,"COMMITTED");
  assert.equal(f.row("R1").state,"COMMITTED");assert.equal(f.balance().consumed_units,1);
  assert.equal(f.quota.settleDeviceCall("R1","S1","2026-10",1,receipt).existing,true);
  assert.equal(f.balance().consumed_units,1);
});
await check("retention-delete-never-refunds-committed-use",(f)=>{
  f.reserve("R1");f.quota.commit("R1","S1",receipt,10);
  assert.equal(f.balance().consumed_units,1);
  f.db.prepare("DELETE FROM request_state WHERE request_id='R1'").run();
  assert.equal(f.balance().consumed_units,1);
  f.reserve("R2");assert.equal(f.balance().consumed_units,2);
  f.db.prepare("DELETE FROM request_state WHERE request_id='R2'").run();
  assert.equal(f.balance().consumed_units,1,"uncommitted reservation must be refunded");
});
console.log(JSON.stringify({
  schema:"hara.commander-approval-async-quota-tests.v1",state:"PASS",
  scenarios:records.length,checks:records,sqlite:"IN_MEMORY_REAL_SQLITE",
  production_class_exercised:true,remote_services_used:false,
  worker_sha256:createHash("sha256").update(source).digest("hex"),
}));
