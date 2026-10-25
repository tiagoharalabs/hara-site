// Boundary tests use synthetic protected pins and fake product handlers. No
// Cloudflare invocation, native resource admission or Windows acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {profileDigest} from '../src/cloudflare-meter-reader.mjs';
import {OPERATION_DIMENSIONS} from '../src/qa-resource-budget.mjs';
import {wrapQaEntry} from './recovery_resource_qa_r163.mjs';
const bounds={schema:'hara.commander.r163.resource-bounds.v1',operations:Object.fromEntries(
 ['WORKER_FETCH','QUEUE','DLQ','SCHEDULED'].map(k=>[k,Object.fromEntries(OPERATION_DIMENSIONS.map(d=>[d,1000]))]))};
async function fixture(){
 const calls=[];const env={ENVIRONMENT:'DEV',R163_QA_ISOLATED:'true',R163_QA_BUDGET_V2_ENABLED:'true',
  R163_QA_OPERATION_BOUNDS_JSON:JSON.stringify(bounds),R163_QA_OPERATION_BOUNDS_SHA256:await profileDigest(bounds)};
 const legacy={fetch:async(req,e,ctx)=>{calls.push(['legacy',new URL(req.url).pathname]);
  ctx?.waitUntil?.(Promise.resolve().then(()=>calls.push(['background'])));return Response.json({legacy:true});},
  queue:async batch=>calls.push(['queue',batch.queue]),scheduled:async()=>calls.push(['scheduled'])};
 const product={fetch:async(req,e)=>{calls.push(['product',new URL(req.url).pathname]);return Response.json({product:true});}};
 const entry=wrapQaEntry(legacy,product,{budgetFactory:()=>({run:async(kind,upper,fn)=>{
  calls.push(['reserve',kind]);if(env.testDeny)throw Error('HOLD_SYNTHETIC_NATIVE_METER');
  const r=await fn(env);calls.push(['settled',kind]);return r;
 }})});return {calls,env,entry};
}
const request=path=>new Request('https://qa.invalid'+path,{method:path==='/api/device/channel'?'GET':'POST'});
test('default-OFF wrapper preserves the existing restricted QA surface',async()=>{
 const f=await fixture();delete f.env.R163_QA_BUDGET_V2_ENABLED;
 await f.entry.fetch(request('/api/device/calls/next'),f.env,{});
 assert.deepEqual(f.calls,[['legacy','/api/device/calls/next']]);
});
test('a changed operation profile cannot execute a product handler',async()=>{
 const f=await fixture();f.env.R163_QA_OPERATION_BOUNDS_SHA256='0'.repeat(64);
 const r=await f.entry.fetch(request('/api/device/calls/next'),f.env,{});
 assert.equal(r.status,503);assert.equal(f.calls.length,0);
});
test('claim complete lease and revoke route through the actual authenticated Worker behind a grant',async()=>{
 for(const path of ['/api/device/calls/next','/api/device/calls/complete','/api/device/product-lease','/api/device/revoke-self']){
  const f=await fixture();const r=await f.entry.fetch(request(path),f.env,{});
  assert.equal(r.status,200);assert.deepEqual(f.calls,[['reserve','WORKER_FETCH'],['product',path],['settled','WORKER_FETCH']]);
 }
});
test('missing native metering denies a grant before any product effect',async()=>{
 const f=await fixture();f.env.testDeny=true;
 const r=await f.entry.fetch(request('/api/device/calls/complete'),f.env,{});
 assert.equal(r.status,503);assert.deepEqual(f.calls,[['reserve','WORKER_FETCH']]);
});
test('waitUntil work completes inside the same grant and cannot escape settlement',async()=>{
 const f=await fixture();await f.entry.fetch(request('/api/device/heartbeat'),f.env,{});
 assert.deepEqual(f.calls,[['reserve','WORKER_FETCH'],['legacy','/api/device/heartbeat'],['background'],['settled','WORKER_FETCH']]);
});
test('Queue and DLQ invocations debit their distinct resource dimensions',async()=>{
 for(const [queue,kind] of [['hara-commander-r163-recovery-dev-20261024','QUEUE'],['hara-commander-r163-recovery-dlq-dev-20261024','DLQ']]){
  const f=await fixture();await f.entry.queue({queue,messages:[]},f.env,{});
  assert.deepEqual(f.calls,[['reserve',kind],['queue',queue],['settled',kind]]);
 }
 const f=await fixture();await assert.rejects(()=>f.entry.queue({queue:'unbound',messages:[]},f.env,{}));assert.equal(f.calls.length,0);
});
test('unbounded native WSS and file-driven start/debit remain explicit HOLD',async()=>{
 for(const path of ['/api/device/channel','/__qa/start','/__qa/debit']){
  const f=await fixture();const r=await f.entry.fetch(request(path),f.env,{});
  assert.equal(r.status,503);assert.ok((await r.json()).code.startsWith('HOLD_'));
  assert.ok(!f.calls.some(row=>['legacy','product'].includes(row[0])));
 }
});

import * as resource from './recovery_resource_qa_r163.mjs';
test('DO alarm uses an invocation view and meters storage and lifecycle in the same grant',async()=>{
 const f=await fixture(),calls=[];const originalDb={original:true},meteredDb={metered:true};
 class Core {constructor(ctx,env){this.ctx=ctx;this.env=env;this.presenceTail=Promise.resolve();}
  withPresence(fn){const p=this.presenceTail.then(fn);this.presenceTail=p.catch(()=>{});return p;}
  alarm(){return this.withPresence(async()=>{assert.equal(this.env.PRODUCT_DB,meteredDb);await this.ctx.storage.get('lifecycle');await this.ctx.storage.setAlarm(1000);});}}
 const Wrapped=resource.wrapQaDeviceChannel(Core,{budgetFactory:env=>({run:async(kind,upper,work)=>{
  calls.push(kind);return work({...env,PRODUCT_DB:meteredDb},{effect:async(counts,fn)=>{calls.push(counts);return fn();},consume:counts=>calls.push(counts)});
 }})});
 const p=structuredClone(bounds);p.operations.DO_ALARM=p.operations.WORKER_FETCH;
 f.env.R163_QA_OPERATION_BOUNDS_JSON=JSON.stringify(p);f.env.R163_QA_OPERATION_BOUNDS_SHA256=await profileDigest(p);f.env.PRODUCT_DB=originalDb;
 const actor=new Wrapped({storage:{async get(){return 'stored';},async setAlarm(){}},getWebSockets:()=>[]},f.env);
 await actor.alarm();assert.equal(actor.env.PRODUCT_DB,originalDb);
 assert.deepEqual(calls,['DO_ALARM',{do_storage_reads:1},{do_storage_writes:1,do_alarms:1}]);
});
test('unbounded DO auto-response connect cannot mutate product lifecycle',async()=>{
 const f=await fixture();let effects=0;
 class Core{constructor(ctx,env){this.ctx=ctx;this.env=env;}async fetch(){effects++;return Response.json({ok:true});}}
 const Wrapped=resource.wrapQaDeviceChannel(Core,{budgetFactory:()=>({run:async(_k,_u,fn)=>fn(f.env,{})})});
 const p=structuredClone(bounds);p.operations.DO_FETCH=p.operations.WORKER_FETCH;
 f.env.R163_QA_OPERATION_BOUNDS_JSON=JSON.stringify(p);f.env.R163_QA_OPERATION_BOUNDS_SHA256=await profileDigest(p);
 const actor=new Wrapped({getWebSockets:()=>[]},f.env);
 await assert.rejects(()=>actor.fetch(new Request('https://do.invalid/connect')),/HOLD_NATIVE_WEBSOCKET_METER/);assert.equal(effects,0);
});

test('existing socket input and output share the invocation meter',async()=>{
 const f=await fixture(),counts=[],sent=[];const socket={send:m=>sent.push(m),close(){}};
 class Core{constructor(ctx,env){this.ctx=ctx;this.env=env;}async webSocketMessage(s,m){s.send(m);}}
 const p=structuredClone(bounds);p.operations.DO_MESSAGE=p.operations.WORKER_FETCH;
 f.env.R163_QA_OPERATION_BOUNDS_JSON=JSON.stringify(p);f.env.R163_QA_OPERATION_BOUNDS_SHA256=await profileDigest(p);
 const Wrapped=resource.wrapQaDeviceChannel(Core,{budgetFactory:()=>({run:async(_k,_u,fn)=>fn(f.env,{consume:c=>counts.push(c)})})});
 const actor=new Wrapped({storage:{},getWebSockets:()=>[socket]},f.env);await actor.webSocketMessage(socket,'reply');
 assert.deepEqual(sent,['reply']);assert.deepEqual(counts,[{ws_messages_in:1},{ws_messages_out:1}]);
});

test('nested waitUntil is drained before settling the resource grant',async()=>{
 const f=await fixture(),order=[];let release,entered;
 const started=new Promise(resolve=>{entered=resolve;});
 const late=new Promise(resolve=>{release=resolve;});
 const legacy={fetch:async(_r,_e,ctx)=>{ctx.waitUntil(new Promise(resolve=>setImmediate(resolve)).then(()=>{
  ctx.waitUntil(late.then(()=>order.push('late-effect')));
 }));entered();return Response.json({ok:true});}};
 const entry=wrapQaEntry(legacy,legacy,{budgetFactory:()=>({run:async(_k,_u,fn)=>{
  const r=await fn(f.env);order.push('settled');return r;
 }})});
 const response=entry.fetch(request('/api/device/heartbeat'),f.env,{});
 await started;
 await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(order,[]);
 release();await response;assert.deepEqual(order,['late-effect','settled']);
});
