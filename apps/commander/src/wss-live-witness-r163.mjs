// DEV source instrumentation only. Native handles/probe timestamps are sampled
// by the server, independently of the load generator. No network is opened by
// this module; a collected record is never a financial or execution admission.
import {profileDigest} from './cloudflare-meter-reader.mjs';

const CONTRACT='commercial-0.3.56-durable-dev.v1';
const integer=n=>Number.isSafeInteger(n)&&n>=0;
const id=s=>typeof s==='string'&&/^[A-Za-z0-9_.:-]{1,180}$/.test(s);
const hex=(s,n)=>typeof s==='string'&&new RegExp('^[0-9a-f]{'+n+'}$').test(s);
const fail=code=>{throw Error(code);};
function bindingValid(binding,member=false){
  if(!binding||binding.approved===true||!hex(binding.source_head,40)
      ||!id(binding.worker_version)||!hex(binding.resource_sha256,64)
      ||member&&(!id(binding.tenant_id)||!id(binding.device_id)))fail('HOLD_WSS_BINDING');
}
function probeValid(connection,captured,maxProbeAgeMs){
  if(!id(connection?.connection_id)||!integer(connection.connected_at_ms)
      ||!integer(connection.last_probe_ms)||connection.connected_at_ms>connection.last_probe_ms
      ||connection.last_probe_ms>captured||captured-connection.last_probe_ms>maxProbeAgeMs)fail('HOLD_WSS_PROBE');
}
function bounds(nonce,maxProbeAgeMs){
  if(!hex(nonce,32)||!integer(maxProbeAgeMs)||maxProbeAgeMs<1||maxProbeAgeMs>120000)fail('HOLD_WSS_BINDING');
}

function qaBinding(env){
  if(env.ENVIRONMENT!=='DEV'||env.R163_QA_ISOLATED!=='true'
      ||env.R163_QA_WSS_WITNESS_ENABLED!=='true'||env.R163_QA_BUDGET_V2_ENABLED!=='true')fail('HOLD_WSS_QA_ISOLATION');
  const binding={source_head:env.R163_QA_SOURCE_HEAD,worker_version:env.CF_VERSION_METADATA?.id,
    resource_sha256:env.R163_QA_RESOURCE_SHA256};
  bindingValid(binding);
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(binding.worker_version))fail('HOLD_WSS_BINDING');
  return binding;
}

async function boundedJson(message,limit){
  const declared=message.headers.get('content-length');
  if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>limit))fail('HOLD_WSS_BODY');
  const reader=message.body?.getReader();if(!reader)fail('HOLD_WSS_BODY');
  const chunks=[];let length=0;
  try{
    for(;;){
      const {done,value}=await reader.read();if(done)break;
      length+=value.byteLength;
      if(length>limit){await reader.cancel();fail('HOLD_WSS_BODY');}
      chunks.push(value);
    }
    const raw=new Uint8Array(length);let cursor=0;
    for(const chunk of chunks){raw.set(chunk,cursor);cursor+=chunk.byteLength;}
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
  }catch{fail('HOLD_WSS_BODY');}finally{reader.releaseLock();}
}

// Called only from the internally authenticated DO status route, through its
// cumulative metering wrapper. Configuration remains protected native input.
export async function captureQaWssStatus(request,env,ctx,readDevice,{now=Date.now}={}){
  const common=qaBinding(env);
  if(request.method!=='GET'||request.headers.get('x-hara-channel-authenticated')!=='1')fail('HOLD_WSS_INTERNAL_AUTH');
  const binding={...common,tenant_id:request.headers.get('x-hara-tenant-id'),
    device_id:request.headers.get('x-hara-device-id')};
  bindingValid(binding,true);
  const nonce=request.headers.get('x-hara-wss-witness-nonce');bounds(nonce,90000);
  if(typeof readDevice!=='function')fail('HOLD_WSS_LIFECYCLE');
  const device=await readDevice(binding);
  if(!device||device.tenant_id!==binding.tenant_id||device.device_id!==binding.device_id
      ||device.state!=='ACTIVE'||device.revoked_at_utc!==null||device.tunnel_mode!=='EVENT_V2')fail('HOLD_WSS_LIFECYCLE');
  return captureWssStatus(ctx,binding,{nonce,now});
}

// One status lookup per control request. The independent executor collects
// bounded requests; a Worker invocation never fans out to 20,000 subrequests.
// The dedicated QA control authenticates before calling this helper, and both
// Worker and DO grants must be admitted before either can spend.
export async function readQaWssStatus(request,env){
  const common=qaBinding(env);
  if(request.method!=='POST'||!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type')||''))fail('HOLD_WSS_BODY');
  const member=await boundedJson(request,4096);
  if(!member||Object.keys(member).sort().join(',')!=='device_id,nonce,tenant_id')fail('HOLD_WSS_BODY');
  const binding={...common,tenant_id:member.tenant_id,device_id:member.device_id};
  bindingValid(binding,true);bounds(member.nonce,90000);
  if(typeof env.DEVICE_CHANNEL?.getByName!=='function')fail('HOLD_WSS_NAMESPACE');
  const stub=env.DEVICE_CHANNEL.getByName(member.tenant_id+':'+member.device_id);
  const response=await stub.fetch(new Request('https://device-channel/status',{headers:{
    'x-hara-channel-authenticated':'1','x-hara-tenant-id':member.tenant_id,
    'x-hara-device-id':member.device_id,'x-hara-wss-witness-nonce':member.nonce,
  },signal:request.signal}));
  if(!response.ok){await response.body?.cancel();fail('HOLD_WSS_STATUS');}
  const record=await boundedJson(response,16384),current=Date.now();
  bindingValid(record,true);
  if(record.schema!=='hara.commander.r163.wss-status.v1'||record.nonce!==member.nonce
      ||record.native_acceptance!==false||Object.entries(binding).some(([k,v])=>record[k]!==v)
      ||!integer(record.captured_ms)||record.captured_ms>current||current-record.captured_ms>90000
      ||!Array.isArray(record.connections))fail('HOLD_WSS_BINDING');
  for(const connection of record.connections)probeValid(connection,record.captured_ms,90000);
  return record;
}

export function captureWssStatus(ctx,binding,{nonce,now=Date.now,maxProbeAgeMs=90000}={}){
  bindingValid(binding,true);bounds(nonce,maxProbeAgeMs);
  const captured=now();
  if(!integer(captured)||typeof ctx?.getWebSockets!=='function'
      ||typeof ctx.getWebSocketAutoResponseTimestamp!=='function')fail('HOLD_WSS_NATIVE_TIMESTAMP');
  const connections=[];
  for(const socket of ctx.getWebSockets()){
    if(socket.readyState!==1)continue;
    const attachment=socket.deserializeAttachment();
    if(attachment?.superseded)continue;
    if(!attachment||attachment.tenant_id!==binding.tenant_id||attachment.device_id!==binding.device_id
        ||attachment.event_v2_contract!==CONTRACT)fail('HOLD_WSS_BINDING');
    const probe=ctx.getWebSocketAutoResponseTimestamp(socket);
    if(probe===null||probe===undefined)fail('HOLD_WSS_PROBE');
    const connection={connection_id:attachment.connection_id,connected_at_ms:attachment.connected_at_ms,
      last_probe_ms:Number(probe)};
    probeValid(connection,captured,maxProbeAgeMs);connections.push(connection);
  }
  return {schema:'hara.commander.r163.wss-status.v1',...binding,nonce,captured_ms:captured,
    connections,native_acceptance:false};
}

export async function collectWssWitness(cohort,fetchStatus,{binding,nonce,now=Date.now,
  maxConcurrent=8,maxSpanMs=5000,maxProbeAgeMs=90000,cohortSha256}={}){
  bindingValid(binding);bounds(nonce,maxProbeAgeMs);
  const expected=Object.freeze({source_head:binding.source_head,
    worker_version:binding.worker_version,resource_sha256:binding.resource_sha256});
  if(!Array.isArray(cohort)||!cohort.length||cohort.length>20000
      ||!integer(maxConcurrent)||maxConcurrent<1||maxConcurrent>64
      ||!integer(maxSpanMs)||maxSpanMs<1||maxSpanMs>60000||typeof fetchStatus!=='function')fail('HOLD_WSS_COHORT');
  const members=new Set(),snapshot=[];
  for(const member of cohort){
    if(!member||Object.keys(member).sort().join(',')!=='device_id,tenant_id'
        ||!id(member.tenant_id)||!id(member.device_id))fail('HOLD_WSS_COHORT');
    const key=JSON.stringify([member.tenant_id,member.device_id]);
    if(members.has(key))fail('HOLD_WSS_DUPLICATE_MEMBER');members.add(key);
    snapshot.push(Object.freeze({tenant_id:member.tenant_id,device_id:member.device_id}));
  }
  Object.freeze(snapshot);
  if(!hex(cohortSha256,64)||await profileDigest(snapshot)!==cohortSha256)fail('HOLD_WSS_COHORT_PIN');
  const records=new Array(snapshot.length),abort=new AbortController();
  let cursor=0,error,timer;
  const worker=async()=>{
    while(!error){
      const index=cursor++;if(index>=snapshot.length)return;
      try{records[index]=structuredClone(await fetchStatus({...snapshot[index]},{nonce,signal:abort.signal}));}
      catch(cause){
        const code=/^HOLD_[A-Z0-9_]{1,100}$/.test(cause?.message)?cause.message:'HOLD_WSS_STATUS';
        error??=Error(code);abort.abort();
      }
    }
  };
  try{
    await Promise.race([
      Promise.all(Array.from({length:Math.min(maxConcurrent,snapshot.length)},worker)),
      new Promise((_,reject)=>{timer=setTimeout(()=>{
        error=Error('HOLD_WSS_COLLECTION_TIMEOUT');abort.abort();reject(error);
      },maxSpanMs);}),
    ]);
    if(error)throw error;
  }finally{clearTimeout(timer);}
  const current=now(),ids=new Set();let first=Infinity,last=0,latestConnect=0;
  if(!integer(current))fail('HOLD_WSS_CLOCK');
  for(let index=0;index<records.length;index++){
    const record=records[index],member=snapshot[index];
    bindingValid(record,true);
    if(record.schema!=='hara.commander.r163.wss-status.v1'||record.nonce!==nonce
        ||record.native_acceptance!==false||record.tenant_id!==member.tenant_id
        ||record.device_id!==member.device_id||Object.entries(expected).some(([k,v])=>record[k]!==v))fail('HOLD_WSS_BINDING');
    if(!integer(record.captured_ms)||record.captured_ms>current||current-record.captured_ms>maxSpanMs
        ||!Array.isArray(record.connections)||record.connections.length!==1)fail('HOLD_WSS_COVERAGE');
    const connection=record.connections[0];probeValid(connection,record.captured_ms,maxProbeAgeMs);
    if(ids.has(connection.connection_id))fail('HOLD_WSS_DUPLICATE_CONNECTION');ids.add(connection.connection_id);
    first=Math.min(first,record.captured_ms);last=Math.max(last,record.captured_ms);
    latestConnect=Math.max(latestConnect,connection.connected_at_ms);
  }
  if(last-first>maxSpanMs||latestConnect>first)fail('HOLD_WSS_SIMULTANEOUS_INTERVAL');
  return {schema:'hara.commander.r163.wss-witness.v1',...expected,nonce,cohort_sha256:cohortSha256,
    live_wss:records.length,observed_at_ms:first,snapshot_span_ms:last-first,records,
    claim:'OPEN_HANDLE_AND_NATIVE_PROBE_INTERVAL_REQUIRES_INDEPENDENT_NATIVE_ATTESTATION',
    native_acceptance:false,execute_allowed:false};
}
