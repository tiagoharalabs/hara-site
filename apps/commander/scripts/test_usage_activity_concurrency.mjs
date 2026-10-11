import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

// Optional excerpt fixtures make the before/after regression reproducible offline.
// With no argument, the test reads the full, actual product source in the repo.
const sourcePath = process.argv[2] || fileURLToPath(new URL('../public/app.js', import.meta.url));
const excerptMode = process.argv.includes('--excerpts');
const source = fs.readFileSync(sourcePath, 'utf8');
function extract(start, end) {
  const a = source.indexOf(start);
  const b = source.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, 'SOURCE_FUNCTION_BOUNDARIES_REQUIRED');
  return source.slice(a, b).trim();
}
const guestSource = extract('  function setGuestHeader() {', '  function setAuthenticatedHeader(');
const loaderSource = extract('  async function loadUsageActivity(', '  async function loadServiceHealth(');
const deferred = () => { let resolve, reject; const promise = new Promise((a,b)=>{resolve=a;reject=b;}); return {promise,resolve,reject}; };
const payload = (window, tag) => ({window:{key:window},tag,transactions:[]});
const button = () => ({isConnected:true,disabled:false,textContent:'Atualizar'});
function setup(permission) {
  const reads=[], renders=[], toasts=[], panel={hidden:false};
  const sandbox={
    remotePortal:true, sessionAuthenticated:true, sessionDegraded:false,
    sessionDegradedReason:'',currentRole:'OWNER',dashboardCache:{},dashboardCacheAt:1,
    devicesCache:{},devicesCacheAt:1,activityReadGeneration:0,
    activityTriggerReads:new WeakMap(), activityCache:new Map(), activityWindow:'7d',
    ACTIVITY_CACHE_MS:15000, guestActions:{hidden:true},sessionActions:{hidden:false},Date,
    document:{getElementById:()=>panel,body:{classList:{remove(){}}}},
    localLoopbackPermissionState:permission || (()=>Promise.resolve('granted')),
    fetchLocalActivityDirect(key){const d=deferred();reads.push({key,...d});return d.promise;},
    renderActivity(p){renders.push(p);panel.hidden=false;},
    showToast(message){toasts.push(message);},
  };
  vm.createContext(sandbox);
  vm.runInContext(guestSource+'\n'+loaderSource,sandbox);
  return {ctx:sandbox,reads,renders,toasts,panel};
}
const tick=async()=>{for(let i=0;i<4;i++)await Promise.resolve();};
const results=[];
async function test(name,fn) {
  let timer;
  try {
    await Promise.race([fn(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('TEST_DEADLINE')),1000);})]);
    results.push({name,state:'PASS'});
  } catch(error) { results.push({name,state:'FAIL',error:error.code || error.name}); }
  finally { clearTimeout(timer); }
}

await test('older_window_response_cannot_poison_selected_window_cache',async()=>{
  const t=setup();const first=t.ctx.loadUsageActivity(null,true);await tick();
  t.ctx.activityWindow='24h';const second=t.ctx.loadUsageActivity(null,true);await tick();
  t.reads[0].resolve(payload('7d','old'));await first;
  assert.equal(t.renders.length,0);assert.equal(t.ctx.activityCache.has('24h'),false);
  t.reads[1].resolve(payload('24h','current'));await second;
  assert.equal(t.renders.at(-1).tag,'current');assert.equal(t.ctx.activityCache.get('24h').payload.window.key,'24h');
});
await test('out_of_order_same_window_keeps_newest_result',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(null,true);await tick();
  const b=t.ctx.loadUsageActivity(null,true);await tick();
  t.reads[1].resolve(payload('7d','new'));await b;t.reads[0].resolve(payload('7d','old'));await a;
  assert.deepEqual(t.renders.map(x=>x.tag),['new']);assert.equal(t.ctx.activityCache.get('7d').payload.tag,'new');
});
await test('superseded_permission_result_does_not_start_extra_agent_read',async()=>{
  const permissions=[deferred(),deferred()];let n=0;
  const t=setup(()=>permissions[n++].promise);
  const a=t.ctx.loadUsageActivity(null,true);t.ctx.activityWindow='24h';const b=t.ctx.loadUsageActivity(null,true);
  permissions[1].resolve('granted');await tick();t.reads[0].resolve(payload('24h','new'));await b;
  permissions[0].resolve('granted');await tick();
  // Resolve any incorrectly issued extra request to leave no dangling operation.
  for(const read of t.reads.slice(1))read.resolve(payload(read.key,'old'));
  await a;assert.equal(t.reads.length,1);
});
await test('logout_clears_all_activity_cache_entries',async()=>{
  const t=setup();for(const key of ['24h','7d','30d'])t.ctx.activityCache.set(key,{at:Date.now(),payload:payload(key,'private')});
  t.ctx.setGuestHeader();assert.equal(t.ctx.activityCache.size,0);assert.equal(t.panel.hidden,true);
});
await test('pending_reply_after_logout_does_not_repopulate_or_render',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(null,true);await tick();t.ctx.setGuestHeader();
  t.reads[0].resolve(payload('7d','previous'));await a;
  assert.equal(t.ctx.activityCache.size,0);assert.equal(t.renders.length,0);assert.equal(t.panel.hidden,true);
});
await test('old_reply_is_stale_even_after_session_becomes_active_again',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(null,true);await tick();
  t.ctx.setGuestHeader();t.ctx.sessionAuthenticated=true;
  t.reads[0].resolve(payload('7d','previous_session'));await a;
  assert.equal(t.ctx.activityCache.size,0);assert.equal(t.renders.length,0);
});
await test('cached_selection_retires_pending_previous_selection',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(null,true);await tick();
  t.ctx.activityCache.set('24h',{at:Date.now(),payload:payload('24h','cached')});t.ctx.activityWindow='24h';
  await t.ctx.loadUsageActivity();t.reads[0].resolve(payload('7d','old'));await a;
  assert.deepEqual(t.renders.map(x=>x.tag),['cached']);assert.equal(t.ctx.activityCache.get('24h').payload.tag,'cached');
});
await test('stale_denial_cannot_hide_newer_success',async()=>{
  const old=deferred();let n=0;const t=setup(()=>++n===1?old.promise:Promise.resolve('granted'));
  const a=t.ctx.loadUsageActivity(button(),true);const b=t.ctx.loadUsageActivity(null,true);await tick();
  t.reads[0].resolve(payload('7d','new'));await b;old.resolve('denied');await a;
  assert.equal(t.panel.hidden,false);assert.equal(t.toasts.length,0);
});
await test('stale_empty_reply_cannot_hide_newer_success',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(button(),true);await tick();const b=t.ctx.loadUsageActivity(null,true);await tick();
  t.reads[1].resolve(payload('7d','new'));await b;t.reads[0].resolve(null);await a;
  assert.equal(t.panel.hidden,false);assert.equal(t.toasts.length,0);
});
await test('shared_button_remains_busy_until_its_latest_read_finishes',async()=>{
  const t=setup();const trigger=button();const a=t.ctx.loadUsageActivity(trigger,true);await tick();
  const b=t.ctx.loadUsageActivity(trigger,true);await tick();
  t.reads[0].resolve(payload('7d','old'));await a;assert.equal(trigger.disabled,true);
  t.reads[1].resolve(payload('7d','new'));await b;assert.equal(trigger.disabled,false);assert.equal(trigger.textContent,'Atualizar');
});
await test('different_buttons_restore_independently',async()=>{
  const t=setup(),x=button(),y=button();const a=t.ctx.loadUsageActivity(x,true);await tick();
  const b=t.ctx.loadUsageActivity(y,true);await tick();t.reads[0].resolve(null);await a;
  assert.equal(x.disabled,false);assert.equal(y.disabled,true);
  t.reads[1].resolve(payload('7d','new'));await b;assert.equal(y.disabled,false);
});
await test('unexpected_read_error_is_handled_without_exporting_error_details',async()=>{
  const t=setup(),trigger=button();const a=t.ctx.loadUsageActivity(trigger,true);await tick();
  t.reads[0].reject(new Error('PRIVATE_TEST_DETAIL'));await a;
  assert.equal(trigger.disabled,false);assert.equal(t.panel.hidden,true);
  assert.equal(t.toasts.length,1);assert.ok(!t.toasts[0].includes('PRIVATE_TEST_DETAIL'));
});
await test('stale_exception_does_not_override_current_ui',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(button(),true);await tick();const b=t.ctx.loadUsageActivity(null,true);await tick();
  t.reads[1].resolve(payload('7d','new'));await b;t.reads[0].reject(new Error('old'));await a;
  assert.equal(t.panel.hidden,false);assert.equal(t.toasts.length,0);
});
await test('normal_success_uses_selected_window',async()=>{
  const t=setup();t.ctx.activityWindow='30d';const a=t.ctx.loadUsageActivity(null,true);await tick();
  assert.equal(t.reads[0].key,'30d');t.reads[0].resolve(payload('30d','ok'));await a;
  assert.equal(t.ctx.activityCache.get('30d').payload.tag,'ok');assert.equal(t.renders.length,1);
});
await test('valid_cache_hit_does_not_issue_agent_request',async()=>{
  const t=setup();t.ctx.activityCache.set('7d',{at:Date.now(),payload:payload('7d','hit')});
  await t.ctx.loadUsageActivity();assert.equal(t.reads.length,0);assert.equal(t.renders[0].tag,'hit');
});
await test('logged_out_or_local_preview_does_not_start_activity_read',async()=>{
  const t=setup();t.ctx.sessionAuthenticated=false;await t.ctx.loadUsageActivity();
  t.ctx.sessionAuthenticated=true;t.ctx.remotePortal=false;await t.ctx.loadUsageActivity();
  assert.equal(t.reads.length,0);assert.equal(t.renders.length,0);
});
await test('permission_denial_restores_trigger_without_agent_call',async()=>{
  const t=setup(()=>Promise.resolve('denied')),trigger=button();await t.ctx.loadUsageActivity(trigger,true);
  assert.equal(t.reads.length,0);assert.equal(trigger.disabled,false);assert.equal(trigger.textContent,'Atualizar');assert.equal(t.panel.hidden,true);
});
await test('removed_button_does_not_receive_late_dom_mutations',async()=>{
  const t=setup(),trigger=button();const a=t.ctx.loadUsageActivity(trigger,true);await tick();trigger.isConnected=false;
  t.reads[0].resolve(payload('7d','ok'));await a;assert.equal(trigger.disabled,true);
});
await test('forced_empty_read_clears_old_exportable_cache',async()=>{
  const t=setup();t.ctx.activityCache.set('7d',{at:Date.now(),payload:payload('7d','old')});
  const a=t.ctx.loadUsageActivity(button(),true);await tick();t.reads[0].resolve(null);await a;
  assert.equal(t.ctx.activityCache.has('7d'),false);
});
await test('forced_denied_permission_clears_old_exportable_cache',async()=>{
  const t=setup(()=>Promise.resolve('denied'));
  t.ctx.activityCache.set('7d',{at:Date.now(),payload:payload('7d','old')});
  await t.ctx.loadUsageActivity(button(),true);assert.equal(t.ctx.activityCache.has('7d'),false);
});
await test('button_previously_disabled_is_not_enabled_by_diagnostics',async()=>{
  const t=setup(),trigger=button();trigger.disabled=true;
  const a=t.ctx.loadUsageActivity(trigger,true);await tick();t.reads[0].resolve(payload('7d','ok'));await a;
  assert.equal(trigger.disabled,true);assert.equal(trigger.textContent,'Atualizar');
});
await test('older_button_finalizer_does_not_overwrite_newer_completion',async()=>{
  const t=setup(),trigger=button();const a=t.ctx.loadUsageActivity(trigger,true);await tick();
  const b=t.ctx.loadUsageActivity(trigger,true);await tick();t.reads[1].resolve(payload('7d','new'));await b;
  trigger.textContent='Ready';t.reads[0].resolve(payload('7d','old'));await a;
  assert.equal(trigger.disabled,false);assert.equal(trigger.textContent,'Ready');
});
await test('unexpected_permission_error_is_handled_without_agent_request',async()=>{
  const t=setup(()=>Promise.reject(new Error('PRIVATE_TEST_DETAIL'))),trigger=button();
  await t.ctx.loadUsageActivity(trigger,true);assert.equal(t.reads.length,0);
  assert.equal(trigger.disabled,false);assert.equal(t.panel.hidden,true);
  assert.equal(t.toasts.length,1);assert.ok(!t.toasts[0].includes('PRIVATE_TEST_DETAIL'));
});
await test('selection_change_without_new_read_still_discards_old_response',async()=>{
  const t=setup();const a=t.ctx.loadUsageActivity(null,true);await tick();t.ctx.activityWindow='30d';
  t.reads[0].resolve(payload('7d','old'));await a;
  assert.equal(t.ctx.activityCache.size,0);assert.equal(t.renders.length,0);
});
if(!excerptMode)await test('required_generation_and_weak_button_ownership_are_declared',()=>{
  assert.ok(source.includes('let activityReadGeneration = 0;'));
  assert.ok(source.includes('const activityTriggerReads = new WeakMap();'));
});
const report={schema:'hara.commander-activity-concurrency.v1',node_version:process.version,
  source_kind:excerptMode?'EXACT_FUNCTION_EXCERPTS_FROM_REMOTE_READ':'FULL_PRODUCT_SOURCE',
  source_sha256:createHash('sha256').update(source).digest('hex'),
  function_sha256:{guest:createHash('sha256').update(guestSource).digest('hex'),loader:createHash('sha256').update(loaderSource).digest('hex')},
  scope:'LOCAL_VM_WITH_MOCKED_PERMISSION_AND_AGENT_NO_NETWORK',
  checked:results.length,passed:results.filter(x=>x.state==='PASS').length,failed:results.filter(x=>x.state==='FAIL').length,tests:results};
console.log(JSON.stringify(report,null,2));process.exitCode=report.failed?1:0;
