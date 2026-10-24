// #163 behavioral regressions against the actual DeviceChannel implementation.
// SQLite and VM-hosted DO/socket fixtures only: no Cloudflare, VM or credentials.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {DatabaseSync} from "node:sqlite";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";

const APP=fileURLToPath(new URL("../",import.meta.url));
const production=fs.readFileSync(new URL("../src/device-channel.mjs",import.meta.url),"utf8")
  .replace(/^import .*;\n/gm,"").replace(/^export /gm,"");
const BASE=Date.parse("2026-10-24T12:00:00.000Z");
const EVENT_SCHEMA="hara.commander-device-event.v2";
const copy=x=>JSON.parse(JSON.stringify(x));
const pending=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
function fixture({state="ACTIVE",mode="EVENT_V2"}={}) {
  let now=BASE;
  const db=new DatabaseSync(":memory:");
  db.exec("CREATE TABLE commander_devices(tenant_id TEXT,device_id TEXT,state TEXT,"+
    "revoked_at_utc TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT)");
  db.prepare("INSERT INTO commander_devices VALUES(?,?,?,?,?,?)").run(
    "TENANT-A","DEVICE-A",state,state==="REVOKED"?new Date(now-1000).toISOString():null,
    mode,new Date(now-10000).toISOString());
  const sockets=[],storage=new Map(),writes=[],hooks={};
  class Socket {
    constructor({superseded=false,device="DEVICE-A",tenant="TENANT-A"}={}) {
      this.readyState=1;this.sent=[];this.closes=[];
      this.attachment={schema:"hara.commander-device-channel.v2",tenant_id:tenant,
        device_id:device,superseded,connection_id:crypto.randomUUID()};
    }
    serializeAttachment(value){this.attachment=copy(value);}
    deserializeAttachment(){return copy(this.attachment);}
    send(value){this.sent.push(value);this.onSend?.(value);}
    close(code,reason){this.closes.push({code,reason});this.readyState=3;}
  }
  const ctx={
    getWebSockets(){return sockets;},acceptWebSocket(socket){sockets.push(socket);},
    blockConcurrencyWhile(callback){return callback();},
    storage:{
      async put(key,value){storage.set(key,copy(value));},
      async get(key){return storage.get(key);},async delete(key){storage.delete(key);},
      async setAlarm(at){storage.set("$alarm",at);},async deleteAlarm(){storage.delete("$alarm");},
      async getAlarm(){return storage.get("$alarm")??null;},
    },
  };
  const env={PRODUCT_DB:{prepare(sql){return {bind(...args){return {
    async run(){await hooks.beforeRun?.(sql,args);writes.push(sql);
      return {meta:{changes:db.prepare(sql).run(...args).changes}};},
    async first(){return db.prepare(sql).get(...args)||null;},
    async all(){return {results:db.prepare(sql).all(...args)};},
  };}};}}};
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
  const sandbox={DurableObject:class {},Date:ClockDate,Response:UpgradeResponse,Request,
    URL,TextEncoder,TextDecoder,WebSocket:{OPEN:1},
    WebSocketPair:class {constructor(){this[0]=new Socket();this[1]=new Socket();}},
    scheduler:{wait(){return new Promise(()=>{});}},crypto:globalThis.crypto,
    canonicalChannelTelemetry(x){return x;},telemetryRollupQuery(){throw Error("UNEXPECTED_TELEMETRY");}};
  vm.createContext(sandbox);
  vm.runInContext(production+"\nglobalThis.Subject=DeviceChannel;",sandbox);
  const channel=new sandbox.Subject(ctx,env);
  return {channel,ctx,sockets,storage,db,writes,hooks,
    socket(options={}){const s=new Socket(options);sockets.push(s);return s;},
    row(){return db.prepare("SELECT * FROM commander_devices").get();},
    at(delta){now=BASE+delta;},close(){db.close();}};
}
function internal(path,body=null){return new Request("https://channel.invalid"+path,{
  method:body===null?"GET":"POST",headers:{"x-hara-channel-authenticated":"1",
    "x-hara-tenant-id":"TENANT-A","x-hara-device-id":"DEVICE-A",
    ...(path==="/connect"?{upgrade:"websocket"}:{}),"content-type":"application/json"},
  ...(body===null?{}:{body:JSON.stringify(body)})});}
function result(callId="CALL-1") {return {schema:EVENT_SCHEMA,type:"CALL_RESULT",call_id:callId,
  state:"COMPLETED",result:{synthetic:true},error_code:null,learning_signal:{
    schema:"hara.commander-learning-signal.v1",tool_id:"device.info",tool_family:"READ_ONLY",
    outcome:"COMPLETED",latency_bucket:"LT_100MS",result_bytes_bucket:"LT_1K",
    platform:"LINUX",agent_version:"0.3.56",transport_mode:"EVENT_V2",
    privileged_attempt:false,customer_content_collected:false}};}
const failures=[],passes=[];
async function check(name,callback){const f=fixture();try{await callback(f);passes.push(name);
  console.log("PASS "+name);}catch(error){failures.push({name,error:String(error?.stack||error)});
  console.error("FAIL "+name+": "+error.message);}finally{f.close();}}

await check("superseded_liveness_cannot_refresh_presence",async f=>{
  const old=f.socket({superseded:true});
  const before=f.row().last_seen_at_utc;f.at(1000);
  await f.channel.webSocketMessage(old,JSON.stringify({schema:EVENT_SCHEMA,type:"LIVENESS"}));
  assert.equal(f.row().last_seen_at_utc,before);
});
await check("superseded_result_cannot_complete_current_channel_rpc",async f=>{
  const old=f.socket({superseded:true}),current=f.socket(),received=[];
  f.channel.pendingTransient.set("CALL-1",{socket:current,resolve:x=>received.push(x),reject(){}});
  await f.channel.webSocketMessage(old,JSON.stringify(result()));
  assert.equal(received.length,0,"superseded channel completed a newer channel's call");
});
await check("result_must_belong_to_exact_dispatch_socket",async f=>{
  const assigned=f.socket(),other=f.socket(),received=[];
  f.channel.pendingTransient.set("CALL-1",{socket:assigned,resolve:x=>received.push(x),reject(){}});
  await f.channel.webSocketMessage(other,JSON.stringify(result()));
  assert.equal(received.length,0,"unassigned socket completed another socket's call");
});
await check("old_socket_error_does_not_cancel_current_channel_rpc",async f=>{
  const old=f.socket({superseded:true}),current=f.socket(),errors=[];
  f.channel.pendingTransient.set("CALL-1",{socket:current,resolve(){},reject:x=>errors.push(x)});
  f.channel.webSocketError(old,Error("synthetic old socket failure"));
  assert.equal(errors.length,0,"stale socket error cancelled the current RPC");
  assert.equal(f.channel.pendingTransient.size,1);
});
await check("status_ignores_superseded_open_socket",async f=>{
  f.socket({superseded:true});f.socket();
  const response=await f.channel.fetch(internal("/status"));
  assert.equal((await response.json()).connected,1);
});
await check("notification_never_targets_superseded_socket",async f=>{
  const old=f.socket({superseded:true}),current=f.socket();
  const response=await f.channel.fetch(internal("/notify",{call_id:"CALL-1"}));
  assert.equal(old.sent.length,0,"old socket received a fresh wake");
  assert.equal(current.sent.length,1);assert.equal((await response.json()).delivered,1);
});
await check("superseded_open_zombie_cannot_suppress_offline_alarm",async f=>{
  f.socket({superseded:true});
  f.storage.set("pending_offline",{tenant_id:"TENANT-A",device_id:"DEVICE-A",scheduled_at_ms:BASE});
  await f.channel.alarm();assert.equal(f.row().tunnel_mode,"EVENT_V2_OFFLINE");
});
await check("offline_alarm_cannot_win_over_new_authenticated_connection",async f=>{
  f.storage.set("pending_offline",{tenant_id:"TENANT-A",device_id:"DEVICE-A",scheduled_at_ms:BASE});
  const entered=pending(),release=pending();
  f.hooks.beforeRun=async sql=>{if(sql.includes("SET tunnel_mode = 'EVENT_V2_OFFLINE'")){
    entered.resolve();await release.promise;}};
  const alarm=f.channel.alarm();await entered.promise;
  const connect=f.channel.fetch(internal("/connect"));
  // Permit a correct implementation to serialize alarm/connect instead of racing.
  await Promise.race([connect,new Promise(r=>setTimeout(r,30))]);release.resolve();
  await alarm;const response=await connect;
  assert.equal(response.status,101);assert.ok(f.sockets.some(s=>s.readyState===1&&!s.attachment.superseded));
  assert.equal(f.row().tunnel_mode,"EVENT_V2","OFFLINE D1 write won after reconnect accepted");
});
await check("revocation_race_during_connect_fails_closed",async f=>{
  f.db.exec("UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-24T12:00:00Z'");
  const response=await f.channel.fetch(internal("/connect"));
  assert.notEqual(response.status,101,"revoked enrollment accepted after pre-authentication race");
  assert.equal(f.sockets.length,0);
});
await check("revoked_liveness_cannot_restore_active_presence",async f=>{
  const socket=f.socket();
  f.db.exec("UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-24T12:00:00Z'");
  await f.channel.webSocketMessage(socket,JSON.stringify({schema:EVENT_SCHEMA,type:"LIVENESS"}));
  assert.equal(f.row().state,"REVOKED");assert.notEqual(socket.readyState,1);
});
await check("transient_result_is_consumed_once_and_replay_mode_preserved",async f=>{
  const socket=f.socket(),sent=pending();socket.onSend=sent.resolve;
  const reply=f.channel.fetch(internal("/dispatch",{call_id:"CALL-1",request_id:"REQ-1",
    tool_id:"hara.device.info",execution_mode:"REPLAY_ONLY",payload:{synthetic:true}}));
  const event=JSON.parse(await sent.promise);assert.equal(event.execution_mode,"REPLAY_ONLY");
  await f.channel.webSocketMessage(socket,JSON.stringify(result()));
  assert.equal((await (await reply).json()).state,"COMPLETED");
  assert.equal(f.channel.pendingTransient.size,0);
  await f.channel.webSocketMessage(socket,JSON.stringify(result()));
  assert.equal(socket.sent.length,1);assert.equal(f.channel.pendingTransient.size,0);
});
for (const cause of ["REVOKED","STOPPED"]) {
  await check("invalidate_"+cause.toLowerCase()+"_closes_only_exact_scope_and_pending_rpc",async f=>{
    const target=f.socket(),otherDevice=f.socket({device:"DEVICE-B"}),
      otherTenant=f.socket({tenant:"TENANT-B"}),rejected=[];
    f.channel.pendingTransient.set("TARGET",{socket:target,resolve(){},reject:error=>rejected.push(error)});
    f.channel.pendingTransient.set("FOREIGN",{socket:otherTenant,resolve(){},reject(){throw Error("CROSS_TENANT_INVALIDATION");}});
    f.db.exec(cause==="REVOKED"
      ? "UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-24T12:00:00Z'"
      : "UPDATE commander_devices SET tunnel_mode='EVENT_V2_OFFLINE'");
    const response=await f.channel.fetch(internal("/invalidate",{}));
    assert.ok(response.ok,"missing/failed admitted internal invalidation: HTTP "+response.status);
    assert.notEqual(target.readyState,1);assert.equal(rejected.length,1);
    assert.equal(f.channel.pendingTransient.has("TARGET"),false);
    assert.equal(f.channel.pendingTransient.has("FOREIGN"),true);
    assert.equal(otherDevice.readyState,1);assert.equal(otherTenant.readyState,1);
    const again=await f.channel.fetch(internal("/invalidate",{}));
    assert.ok(again.ok,"repeat invalidation must be idempotent");
    assert.equal(rejected.length,1);
  });
}
await check("invalidate_refuses_still_active_device_without_closing_channel",async f=>{
  const socket=f.socket();
  const response=await f.channel.fetch(internal("/invalidate",{}));
  const body=await response.json();
  assert.ok(response.status>=400&&response.status!==404,
    "active invalidation must fail by live-device precondition, not missing route");
  assert.notEqual(body.code,"CHANNEL_ROUTE_NOT_FOUND");
  assert.equal(socket.readyState,1);
});
await check("invalidate_requires_internal_authentication",async f=>{
  const socket=f.socket();
  const response=await f.channel.fetch(new Request("https://channel.invalid/invalidate",{
    method:"POST",headers:{"content-type":"application/json"},body:"{}"}));
  assert.equal(response.status,401);assert.equal(socket.readyState,1);
});
await check("revoked_dispatch_never_sends_customer_effect",async f=>{
  const socket=f.socket();
  // Resolve an illegally dispatched fixture call so a regression fails instead
  // of hanging on the normal RPC timer. No customer effect is performed.
  socket.onSend=()=>queueMicrotask(()=>f.channel.webSocketMessage(socket,JSON.stringify(result())));
  f.db.exec("UPDATE commander_devices SET state='REVOKED',revoked_at_utc='2026-10-24T12:00:00Z'");
  const response=await f.channel.fetch(internal("/dispatch",{call_id:"CALL-1",request_id:"REQ-1",
    tool_id:"hara.device.info",execution_mode:"EXECUTE_OR_REPLAY",payload:{synthetic:true}}));
  assert.equal(socket.sent.length,0,"revoked enrollment received CALL_TRANSIENT");
  assert.ok(response.status>=400);assert.equal(f.channel.pendingTransient.size,0);
});
await check("transport_times_out_missing_pong_instead_of_sustaining_zombie",async()=>{
  const script=String.raw`
import importlib.util,sys,socket
from pathlib import Path
p=Path(sys.argv[1])/'experimental/event_v2_websocket.py'
spec=importlib.util.spec_from_file_location('r163_zombie_transport',p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
class Socket:
 def __init__(self):self.timeout=25;self.sent=[];self.now=0
 def gettimeout(self):return self.timeout
 def settimeout(self,value):self.timeout=value
 def recv(self,n):self.now+=float(self.timeout or 60);raise socket.timeout()
 def read(self,n):return self.recv(n)
 def sendall(self,data):self.sent.append(data)
 def close(self):pass
s=Socket()
if hasattr(m,'time'):m.time.monotonic=lambda:s.now
failed=False
for i in range(6):
 try:m.recv_event_or_keepalive(s)
 except m.EventV2Error as e:
  assert 'PONG' in str(e) or 'TIMEOUT' in str(e),str(e)
  failed=True;break
assert failed,'missing PONG accepted forever; stale TCP socket remains connected'
print('PONG_WATCHDOG_PASS')
`;
  const process=spawnSync("python3",["-c",script,APP],{encoding:"utf8",timeout:2000});
  assert.equal(process.status,0,process.stderr||process.error?.message);
});
function transportFrames(body){
  const prefix=String.raw`
import importlib.util,sys,socket,json
from pathlib import Path
p=Path(sys.argv[1])/'experimental/event_v2_websocket.py'
spec=importlib.util.spec_from_file_location('r163_pong_frames',p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
class Socket:
 def __init__(self):self.timeout=25;self.sent=[];self.now=0.;self.actions=[]
 def gettimeout(self):return self.timeout
 def settimeout(self,value):self.timeout=value
 def read(self,n):
  action=self.actions[0]
  if action=='TIMEOUT':
   self.actions.pop(0);self.now+=float(self.timeout);raise socket.timeout()
  raw,step=action
  if self.timeout is not None and step>self.timeout:
   self.now+=self.timeout;raise socket.timeout()
  self.now+=step;value=raw[:1];action[0]=raw[1:]
  if not action[0]:self.actions.pop(0)
  return value
 def recv(self,n):return self.read(n)
 def sendall(self,data):self.sent.append(data)
 def close(self):pass
 def frame(self,opcode,payload,step=.01):
  assert len(payload)<126
  self.actions.append([bytes([0x80|opcode,len(payload)])+payload,step])
s=Socket();m.time.monotonic=lambda:s.now
def ping_nonce():
 wire=s.sent[-1];assert wire[0]&15==9
 size=wire[1]&127;mask=wire[2:6]
 return bytes(b^mask[i%4] for i,b in enumerate(wire[6:6+size]))
s.actions.append('TIMEOUT');assert m.recv_event_or_keepalive(s) is None
nonce=ping_nonce();assert len(nonce)>0
deadline=s.now+20
`;
  const result=spawnSync("python3",["-c",prefix+body,APP],{encoding:"utf8",timeout:2000});
  assert.equal(result.status,0,result.stderr||result.error?.message);
}
await check("pong_wrong_nonce_cannot_clear_outstanding_probe",()=>transportFrames(String.raw`
s.frame(10,b'WRONG_NONCE');assert m.recv_event_or_keepalive(s) is None
s.actions.append('TIMEOUT')
failed=False
try:m.recv_event_or_keepalive(s)
except m.EventV2Error as e:
 assert 'PONG_TIMEOUT' in str(e),str(e)
 failed=True
assert failed,'unrelated PONG cleared an outstanding nonce'
assert s.now<=deadline+.000001
`));
await check("pong_correct_nonce_clears_probe_and_allows_next_idle_ping",()=>transportFrames(String.raw`
s.frame(10,nonce);assert m.recv_event_or_keepalive(s) is None
old_count=len(s.sent)
s.actions.append('TIMEOUT');assert m.recv_event_or_keepalive(s) is None
assert len(s.sent)==old_count+1,'matched PONG did not permit a fresh idle probe'
assert s.now>deadline,'test must cross the former probe deadline'
`));
await check("event_traffic_and_partial_reads_cannot_extend_pong_deadline",()=>transportFrames(String.raw`
event=json.dumps({'schema':m.EVENT_SCHEMA,'type':'CALL_AVAILABLE','call_id':'CALL-1'},
 separators=(',',':')).encode()
for at in [61,66,71]:
 s.now=at;s.frame(1,event,step=.01)
 assert m.recv_event_or_keepalive(s).opcode==1
# TCP data keeps arriving within each socket read timeout, while one complete
# event frame straddles the global PONG deadline. No event may reach execution
# after that deadline, and byte drips must not extend it either.
s.now=deadline-.5;s.frame(1,event,step=.2)
failed=False
try:m.recv_event_or_keepalive(s)
except m.EventV2Error as e:
 assert 'PONG_TIMEOUT' in str(e),str(e)
 failed=True
assert failed,'frame arriving after global PONG deadline reached application execution'
assert s.now<=deadline+.000001,('partial-frame reads extended 20s watchdog',s.now,deadline)
`));
console.log(JSON.stringify({schema:"hara.commander.event-v2.reliability-test.v1",
  scope:"ISOLATED_SOURCE_ONLY",pass:passes.length,fail:failures.length,
  failures:failures.map(({name,error})=>({name,error}))},null,2));
if(failures.length)process.exitCode=1;
