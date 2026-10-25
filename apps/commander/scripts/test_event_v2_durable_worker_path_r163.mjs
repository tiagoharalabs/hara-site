// #163: execute the real Worker's durable claim/completion SQL with SQLite.
// Authentication and metadata boundaries are synthetic fixtures. This is not
// hosted WSS, a 20k transport test, or commercial Agent Event V2 acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';

const sourcePath=process.env.R163_WORKER_SOURCE||new URL('../src/worker.js',import.meta.url);
const source=fs.readFileSync(sourcePath,'utf8');
const sha=value=>createHash('sha256').update(value).digest('hex');
function realFunction(name){
  const start=source.search(new RegExp('^async function '+name+'\\(', 'm'));
  assert.ok(start>=0,'real Worker function missing: '+name);
  const closing=/^}\r?$/gm;closing.lastIndex=start;
  const end=closing.exec(source);
  assert.ok(end&&end.index>start,'real Worker function end missing: '+name);
  return source.slice(start,end.index+1);
}
const claimSource=realFunction('claimNextDeviceCall');
const completeSource=realFunction('completeDeviceCall');
const NOW=Date.parse('2026-10-25T00:00:00.000Z');
const iso=offset=>new Date(NOW+offset).toISOString();
const FIELDS=['call_id','request_id','tenant_id','device_id','tool_id','payload_json',
  'state','created_at_utc','claimed_at_utc','completed_at_utc','expires_at_utc',
  'usage_mode','usage_units','usage_period_key','usage_budget_id',
  'approval_timeout_seconds','execution_budget_ms','result_json','error_code',
  'call_result_metadata_json'];

function fixture(t){
  const db=new DatabaseSync(':memory:');let now=NOW;
  const writes=[],observations=[],hooks={};
  db.exec(`CREATE TABLE commander_devices(
    device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,state TEXT NOT NULL,
    revoked_at_utc TEXT,platform TEXT,approval_mode TEXT,agent_version TEXT);
    CREATE TABLE commander_device_calls(
    call_id TEXT PRIMARY KEY,request_id TEXT NOT NULL,tenant_id TEXT NOT NULL,
    device_id TEXT NOT NULL,tool_id TEXT NOT NULL,payload_json TEXT NOT NULL,
    state TEXT NOT NULL,created_at_utc TEXT NOT NULL,claimed_at_utc TEXT,
    completed_at_utc TEXT,expires_at_utc TEXT NOT NULL,
    usage_mode TEXT,usage_units INTEGER,usage_period_key TEXT,usage_budget_id TEXT,
    approval_timeout_seconds INTEGER NOT NULL DEFAULT 0,
    execution_budget_ms INTEGER NOT NULL DEFAULT 30000,
    result_json TEXT,error_code TEXT,call_result_metadata_json TEXT);
    CREATE INDEX idx_device_calls_poll
      ON commander_device_calls(device_id,state,expires_at_utc,created_at_utc);
    INSERT INTO commander_devices VALUES
      ('SYNTHETIC-DEVICE-A','SYNTHETIC-TENANT-A','ACTIVE',NULL,'LINUX','PERSISTENT_TRUSTED','0.3.56'),
      ('SYNTHETIC-DEVICE-B','SYNTHETIC-TENANT-B','ACTIVE',NULL,'LINUX','PERSISTENT_TRUSTED','0.3.56');`);
  const adapter={prepare:sql=>({bind:(...args)=>({
    all:async()=>{
      const rows=db.prepare(sql).all(...args);
      if(/^\s*UPDATE\b/i.test(sql))writes.push({sql,changes:rows.length});
      return {results:rows};
    },
    first:async()=>db.prepare(sql).get(...args)??null,
    run:async()=>{const result=db.prepare(sql).run(...args);
      if(/^\s*UPDATE\b/i.test(sql))writes.push({sql,changes:result.changes});
      return {meta:{changes:result.changes}};},
  })})};
  const env={PRODUCT_DB:adapter};
  // A real credential verifier is intentionally outside this fixture. Identity
  // is supplied by the test boundary and then resolved from live SQLite rows.
  const resolveDeviceCredential=async(_env,request)=>{
    const row=db.prepare('SELECT * FROM commander_devices WHERE device_id=?')
      .get(request.headers.get('x-synthetic-authenticated-device'));
    if(!row||row.state!=='ACTIVE'||row.revoked_at_utc)throw Error('DEVICE_AUTH_INVALID');
    // Model an independently committed revocation after the credential read,
    // while preserving the authenticated snapshot returned by that read.
    await hooks.afterCredential?.(row);
    return row;
  };
  const context=vm.createContext({
    console,TextEncoder,JSON,Number,String,
    resolveDeviceCredential,nowIso:()=>new Date(now).toISOString(),
    CALL_ROW_FIELDS:FIELDS.join(','),
    asyncApprovalDevice:device=>device.platform==='WINDOWS'&&device.approval_mode==='ASK_EVERY_ACTION',
    cleanId:(value,max)=>{
      if(typeof value!=='string'||value.length<1||value.length>max||!/^[A-Za-z0-9_.:-]+$/.test(value))throw Error('ID_INVALID');
      return value;
    },
    boundedJson:(value,max,code)=>{const raw=JSON.stringify(value);
      if(Buffer.byteLength(raw)>max)throw Error(code);return raw;},
    redactedDeviceCallContent:async raw=>JSON.stringify({schema:'SYNTHETIC_REDACTED_HASH_ONLY',sha256:sha(raw)}),
    deviceCallStoredContentMatches:async(stored,incoming)=>{
      if(stored===incoming)return true;
      try {const marker=JSON.parse(stored);return marker.schema==='SYNTHETIC_REDACTED_HASH_ONLY'&&marker.sha256===sha(incoming);}
      catch{return false;}
    },
    safeCallResultMetadata:(result,row)=>({state:row.state,error_code:row.error_code,
      receipt_sha256:typeof result?.bridge_receipt_sha256==='string'?result.bridge_receipt_sha256:null}),
    settleCallUsage:async()=>{throw Error('UNEXPECTED_ASYNC_APPROVAL_USAGE_IN_LINUX_FIXTURE');},
    reconcileAgentVersion:async(_env,device,call)=>{observations.push({device:device.device_id,call:call.call_id});},
  });
  vm.runInContext(claimSource+'\n'+completeSource+
    '\nglobalThis.subject=Object.freeze({claimNextDeviceCall,completeDeviceCall});',context);
  const request=(device='SYNTHETIC-DEVICE-A',query='')=>new Request(
    'https://synthetic.invalid/api/device/calls/next'+query,
    {method:'POST',headers:{'x-synthetic-authenticated-device':device}});
  const add=(id,{tenant='SYNTHETIC-TENANT-A',device='SYNTHETIC-DEVICE-A',
    created=-1000,expires=60000,payload={synthetic_intent:id}}={})=>{
    db.prepare(`INSERT INTO commander_device_calls
      (call_id,request_id,tenant_id,device_id,tool_id,payload_json,state,
       created_at_utc,expires_at_utc,usage_mode,usage_units,usage_period_key)
      VALUES(?,?,?,?,?,?,'PENDING',?,?,?,1,'2026-10')`).run(
        id,'REQUEST-'+id,tenant,device,'hara.device.info',JSON.stringify(payload),iso(created),iso(expires),'CLOUD_QUOTA');
  };
  const row=id=>db.prepare('SELECT * FROM commander_device_calls WHERE call_id=?').get(id);
  const completion=(id,extra={})=>({call_id:id,state:'COMPLETED',result:{
    synthetic_result:'completed-once',bridge_receipt_sha256:'a'.repeat(64),...extra}});
  const claim=req=>context.subject.claimNextDeviceCall(env,req??request());
  const complete=(body,req)=>context.subject.completeDeviceCall(env,req??request(),body);
  const acceptedCompletionWrites=()=>writes.filter(write=>/SET state = \?, completed_at_utc/.test(write.sql))
    .reduce((count,write)=>count+write.changes,0);
  t.after(()=>db.close());
  return {db,writes,observations,hooks,request,add,row,claim,complete,completion,acceptedCompletionWrites,
    at:offset=>{now=NOW+offset;}};
}

test('forged wake IDs and no-wake V1 fallback both select the first authorized durable call',async t=>{
  for(const query of ['?call_id=FORGED-TENANT-B&tenant_id=SYNTHETIC-TENANT-B','']){
    const f=fixture(t);
    f.add('FIRST-A',{created:-2000});f.add('SECOND-A',{created:-1000});
    f.add('FORGED-TENANT-B',{tenant:'SYNTHETIC-TENANT-B',device:'SYNTHETIC-DEVICE-B',created:-3000});
    const claim=await f.claim(f.request('SYNTHETIC-DEVICE-A',query));
    assert.equal(claim.schema,'hara.commander-device-call-claim.v1');
    assert.equal(claim.call_id,'FIRST-A');assert.equal(claim.payload.synthetic_intent,'FIRST-A');
    assert.equal(f.row('FIRST-A').state,'EXECUTING');assert.equal(f.row('SECOND-A').state,'PENDING');
    assert.equal(f.row('FORGED-TENANT-B').state,'PENDING');
    assert.notEqual(f.row('FIRST-A').payload_json,JSON.stringify(claim.payload),'claimed payload was not redacted');
  }
});
test('parallel duplicate claims yield one EXECUTING call and tenant B cannot complete tenant A',async t=>{
  const f=fixture(t);f.add('ONE-A');
  const results=await Promise.all(Array.from({length:8},()=>f.claim()));
  assert.equal(results.filter(Boolean).length,1);
  assert.equal(f.db.prepare("SELECT count(*) AS n FROM commander_device_calls WHERE state='EXECUTING'").get().n,1);
  const before=f.writes.reduce((n,row)=>n+row.changes,0);
  await assert.rejects(()=>f.complete(f.completion('ONE-A'),f.request('SYNTHETIC-DEVICE-B')),/DEVICE_CALL_NOT_FOUND/);
  assert.equal(f.row('ONE-A').state,'EXECUTING');assert.equal(f.row('ONE-A').result_json,null);
  assert.equal(f.writes.reduce((n,row)=>n+row.changes,0),before);
});
test('completion receipt replay is existing true without a second accepted update; conflicting content is denied',async t=>{
  const f=fixture(t);f.add('REPLAY-A');await f.claim();const body=f.completion('REPLAY-A');
  const accepted=await f.complete(body),saved={...f.row('REPLAY-A')};
  assert.equal(accepted.existing,false);assert.equal(f.acceptedCompletionWrites(),1);
  const replay=await f.complete(body);
  assert.equal(replay.existing,true);assert.equal(f.acceptedCompletionWrites(),1);
  assert.equal(f.observations.length,1,'replayed completion repeated version observation');
  assert.deepEqual({...f.row('REPLAY-A')},saved);
  await assert.rejects(()=>f.complete(f.completion('REPLAY-A',{synthetic_result:'different-effect-same-receipt'})),/IDEMPOTENCY_CONFLICT/);
  assert.equal(f.acceptedCompletionWrites(),1);assert.deepEqual({...f.row('REPLAY-A')},saved);
});
test('expired pending calls cannot be claimed and expired execution cannot be accepted as completed',async t=>{
  const f=fixture(t);f.add('ALREADY-EXPIRED',{created:-3000,expires:-1});
  assert.equal(await f.claim(),null);assert.equal(f.row('ALREADY-EXPIRED').state,'PENDING');
  f.add('EXPIRES-AFTER-CLAIM',{expires:1000});assert.equal((await f.claim()).call_id,'EXPIRES-AFTER-CLAIM');
  f.at(1001);
  await assert.rejects(()=>f.complete(f.completion('EXPIRES-AFTER-CLAIM')),/DEVICE_CALL_EXPIRED/);
  assert.equal(f.row('EXPIRES-AFTER-CLAIM').state,'EXPIRED');
  assert.equal(f.row('EXPIRES-AFTER-CLAIM').error_code,'DEVICE_CALL_EXPIRED');
  assert.equal(f.row('EXPIRES-AFTER-CLAIM').result_json,null);assert.equal(f.acceptedCompletionWrites(),0);
});
test('revoked enrollment cannot claim pending work or complete an already claimed effect',async t=>{
  const f=fixture(t);f.add('CLAIMED-BEFORE-REVOKE');await f.claim();f.add('PENDING-A');
  f.db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id=?")
    .run(iso(0),'SYNTHETIC-DEVICE-A');
  const before=f.writes.reduce((n,row)=>n+row.changes,0);
  await assert.rejects(()=>f.claim(),/DEVICE_AUTH_INVALID/);
  await assert.rejects(()=>f.complete(f.completion('CLAIMED-BEFORE-REVOKE')),/DEVICE_AUTH_INVALID/);
  assert.equal(f.row('PENDING-A').state,'PENDING');assert.equal(f.row('CLAIMED-BEFORE-REVOKE').state,'EXECUTING');
  assert.equal(f.row('CLAIMED-BEFORE-REVOKE').result_json,null);assert.equal(f.acceptedCompletionWrites(),0);
  assert.equal(f.writes.reduce((n,row)=>n+row.changes,0),before);
  // The real claim UPDATE joins the current enrollment. Completion must retain
  // the same live fence across its await of the credential-read snapshot.
  const race=fixture(t);race.add('REVOCATION-RACE');
  const revoke=()=>race.db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id=?")
    .run(iso(0),'SYNTHETIC-DEVICE-A');
  race.hooks.afterCredential=revoke;
  assert.equal(await race.claim(),null,'claim trusted a stale ACTIVE credential snapshot');
  assert.equal(race.row('REVOCATION-RACE').state,'PENDING');
  race.hooks.afterCredential=null;
  race.db.prepare("UPDATE commander_devices SET state='ACTIVE',revoked_at_utc=NULL WHERE device_id=?")
    .run('SYNTHETIC-DEVICE-A');
  await race.claim();race.hooks.afterCredential=revoke;
  await assert.rejects(()=>race.complete(race.completion('REVOCATION-RACE')),/DEVICE_/,
    'completion trusted an ACTIVE snapshot after live enrollment revocation');
  assert.notEqual(race.row('REVOCATION-RACE').state,'COMPLETED');
  assert.equal(race.row('REVOCATION-RACE').result_json,null);assert.equal(race.acceptedCompletionWrites(),0);
});
test('parallel completion replay accepts one durable terminal result without repeating completion observations',async t=>{
  const f=fixture(t);f.add('CONCURRENT-COMPLETE');await f.claim();const body=f.completion('CONCURRENT-COMPLETE');
  const replies=await Promise.all(Array.from({length:8},()=>f.complete(body)));
  assert.equal(replies.filter(reply=>reply.existing===false).length,1);
  assert.equal(replies.filter(reply=>reply.existing===true).length,7);
  assert.equal(f.acceptedCompletionWrites(),1);assert.equal(f.observations.length,1);
  assert.equal(f.row('CONCURRENT-COMPLETE').state,'COMPLETED');
});

console.log(JSON.stringify({schema:'hara.commander.event-v2.durable-worker-path-test.v1',
  scope:'REAL_WORKER_FUNCTIONS_REAL_SQLITE_SYNTHETIC_AUTH_BOUNDARY',source_sha256:sha(source),
  function_sha256:{claimNextDeviceCall:sha(claimSource),completeDeviceCall:sha(completeSource)},
  auth_boundary_fake:true,metadata_helpers_fake:true,hosted_wss_20k:false,commercial_agent_event_v2_acceptance:false}));
