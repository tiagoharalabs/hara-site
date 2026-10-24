import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import {
 TELEMETRY_SCHEMA, TELEMETRY_FIELDS, TELEMETRY_MAX_COUNTER,
 canonicalChannelTelemetry, telemetryRollupQuery, readTenantDeviceTelemetry,
} from "../src/device-telemetry.mjs";

let checked=0;
function check(fn){fn();checked++;}
const good={
 schema:TELEMETRY_SCHEMA,window_days:7,
 ...Object.fromEntries(TELEMETRY_FIELDS.map((k,i)=>[k,i])),
};
check(()=>assert.deepEqual(canonicalChannelTelemetry(good),good));
check(()=>assert.equal(TELEMETRY_FIELDS.length,10));
for(const [name,v] of [
 ["no_schema",{...good,schema:null}],
 ["different_schema",{...good,schema:"untrusted"}],
 ["wrong_window",{...good,window_days:30}],
 ["extra_data",{...good,customer_content:"private command"}],
 ["tool_id",{...good,tool_id:"hara.process.run"}],
 ["argument",{...good,arguments:{content:"private"}}],
 ["negative",{...good,durable_calls:-1}],
 ["fraction",{...good,connections:0.2}],
 ["string",{...good,transient_calls:"3"}],
 ["bool",{...good,disconnects:true}],
 ["too_large",{...good,connected_seconds:1e15}],
 ["array",[good]],
 ["null",null],
]) check(()=>assert.throws(()=>canonicalChannelTelemetry(v),/CHANNEL_TELEMETRY_INVALID/,name));
check(()=>assert.equal(canonicalChannelTelemetry({...good,connections:TELEMETRY_MAX_COUNTER}).connections,TELEMETRY_MAX_COUNTER));

let sql="", binds=[];
const env={PRODUCT_DB:{prepare(s){sql=s;return {bind(...args){binds=args;return {sql,args,all:async()=>({results:[]})}}}}}};
const upsert=telemetryRollupQuery(env,"TENANT-A","DEVICE-A","2026-10-11T12:00:00Z",good);
check(()=>assert.equal(binds[0],"TENANT-A"));
check(()=>assert.equal(binds[1],"DEVICE-A"));
check(()=>assert.deepEqual(binds.slice(-2),["TENANT-A","DEVICE-A"]));
check(()=>assert.ok(sql.includes("FROM commander_devices d WHERE d.tenant_id = ? AND d.device_id = ?")));
check(()=>assert.ok(sql.includes("d.state = 'ACTIVE' AND d.revoked_at_utc IS NULL")));
check(()=>assert.ok(sql.includes("d.tunnel_mode = 'EVENT_V2'")));
check(()=>assert.ok(sql.includes("excluded.received_at_utc >= commander_device_telemetry_snapshot.received_at_utc")));
check(()=>assert.ok(!sql.includes("TENANT-A") && !sql.includes("DEVICE-A")));
check(()=>assert.equal(upsert.args.length,4+TELEMETRY_FIELDS.length+2));

const migration=fs.readFileSync(new URL("../migrations/0034_event_v2_telemetry_rollup_20261011.sql",import.meta.url),"utf8");
const py=String.raw`
import sqlite3,json,sys
info=json.loads(sys.stdin.read())
c=sqlite3.connect(":memory:")
c.execute("PRAGMA foreign_keys=ON")
c.execute("""CREATE TABLE commander_devices (
device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,state TEXT NOT NULL,
revoked_at_utc TEXT,tunnel_mode TEXT NOT NULL,device_name TEXT NOT NULL,
platform TEXT,agent_version TEXT,last_seen_at_utc TEXT,created_at_utc TEXT)""")
c.executescript(info["migration"])
def device(id,tenant,state="ACTIVE",mode="EVENT_V2"):
 c.execute("INSERT INTO commander_devices VALUES(?,?,?,NULL,?,?,?,'0.3.44','2026-10-11T12:00:00Z','2026-10-11')",
  (id,tenant,state,mode,id,"LINUX"))
device("DEVICE-A","TENANT-A")
device("DEVICE-B","TENANT-B")
device("DEVICE-REVOKED","TENANT-A","REVOKED")
sql=info["sql"];values=info["binds"]
c.execute(sql,values)
assert c.execute("SELECT COUNT(*) FROM commander_device_telemetry_snapshot").fetchone()[0]==1
assert c.execute("SELECT durable_calls FROM commander_device_telemetry_snapshot WHERE device_id='DEVICE-A'").fetchone()[0]==4
# Replay is an absolute replacement, not additive accumulation.
c.execute(sql,values)
assert c.execute("SELECT durable_calls FROM commander_device_telemetry_snapshot").fetchone()[0]==4
# A stale timestamp cannot replace a newer device report.
stale=values.copy();stale[2]="2026-10-10T00:00:00Z";stale[4+info["durable_index"]]=999
c.execute(sql,stale)
assert c.execute("SELECT durable_calls FROM commander_device_telemetry_snapshot").fetchone()[0]==4
# An old/cross-tenant socket cannot choose a different tenant key.
wrong=values.copy();wrong[0]="TENANT-B";wrong[1]="DEVICE-A";wrong[-2:]=["TENANT-B","DEVICE-A"]
c.execute(sql,wrong)
assert c.execute("SELECT COUNT(*) FROM commander_device_telemetry_snapshot").fetchone()[0]==1
# An inactive device cannot write a telemetry snapshot.
revoked=values.copy();revoked[1]="DEVICE-REVOKED";revoked[-1]="DEVICE-REVOKED"
c.execute(sql,revoked)
assert c.execute("SELECT COUNT(*) FROM commander_device_telemetry_snapshot").fetchone()[0]==1
# A valid separate tenant can persist independently.
other=values.copy();other[0]="TENANT-B";other[1]="DEVICE-B";other[-2:]=["TENANT-B","DEVICE-B"]
c.execute(sql,other)
assert c.execute("SELECT COUNT(*) FROM commander_device_telemetry_snapshot").fetchone()[0]==2
print("D1_SQLITE_EXACT_UPSERT=PASS")
`;
const result=spawnSync("python3",["-B","-c",py],{
 input:JSON.stringify({migration,sql,binds,durable_index:TELEMETRY_FIELDS.indexOf("durable_calls")}),
 encoding:"utf8",maxBuffer:100000,timeout:15000
});
check(()=>assert.equal(result.status,0,result.stderr));
check(()=>assert.match(result.stdout,/D1_SQLITE_EXACT_UPSERT=PASS/));

let latestQuery="", latestArgs=[];
const tenantEnv={PRODUCT_DB:{prepare(q){latestQuery=q;return {
 bind(...args){latestArgs=args;return {all:async()=>({results:[
  {device_id:"D1",computer:"host-a",platform:"LINUX",agent_version:"0.3.44",
   tunnel_mode:"EVENT_V2",last_seen_at_utc:"2026-10-11",
   last_reported_at_utc:"2026-10-11",window_days:7,...good},
  {device_id:"D2",computer:"host-b",platform:"LINUX",agent_version:"0.3.44",
   tunnel_mode:"EVENT_V2",last_seen_at_utc:"2026-10-11",
   last_reported_at_utc:null,window_days:null},
 ]})}}}
}}};
const fleet=await readTenantDeviceTelemetry(tenantEnv,"TENANT-A",null,50);
check(()=>assert.deepEqual(latestArgs,["TENANT-A",50]));
check(()=>assert.ok(latestQuery.includes("d.tenant_id = ?")));
check(()=>assert.ok(latestQuery.includes("t.tenant_id = d.tenant_id")));
check(()=>assert.equal(fleet.count,2));
check(()=>assert.equal(fleet.devices[0].metrics.durable_calls,good.durable_calls));
check(()=>assert.equal(fleet.devices[1].metrics,null));
check(()=>assert.ok(!JSON.stringify(fleet).includes("customer_content")));
await readTenantDeviceTelemetry(tenantEnv,"TENANT-A","host-a",1);
check(()=>assert.deepEqual(latestArgs,["TENANT-A","host-a",1]));
for(const v of [0,-1,101,"5",1.5]) {
 await (async()=>{await assert.rejects(
  ()=>readTenantDeviceTelemetry(tenantEnv,"TENANT-A",null,v),/TELEMETRY_LIMIT_INVALID/
 );checked++})();
}
console.log(JSON.stringify({schema:"hara.commander-device-telemetry-tests.v1",checked,passed:checked,failed:0,network:false,real_sqlite_exercised:true},null,2));
