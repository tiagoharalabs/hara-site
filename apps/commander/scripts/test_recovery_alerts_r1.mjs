import assert from "node:assert/strict";
import {DatabaseSync} from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {
  recoveryAlertsEnabled,recoveryDeviceEnabled,readRecoveryEventBody,ingestRecoveryEvent,listRecoveryEvents,
  acknowledgeRecoveryEvent,detectOfflineRecoveryEvents,observeHeartbeatRecovery,
  cleanupRecoveryEvents,
} from "../src/recovery-alerts.mjs";
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const NOW=Date.parse("2026-10-24T12:00:00.000Z");
const at=delta=>new Date(NOW+delta).toISOString();
const count=db=>db.prepare("SELECT count(*) AS n FROM commander_device_recovery_events").get().n;
function harness() {
  const db=new DatabaseSync(":memory:");
  db.exec("CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);"+
          "CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,"+
          "state TEXT,revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,"+
          "last_seen_at_utc TEXT,created_at_utc TEXT)");
  db.exec(fs.readFileSync(path.join(ROOT,"migrations/0037_device_recovery_alerts.sql"),"utf8"));
  db.prepare("INSERT INTO tenants VALUES (?)").run("TENANT-A");
  db.prepare("INSERT INTO tenants VALUES (?)").run("TENANT-B");
  const add=(id,tenant="TENANT-A",state="ACTIVE",mode="OUTBOUND_RELAY",
    approval="PERSISTENT_TRUSTED",lastSeen=at(-300000),created=at(-86400000))=>
    db.prepare("INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)").run(
      id,tenant,state,state==="REVOKED"?at(-1000):null,approval,mode,lastSeen,created);
  add("DEV-A");add("DEV-B","TENANT-B");add("STOPPED","TENANT-A","ACTIVE","OUTBOUND_RELAY_OFFLINE");
  add("REVOKED","TENANT-A","REVOKED");add("ASK","TENANT-A","ACTIVE","OUTBOUND_RELAY","ASK_EVERY_ACTION");
  add("JUST-ENROLLED","TENANT-A","ACTIVE","OUTBOUND_RELAY","PERSISTENT_TRUSTED",at(-300000),at(-300000));
  const adapter={
    prepare:(sql)=>({
      bind:(...args)=>({
        first:async()=>db.prepare(sql).get(...args)||null,
        all:async()=>({results:db.prepare(sql).all(...args)}),
        run:async()=>({meta:{changes:db.prepare(sql).run(...args).changes}}),
      }),
    }),
  };
  const env={PRODUCT_DB:adapter,COMMANDER_RECOVERY_ALERTS_ENABLED:"true"};
  const device=(id="DEV-A",tenant="TENANT-A")=>{
    const row=db.prepare("SELECT * FROM commander_devices WHERE device_id=?").get(id);
    return {...row,tenant_id:tenant};
  };
  const admin=(tenant="TENANT-A",role="OWNER")=>({
    tenant_id:tenant,subject_id:"SUBJECT-"+tenant,role
  });
  return {db,add,env,device,admin};
}
function agentEvent(incident="INCIDENT-00001",sequence=1,state="STALLED",delta=-20000) {
  return {schema:"hara.commander.recovery-event.v1",incident_id:incident,
    generation:1,sequence,state,at_utc:at(delta)};
}
async function reject(asyncFn,code) {
  await assert.rejects(asyncFn,error=>error?.message===code,
    "Expected "+code);
}
async function tests() {
 let n=0;
 const check=(name)=>{n++;console.log("PASS "+name);};
 {
  const {env,device,db}=harness();
  assert.equal(recoveryAlertsEnabled(env),true);
  const e=agentEvent();
  env.COMMANDER_RECOVERY_ALERTS_ENABLED="false";
  await reject(()=>ingestRecoveryEvent(env,device(),e,NOW),"RECOVERY_ALERTS_DISABLED");
  assert.equal(count(db),0); check("feature_disabled_default_fail_closed");
 }
 {
  const {env,device,db,admin}=harness();
  const e=agentEvent();
  const ack=await ingestRecoveryEvent(env,device(),e,NOW);
  assert.equal(ack.ack,"PERSISTED");assert.equal(ack.external_delivery_confirmed,false);
  assert.equal(count(db),1);
  const again=await ingestRecoveryEvent(env,device(),e,NOW);
  assert.equal(again.duplicate,true);
  assert.equal(again.event_id,ack.event_id);
  assert.equal(count(db),1);
  check("persisted_durable_receipt_and_exact_replay");
  await reject(()=>ingestRecoveryEvent(env,device(),{...e,state:"RECOVERED"},NOW),"RECOVERY_EVENT_IDEMPOTENCY_CONFLICT");
  assert.equal(count(db),1);check("conflicting_replay_rejected");
  await reject(()=>ingestRecoveryEvent(env,device(),
    agentEvent("INCIDENT-00001",3,"RECOVERED"),NOW),
    "RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER");
  await ingestRecoveryEvent(env,device(),agentEvent("INCIDENT-00001",2,"RECOVERING"),NOW);
  assert.equal(count(db),2);check("out_of_order_denied");
  const someone=await ingestRecoveryEvent(env,device("DEV-B","TENANT-B"),agentEvent("INCIDENT-00001"),NOW);
  assert.notEqual(someone.event_id,ack.event_id);
  const list=await listRecoveryEvents(env,admin());
  assert.equal(list.events.length,2);
  assert.ok(list.events.every(e=>e.device_id==="DEV-A"));
  assert.equal(list.external_delivery_confirmed,false);
  const other=await listRecoveryEvents(env,admin("TENANT-B"));
  assert.equal(other.events.length,1);
  await reject(()=>listRecoveryEvents(env,admin("TENANT-A","MEMBER")),"RECOVERY_ALERTS_ADMIN_REQUIRED");
  await reject(()=>listRecoveryEvents(env,null),"AUTH_REQUIRED");
  check("tenant_isolation_and_admin_read");
  await reject(()=>acknowledgeRecoveryEvent(env,admin("TENANT-B"),{event_id:ack.event_id},NOW),"RECOVERY_EVENT_NOT_FOUND");
  await reject(()=>acknowledgeRecoveryEvent(env,admin("TENANT-A","MEMBER"),{event_id:ack.event_id},NOW),"RECOVERY_ALERTS_ADMIN_REQUIRED");
  const humanAck=await acknowledgeRecoveryEvent(env,admin(),{event_id:ack.event_id},NOW);
  assert.equal(humanAck.ack,"PORTAL_ACKNOWLEDGED");
  assert.equal(humanAck.external_delivery_confirmed,false);
  const repeated=await acknowledgeRecoveryEvent(env,admin(),{event_id:ack.event_id},NOW+9000);
  assert.equal(humanAck.acknowledged_at_utc,repeated.acknowledged_at_utc);
  check("separate_portal_human_ack_not_external_delivery");
  await reject(()=>ingestRecoveryEvent(env,device(),{...e,tenant_id:"TENANT-B"},NOW),"RECOVERY_EVENT_INVALID");
  await reject(()=>ingestRecoveryEvent(env,device(),{...e,device_id:"DEV-B"},NOW),"RECOVERY_EVENT_INVALID");
  await reject(()=>ingestRecoveryEvent(env,device("REVOKED"),e,NOW),"DEVICE_AUTH_INVALID");
  check("no_tenant_device_spoof_and_revoked_denied");
  for (const bad of [
    {...e,incident_id:"bad"},{...e,sequence:0},{...e,sequence:1.1},
    {...e,at_utc:at(600000)},{...e,at_utc:"2025-01-01T00:00:00Z"},
    {...e,state:"EXPLOITED"},{...e,error_code:"log_token_here!"},
    {...e,nested:{a:1}},
  ]) await reject(()=>ingestRecoveryEvent(env,device(),bad,NOW),
    bad.at_utc!==e.at_utc?"RECOVERY_EVENT_TIME_INVALID":"RECOVERY_EVENT_INVALID");
  check("input_type_boundaries");
 }
 {
  const clean=agentEvent();
  const body=new Request("https://dev.example/api/device/recovery-events",{method:"POST",
    headers:{"content-type":"application/json"},body:JSON.stringify(clean)});
  assert.deepEqual(await readRecoveryEventBody(body),clean);
  const dup='{"schema":"hara.commander.recovery-event.v1","schema":"hara.commander.recovery-event.v1"}';
  await reject(()=>readRecoveryEventBody(new Request("https://dev.example/",{method:"POST",body:dup})),"RECOVERY_EVENT_INVALID");
  await reject(()=>readRecoveryEventBody(new Request("https://dev.example/",{method:"POST",body:"x".repeat(2500)})),"RECOVERY_EVENT_BODY_TOO_LARGE");
  check("bounded_json_decoder_rejects_ambiguous_and_large_payloads");
 }
 {
  const {env,db,device,admin}=harness();
  const first=await detectOfflineRecoveryEvents(env,NOW,100);
  assert.equal(first.persisted,2);
  const stored=db.prepare("SELECT * FROM commander_device_recovery_events").all();
  assert.ok(stored.every(x=>x.origin==="SERVER" && x.event_state==="DEGRADED"));
  assert.ok(stored.every(x=>["DEV-A","DEV-B"].includes(x.device_id)));
  assert.ok(stored.every(x=>x.heartbeat_anchor_at_utc===at(-300000)));
  const next=await detectOfflineRecoveryEvents(env,NOW+2000,100);
  assert.equal(next.persisted,0);
  assert.equal(count(db),2);check("server_offline_dedup_and_exclude_stopped_revoked_ask_never_online");
  db.prepare("UPDATE commander_devices SET last_seen_at_utc=? WHERE device_id=?").run(at(0),"DEV-A");
  const restored=await observeHeartbeatRecovery(env,device("DEV-A"),NOW);
  assert.equal(restored,null); // Called AFTER update, requires pre-update device snapshot
  const oldDevice={...device("DEV-A"),last_seen_at_utc:at(-300000)};
  const recovery=await observeHeartbeatRecovery(env,oldDevice,NOW);
  assert.equal(recovery.ack,"PERSISTED");assert.equal(count(db),3);
  const one=db.prepare("SELECT event_state FROM commander_device_recovery_events WHERE device_id='DEV-A' ORDER BY sequence").all();
  assert.deepEqual(one.map(x=>x.event_state),["DEGRADED","RECOVERED"]);
  assert.equal((await listRecoveryEvents(env,admin())).events.length,2);
  check("recovery_after_real_heartbeat_correlated_to_offline_incident");
 }
 {
  const {env,db}=harness();
  db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='DEV-A'").run(at(-1000));
  const result=await detectOfflineRecoveryEvents(env,NOW,100);
  assert.equal(result.persisted,1);assert.equal(count(db),1);
  check("revocation_blocks_server_detection");
 }
 {
  const {env,db,device}=harness();
  const stale=await ingestRecoveryEvent(env,device(),agentEvent(),NOW-10);
  db.prepare("UPDATE commander_device_recovery_events SET persisted_at_utc=? WHERE event_id=?").run(
    at(-92*86400000),stale.event_id);
  const cleaned=await cleanupRecoveryEvents(env,NOW);
  assert.equal(cleaned.deleted,1);assert.equal(count(db),0);
  check("bounded_retention_cleanup");
 }
 {
  const {env,device,db}=harness();
  const e=agentEvent("INCIDENT-RACE01");
  const results=await Promise.all(Array.from({length:12},()=>ingestRecoveryEvent(env,device(),e,NOW)));
  assert.equal(results.filter(x=>!x.duplicate).length,1);
  assert.equal(count(db),1);
  check("concurrent_ingest_one_durable_row");
  db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='DEV-A'").run(at(-1000));
  await reject(()=>ingestRecoveryEvent(env,{...device(),state:"ACTIVE",revoked_at_utc:null},e,NOW),"DEVICE_AUTH_INVALID");
  check("revocation_blocks_exact_duplicate_even_after_source_read");
 }
 {
  const {env,device,db}=harness();
  await reject(()=>ingestRecoveryEvent(env,device(),
    agentEvent("INCIDENT-GAP101",2,"RECOVERING"),NOW),
    "RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER");
  assert.equal(count(db),0);
  await ingestRecoveryEvent(env,device(),agentEvent("INCIDENT-GAP101",1,"STALLED"),NOW);
  await reject(()=>ingestRecoveryEvent(env,device(),
    agentEvent("INCIDENT-GAP101",3,"RECOVERED"),NOW),
    "RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER");
  assert.equal(count(db),1);
  check("contiguous_incident_sequences_no_gaps");
 }
 const dev=JSON.parse(fs.readFileSync(path.join(ROOT,"wrangler.dev.jsonc"),"utf8"));
 const prod=JSON.parse(fs.readFileSync(path.join(ROOT,"wrangler.jsonc"),"utf8"));
 assert.ok(dev.triggers.crons.includes("* * * * *"));
 assert.equal(dev.vars.COMMANDER_RECOVERY_ALERTS_ENABLED,"false");
 // PROD cron triggers only a whitelist-scoped scanner. The checked-in config
 // remains feature-OFF without the explicit bounded device ID authorization.
 assert.ok(prod.triggers.crons.includes("* * * * *"));
 assert.ok(prod.triggers.crons.includes("17 * * * *"));
 assert.equal(prod.vars.COMMANDER_RECOVERY_ALERTS_ENABLED,undefined);
 assert.equal(prod.vars.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS,undefined);
 assert.equal(prod.routes?.[0]?.pattern,"commander.haralabs.com.br");
 assert.equal(prod.routes?.[0]?.custom_domain,true);
 check("prod_minute_cron_preserves_hourly_domain_and_fail_closed_source");
 const scheduleOnly=JSON.parse(fs.readFileSync(
   path.join(ROOT,"scripts/wrangler-triggers-only-prod-r163.jsonc"),"utf8"));
 assert.equal(scheduleOnly.name,prod.name);
 assert.equal(scheduleOnly.workers_dev,false);
 assert.equal(scheduleOnly.preview_urls,false);
 assert.deepEqual(scheduleOnly.triggers.crons,prod.triggers.crons);
 assert.equal("routes" in scheduleOnly,false);
 assert.equal("assets" in scheduleOnly,false);
 assert.equal("vars" in scheduleOnly,false);
 check("prod_triggers_only_profile_isolates_routes_bindings_and_secrets");
 const html=fs.readFileSync(path.join(ROOT,"public/index.html"),"utf8");
 const ui=fs.readFileSync(path.join(ROOT,"public/recovery-alerts.js"),"utf8");
 assert.ok(html.includes("recovery-alerts.js?v=")&&html.includes("recovery-alerts.css?v="));
 assert.ok(ui.includes("textContent=")&&ui.includes('result.ack==="PORTAL_ACKNOWLEDGED"'));
 assert.ok(!ui.includes("innerHTML")&&!ui.includes("localStorage")&&!ui.includes("sessionStorage"));
 assert.ok(ui.includes("credentials:\"same-origin\""));
 check("portal_alert_inbox_manual_ack_and_text_only");
 {
  const {env,db,device,admin}=harness();
  const codex={schema:"hara.commander.recovery-alert.proposal.v1",
    event_id:"e".repeat(32),client_incident_key:"a".repeat(32),
    transition_seq:1,worker:"executor",state:"STALLED",
    observed_at_utc:at(-15000),detector:"LINUX_PROCESS_GUARDIAN"};
  const first=await ingestRecoveryEvent(env,device(),codex,NOW);
  assert.equal(first.ack,"PERSISTED");assert.equal(first.client_event_id,codex.event_id);
  assert.equal(first.external_delivery_confirmed,false);
  assert.equal(count(db),1);
  const row=db.prepare("SELECT client_event_id,worker,detector FROM commander_device_recovery_events").get();
  assert.equal(row.client_event_id,codex.event_id);
  assert.equal(row.worker,"executor");
  assert.equal(row.detector,"LINUX_PROCESS_GUARDIAN");
  const dup=await ingestRecoveryEvent(env,device(),codex,NOW);
  assert.equal(dup.duplicate,true);
  check("codex_outbox_exact_envelope_and_stored_source_identity");
  await reject(()=>ingestRecoveryEvent(env,device(),{...codex,worker:"heartbeat"},NOW),"RECOVERY_EVENT_IDEMPOTENCY_CONFLICT");
  await reject(()=>ingestRecoveryEvent(env,device(),{...codex,event_id:"b".repeat(32)},NOW),"RECOVERY_EVENT_IDEMPOTENCY_CONFLICT");
  await reject(()=>ingestRecoveryEvent(env,device(),{...codex,tenant_id:"TENANT-B"},NOW),"RECOVERY_EVENT_INVALID");
  await reject(()=>ingestRecoveryEvent(env,device(),{...codex,token:"sensitive"},NOW),"RECOVERY_EVENT_INVALID");
  check("codex_outbox_conflicts_and_tenant_claim_rejected");
  const next=await ingestRecoveryEvent(env,device(),{...codex,event_id:"f".repeat(32),transition_seq:2,state:"RECOVERED"},NOW);
  assert.equal(next.ack,"PERSISTED");
  const list=await listRecoveryEvents(env,admin());
  assert.equal(list.events.length,2);
  assert.equal(list.events[0].detector,"LINUX_PROCESS_GUARDIAN");
  check("codex_outbox_ordered_transition_and_portal_read");
 }
 {
  const {env,db,device,add}=harness();
  const id="HARA-DEVICE-00000000-0000-4000-8000-000000000001";
  const other="HARA-DEVICE-00000000-0000-4000-8000-000000000002";
  add(id);add(other);
  env.ENVIRONMENT="PROD";
  assert.equal(recoveryDeviceEnabled(env,device(id)),false);
  await reject(()=>ingestRecoveryEvent(env,device(id),
    agentEvent("INCIDENT-PROD001"),NOW),"RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  assert.equal((await detectOfflineRecoveryEvents(env,NOW,500)).checked,0);
  assert.equal(count(db),0);
  check("prod_canary_absent_fail_closed");
  for(const invalid of ["DEV-A",id+","+id,Array.from({length:17},
    (_,i)=>"HARA-DEVICE-00000000-0000-4000-8000-"+String(i).padStart(12,"0")).join(",")]) {
    env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=invalid;
    assert.equal(recoveryDeviceEnabled(env,device(id)),false);
  }
  check("prod_invalid_or_oversized_allowlist_denied");
  env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=id;
  assert.equal(recoveryDeviceEnabled(env,device(id)),true);
  assert.equal(recoveryDeviceEnabled(env,device(other)),false);
  await reject(()=>ingestRecoveryEvent(env,device(other),
    agentEvent("INCIDENT-PROD002"),NOW),"RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  const saved=await ingestRecoveryEvent(env,device(id),
    agentEvent("INCIDENT-PROD003"),NOW);
  assert.equal(saved.ack,"PERSISTED");
  const scanner=await detectOfflineRecoveryEvents(env,NOW,500);
  assert.equal(scanner.checked,1);
  const otherEvents=db.prepare("SELECT COUNT(*) AS n FROM commander_device_recovery_events WHERE device_id=?").get(other).n;
  assert.equal(otherEvents,0);
  check("prod_canary_exact_device_scope");
  env.COMMANDER_RECOVERY_ALERTS_ENABLED="false";
  assert.equal(recoveryDeviceEnabled(env,device(id)),false);
  check("prod_global_kill_switch_works");
 }
 {
  const {env,db,device,admin,add}=harness();
  const canary="HARA-DEVICE-00000000-0000-4000-8000-000000000001";
  add(canary);
  const ordinary=await ingestRecoveryEvent(env,device("DEV-A"),
    agentEvent("INCIDENT-NONCANARY"),NOW);
  env.ENVIRONMENT="PROD";
  env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=canary;
  const observed=await ingestRecoveryEvent(env,device(canary),
    agentEvent("INCIDENT-CANARY01"),NOW);
  const scoped=await listRecoveryEvents(env,admin("TENANT-A"));
  assert.equal(scoped.events.length,1);
  assert.equal(scoped.events[0].device_id,canary);
  await reject(()=>listRecoveryEvents(env,admin("TENANT-B")),
    "RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  await reject(()=>acknowledgeRecoveryEvent(env,admin("TENANT-B"),
    {event_id:observed.event_id},NOW),"RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  await reject(()=>acknowledgeRecoveryEvent(env,admin("TENANT-A"),
    {event_id:ordinary.event_id},NOW),"RECOVERY_EVENT_NOT_FOUND");
  const ack=await acknowledgeRecoveryEvent(env,admin("TENANT-A"),
    {event_id:observed.event_id},NOW);
  assert.equal(ack.ack,"PORTAL_ACKNOWLEDGED");
  assert.equal(db.prepare("SELECT portal_ack_at_utc FROM commander_device_recovery_events WHERE event_id=?").get(ordinary.event_id).portal_ack_at_utc,null);
  check("prod_portal_scope_exact_canary_only");
  env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS="";
  await reject(()=>listRecoveryEvents(env,admin("TENANT-A")),
    "RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  check("prod_portal_scope_empty_allowlist_denied_before_query");
 }
 const worker=fs.readFileSync(path.join(ROOT,"src/worker.js"),"utf8");
 assert.ok(worker.includes("const persistInterval = recoveryDeviceEnabled(env,device) ? 60 : DEVICE_HEARTBEAT_PERSIST_SECONDS;"));
 assert.ok(worker.includes("const persistCutoff = new Date(Date.now() - persistInterval * 1000).toISOString();"));
 check("watch_heartbeat_persistence_60_seconds_only_when_feature_enabled");
 for (const token of [
  '"/api/device/recovery-events"','"/api/portal/recovery-events"',
  '"/api/portal/recovery-events/ack"','resolveDeviceCredential(env,request)',
  'detectOfflineRecoveryEvents(env)','observeHeartbeatRecovery(env,device',
  'recoveryAlertsEnabled(env)',
 ]) assert.ok(worker.includes(token),"missing wiring "+token);
 check("worker_route_source_wiring");
 console.log("RECOVERY_ALERTS_R1="+n+"_CHECKS_PASS");
}
tests().catch(error=>{console.error("RECOVERY_ALERTS_R1_FAIL",error);process.exitCode=1;});
