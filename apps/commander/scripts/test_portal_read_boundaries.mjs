import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
const source = fs.readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
const helper = source.split('// PORTAL_READ_COORDINATOR_BEGIN')[1]?.split('// PORTAL_READ_COORDINATOR_END')[0];
assert.ok(helper, 'EXACT_SOURCE_REQUIRED');
const make = vm.runInNewContext(helper + '\ncreatePortalReadCoordinator', {URL, Request, Response, AbortController, DOMException, setTimeout, clearTimeout});
const origin = 'https://commander.example.invalid';
const path = '/api/portal/devices';
const rows = [];
async function test(name, fn) {let timer;try {await Promise.race([fn(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('TEST_DEADLINE')),500);})]);rows.push({name,state:'PASS'});}catch(e){rows.push({name,state:'FAIL',error:e.message === 'TEST_DEADLINE' ? e.message : e.code || e.name});}finally{clearTimeout(timer);}}
const oversized = e => e?.message === 'PORTAL_READ_RESPONSE_TOO_LARGE';
const body = n => new Response(new Uint8Array(n));
await test('declared_oversize_rejected_before_body_read',async()=>{
 let reads=0,signal,cancelled=false;
 const response={headers:new Headers({'content-length':'100'}),body:{getReader(){return {async read(){reads++;return {done:true};},async cancel(){cancelled=true;},releaseLock(){}};}}};
 const read=make(async(_url,init)=>{signal=init.signal;return response;},origin,{maxResponseBytes:32});
 await assert.rejects(read(path),oversized);assert.equal(reads,0);assert.equal(signal.aborted,true);assert.equal(cancelled,true);
});
await test('streamed_oversize_without_length_is_cancelled',async()=>{
 let cancelled=false,pulls=0;
 const stream=new ReadableStream({pull(c){if(++pulls<=3)c.enqueue(new Uint8Array(20));else c.close();},cancel(){cancelled=true;}});
 const read=make(async()=>new Response(stream),origin,{maxResponseBytes:32});
 await assert.rejects(read(path),oversized);assert.equal(cancelled,true);
});
await test('false_content_length_cannot_hide_actual_oversize',async()=>{
 const read=make(async()=>new Response(new Uint8Array(64),{headers:{'content-length':'1'}}),origin,{maxResponseBytes:32});
 await assert.rejects(read(path),oversized);
});
await test('limit_is_bytes_not_character_count',async()=>{
 const read=make(async()=>new Response('á'.repeat(17)),origin,{maxResponseBytes:32});
 await assert.rejects(read(path),oversized);
});
await test('exact_limit_preserves_all_bytes',async()=>{
 const bytes=new Uint8Array(32).map((_,i)=>i);
 const read=make(async()=>new Response(bytes),origin,{maxResponseBytes:32});
 assert.deepEqual(new Uint8Array(await (await read(path)).arrayBuffer()),bytes);
});
await test('oversized_read_releases_slot_without_retry',async()=>{
 let n=0;const read=make(async()=>body(++n===1?33:16),origin,{maxResponseBytes:32});
 await assert.rejects(read(path),oversized);assert.equal(n,1);
 assert.equal((await (await read(path)).arrayBuffer()).byteLength,16);assert.equal(n,2);
});
await test('shared_oversized_read_rejects_all_waiters_once',async()=>{
 let n=0,release;const blocked=new Promise(r=>release=r);
 const read=make(async()=>{n++;await blocked;return body(33);},origin,{maxResponseBytes:32});
 const jobs=Array.from({length:16},()=>read(path).then(()=>false,oversized));release();
 assert.ok((await Promise.all(jobs)).every(Boolean));assert.equal(n,1);
});
await test('custom_fetch_options_keep_independent_native_requests',async()=>{
 for(const init of [{cache:'reload'},{redirect:'manual'},{integrity:'sha256-example'},{mode:'same-origin'},{referrerPolicy:'no-referrer'},{keepalive:true}]){
  let n=0;const read=make(async(_url,options)=>{assert.equal(options,init);n++;return body(1);},origin);
  await Promise.all([read(path,init),read(path,init)]);assert.equal(n,2);
 }
});
await test('default_and_no_store_do_not_share_a_read',async()=>{
 let n=0,release;const blocked=new Promise(r=>release=r);
 const read=make(async()=>{n++;await blocked;return body(1);},origin);
 const jobs=[read(path),read(path,{cache:'no-store'})];release();await Promise.all(jobs);assert.equal(n,2);
});
await test('same_no_store_requests_still_share_one_read',async()=>{
 let n=0,release;const blocked=new Promise(r=>release=r);
 const read=make(async()=>{n++;await blocked;return body(1);},origin);
 const jobs=Array.from({length:32},()=>read(path,{cache:'no-store',credentials:'same-origin'}));release();
 await Promise.all(jobs);assert.equal(n,1);
});
await test('abort_cancels_stalled_stream_and_clears_deadline',async()=>{
 let timer,cleared=0,cancelled=false;
 const response=new Response(new ReadableStream({cancel(){cancelled=true;}}));
 const read=make(async()=>response,origin,{setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{cleared++;}});
 const pending=read(path);const rejected=assert.rejects(pending,{name:'AbortError'});
 await Promise.resolve();timer();await rejected;
 assert.equal(cancelled,true);assert.equal(cleared,1);
});
await test('bodyless_success_still_works',async()=>{
 const read=make(async()=>new Response(null,{status:204}),origin,{maxResponseBytes:32});
 const response=await read(path);assert.equal(response.status,204);assert.equal(await response.text(),'');
});
const report={schema:'hara.portal-read-boundaries-tests.v1',source_app_sha256:createHash('sha256').update(source).digest('hex'),checked:rows.length,passed:rows.filter(x=>x.state==='PASS').length,failed:rows.filter(x=>x.state==='FAIL').length,scope:'LOCAL_MOCKED_HTTP_NO_NETWORK',tests:rows};
console.log(JSON.stringify(report,null,2));process.exitCode=report.failed?1:0;
