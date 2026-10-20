// Independent review only: immutable source snapshot, SQLite :memory:, fake event signatures.
// No real credentials, no network, no edits to the active Codex workspace.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { webcrypto } from 'node:crypto';
import { handleStripeWebhook, createBillingCheckout } from './apps/commander/src/billing.mjs';
let realNetworkAttempts = 0;
globalThis.fetch = async () => { realNetworkAttempts++; throw Error('PEER_NETWORK_FORBIDDEN'); };
const stamp = Math.floor(Date.now()/1000);
const findings = [];
function fixture(tag) {
  const db = new DatabaseSync(':memory:');
  for (const name of ['0001_product.sql','0003_plan_grants.sql','0013_billing_v1.sql','0014_founder_internal_entitlement.sql','0021_commercial_terms_20261005.sql','0036_commander_prelaunch_commercial_terms.sql']) {
    db.exec(fs.readFileSync(new URL('./apps/commander/migrations/'+name,import.meta.url),'utf8'));
  }
  const tenant='HARA-TENANT-PEER-'+tag;
  db.prepare('INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)').run(tenant,'Isolated reviewer fixture','ACTIVE','DEV','2026-10-20T00:00:00Z');
  const wrapper=(stmt,args=[])=>({async first(){return stmt.get(...args)||null;},async all(){return {results:stmt.all(...args)};},async run(){return {meta:{changes:Number(stmt.run(...args).changes)}};}});
  const env={ENVIRONMENT:'DEV',STRIPE_SECRET_KEY:'sk_test_PeerFixtureNotACredential123',STRIPE_WEBHOOK_SECRET:'whsec_PeerFixtureNotACredential123',STRIPE_PRICE_STANDARD:'price_peer_standard',PRODUCT_DB:{prepare(sql){const stmt=db.prepare(sql);return {bind(...args){return wrapper(stmt,args);}};},async batch(statements){db.exec('BEGIN');try{const results=[];for(const statement of statements) results.push(await statement.run());db.exec('COMMIT');return results;}catch(e){db.exec('ROLLBACK');throw e;}}}};
  const subscription=(overrides={})=>({id:'sub_peer_'+tag,customer:'cus_peer_'+tag,status:'active',metadata:{tenant_id:tenant,plan_code:'STANDARD'},items:{data:[{price:{id:'price_peer_standard'},current_period_start:stamp-3600,current_period_end:stamp+86400}]},cancel_at_period_end:false,...overrides});
  async function deliver(id,type,object,created=stamp) {
    const raw=JSON.stringify({id,type,created,livemode:false,data:{object}});
    const ts=Math.floor(Date.now()/1000);
    const key=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(env.STRIPE_WEBHOOK_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign']);
    const sig=Buffer.from(await webcrypto.subtle.sign('HMAC',key,new TextEncoder().encode(ts+'.'+raw))).toString('hex');
    return handleStripeWebhook(new Request('https://offline.invalid/api/billing/stripe/webhook',{method:'POST',headers:{'stripe-signature':`t=${ts},v1=${sig}`},body:raw}),env);
  }
  const paid=()=>db.prepare('SELECT state,plan_code,valid_until_utc FROM entitlements WHERE entitlement_id=?').get('BILLING:'+tenant)||null;
  const connection=()=>db.prepare('SELECT state,subscription_status,cancel_at_period_end FROM billing_connections WHERE tenant_id=?').get(tenant)||null;
  return {db,env,tenant,subscription,deliver,paid,connection};
}
async function check(id,fn){try{const result=await fn();findings.push({id,...result});}catch(e){findings.push({id,harness_error:String(e.stack||e).slice(0,1800)});}}
await check('R2-BILL-01-OLD-SAME-SUBSCRIPTION-FAILURE',async()=>{
  const f=fixture('LATE');
  await f.deliver('evt_peer_late_created','customer.subscription.created',f.subscription(),stamp-400);
  await f.deliver('evt_peer_late_recovered','customer.subscription.updated',f.subscription(),stamp-50);
  assert.equal(f.paid().state,'ACTIVE');
  const result=await f.deliver('evt_peer_late_failure','invoice.payment_failed',{id:'in_peer_old',customer:'cus_peer_LATE',subscription:'sub_peer_LATE'},stamp-200);
  const observed=f.paid().state;f.db.close();
  return {reproduced:observed==='SUSPENDED',expected:'Old failure must not undo a more recent paid/recovered canonical subscription state',observed,handler:result.result_code,scope:'real handler + in-memory SQLite; delayed unique event, not duplicate event ID'};
});
await check('R2-BILL-02-OLD-UPDATE-REMOVES-CANCEL-DEADLINE',async()=>{
  const f=fixture('CANCEL');
  await f.deliver('evt_peer_cancel_created','customer.subscription.created',f.subscription(),stamp-400);
  await f.deliver('evt_peer_cancel_scheduled','customer.subscription.updated',f.subscription({cancel_at_period_end:true}),stamp-50);
  const before=f.paid().valid_until_utc;assert.ok(before);
  await f.deliver('evt_peer_cancel_stale','customer.subscription.updated',f.subscription(),stamp-200);
  const after=f.paid().valid_until_utc;const connection=f.connection();f.db.close();
  return {reproduced:after===null&&connection.cancel_at_period_end===0,expected:'Delayed pre-cancellation snapshot must not clear current scheduled end',before,after,connection};
});
await check('R2-BILL-03-ORPHAN-PROCESSING-ACKNOWLEDGED',async()=>{
  const f=fixture('CRASH');
  f.db.prepare("INSERT INTO billing_webhook_events (event_id,provider,event_type,state,received_at_utc,processed_at_utc,result_code) VALUES (?,'STRIPE',?,'PROCESSING',?,NULL,NULL)").run('evt_peer_crash','customer.subscription.created','2026-10-01T00:00:00Z');
  const retries=[];for(let i=0;i<3;i++) retries.push(await f.deliver('evt_peer_crash','customer.subscription.created',f.subscription()));
  const row=f.db.prepare('SELECT state,processed_at_utc FROM billing_webhook_events WHERE event_id=?').get('evt_peer_crash');const paid=f.paid();f.db.close();
  return {reproduced:retries.every(x=>x.ok&&x.result_code==='EVENT_IN_PROGRESS')&&row.state==='PROCESSING'&&paid===null,expected:'A stale claim must be recoverable; do not acknowledge durable completion with no recovery path',row,paid,retries:retries.map(x=>({ok:x.ok,duplicate:x.duplicate,result_code:x.result_code})),scope:'seeded crash-equivalent persisted state; no actual Worker killed'};
});
await check('R2-BILL-04-CONCURRENT-CHECKOUTS',async()=>{
  const f=fixture('CHECKOUT');let calls=0;const keys=[];
  const fetcher=async(_url,options)=>{const n=++calls;keys.push(new Headers(options.headers).get('idempotency-key'));return new Response(JSON.stringify({id:'cs_test_peer_'+n,url:'https://checkout.stripe.com/c/pay/cs_test_peer_'+n}),{status:200,headers:{'content-type':'application/json'}});};
  const request=()=>new Request('https://commander.haralabs.com.br/api/portal/billing/checkout',{method:'POST'});
  const session={tenant_id:f.tenant,subject_id:'PEER-OWNER',role:'OWNER'};
  const sessions=await Promise.all([createBillingCheckout(request(),f.env,session,'STANDARD',fetcher),createBillingCheckout(request(),f.env,session,'STANDARD',fetcher)]);
  const ids=sessions.map(x=>x.checkout_session_id);f.db.close();
  return {reproduced:calls===2&&new Set(ids).size===2&&keys.every(x=>x===null),expected:'Concurrent first checkout calls must reuse or serialize one purchase attempt',mock_provider_calls:calls,idempotency_keys:keys,checkout_ids:ids,real_charge:false,scope:'mock Stripe responses, not proof of two payments'};
});
await check('R2-BILL-05-FOUNDER-EXPIRED-BY-PURCHASE',async()=>{
  const f=fixture('FOUNDER');
  f.db.prepare('INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc) VALUES (?,?,NULL,?,?,?,NULL)').run('FOUNDER:PEER',f.tenant,'FOUNDER_INTERNAL','ACTIVE','2026-10-01T00:00:00Z');
  await f.deliver('evt_peer_founder_purchase','customer.subscription.created',f.subscription());
  const founder=f.db.prepare("SELECT state,plan_code FROM entitlements WHERE entitlement_id='FOUNDER:PEER'").get();f.db.close();
  return {reproduced:founder.state!=='ACTIVE',expected:'Founder/Internal exemption must not be invalidated by paid-plan synchronization',founder,scope:'synthetic Founder tenant; existing real Founder untouched'};
});
await check('R2-LEASE-06-EXPIRY-NOT-ENFORCED-ON-LOCAL-LEASE',async()=>{
  const f=fixture('LEASE');const source=fs.readFileSync(new URL('./apps/commander/src/worker.js',import.meta.url),'utf8');
  function extract(name){const pattern=new RegExp('(?:async )?function '+name+'\\(');const m=pattern.exec(source);assert.ok(m,'function missing '+name);const end=source.indexOf('\n}',m.index);assert.ok(end>m.index);return source.slice(m.index,end+2);}
  const oldExpiry=new Date(Date.now()-3600000).toISOString();
  f.db.prepare('INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc) VALUES (?,?,NULL,?,?,?,?)').run('BILLING:'+f.tenant,f.tenant,'STANDARD','ACTIVE','2026-10-01T00:00:00Z',oldExpiry);
  const resolver=new Function('return ('+extract('entitlementForTenant')+')')();
  const expiredRow=await resolver(f.env,f.tenant);
  const mk=now=>now.toISOString().slice(0,7);const me=period=>{const [y,m]=period.split('-').map(Number);return new Date(Date.UTC(y,m,1)).toISOString();};
  const leaseFn=new Function('PRODUCT_LEASE_TTL_SECONDS','monthKey','monthEndUtc','localBudgetEligibleDevice','crypto','return ('+extract('productLeaseForContext')+')')(21600,mk,me,()=>false,webcrypto);
  const now=new Date();const nearExpiry=new Date(now.getTime()+60000).toISOString();
  const lease=leaseFn({tenant_id:f.tenant,entitlement_id:'BILLING:'+f.tenant,plan_code:'STANDARD',plan_name:'Commander',meter_id:'HARA_COMMANDER_GOVERNED_INVOKE',period_kind:'CALENDAR_MONTH',unit_limit:1000000,valid_until_utc:nearExpiry},{device_id:'PEER-DEVICE',platform:'LINUX'},[],now);
  const beyond=Date.parse(lease.valid_until_utc)>Date.parse(nearExpiry);f.db.close();
  return {reproduced:!!expiredRow&&beyond,expected:'Reject expired entitlement and cap lease expiry at paid entitlement deadline',expired_entitlement_returned:!!expiredRow,expired_at:oldExpiry,paid_until:nearExpiry,lease_until:lease.valid_until_utc,scope:'actual extracted pure resolver/lease functions; not an HTTP exploit or signed lease issuance'};
});
const report={schema:'hara.commander-peer-billing-review.v1',observed_utc:new Date().toISOString(),snapshot:JSON.parse(fs.readFileSync(new URL('./SNAPSHOT.json',import.meta.url),'utf8')),findings,real_network_attempts:realNetworkAttempts,production_mutation:false};
fs.writeFileSync(new URL('./peer_results.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({schema:report.schema,observed_utc:report.observed_utc,source_head:report.snapshot.head,findings,real_network_attempts:realNetworkAttempts,production_mutation:false},null,2));
process.exitCode=findings.some(x=>x.harness_error)?3:findings.some(x=>x.reproduced)?2:0;
