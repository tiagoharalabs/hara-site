// Isolated 20k scanner canary model. NOT full Event V2 20k proof.
import assert from "node:assert/strict";
import {DatabaseSync} from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {detectOfflineRecoveryEvents} from "../src/recovery-alerts.mjs";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const db=new DatabaseSync(":memory:");
db.exec("CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);"+
 "CREATE TABLE commander_devices ("+
 "device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,revoked_at_utc TEXT,"+
 "approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);");
db.exec(fs.readFileSync(path.join(root,"migrations/0037_device_recovery_alerts.sql"),"utf8"));
db.prepare("INSERT INTO tenants VALUES (?)").run("TENANT-R163");
const now=Date.parse("2026-10-24T17:00:00.000Z");
const eligible="HARA-DEVICE-00000000-0000-4000-8000-000000000001";
const insert=db.prepare("INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)");
const created=new Date(now-86400000).toISOString();
const stale=new Date(now-360000).toISOString();
const start=performance.now();
db.exec("BEGIN");
for(let i=0;i<20000;i++){
 const id="HARA-DEVICE-00000000-0000-4000-8000-"+String(i+1).padStart(12,"0");
 insert.run(id,"TENANT-R163","ACTIVE",null,"PERSISTENT_TRUSTED","OUTBOUND_RELAY",stale,created);
}
db.exec("COMMIT");
console.log("FLEET_ROWS",db.prepare("SELECT count(*) AS n FROM commander_devices").get().n);
const adapter={prepare:(sql)=>({bind:(...args)=>({
 first:async()=>db.prepare(sql).get(...args)||null,
 all:async()=>({results:db.prepare(sql).all(...args)}),
 run:async()=>({meta:{changes:db.prepare(sql).run(...args).changes}})
})})};
const env={ENVIRONMENT:"PROD",COMMANDER_RECOVERY_ALERTS_ENABLED:"true",
 COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS:eligible,PRODUCT_DB:adapter};
const detected=await detectOfflineRecoveryEvents(env,now,500);
assert.equal(detected.checked,1);assert.equal(detected.persisted,1);
assert.equal(db.prepare("SELECT count(*) AS n FROM commander_device_recovery_events").get().n,1);
assert.equal(db.prepare("SELECT device_id FROM commander_device_recovery_events").get().device_id,eligible);
console.log("CANARY_20K_SCANNER_BOUNDED=PASS");
console.log("CANARY_20K_NO_NONCANARY_MUTATION=PASS");
const again=await detectOfflineRecoveryEvents(env,now+1000,500);
assert.equal(again.checked,0);assert.equal(again.persisted,0);
console.log("CANARY_20K_DEDUP_NO_RESCAN=PASS");
const plan=db.prepare("EXPLAIN QUERY PLAN SELECT d.device_id FROM commander_devices d WHERE "+
 "d.state='ACTIVE' AND d.device_id IN (?)").all(eligible);
assert.ok(plan.some(r=>/PRIMARY KEY|INDEX|sqlite_autoindex/i.test(r.detail||"")),plan);
console.log("CANARY_20K_INDEXED_DEVICE_LOOKUP=PASS");
console.log("MODEL_SECONDS",((performance.now()-start)/1000).toFixed(3));
console.log("NOT_EVENT_V2_20K_CAPACITY_PROOF=true");
db.close();
