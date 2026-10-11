import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
const source = fs.readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
const helper = source.split('// PORTAL_READ_COORDINATOR_BEGIN')[1]?.split('// PORTAL_READ_COORDINATOR_END')[0];
assert.ok(helper, 'EXACT_SHIPPED_COORDINATOR_REQUIRED');
const make = vm.runInNewContext(helper + '\ncreatePortalReadCoordinator', {URL, Request, Response, AbortController, DOMException, setTimeout, clearTimeout});
const origin = 'https://commander.example.invalid';
const path = '/api/portal/devices';
const tests = [];
const test = async (name, fn) => { await fn(); tests.push({name, state:'PASS'}); };
const json = (data={ok:true}, init={}) => new Response(JSON.stringify(data),init);

await test('1000_concurrent_same_tab_reads_share_one_network_request', async () => {
  let count=0, release;
  const blocked = new Promise(r=>release=r);
  const read=make(async()=>{count++; await blocked; return json({unique:42});},origin);
  const jobs=Array.from({length:1000},()=>read(path).then(r=>r.json()));
  assert.equal(count,1); release();
  const values=await Promise.all(jobs);
  assert.ok(values.every(v=>v.unique===42)); assert.equal(count,1);
  await read(path); assert.equal(count,2); // No completed-response cache.
});
await test('distinct_endpoints_are_not_coalesced', async()=>{
  let n=0; const read=make(async()=>json({n:++n}),origin);
  const out=await Promise.all([read(path),read('/api/portal/session')]);
  assert.equal(n,2); assert.equal(out.length,2);
});
await test('post_requests_never_coalesced_or_retried', async()=>{
  let n=0;const read=make(async()=>{n++;return json();},origin);
  await Promise.all([read('/api/portal/devices/revoke',{method:'POST',body:'{}'}),read('/api/portal/devices/revoke',{method:'POST',body:'{}'})]);
  assert.equal(n,2);
});
await test('writes_abort_inflight_reads_and_new_reads_use_new_generation',async()=>{
  let readCalls=0, aborts=0;
  const read=make(async(url,init)=>{
    if(init.method==='POST') return json();
    if(++readCalls===1) return new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>{aborts++;reject(new DOMException('Aborted','AbortError'));},{once:true}));
    return json({fresh:true});
  },origin);
  const old=read(path);const rejected=assert.rejects(old,{name:'AbortError'});
  await read('/api/portal/devices/select',{method:'POST'});await rejected;
  assert.equal(aborts,1);assert.equal((await (await read(path)).json()).fresh,true);
});
await test('logout_also_invalidates_prior_reads',async()=>{
  let aborted=false;const read=make(async(url,init)=>{
    if(url==='/auth/logout') return json();
    return new Promise((_,reject)=>init.signal.addEventListener('abort',()=>{aborted=true;reject(new DOMException('Aborted','AbortError'));}));
  },origin);
  const first=read(path);const rejected=assert.rejects(first,{name:'AbortError'});
  await read('/auth/logout',{method:'POST'});await rejected;assert.equal(aborted,true);
});
await test('retry_after_seconds_suppresses_only_same_endpoint',async()=>{
  let now=0,n=0;const read=make(async()=>{n++;return json({}, {status:429,headers:{'retry-after':'30'}});},origin,{now:()=>now});
  assert.equal((await read(path)).status,429);
  assert.equal((await read(path)).status,429);assert.equal(n,1);
  await read('/api/portal/session');assert.equal(n,2);
  now=31000;await read(path);assert.equal(n,3);
});
await test('retry_after_http_date_is_respected',async()=>{
  let now=Date.parse('2026-10-11T12:00:00Z'),n=0;
  const read=make(async()=>{n++;return json({}, {status:503,headers:{'retry-after':'Sun, 11 Oct 2026 12:02:00 GMT'}});},origin,{now:()=>now});
  await read(path);now+=60000;await read(path);assert.equal(n,1);
  now+=61000;await read(path);assert.equal(n,2);
});
await test('malformed_retry_after_uses_bounded_jitter_without_automatic_retry',async()=>{
  let now=0,n=0;const read=make(async()=>{n++;return json({}, {status:503,headers:{'retry-after':'bad'}});},origin,{now:()=>now,random:()=>0.5});
  await read(path);now=2000;await read(path);assert.equal(n,1);
  now=2501;await read(path);assert.equal(n,2);
});
await test('401_is_not_cached',async()=>{
  let n=0;const read=make(async()=>{n++;return json({}, {status:401});},origin);
  await read(path);await read(path);assert.equal(n,2);
});
await test('network_failure_is_released_and_never_auto_retried',async()=>{
  let n=0;const read=make(async()=>{if(++n===1)throw new TypeError('network');return json();},origin);
  await assert.rejects(read(path));assert.equal(n,1);await read(path);assert.equal(n,2);
});
await test('timeout_aborts_network_and_releases_slot',async()=>{
  let timer,n=0;const read=make(async(_url,init)=>{
    if(++n>1)return json();
    return new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Timeout','AbortError'))));
  },origin,{setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{}});
  const p=read(path);const rejected=assert.rejects(p,{name:'AbortError'});timer();await rejected;
  await read(path);assert.equal(n,2);
});
await test('timeout_covers_body_not_just_headers',async()=>{
  let timer,signal,cancelled=false;
  const response=new Response(new ReadableStream({cancel(){cancelled=true;}}));
  const read=make(async(_url,init)=>{signal=init.signal;return response;},origin,{setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{}});
  const p=read(path);const rejected=assert.rejects(p,{name:'AbortError'});
  await Promise.resolve();timer();assert.equal(signal.aborted,true);await rejected;assert.equal(cancelled,true);
});
await test('custom_headers_signals_query_and_credentials_bypass_sharing',async()=>{
  for(const init of [{headers:{'x-test':'1'}},{signal:new AbortController().signal},{credentials:'omit'}]){
    let n=0;const read=make(async()=>{n++;return json();},origin);
    await Promise.all([read(path,init),read(path,init)]);assert.equal(n,2);
  }
  let n=0;const read=make(async()=>{n++;return json();},origin);
  await Promise.all([read(path+'?x=1'),read(path+'?x=1')]);assert.equal(n,2);
});
await test('external_and_localhost_requests_are_unchanged',async()=>{
  let n=0;const read=make(async()=>{n++;return json();},origin);
  const url='http://127.0.0.1:32145/activity';await Promise.all([read(url),read(url)]);assert.equal(n,2);
});
await test('204_response_remains_bodyless',async()=>{
  const read=make(async()=>new Response(null,{status:204}),origin);assert.equal((await read(path)).status,204);
});
await test('all_existing_fetch_calls_route_through_coordinator',async()=>{
  assert.ok(source.includes('const portalFetch = createPortalReadCoordinator'));
  assert.equal((source.match(/\bfetch\(/g)||[]).length,1);
  assert.ok(source.includes('portalFetch("/auth/logout", { method: "POST"'));
});

for (const outcome of ['success','http_error','network_error']) {
  await test('reads_during_write_invalidated_at_'+outcome,async()=>{
    let endWrite,endRead,n=0;
    const writing=new Promise(r=>endWrite=r),reading=new Promise(r=>endRead=r);
    const read=make(async(_url,init)=>{
      if(init.method==='POST') {n++;await writing;if(outcome==='network_error')throw new TypeError('synthetic');return json({}, {status:outcome==='http_error'?503:200});}
      await reading;return json({stale:true});
    },origin);
    const write=read('/api/portal/devices/select',{method:'POST'}).catch(e=>e);
    const stale=read(path).then(()=>({accepted:true}),e=>({accepted:false,name:e.name}));
    endWrite();await write;endRead();
    assert.deepEqual(await stale,{accepted:false,name:'AbortError'});assert.equal(n,1);
  });
}
for(const useOverride of [false,true]) {
  await test('request_object_write_invalidates_'+useOverride,async()=>{
    let endRead,seen;
    const reading=new Promise(r=>endRead=r);
    const input=new Request(origin+'/api/portal/devices/select',{method:useOverride?'GET':'POST'});
    const read=make(async(value,init)=>{
      if(value===input){seen=value;return json();}
      await reading;return json({stale:true});
    },origin);
    const stale=read(path).then(()=>false,e=>e.name==='AbortError');
    await read(input,useOverride?{method:'POST'}:{});endRead();
    assert.equal(await stale,true);assert.equal(seen,input);
  });
}
await test('each_overlapping_write_completion_invalidates_reads',async()=>{
  let finishOne,finishTwo,finishRead;
  const one=new Promise(r=>finishOne=r),two=new Promise(r=>finishTwo=r),reading=new Promise(r=>finishRead=r);
  const read=make(async(_url,init)=>{
    if(init.method==='POST'){await (init.body==='one'?one:two);return json();}
    await reading;return json({stale:true});
  },origin);
  const first=read('/api/portal/devices/select',{method:'POST',body:'one'});
  const second=read('/api/portal/devices/select',{method:'POST',body:'two'});
  finishOne();await first;
  const stale=read(path).then(()=>false,e=>e.name==='AbortError');
  finishTwo();await second;finishRead();assert.equal(await stale,true);
});

console.log(JSON.stringify({state:'PASS',source_app_sha256:createHash('sha256').update(source).digest('hex'),tests:tests.length,results:tests,environment:'NODE_WITH_MOCK_NETWORK_NOT_CLOUDFLARE',certifies_cloudflare_concurrency:false},null,2));
