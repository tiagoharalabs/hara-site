// #163 independent server detector: actual DeviceChannel + canonical recovery
// writer in a VM, real SQLite and synthetic hibernation/socket/clock boundaries.
// No network, Agent install, native alarm scheduler or 20k capacity is proven.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';

const BASE=Date.parse('2026-10-25T00:00:00.000Z');
const CONTRACT='commercial-0.3.56-durable-dev.v1';
const channelSource=fs.readFileSync(new URL('../src/device-channel.mjs',import.meta.url),'utf8');
const recoverySource=fs.readFileSync(new URL('../src/recovery-alerts.mjs',import.meta.url),'utf8');
const withoutImports=source=>source.replace(/^import\s[\s\S]*?;\r?\n/gm,'').replace(/^export /gm,'');
const sha=value=>createHash('sha256').update(value).digest('hex');
const plain=value=>JSON.parse(JSON.stringify(value));

function fixture(t){
  let now=BASE;
  const db=new DatabaseSync(':memory:');
  db.exec(`PRAGMA foreign_keys=ON;
    CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);
    INSERT INTO tenants VALUES('TENANT-A');
    CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,
      state TEXT NOT NULL,revoked_at_utc TEXT,platform TEXT,approval_mode TEXT,
      agent_version TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);
    INSERT INTO commander_devices VALUES('DEVICE-A','TENANT-A','ACTIVE',NULL,
      'LINUX','PERSISTENT_TRUSTED','0.3.56','EVENT_V2',
      '2026-10-25T00:00:00.000Z','2026-10-24T00:00:00.000Z');
    CREATE TABLE commander_device_recovery_events(
      event_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,device_id TEXT NOT NULL,
      incident_id TEXT NOT NULL,generation INTEGER NOT NULL,sequence INTEGER NOT NULL,
      event_state TEXT NOT NULL CHECK(event_state IN ('STALLED','RECOVERING','RECOVERED','DEGRADED')),
      origin TEXT NOT NULL CHECK(origin IN ('AGENT','SERVER')),
      client_event_id TEXT,worker TEXT,detector TEXT,error_code TEXT,
      event_at_utc TEXT NOT NULL,heartbeat_anchor_at_utc TEXT,payload_sha256 TEXT NOT NULL,
      persisted_at_utc TEXT NOT NULL,portal_ack_at_utc TEXT,portal_ack_subject_id TEXT,
      UNIQUE(tenant_id,device_id,incident_id,generation,sequence),
      FOREIGN KEY(device_id) REFERENCES commander_devices(device_id),
      FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id));
    CREATE UNIQUE INDEX idx_recovery_event_client_identity ON commander_device_recovery_events
      (tenant_id,device_id,client_event_id) WHERE client_event_id IS NOT NULL;
    CREATE INDEX idx_recovery_events_device_incident ON commander_device_recovery_events
      (device_id,incident_id,generation,sequence);
    CREATE INDEX idx_recovery_events_server_anchor ON commander_device_recovery_events
      (device_id,heartbeat_anchor_at_utc) WHERE origin='SERVER' AND event_state='DEGRADED';`);
  const metrics={queries:[],writes:[]},hooks={};
  const dbAdapter={prepare:sql=>({bind:(...args)=>({
    first:async()=>{await hooks.beforeQuery?.(sql,args);metrics.queries.push(sql);
      return db.prepare(sql).get(...args)??null;},
    all:async()=>{await hooks.beforeQuery?.(sql,args);metrics.queries.push(sql);
      return {results:db.prepare(sql).all(...args)};},
    run:async()=>{await hooks.beforeQuery?.(sql,args);metrics.queries.push(sql);
      const result=db.prepare(sql).run(...args);metrics.writes.push({sql,changes:result.changes});
      return {meta:{changes:result.changes}};},
  })})};
  const env={ENVIRONMENT:'DEV',DEVICE_EVENT_V2_ENABLED:'true',
    DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED:'true',COMMANDER_RECOVERY_ALERTS_ENABLED:'true',
    PRODUCT_DB:dbAdapter};
  class ClockDate extends Date {
    constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}
  }
  class UpgradeResponse {
    constructor(body,options={}){
      if(options.status===101){this.status=101;this.webSocket=options.webSocket;return;}
      return new Response(body,options);
    }
    static json(...args){return Response.json(...args);}
  }
  class Socket {
    constructor(){this.readyState=1;this.sent=[];this.closes=[];this.attachment={};}
    serializeAttachment(value){this.attachment=plain(value);}
    deserializeAttachment(){return plain(this.attachment);}
    send(value){this.sent.push(value);}
    close(code,reason){this.closes.push({code,reason});this.readyState=3;}
  }
  const sockets=[],storage=new Map(),probeTimes=new Map();
  const ctx={getWebSockets:()=>sockets,acceptWebSocket:socket=>sockets.push(socket),
    setWebSocketAutoResponse(){},getWebSocketAutoResponseTimestamp:socket=>probeTimes.get(socket)??null,
    storage:{async get(key){return storage.get(key);},async put(key,value){storage.set(key,plain(value));},
      async delete(key){storage.delete(key);},async setAlarm(value){storage.set('$alarm',Number(value));},
      async getAlarm(){return storage.get('$alarm')??null;},async deleteAlarm(){storage.delete('$alarm');}}};
  const recoveryRuntime=vm.createContext({Date:ClockDate,crypto:globalThis.crypto,
    TextEncoder,TextDecoder,Number,String,console,performance});
  const names=[...recoverySource.matchAll(/^export (?:async )?function (\w+)/gm)].map(match=>match[1]);
  vm.runInContext(withoutImports(recoverySource)+'\nglobalThis.api={'+names.join(',')+'};',recoveryRuntime);
  const runtime=vm.createContext({DurableObject:class {},Date:ClockDate,Request,Headers,
    Response:UpgradeResponse,URL,TextEncoder,TextDecoder,crypto:globalThis.crypto,
    WebSocket:{OPEN:1},WebSocketRequestResponsePair:class {},
    WebSocketPair:class {constructor(){this[0]=new Socket();this[1]=new Socket();}},
    scheduler:{wait:()=>new Promise(()=>{})},canonicalChannelTelemetry:value=>value,
    telemetryRollupQuery:()=>{throw Error('UNEXPECTED_TELEMETRY');},...recoveryRuntime.api});
  vm.runInContext(withoutImports(channelSource)+'\nglobalThis.Subject=DeviceChannel;',runtime);
  const channel=new runtime.Subject(ctx,env);
  const connect=async(contract=CONTRACT)=>{
    const request=new Request('https://device-channel/connect',{headers:{upgrade:'websocket',
      'x-hara-channel-authenticated':'1','x-hara-tenant-id':'TENANT-A','x-hara-device-id':'DEVICE-A',
      ...(contract===null?{}:{'x-hara-event-v2-contract':contract})}});
    return channel.fetch(request);
  };
  t.after(()=>db.close());
  return {env,ctx,db,hooks,metrics,channel,sockets,storage,connect,recovery:recoveryRuntime.api,
    at:offset=>{now=BASE+offset;},
    probe:(socket,offset)=>probeTimes.set(socket,new ClockDate(BASE+offset)),
    events:()=>db.prepare('SELECT * FROM commander_device_recovery_events ORDER BY sequence').all(),
    row:()=>db.prepare("SELECT * FROM commander_devices WHERE device_id='DEVICE-A'").get()};
}

test('commercial connect schedules independent <=120s alarm and retains server timestamp fallback',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);
  const socket=f.sockets.at(-1),attachment=socket.deserializeAttachment();
  assert.equal(attachment.connected_at_ms,BASE);
  const alarm=await f.ctx.storage.getAlarm();
  assert.ok(alarm>BASE&&alarm<=BASE+120000,'independent detector not scheduled inside 120s');
});
test('commercial connect fails closed when native auto-response timestamps are unavailable',async t=>{
  const f=fixture(t);delete f.ctx.getWebSocketAutoResponseTimestamp;
  const response=await f.connect();
  assert.notEqual(response.status,101);assert.equal(f.sockets.length,0);assert.equal(f.events().length,0);
});
test('an OPEN socket without fresh application probe becomes canonical SERVER incident and OFFLINE',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  f.at(119999);await f.channel.alarm();
  assert.equal(socket.readyState,1);assert.equal(f.events().length,0);
  f.at(120000);await f.channel.alarm();
  assert.notEqual(socket.readyState,1,'OPEN/PID/transport presence hid the missing application probe');
  assert.equal(socket.closes.at(-1).code,4002);
  assert.equal(f.row().tunnel_mode,'EVENT_V2_OFFLINE');
  const rows=f.events();assert.equal(rows.length,1);
  assert.equal(rows[0].origin,'SERVER');assert.equal(rows[0].event_state,'DEGRADED');
  assert.equal(rows[0].error_code,'EVENT_V2_PROBE_STALE');
  assert.equal(rows[0].worker,null);assert.equal(rows[0].detector,null);
  assert.equal(rows[0].sequence,1);assert.match(rows[0].event_id,/^HARA-REC-[a-f0-9]{48}$/);
  assert.equal(rows[0].portal_ack_at_utc,null);
  await f.channel.alarm();assert.equal(f.events().length,1,'duplicate alarm duplicated the same incident');
});
test('fresh hibernation probe reschedules detector without healthy-state D1 writes',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  f.probe(socket,60000);f.at(120000);f.metrics.writes.length=0;
  await f.channel.alarm();
  assert.equal(socket.readyState,1);assert.equal(f.events().length,0);
  assert.ok(f.metrics.writes.every(write=>write.changes===0),'healthy probe caused durable D1 writes');
  const next=await f.ctx.storage.getAlarm();assert.ok(next>BASE+120000&&next<=BASE+180000);
});
test('replacement connection recovers the same incident only after its first fresh probe',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);
  f.at(120000);await f.channel.alarm();assert.equal(f.events().length,1);
  const loss=f.events()[0];
  f.at(121000);assert.equal((await f.connect()).status,101);const replacement=f.sockets.at(-1);
  assert.equal(f.events().length,1,'new OPEN socket fabricated RECOVERED before an application probe');
  f.probe(replacement,122000);
  const alarm=await f.ctx.storage.getAlarm();assert.ok(alarm<=BASE+241000&&alarm>BASE+121000);
  f.at(alarm-BASE);await f.channel.alarm();
  const rows=f.events();assert.equal(rows.length,2);
  assert.deepEqual(rows.map(row=>row.event_state),['DEGRADED','RECOVERED']);
  assert.equal(rows[1].origin,'SERVER');assert.equal(rows[1].incident_id,loss.incident_id);
  assert.equal(rows[1].generation,loss.generation);assert.equal(rows[1].sequence,2);
  assert.equal(f.row().tunnel_mode,'EVENT_V2');assert.equal(replacement.readyState,1);
});
for(const state of ['REVOKED','MANUALLY_OFFLINE'])test('lifecycle fence suppresses a false incident: '+state,async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  f.db.exec(state==='REVOKED'
    ? "UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-25T00:01:00.000Z'"
    : "UPDATE commander_devices SET tunnel_mode='EVENT_V2_OFFLINE'");
  f.at(120000);await f.channel.alarm();
  assert.equal(f.events().length,0);assert.notEqual(socket.readyState,1);
});
test('a fresh probe during incident persistence prevents false OFFLINE and records matching RECOVERED',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  let raced=false;
  f.hooks.beforeQuery=sql=>{
    if(!raced&&sql.includes('INSERT INTO commander_device_recovery_events')){
      raced=true;f.probe(socket,120000);
    }
  };
  f.at(120000);await f.channel.alarm();assert.equal(raced,true);
  assert.equal(socket.readyState,1);assert.equal(f.row().tunnel_mode,'EVENT_V2');
  const rows=f.events();assert.deepEqual(rows.map(row=>row.event_state),['DEGRADED','RECOVERED']);
  assert.equal(rows[0].incident_id,rows[1].incident_id);assert.equal(rows[1].sequence,2);
});
test('legacy channels retain existing behavior without an independent commercial alarm',async t=>{
  const f=fixture(t);delete f.ctx.getWebSocketAutoResponseTimestamp;
  assert.equal((await f.connect(null)).status,101);const socket=f.sockets.at(-1);
  assert.equal(await f.ctx.storage.getAlarm(),null);
  f.at(180000);await f.channel.alarm();assert.equal(socket.readyState,1);assert.equal(f.events().length,0);
});
test('canonical Event V2 writer itself retains DEV, exact opt-in and recovery-alert gates',async t=>{
  for(const override of [
    {ENVIRONMENT:'PROD'},
    {DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED:'false'},
    {DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED:true},
    {COMMANDER_RECOVERY_ALERTS_ENABLED:'false'},
  ]){
    const f=fixture(t);Object.assign(f.env,override);
    assert.equal(typeof f.recovery.observeEventV2ChannelLoss,'function','canonical Event V2 loss export is missing');
    try {
      await f.recovery.observeEventV2ChannelLoss(f.env,f.row(),{
        probe_anchor_ms:BASE,at_ms:BASE+120000,error_code:'EVENT_V2_PROBE_STALE'});
    } catch(error){assert.match(String(error?.message||error),/RECOVERY|EVENT_V2|ADMITTED|DISABLED/);}
    assert.equal(f.events().length,0,'Event V2 writer bypassed a closed feature/scope gate');
  }
});

// Adversarial retries and cross-await lifecycle changes. These faults affect
// only the fixture's storage/probe/D1 boundaries, never the source functions.
test('DEGRADED persisted before incident-pointer I/O failure remains retryable at a later timestamp',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  const put=f.ctx.storage.put;let failed=false;
  f.ctx.storage.put=async(key,value)=>{
    if(!failed&&key==='commercial_recovery_incident'&&f.events().length===1){
      failed=true;throw Error('SYNTHETIC_INCIDENT_POINTER_PUT_FAILED');
    }
    return put(key,value);
  };
  f.at(120000);
  await assert.rejects(()=>f.channel.alarm(),/SYNTHETIC_INCIDENT_POINTER_PUT_FAILED/);
  assert.equal(failed,true);assert.equal(f.events().length,1);
  const first={...f.events()[0]};assert.equal(first.event_state,'DEGRADED');
  f.at(121000);await f.channel.alarm();
  assert.deepEqual(f.events().map(row=>({...row})),[first],
    'alarm retry changed or duplicated the canonical first loss');
  assert.notEqual(socket.readyState,1);assert.equal(f.row().tunnel_mode,'EVENT_V2_OFFLINE');
});
test('RECOVERED persisted before pointer-delete I/O failure remains retryable without fingerprint conflict',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);
  f.at(120000);await f.channel.alarm();assert.equal(f.events().length,1);
  f.at(121000);assert.equal((await f.connect()).status,101);const replacement=f.sockets.at(-1);
  f.probe(replacement,240000);f.at(241000);
  const remove=f.ctx.storage.delete;let failed=false;
  f.ctx.storage.delete=async key=>{
    if(!failed&&key==='commercial_recovery_incident'&&f.events().length===2){
      failed=true;throw Error('SYNTHETIC_INCIDENT_POINTER_DELETE_FAILED');
    }
    return remove(key);
  };
  await assert.rejects(()=>f.channel.alarm(),/SYNTHETIC_INCIDENT_POINTER_DELETE_FAILED/);
  assert.equal(failed,true);assert.equal(f.events().length,2);
  const before=f.events().map(row=>({...row}));assert.equal(before[1].event_state,'RECOVERED');
  f.probe(replacement,241500);f.at(242000);await f.channel.alarm();
  assert.deepEqual(f.events().map(row=>({...row})),before);
  assert.equal(f.storage.has('commercial_recovery_incident'),false);
  assert.equal(replacement.readyState,1);assert.equal(f.row().tunnel_mode,'EVENT_V2');
});
test('closed-channel grace alarm retains its original loss identity across incident-pointer failure',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  socket.close(1006,'SYNTHETIC_NETWORK_CLOSE');
  await f.channel.webSocketClose(socket,1006,'SYNTHETIC_NETWORK_CLOSE',false);
  const scheduled=await f.ctx.storage.getAlarm();assert.ok(scheduled>BASE&&scheduled<=BASE+60000);
  const put=f.ctx.storage.put;let failed=false;
  f.ctx.storage.put=async(key,value)=>{
    if(!failed&&key==='commercial_recovery_incident'&&f.events().length===1){
      failed=true;throw Error('SYNTHETIC_CLOSED_INCIDENT_POINTER_FAILED');
    }
    return put(key,value);
  };
  f.at(scheduled-BASE);
  await assert.rejects(()=>f.channel.alarm(),/SYNTHETIC_CLOSED_INCIDENT_POINTER_FAILED/);
  assert.equal(failed,true);assert.equal(f.events().length,1);
  const first={...f.events()[0]};assert.equal(first.error_code,'EVENT_V2_CHANNEL_CLOSED');
  f.at(scheduled-BASE+1000);await f.channel.alarm();
  assert.deepEqual(f.events().map(row=>({...row})),[first]);
  assert.equal(f.row().tunnel_mode,'EVENT_V2_OFFLINE');
});
function afterAutomaticOfflineWrite(f,callback){
  const prepare=f.env.PRODUCT_DB.prepare;let fired=false;
  f.env.PRODUCT_DB.prepare=sql=>{
    const statement=prepare(sql);
    return {bind(...args){
      const bound=statement.bind(...args);
      return {...bound,async run(){
        const result=await bound.run();
        if(!fired&&result.meta?.changes===1&&/SET tunnel_mode\s*=\s*'EVENT_V2_OFFLINE'/.test(sql)){
          fired=true;callback(args);
        }
        return result;
      }};
    }};
  };
  return ()=>fired;
}
test('fresh probe during the final automatic OFFLINE write restores only its own presence and recovers',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  const fired=afterAutomaticOfflineWrite(f,()=>f.probe(socket,120000));
  f.at(120000);await f.channel.alarm();assert.equal(fired(),true);
  assert.equal(socket.readyState,1,'a probe that arrived during awaited D1 write was closed');
  assert.equal(f.row().tunnel_mode,'EVENT_V2','fresh connection was left OFFLINE after its own write');
  const rows=f.events();assert.deepEqual(rows.map(row=>row.event_state),['DEGRADED','RECOVERED']);
  assert.equal(rows[0].incident_id,rows[1].incident_id);assert.equal(rows[1].sequence,2);
});
test('a manual OUTBOUND_RELAY_OFFLINE write at the same timestamp is never undone by a late fresh probe',async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  const fired=afterAutomaticOfflineWrite(f,args=>{
    f.db.prepare("UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE',last_seen_at_utc=? WHERE device_id='DEVICE-A'")
      .run(args[0]);
    f.probe(socket,120000);
  });
  f.at(120000);await f.channel.alarm();assert.equal(fired(),true);
  assert.equal(f.row().tunnel_mode,'OUTBOUND_RELAY_OFFLINE','recovery overrode explicit operator stop');
  assert.notEqual(socket.readyState,1);
  assert.ok(f.events().every(row=>row.event_state!=='RECOVERED'),'manual stop fabricated RECOVERED');
});
for(const lifecycle of ['REVOKED','MANUAL_STOP'])test('lifecycle change between device SELECT and incident INSERT is handled: '+lifecycle,async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  let changed=false;
  f.hooks.beforeQuery=sql=>{
    if(changed||!sql.includes('INSERT INTO commander_device_recovery_events'))return;
    changed=true;
    f.db.exec(lifecycle==='REVOKED'
      ? "UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-25T00:02:00.000Z'"
      : "UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE'");
  };
  f.at(120000);await f.channel.alarm();assert.equal(changed,true);
  assert.equal(f.events().length,0,'stale device preimage created an incident after lifecycle invalidation');
  assert.notEqual(socket.readyState,1,'an uncaught persistence error stranded the invalid socket OPEN');
  if(lifecycle==='REVOKED')assert.equal(f.row().state,'REVOKED');
  else assert.equal(f.row().tunnel_mode,'OUTBOUND_RELAY_OFFLINE');
});

test('raw AGENT input cannot reserve the canonical Event V2 SERVER namespace',async t=>{
  const f=fixture(t);
  const body={schema:'hara.commander.recovery-event.v1',incident_id:'event-v2-'+'a'.repeat(40),
    generation:1,sequence:1,state:'DEGRADED',at_utc:new Date(BASE).toISOString()};
  await assert.rejects(()=>f.recovery.ingestRecoveryEvent(f.env,f.row(),body,BASE),/RECOVERY_EVENT_SERVER_NAMESPACE/);
  assert.equal(f.events().length,0);assert.equal(f.metrics.queries.length,0);
});
test('ordinary AGENT events still persist and deduplicate for every transport with commercial opt-in OFF',async t=>{
  const f=fixture(t);f.env.DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED='false';
  const modes=['OUTBOUND_RELAY','EVENT_V2','LOCAL_TUNNEL','EVENT_V2_OFFLINE','OUTBOUND_RELAY_OFFLINE'];
  for(let n=0;n<modes.length;n++){
    f.db.prepare('UPDATE commander_devices SET tunnel_mode=?').run(modes[n]);
    const body={schema:'hara.commander.recovery-event.v1',incident_id:'ordinary-agent-'+n,
      generation:1,sequence:1,state:'STALLED',at_utc:new Date(BASE).toISOString()};
    const first=await f.recovery.ingestRecoveryEvent(f.env,f.row(),body,BASE);
    const repeat=await f.recovery.ingestRecoveryEvent(f.env,f.row(),body,BASE+1);
    assert.equal(first.ack,'PERSISTED');assert.equal(first.duplicate,false);
    assert.equal(repeat.duplicate,true);assert.equal(repeat.event_id,first.event_id);
    assert.equal(first.external_delivery_confirmed,false);
  }
  assert.equal(f.events().length,modes.length);assert.ok(f.events().every(row=>row.origin==='AGENT'));
});
test('legacy SERVER heartbeat recovery retains its OUTBOUND_RELAY live fence',async t=>{
  for(const mode of ['OUTBOUND_RELAY','EVENT_V2']){
    const f=fixture(t),anchor=new Date(BASE-300000).toISOString();
    f.db.prepare('UPDATE commander_devices SET tunnel_mode=?,last_seen_at_utc=?').run(mode,anchor);
    const incident='offline-'+sha(JSON.stringify(['TENANT-A','DEVICE-A',anchor])).slice(0,40);
    // Seed only the historical predecessor fixture; the tested sequence-2
    // write must run through the actual legacy export and canonical SQL.
    f.db.prepare(`INSERT INTO commander_device_recovery_events
      (event_id,tenant_id,device_id,incident_id,generation,sequence,event_state,origin,
       event_at_utc,heartbeat_anchor_at_utc,payload_sha256,persisted_at_utc)
      VALUES(?,'TENANT-A','DEVICE-A',?,1,1,'DEGRADED','SERVER',?,?,?,?)`)
      .run('HARA-REC-'+'b'.repeat(48),incident,new Date(BASE-180000).toISOString(),anchor,'c'.repeat(64),new Date(BASE-180000).toISOString());
    const stalePreimage={...f.row(),tunnel_mode:'OUTBOUND_RELAY'};
    if(mode==='OUTBOUND_RELAY'){
      const receipt=await f.recovery.observeHeartbeatRecovery(f.env,stalePreimage,BASE);
      assert.equal(receipt.ack,'PERSISTED');assert.equal(f.events().length,2);
      assert.equal(f.events()[1].origin,'SERVER');assert.equal(f.events()[1].event_state,'RECOVERED');
    }else{
      await assert.rejects(()=>f.recovery.observeHeartbeatRecovery(f.env,stalePreimage,BASE),/RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER/);
      assert.equal(f.events().length,1,'legacy writer inherited the new Event V2 transport permission');
    }
  }
});
test('cross-tenant preimages cannot create or retrospectively recover another tenant incident',async t=>{
  const f=fixture(t);f.at(120000);
  const observation={probe_anchor_ms:BASE,at_ms:BASE+120000,error_code:'EVENT_V2_PROBE_STALE'};
  const forged={...f.row(),tenant_id:'FORGED-TENANT'};
  await assert.rejects(()=>f.recovery.observeEventV2ChannelLoss(f.env,forged,observation),/DEVICE_AUTH_INVALID/);
  assert.equal(f.events().length,0);
  const incident=await f.recovery.observeEventV2ChannelLoss(f.env,f.row(),observation);
  assert.equal(f.events().length,1);
  f.at(121000);
  await assert.rejects(()=>f.recovery.observeEventV2ChannelRecovery(f.env,forged,incident,BASE+121000),/DEVICE_AUTH_INVALID/);
  assert.equal(f.events().length,1);assert.equal(f.events()[0].event_state,'DEGRADED');
});
for(const lifecycle of ['REVOKED','MANUAL_STOP'])test('fresh-probe recovery cannot hide a lifecycle change during RECOVERED persistence: '+lifecycle,async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);
  f.at(120000);await f.channel.alarm();assert.equal(f.events().length,1);
  f.at(121000);assert.equal((await f.connect()).status,101);const replacement=f.sockets.at(-1);
  f.probe(replacement,240000);let changed=false;
  f.hooks.beforeQuery=(sql,args)=>{
    if(changed||!sql.includes('INSERT INTO commander_device_recovery_events')||!args.includes('RECOVERED'))return;
    changed=true;
    f.db.exec(lifecycle==='REVOKED'
      ? "UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-25T00:04:01.000Z'"
      : "UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE'");
  };
  f.at(241000);await f.channel.alarm();assert.equal(changed,true);
  assert.equal(f.events().length,1,'invalidated device fabricated a new RECOVERED event');
  assert.notEqual(replacement.readyState,1,'recovery write failure stranded an invalidated connection OPEN');
  if(lifecycle==='REVOKED')assert.equal(f.row().state,'REVOKED');
  else assert.equal(f.row().tunnel_mode,'OUTBOUND_RELAY_OFFLINE');
});
for(const lifecycle of ['REVOKED','MANUAL_STOP'])test('fresh application probes cannot preserve an invalidated channel when invalidate RPC was lost: '+lifecycle,async t=>{
  const f=fixture(t);assert.equal((await f.connect()).status,101);const socket=f.sockets.at(-1);
  f.probe(socket,60000);
  f.db.exec(lifecycle==='REVOKED'
    ? "UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-25T00:01:01.000Z'"
    : "UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE'");
  f.at(120000);await f.channel.alarm();
  assert.notEqual(socket.readyState,1,'fresh traffic concealed a live authorization/lifecycle failure');
  assert.equal(socket.closes.at(-1).code,4003);assert.equal(f.events().length,0);
  if(lifecycle==='REVOKED')assert.equal(f.row().state,'REVOKED');
  else assert.equal(f.row().tunnel_mode,'OUTBOUND_RELAY_OFFLINE');
});

console.log(JSON.stringify({schema:'hara.commander.event-v2.commercial-detector-test.v1',
  device_channel_sha256:sha(channelSource),recovery_alerts_sha256:sha(recoverySource),
  scope:'REAL_CANONICAL_RECOVERY_SQLITE_SYNTHETIC_HIBERNATION_CLOCK',
  native_scheduler_acceptance:false,hosted_wss_acceptance:false,capacity_acceptance:false}));
