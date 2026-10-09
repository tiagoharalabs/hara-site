#!/usr/bin/env node
// Isolated Worker handler regression: no Cloudflare credentials, no network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source=readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
const begin=source.indexOf("async function deviceAgentLifecycleTelemetry(");
const end=source.indexOf("async function deviceProductLease(",begin);
assert(begin>0 && end>begin,"worker function exists");
const code=source.slice(begin,end);
const events=[];
let reconciliations=0;
const device={
  device_id:"HARA-DEVICE-TEST",tenant_id:"HARA-TENANT-TEST",
  enrolled_by_subject_id:"HARA-SUBJECT-TEST",agent_version:"0.3.43",
  tunnel_mode:"LOCAL_TUNNEL",
};
const context={
  LOCAL_METERING_MIN_INTERVAL_SECONDS:3600,
  cleanId(value,max){
    if(typeof value!=="string" || value.length>max || !value) throw Error("INVALID_ID");
    return value;
  },
  cleanAgentValue(value){return String(value||"");},
  resolveDeviceCredential:async()=>device,
  reconcileLocalUsageReport:async(_env,_device,report)=>{
    assert(report.metadata_only===true && report.customer_content_included===false);
    reconciliations++;
  },
};
vm.createContext(context);
const telemetry=vm.runInContext(code+"\n;deviceAgentLifecycleTelemetry",context);
const db={
  prepare(query){
    return {
      query,
      args:[],
      bind(...args){this.args=args;return this;},
      async first(){
        const sql=this.query;
        const a=this.args;
        if(sql.includes("WHERE event_id=? AND device_id=?"))
          return events.find(e=>e.event_id===a[0] && e.device_id===a[1])||null;
        if(sql.includes("AND event_type=? LIMIT 1"))
          return events.find(e=>e.device_id===a[0] && e.session_id===a[1] && e.event_type===a[2])||null;
        if(sql.includes("event_type='AGENT_HEARTBEAT'")){
          const matches=events.filter(e=>e.device_id===a[0] && e.session_id===a[1] && e.event_type==="AGENT_HEARTBEAT");
          matches.sort((x,y)=>y.event_at_utc.localeCompare(x.event_at_utc));
          return matches[0]||null;
        }
        throw Error("UNEXPECTED_SQL:"+sql);
      },
    };
  },
  async batch(statements){
    for(const st of statements){
      if(st.query.startsWith("INSERT INTO commander_device_agent_telemetry")){
        const a=st.args;
        events.push({
          event_id:a[0],device_id:a[1],session_id:a[4],event_type:a[5],
          event_at_utc:a[6],received_at_utc:a[7],local_lifetime_units:a[9],
        });
      }else if(st.query.startsWith("UPDATE commander_devices")){
        device.last_seen_at_utc=st.args[0];
      }else throw Error("UNEXPECTED_BATCH_SQL");
    }
  },
};
const env={PRODUCT_DB:db};
const session="HARA-AGENT-SESSION-"+"c".repeat(32);
const base=Date.now()-5*3600*1000;
let sequence=0;
function make(type,minute,id=null){
  sequence++;
  return {
    schema:"hara.commander-agent-telemetry.v1",
    event_id:"HARA-AGENT-EVENT-"+(id||sequence.toString(16).padStart(32,"0")),
    event_type:type,session_id:session,
    event_at_utc:new Date(base+minute*60000).toISOString(),
    session_duration_seconds:minute*60,agent_version:"0.3.43",
    transport_mode:"LOCAL_TUNNEL",
    metadata_only:true,customer_content_included:false,
    usage_report:{
      schema:"hara.commander-local-usage-report.v1",
      lifetime_units:11,daily:[{day_key:"2026-10-08",units:11}],
      metadata_only:true,customer_content_included:false,
    },
  };
}
const start=make("AGENT_START",0);
let result=await telemetry(env,{},start);
assert(result.accepted===true && events.length===1);
console.log("WORKER_AGENT_TELEMETRY_START=PASS");
result=await telemetry(env,{},start);
assert(result.accepted===true && result.existing===true && events.length===1);
console.log("WORKER_AGENT_TELEMETRY_REPLAY_IDEMPOTENT=PASS");
result=await telemetry(env,{},make("AGENT_HEARTBEAT",60));
assert(result.accepted===true && events.length===2);
console.log("WORKER_AGENT_TELEMETRY_HEARTBEAT_1H=PASS");
result=await telemetry(env,{},make("AGENT_HEARTBEAT",90));
assert(result.accepted===false && result.code==="LOCAL_AGENT_HEARTBEAT_EARLY" && events.length===2);
console.log("WORKER_AGENT_TELEMETRY_EARLY_REJECT=PASS");
result=await telemetry(env,{},make("AGENT_HEARTBEAT",120));
assert(result.accepted===true && events.length===3);
console.log("WORKER_AGENT_TELEMETRY_OFFLINE_BACKFILL=PASS");
result=await telemetry(env,{},make("AGENT_STOP",121));
assert(result.accepted===true && events.length===4);
console.log("WORKER_AGENT_TELEMETRY_STOP_WITHIN_1H=PASS");
const invalid=make("AGENT_START",2);
invalid.customer_content_included=true;
await assert.rejects(telemetry(env,{},invalid),/LOCAL_AGENT_TELEMETRY_INVALID/);
console.log("WORKER_AGENT_TELEMETRY_PRIVACY_GUARD=PASS");
device.tunnel_mode="OUTBOUND_RELAY";
await assert.rejects(telemetry(env,{},make("AGENT_HEARTBEAT",180)),/LOCAL_METERING_REQUIRES_LOCAL_TUNNEL/);
console.log("WORKER_AGENT_TELEMETRY_RELAY_GUARD=PASS");
assert(reconciliations===4);
console.log("WORKER_AGENT_TELEMETRY_AGGREGATE_RECONCILE=PASS");
console.log("COMMANDER_AGENT_CLOUDFLARE_TELEMETRY=PASS");
