// #163 commercial .56 DEV negotiation and durable-only Worker/DO boundaries.
// Real source functions and real SQLite; auth/product/quota/socket boundaries
// are injected fixtures. This does not attest hosted WSS or native capacity.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';

const CONTRACT='commercial-0.3.56-durable-dev.v1';
const HEADER='x-hara-event-v2-contract';
const BASE=Date.parse('2026-10-25T00:00:00.000Z');
const workerSource=fs.readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const channelSource=fs.readFileSync(new URL('../src/device-channel.mjs',import.meta.url),'utf8');
const sha=value=>createHash('sha256').update(value).digest('hex');
const plain=value=>JSON.parse(JSON.stringify(value));
function sourceFunction(source,name){
  const start=source.search(new RegExp('^(?:async )?function '+name+'\\(', 'm'));
  assert.ok(start>=0,'real function missing: '+name);
  const closing=/^}\r?$/gm;closing.lastIndex=start;
  const end=closing.exec(source);assert.ok(end&&end.index>start,'real function end missing: '+name);
  return source.slice(start,end.index+1);
}
const policyStart=workerSource.indexOf('function eventV2Enabled(');
const policyEnd=workerSource.indexOf('async function invalidateDeviceEventChannel(',policyStart);
assert.ok(policyStart>=0&&policyEnd>policyStart);
const workerFunctions=workerSource.slice(policyStart,policyEnd)+'\n'+
  sourceFunction(workerSource,'dispatchTransientDeviceCall');
const channelFunctions=channelSource.replace(/^import\s[\s\S]*?;\r?\n/gm,'').replace(/^export /gm,'');

function fixture(t){
  let now=BASE;
  const db=new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,
    state TEXT,revoked_at_utc TEXT,platform TEXT,approval_mode TEXT,agent_version TEXT,
    tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);
    INSERT INTO commander_devices VALUES('DEVICE-A','TENANT-A','ACTIVE',NULL,'LINUX',
    'PERSISTENT_TRUSTED','0.3.56','EVENT_V2','2026-10-25T00:00:00.000Z','2026-10-24T00:00:00.000Z');`);
  const metrics={queries:[],workerRequests:[],operations:[],reserve:0,commit:0,release:0};
  const sockets=[],storage=new Map(),autoResponseAt=new Map();
  const dbAdapter={prepare:sql=>({bind:(...args)=>({
    first:async()=>{metrics.queries.push(sql);return db.prepare(sql).get(...args)??null;},
    all:async()=>{metrics.queries.push(sql);return {results:db.prepare(sql).all(...args)};},
    run:async()=>{metrics.queries.push(sql);return {meta:{changes:db.prepare(sql).run(...args).changes}};},
  })})};
  const env={ENVIRONMENT:'DEV',DEVICE_EVENT_V2_ENABLED:'true',
    DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED:'true',DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED:'true',
    COMMANDER_RECOVERY_ALERTS_ENABLED:'true',PRODUCT_DB:dbAdapter};
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
    send(value){this.sent.push(value);this.onSend?.(value);}
    close(code,reason){this.closes.push({code,reason});this.readyState=3;}
  }
  const ctx={getWebSockets:()=>sockets,acceptWebSocket:socket=>sockets.push(socket),
    setWebSocketAutoResponse(){},getWebSocketAutoResponseTimestamp:socket=>autoResponseAt.get(socket)??null,
    storage:{async get(key){return storage.get(key);},async put(key,value){storage.set(key,plain(value));},
      async delete(key){storage.delete(key);},async setAlarm(value){storage.set('$alarm',value);},
      async getAlarm(){return storage.get('$alarm')??null;},async deleteAlarm(){storage.delete('$alarm');}}};
  const channelRuntime=vm.createContext({DurableObject:class {},Date:ClockDate,
    Response:UpgradeResponse,Request,Headers,URL,TextEncoder,TextDecoder,crypto:globalThis.crypto,
    WebSocket:{OPEN:1},WebSocketRequestResponsePair:class {},
    WebSocketPair:class {constructor(){this[0]=new Socket();this[1]=new Socket();}},
    scheduler:{wait:()=>new Promise(()=>{})},
    canonicalChannelTelemetry:value=>value,telemetryRollupQuery:()=>{throw Error('UNEXPECTED_TELEMETRY');}});
  vm.runInContext(channelFunctions+'\nglobalThis.subject={DeviceChannel,deviceChannelName};',channelRuntime);
  const channel=new channelRuntime.subject.DeviceChannel(ctx,env);
  let statusContract=CONTRACT;
  env.DEVICE_CHANNEL={getByName(name){
    const selected=db.prepare('SELECT tenant_id,device_id FROM commander_devices LIMIT 1').get();
    assert.equal(name,selected.tenant_id+':'+selected.device_id);
    return {async fetch(request){
      metrics.workerRequests.push(request);
      const url=new URL(request.url);metrics.operations.push(url.pathname);
      if(url.pathname==='/connect')return {status:101};
      assert.equal(request.headers.get('x-hara-channel-authenticated'),'1');
      if(url.pathname==='/status')return Response.json({schema:'hara.commander-device-channel.v2',
        connected:1,event_v2_contract:statusContract});
      assert.equal(url.pathname,'/dispatch');
      return Response.json({schema:'hara.commander-transient-rpc.v1',state:'COMPLETED',
        result:{bridge_receipt_sha256:'a'.repeat(64)},learning_signal:null});
    }};
  }};
  env.TENANT_QUOTA={getByName(){return {
    async reserve(){metrics.reserve++;metrics.operations.push('quota.reserve');return {ok:true,state:'RESERVED'};},
    async commit(){metrics.commit++;return {ok:true,state:'COMMITTED'};},
    async release(){metrics.release++;return {ok:true,state:'RELEASED'};},
  };}};
  const cleanId=(value,max)=>{if(typeof value!=='string'||!value||value.length>max)throw Error('ID_INVALID');return value;};
  const workerRuntime=vm.createContext({Request,Response:UpgradeResponse,Headers,URL,TextEncoder,
    TextDecoder,crypto:globalThis.crypto,Date:ClockDate,
    json:Response.json.bind(Response),
    resolveDeviceCredential:async()=>db.prepare('SELECT * FROM commander_devices LIMIT 1').get(),
    deviceChannelName:channelRuntime.subject.deviceChannelName,
    MCP_TOOL_GRANTS:{'hara.functions.invoke':'SYNTHETIC_GRANT'},
    mcpTransientProductContext:async()=>({ok:true,tenant_id:'TENANT-A',subject_id:'SUBJECT-A',
      grants:['SYNTHETIC_GRANT'],unit_limit:10}),mcpBootstrapHints:()=>({}),
    resolveCustomerTargetDevice:async()=>db.prepare('SELECT * FROM commander_devices LIMIT 1').get(),
    canonicalDeviceToolPayload:(_tool,payload)=>payload,boundedJson:JSON.stringify,cleanId,
    deviceOnline:()=>true,isDeviceFunctionAllowed:()=>true,mcpPeriodKey:()=> '2026-10',
    TRANSIENT_EXECUTE_OR_REPLAY:'EXECUTE_OR_REPLAY',TRANSIENT_REPLAY_ONLY:'REPLAY_ONLY',
    TRANSIENT_SAFE_PREEXEC_RELEASE_CODES:new Set(['CHANNEL_TRANSIENT_OFFLINE','CHANNEL_TRANSIENT_BUSY']),
    transientPublicErrorCode:code=>code,recordLearningSignal:()=>({recorded:false})});
  vm.runInContext(workerFunctions+'\nglobalThis.subject={openDeviceEventChannel,dispatchTransientDeviceCall};',workerRuntime);
  const external=(contract=CONTRACT)=>new Request('https://synthetic.invalid/api/device/channel',{
    headers:{upgrade:'websocket',...(contract===null?{}:{[HEADER]:contract}),
      'x-hara-tenant-id':'FORGED-TENANT','x-hara-device-id':'FORGED-DEVICE'}});
  const internal=(path,body=null,contract=CONTRACT)=>new Request('https://device-channel'+path,{
    method:body===null?'GET':'POST',headers:{'x-hara-channel-authenticated':'1',
      'x-hara-tenant-id':'TENANT-A','x-hara-device-id':'DEVICE-A',upgrade:'websocket',
      'content-type':'application/json',...(contract===null?{}:{[HEADER]:contract})},
    ...(body===null?{}:{body:JSON.stringify(body)})});
  const connect=async(contract=CONTRACT)=>{
    const response=await channel.fetch(internal('/connect',null,contract));
    assert.equal(response.status,101);return sockets.at(-1);
  };
  const transient=()=>workerRuntime.subject.dispatchTransientDeviceCall(env,{request_id:'REQ-1',
    tool_id:'hara.functions.invoke',device_id:'DEVICE-A',payload:{function_id:'device.info',arguments:{}}});
  t.after(()=>db.close());
  return {env,db,ctx,channel,sockets,metrics,external,internal,connect,transient,
    open:contract=>workerRuntime.subject.openDeviceEventChannel(env,external(contract)),
    statusContract:value=>{statusContract=value;},at:offset=>{now=BASE+offset;},autoResponseAt};
}

for(const flag of [undefined,'false','TRUE',true])test('commercial Upgrade defaults denied for flag '+String(flag),async t=>{
  const f=fixture(t);f.env.DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED=flag;
  await assert.rejects(()=>f.open(CONTRACT),/DEVICE_EVENT_V2/);
  assert.equal(f.metrics.workerRequests.length,0);
});
test('commercial Upgrade is denied in PROD even for an existing fleet canary',async t=>{
  const f=fixture(t);f.env.ENVIRONMENT='PROD';
  const id='HARA-DEVICE-00000000-0000-4000-8000-000000000001';
  f.db.prepare('UPDATE commander_devices SET device_id=?').run(id);
  f.env.DEVICE_EVENT_V2_CANARY_DEVICE_ID=id;
  await assert.rejects(()=>f.open(CONTRACT),/DEVICE_EVENT_V2/);
  assert.equal(f.metrics.workerRequests.length,0);
});
test('commercial Upgrade retains the existing general Event V2 gate',async t=>{
  const f=fixture(t);f.env.DEVICE_EVENT_V2_ENABLED='false';
  await assert.rejects(()=>f.open(CONTRACT),/DEVICE_EVENT_V2_DISABLED/);
  assert.equal(f.metrics.workerRequests.length,0);
});
test('validated commercial header is forwarded with credential-derived identity only',async t=>{
  const f=fixture(t);assert.equal((await f.open(CONTRACT)).status,101);
  const request=f.metrics.workerRequests[0];
  assert.equal(request.headers.get(HEADER),CONTRACT);
  assert.equal(request.headers.get('x-hara-channel-authenticated'),'1');
  assert.equal(request.headers.get('x-hara-tenant-id'),'TENANT-A');
  assert.equal(request.headers.get('x-hara-device-id'),'DEVICE-A');
});
test('legacy Upgrade without a commercial header remains admitted in DEV',async t=>{
  const f=fixture(t);delete f.env.DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED;
  assert.equal((await f.open(null)).status,101);
  assert.equal(f.metrics.workerRequests[0].headers.get(HEADER),null);
});
test('DO attachment and status expose the validated durable-only contract',async t=>{
  const f=fixture(t);const socket=await f.connect();
  assert.equal(socket.deserializeAttachment().event_v2_contract,CONTRACT);
  const response=await f.channel.fetch(f.internal('/status'));
  assert.equal((await response.json()).event_v2_contract,CONTRACT);
});
test('commercial DO transient dispatch denies before D1 and before socket send',async t=>{
  const f=fixture(t);const socket=await f.connect();
  socket.serializeAttachment({...socket.deserializeAttachment(),event_v2_contract:CONTRACT});
  socket.onSend=raw=>{
    const event=JSON.parse(raw);
    queueMicrotask(()=>f.channel.webSocketMessage(socket,JSON.stringify({
      schema:'hara.commander-device-event.v2',type:'CALL_RESULT',call_id:event.call_id,state:'COMPLETED',
      result:{synthetic:true},error_code:null,learning_signal:{schema:'hara.commander-learning-signal.v1',
      tool_id:'device.info',tool_family:'READ_ONLY',outcome:'COMPLETED',latency_bucket:'LT_100MS',
      result_bytes_bucket:'LT_1K',platform:'LINUX',agent_version:'0.3.56',transport_mode:'EVENT_V2',
      privileged_attempt:false,customer_content_collected:false}})));
  };
  f.metrics.queries.length=0;
  const response=await f.channel.fetch(f.internal('/dispatch',{call_id:'CALL-1',request_id:'REQ-1',
    tool_id:'hara.functions.invoke',execution_mode:'EXECUTE_OR_REPLAY',payload:{function_id:'device.info'}}));
  assert.equal((await response.json()).code,'CHANNEL_TRANSIENT_NOT_ADMITTED');
  assert.equal(f.metrics.queries.length,0);assert.equal(socket.sent.length,0);
});
test('Worker checks commercial DO status before reserving transient quota',async t=>{
  const f=fixture(t);
  await assert.rejects(()=>f.transient(),/DEVICE_TRANSIENT_NOT_ADMITTED/);
  assert.equal(f.metrics.reserve,0);assert.equal(f.metrics.commit,0);assert.equal(f.metrics.release,0);
  assert.deepEqual(f.metrics.operations,['/status']);
});
test('legacy transient still reserves and completes after status permits it',async t=>{
  const f=fixture(t);f.statusContract(null);
  const result=await f.transient();assert.equal(result.state,'COMPLETED');
  assert.equal(f.metrics.reserve,1);assert.equal(f.metrics.commit,1);
});

console.log(JSON.stringify({schema:'hara.commander.event-v2.commercial-worker-test.v1',
  worker_sha256:sha(workerSource),device_channel_sha256:sha(channelSource),
  scope:'SOURCE_VM_REAL_SQLITE_SYNTHETIC_BOUNDARIES',hosted_wss_acceptance:false,native_capacity_acceptance:false}));
