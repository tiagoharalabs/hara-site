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
const ledgerPruneBatch=Number(source.match(/const QUOTA_LEDGER_PRUNE_BATCH\s*=\s*(\d+)\s*;/)?.[1]);
assert.equal(ledgerPruneBatch,1000,"ledger pruning batch changed");
const approvalSource=fs.readFileSync(new URL("../src/approval-async-relay.mjs",new URL(`file://${fs.realpathSync(workerPath)}`)),"utf8");
const approvalTtl=Number(approvalSource.match(/const ASYNC_APPROVAL_RESERVATION_TTL_SECONDS\s*=\s*(\d+)\s*;/)?.[1]);
assert.equal(approvalTtl,1800,"approval reservation TTL changed");
const records=[];
const plain=(value)=>JSON.parse(JSON.stringify(value));
const iso=(value)=>new Date(value).toISOString();
const baseline=Date.parse("2026-10-31T23:45:00.000Z");
const receipt="a".repeat(64);
async function fixture({legacy=false,version1=false}={}) {
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
  if (version1) {
    db.exec(`CREATE TABLE request_state (
      request_id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,period_key TEXT NOT NULL,
      function_id TEXT NOT NULL,state TEXT NOT NULL,units INTEGER NOT NULL,
      receipt_sha256 TEXT,updated_at_utc TEXT NOT NULL,reservation_expires_at_utc TEXT
    );
    CREATE TABLE period_usage (period_key TEXT PRIMARY KEY,consumed_units INTEGER NOT NULL);
    CREATE TABLE quota_meta (id INTEGER PRIMARY KEY,usage_schema_version INTEGER NOT NULL);
    INSERT INTO quota_meta VALUES (1,1);
    CREATE TRIGGER trg_request_state_usage_delete AFTER DELETE ON request_state
    WHEN OLD.state IN ('RESERVED','COMMITTED') AND OLD.units<>0
    BEGIN UPDATE period_usage SET consumed_units=consumed_units-OLD.units WHERE period_key=OLD.period_key; END;
    INSERT INTO request_state VALUES ('V1-C','S1','2026-10','process.run','COMMITTED',1,'${receipt}','2026-10-20T00:00:00Z',NULL);
    INSERT INTO period_usage VALUES ('2026-10',1);`);
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
    ASYNC_APPROVAL_RESERVATION_TTL_SECONDS:approvalTtl,
    QUOTA_LEDGER_RETENTION_DAYS:90,QUOTA_LEDGER_PRUNE_BATCH:2});
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
await check("version1-delete-trigger-upgrades-without-refunding",(f)=>{
  assert.equal(f.db.prepare("SELECT usage_schema_version FROM quota_meta WHERE id=1").get().usage_schema_version,2);
  assert.equal(f.balance().consumed_units,1);
  f.db.prepare("DELETE FROM request_state WHERE request_id='V1-C'").run();
  assert.equal(f.balance().consumed_units,1);
},{version1:true});
await check("bounded-ledger-retention-preserves-quota-and-pending-proof",(f)=>{
  const paid=(id)=>{f.reserve(id,600,"S1","2026-09");f.quota.commit(id,"S1",receipt,10);};
  paid("PAID-C1");paid("PAID-C2");
  f.reserve("TRIAL-C",600,"S1","LIFETIME");f.quota.commit("TRIAL-C","S1",receipt,10);
  f.reserve("SETTLED-R",600,"S1","2026-09");
  assert.equal(f.quota.settleDeviceCall("SETTLED-R","S1","2026-09",1,null).state,"RELEASED");
  f.reserve("UNSETTLED-R",600,"S1","2026-09");f.quota.release("UNSETTLED-R","S1",10);
  assert.equal(f.reserve("DENIED",600,"S1","2026-09","process.run",0).state,"DENIED");
  f.reserve("PENDING",600,"S1","2026-09");
  f.db.prepare("UPDATE request_state SET updated_at_utc='2026-07-01T00:00:00.000Z'").run();
  f.db.prepare("UPDATE request_state SET settled_at_utc='2026-07-01T00:00:00.000Z' WHERE request_id='SETTLED-R'").run();
  const before=f.balance("2026-09").consumed_units;
  assert.equal(f.quota.compactLedger().deleted,2,"batch must remain bounded");
  assert.equal(f.quota.compactLedger().deleted,2);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM request_state WHERE request_id IN ('PAID-C1','PAID-C2','SETTLED-R','DENIED')").get().n,0);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM retired_request_state").get().n,4);
  assert.equal(f.reserve("PAID-C1",600,"S1","2026-09").code,"REQUEST_RETIRED");
  assert.equal(f.quota.commit("PAID-C1","S1",receipt,10).existing,true);
  assert.equal(f.quota.settleDeviceCall("PAID-C1","S1","2026-09",1,receipt).existing,true);
  assert.equal(f.quota.commit("PAID-C1","FOREIGN",receipt,10).code,"IDEMPOTENCY_CONFLICT");
  assert.equal(f.quota.commit("PAID-C1","S1","b".repeat(64),10).code,"IDEMPOTENCY_CONFLICT");
  assert.equal(f.quota.release("SETTLED-R","S1",10).existing,true);
  assert.equal(f.row("TRIAL-C").state,"COMMITTED");
  assert.equal(f.row("UNSETTLED-R").state,"RELEASED");
  assert.equal(f.row("PENDING").state,"RESERVED");
  assert.equal(f.balance("2026-09").consumed_units,before,"compaction refunded or added usage");
  assert.equal(f.balance("LIFETIME").consumed_units,1);
  const deletion=f.statements.find((entry)=>entry.sql.includes("DELETE FROM request_state") && entry.sql.includes("idx_request_state_retention"));
  assert(deletion,"bounded indexed retention query missing");
  const plan=f.db.prepare("EXPLAIN QUERY PLAN "+deletion.sql).all(...deletion.binds).map((row)=>row.detail);
  assert(plan.some((detail)=>detail.includes("idx_request_state_retention")),"retention index unused");
  assert.equal(f.db.prepare("PRAGMA integrity_check").get().integrity_check,"ok");
});
await check("active-quota-object-compacts-on-scheduled-status",(f)=>{
  assert.equal(f.reserve("OLD-DENIAL",600,"S1","2026-09","process.run",0).state,"DENIED");
  f.db.prepare("UPDATE request_state SET updated_at_utc='2026-07-01T00:00:00.000Z' WHERE request_id='OLD-DENIAL'").run();
  f.at(24*60*60*1000);
  assert.equal(f.quota.status("2026-09",10).consumed_units,0);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM request_state WHERE request_id='OLD-DENIAL'").get().n,0);
});
console.log(JSON.stringify({
  schema:"hara.commander-approval-async-quota-tests.v1",state:"PASS",
  scenarios:records.length,checks:records,sqlite:"IN_MEMORY_REAL_SQLITE",
  production_class_exercised:true,remote_services_used:false,
  worker_sha256:createHash("sha256").update(source).digest("hex"),
}));
