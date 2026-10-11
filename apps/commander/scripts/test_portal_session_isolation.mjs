import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';

const source=fs.readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
function extract(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a,'SOURCE_FUNCTION_NOT_FOUND:'+start);
 return source.slice(a,b).trim();
}
const guest=extract('  function setGuestHeader() {','  function setAuthenticatedHeader(');
const header=extract('  async function hydrateSessionHeader() {','  function formatDeviceSeen(');
const devices=extract('  async function loadDevices(','  function armPairingExpiry(');
const dashboard=extract('  async function loadProductDashboard(','  async function loadBillingState(');
const billing=extract('  async function loadBillingState() {','  async function requestBetaAccess(');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const ready=async()=>{for(let k=0;k<5;k++)await Promise.resolve();};
const data=(tenant)=>({identity:{tenant_id:tenant},tenant_id:tenant,device_state:{tenant_id:tenant},tag:tenant});
function setup(){
 const pending=[],renders=[],invalidation=[];
 const billingStatus={textContent:''};
 const betaButton={hidden:false,disabled:false,textContent:'Solicitar acesso beta'};
 let loading=0;
 const fetcher=(_url)=>{const d=deferred();pending.push(d);return d.promise;};
 fetcher.invalidate=()=>invalidation.push('invalidate');
 const sandbox={
  portalSessionGeneration:0,
  portalFetch:fetcher,remotePortal:true,sessionAuthenticated:true,
  sessionDegraded:false,sessionDegradedReason:'',currentRole:'OWNER',
  activityCache:new Map(),activityReadGeneration:0,
  guestActions:{hidden:true},sessionActions:{hidden:false},
  dashboardCache:null,dashboardCacheAt:0,devicesCache:null,devicesCacheAt:0,
  PORTAL_DASHBOARD_CACHE_MS:1000,PORTAL_DEVICES_CACHE_MS:1000,
  apiBase:'/api/portal',dashboardPath:'/dashboard',scenario:'',
  Date,setTimeout,clearTimeout,
  document:{
    body:{classList:{remove(){},add(){}}},
    getElementById:(id)=>id==='billingPlanStatus'?billingStatus:null,
    querySelector:(selector)=>selector==='[data-beta-access]'?betaButton:null,
    querySelectorAll:()=>[],
  },
  history:{replaceState(){}},location:{pathname:'/'},hideBanner(){},
  setState(){},showBanner(){},route(){},applyScenario(){},
  setLoading(v){loading+=v?1:-1;},renderDeviceLoading(){},
  handlePortalAuthFailure(){return false;},showToast(){},
  renderDevices(payload){renders.push({kind:'devices',tenant:payload.tenant_id});},
  applyDashboard(payload){renders.push({kind:'dashboard',tenant:payload.tenant_id});},
  applyIdentity(payload){renders.push({kind:'identity',tenant:payload.tenant_id});},
 };
 vm.createContext(sandbox);
 vm.runInContext(guest+'\n'+header+'\n'+devices+'\n'+dashboard+'\n'+billing,sandbox);
 return {ctx:sandbox,pending,renders,invalidation,billingStatus,betaButton};
}
const response=(payload,status=200)=>({
 ok:status>=200&&status<300,status,
 json:async()=>payload,
});
const checks=[];
async function test(name,fn){
 try{await fn();checks.push({name,state:'PASS'});}
 catch(err){checks.push({name,state:'FAIL',code:err.code||err.name});}
}
await test('logout_advances_session_epoch_and_aborts_pending_reads',async()=>{
 const t=setup();t.ctx.setGuestHeader();
 assert.equal(t.ctx.portalSessionGeneration,1);
 assert.equal(t.invalidation.length,1);
 assert.equal(t.ctx.sessionAuthenticated,false);
});
await test('stale_bootstrap_success_after_logout_does_not_restore_private_content',async()=>{
 const t=setup();const job=t.ctx.loadPortalBootstrap();await ready();
 t.ctx.setGuestHeader();t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.ctx.dashboardCache,null);assert.equal(t.ctx.devicesCache,null);
 assert.equal(t.renders.length,0);
});
await test('stale_bootstrap_unauthorized_reply_cannot_logout_new_session',async()=>{
 const t=setup();const job=t.ctx.loadPortalBootstrap();await ready();
 t.ctx.setGuestHeader();t.ctx.sessionAuthenticated=true;
 const prior=t.ctx.portalSessionGeneration;
 t.pending[0].resolve(response({code:'SESSION_EXPIRED'},401));await job;
 assert.equal(t.ctx.portalSessionGeneration,prior);
 assert.equal(t.ctx.sessionAuthenticated,true);
});
await test('stale_identity_reply_after_logout_cannot_restore_identity',async()=>{
 const t=setup();const job=t.ctx.hydrateSessionHeader();await ready();
 t.ctx.setGuestHeader();t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.renders.length,0);
});
await test('stale_dashboard_reply_after_logout_cannot_repopulate_dashboard',async()=>{
 const t=setup();const job=t.ctx.loadProductDashboard(true);await ready();
 t.ctx.setGuestHeader();t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.ctx.dashboardCache,null);assert.equal(t.renders.length,0);
});
await test('stale_devices_reply_after_logout_cannot_repopulate_devices',async()=>{
 const t=setup();const job=t.ctx.loadDevices(null,true);await ready();
 t.ctx.setGuestHeader();t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.ctx.devicesCache,null);assert.equal(t.renders.length,0);
});
await test('newer_bootstrap_after_logout_can_update_new_session',async()=>{
 const t=setup();const a=t.ctx.loadPortalBootstrap();await ready();
 t.ctx.setGuestHeader();const b=t.ctx.loadPortalBootstrap();await ready();
 t.pending[1].resolve(response(data('ACCOUNT_B')));await b;
 t.pending[0].resolve(response(data('ACCOUNT_A')));await a;
 assert.equal(t.ctx.dashboardCache.tenant_id,'ACCOUNT_B');
 assert.equal(t.ctx.devicesCache.tenant_id,'ACCOUNT_B');
 assert.ok(!t.renders.some(x=>x.tenant==='ACCOUNT_A'));
});
await test('newer_devices_after_logout_not_overwritten_by_previous_response',async()=>{
 const t=setup();const a=t.ctx.loadDevices(null,true);await ready();
 t.ctx.setGuestHeader();const b=t.ctx.loadDevices(null,true);await ready();
 t.pending[1].resolve(response(data('ACCOUNT_B')));await b;
 t.pending[0].resolve(response(data('ACCOUNT_A')));await a;
 assert.equal(t.ctx.devicesCache.tenant_id,'ACCOUNT_B');
 assert.ok(!t.renders.some(x=>x.tenant==='ACCOUNT_A'));
});
await test('stale_billing_reply_after_logout_cannot_publish_previous_account_state',async()=>{
 const t=setup();const job=t.ctx.loadBillingState();await ready();
 t.ctx.setGuestHeader();
 t.pending[0].resolve(response({can_manage:true,activation:{first_checkout_ready:true,provider_configured:true}}));
 await job;
 assert.equal(t.billingStatus.textContent,'');
});
await test('stale_billing_beta_reply_cannot_update_old_customer_action',async()=>{
 const t=setup();const job=t.ctx.loadBillingState();await ready();
 t.pending[0].resolve(response({can_manage:true,activation:{provider_configured:false}}));await ready();
 assert.equal(t.pending.length,2);
 t.ctx.setGuestHeader();
 t.pending[1].resolve(response({request:{state:'APPROVED'}}));await job;
 assert.equal(t.betaButton.textContent,'Solicitar acesso beta');
});
await test('newer_billing_response_after_logout_wins_over_older',async()=>{
 const t=setup();const a=t.ctx.loadBillingState();await ready();t.ctx.setGuestHeader();
 t.ctx.sessionAuthenticated=true;
 const b=t.ctx.loadBillingState();await ready();
 t.pending[1].resolve(response({can_manage:true,activation:{first_checkout_ready:true,provider_configured:true}}));await b;
 t.pending[0].resolve(response({can_manage:false,activation:{first_checkout_ready:false,provider_configured:false}}));await a;
 assert.match(t.billingStatus.textContent,/Pro disponível/);
});

await test('ordinary_bootstrap_success_is_unchanged',async()=>{
 const t=setup();const job=t.ctx.loadPortalBootstrap();await ready();
 t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.ctx.dashboardCache.tenant_id,'ACCOUNT_A');
 assert.equal(t.ctx.devicesCache.tenant_id,'ACCOUNT_A');
});
await test('ordinary_device_refresh_is_unchanged',async()=>{
 const t=setup();const job=t.ctx.loadDevices(null,true);await ready();
 t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.ctx.devicesCache.tenant_id,'ACCOUNT_A');
});
await test('ordinary_identity_hydration_is_unchanged',async()=>{
 const t=setup();const job=t.ctx.hydrateSessionHeader();await ready();
 t.pending[0].resolve(response(data('ACCOUNT_A')));await job;
 assert.equal(t.renders[0].kind,'identity');
});
console.log(JSON.stringify({
 schema:'hara.commander-session-epoch-isolation.v1',
 source_sha256:createHash('sha256').update(source).digest('hex'),
 checked:checks.length,passed:checks.filter(x=>x.state==='PASS').length,
 failed:checks.filter(x=>x.state==='FAIL').length,
 checks,network:false,source_sections:'ACTUAL_PRODUCT_FUNCTIONS'
},null,2));
process.exitCode=checks.some(x=>x.state==='FAIL')?1:0;
