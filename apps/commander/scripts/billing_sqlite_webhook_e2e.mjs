#!/usr/bin/env node
// Offline integration using the real D1 SQL and Stripe webhook handler.
// No Stripe credential, network access, or production DB changes.
import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { handleStripeWebhook as handleStripeWebhookWithFetcher, createBillingCheckout, billingStatus } from "../src/billing.mjs";

const db = new DatabaseSync(":memory:");
const root = new URL("../migrations/", import.meta.url);
for (const file of ["0001_product.sql", "0003_plan_grants.sql", "0005_devices.sql", "0013_billing_v1.sql", "0014_founder_internal_entitlement.sql", "0021_commercial_terms_20261005.sql", "0036_commander_prelaunch_commercial_terms.sql", "0037_billing_recovery_and_checkout_attempts.sql"]) {
  db.exec(fs.readFileSync(new URL(file, root), "utf8"));
}
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)")
  .run("HARA-TENANT-STRIPE-E2E", "Test", "ACTIVE", "DEV", "2026-10-10T00:00:00Z");
db.prepare("INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc) VALUES (?,?,?,?,?,?,?)")
  .run("TRIAL:E2E", "HARA-TENANT-STRIPE-E2E", null, "TRIAL", "ACTIVE", "2026-10-10T00:00:00Z", null);

const wrap = (stmt, args=[]) => ({
  async first(){return stmt.get(...args) || null;},
  async all(){return {results:stmt.all(...args)};},
  async run(){const r=stmt.run(...args);return {meta:{changes:Number(r.changes)}};},
});
const env = {
  ENVIRONMENT:"DEV",
  STRIPE_SECRET_KEY:"sk_test_OfflineFixture123",
  STRIPE_WEBHOOK_SECRET:"whsec_OfflineFixture123",
  STRIPE_PRICE_STANDARD:"price_hara_pro_8000_brl",
  PRODUCT_DB:{
    prepare(sql){
      const stmt=db.prepare(sql);
      return {bind(...args){return wrap(stmt,args);}};
    },
    async batch(rows){
      db.exec("BEGIN");
      try {
        const result=await Promise.all(rows.map(x=>x.run()));
        db.exec("COMMIT");
        return result;
      } catch(e){db.exec("ROLLBACK");throw e;}
    },
  },
};
async function signedEvent(id, type, object, {wrongSignature=false,livemode=false}={}) {
  const raw=JSON.stringify({id,type,created:1791590000,livemode,data:{object}});
  const t=Math.floor(Date.now()/1000);
  const key=await crypto.subtle.importKey("raw", new TextEncoder().encode(env.STRIPE_WEBHOOK_SECRET),
    {name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const digest=new Uint8Array(await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(t+"."+raw)));
  const hash=[...digest].map(v=>v.toString(16).padStart(2,"0")).join("");
  return new Request("https://commander.haralabs.com.br/api/billing/stripe/webhook",{
    method:"POST",
    headers:{"stripe-signature":`t=${t},v1=${wrongSignature?"0".repeat(64):hash}`},
    body:raw,
  });
}
const tenant="HARA-TENANT-STRIPE-E2E";
const customer="cus_e2e";
const subId="sub_e2e";
const subscription=(status)=>({
  id:subId, customer, status, livemode:false,
  metadata:{tenant_id:tenant,plan_code:"STANDARD"},
  items:{data:[{price:{id:env.STRIPE_PRICE_STANDARD}}]}, current_period_end:1794200000,
  cancel_at_period_end:false,
});
const canonical = new Map([[subId, subscription("active")]]);
let providerReads = 0;
let providerUnavailable = false;
const providerGet = async (url, options) => {
  assert.equal(options.method, "GET");
  assert.equal(options.headers.authorization, `Bearer ${env.STRIPE_SECRET_KEY}`);
  const id = url.split("/").at(-1);
  assert.equal(url, `https://api.stripe.com/v1/subscriptions/${id}`);
  providerReads++;
  if (providerUnavailable) throw new Error("OFFLINE_PROVIDER_FAILURE");
  const object = canonical.get(id);
  assert.ok(object, `unexpected provider request for ${id}`);
  return new Response(JSON.stringify(object), {status: 200, headers: {"content-type": "application/json"}});
};
const handleStripeWebhook = (request, environment) => handleStripeWebhookWithFetcher(request, environment, providerGet);
const checkout={id:"cs_test_e2e",customer,subscription:subId,
  client_reference_id:tenant, metadata:{tenant_id:tenant,plan_code:"STANDARD"}};
const connection=()=>db.prepare("SELECT state,subscription_status,external_customer_id,external_subscription_id FROM billing_connections WHERE tenant_id=?").get(tenant);
const paid=()=>db.prepare("SELECT state,plan_code,valid_until_utc FROM entitlements WHERE entitlement_id=?").get("BILLING:"+tenant);
const trial=()=>db.prepare("SELECT state FROM entitlements WHERE entitlement_id=?").get("TRIAL:E2E");
const eventCount=()=>db.prepare("SELECT COUNT(*) AS n FROM billing_webhook_events").get().n;

await assert.rejects(handleStripeWebhook(await signedEvent("evt_bad","checkout.session.completed",checkout,{wrongSignature:true}),env),
  /BILLING_WEBHOOK_SIGNATURE_INVALID/);
assert.equal(eventCount(),0);
console.log("BILLING_SQLITE_WEBHOOK_BAD_SIGNATURE=DENIED");
await assert.rejects(handleStripeWebhook(await signedEvent(
  "evt_live_mismatch", "checkout.session.completed", checkout, {livemode:true}), env),
  /BILLING_WEBHOOK_TEST_EVENT_REQUIRED/);
assert.equal(eventCount(),0);
console.log("BILLING_SQLITE_WRONG_STRIPE_MODE=DENIED");

const created=await handleStripeWebhook(await signedEvent("evt_create","customer.subscription.created",subscription("active")),env);
assert.equal(created.result_code,"SUBSCRIPTION_ACTIVE");
assert.equal(paid().state,"ACTIVE");
assert.equal(paid().plan_code,"STANDARD");
assert.equal(trial().state,"EXPIRED");
assert.equal(connection().state,"ACTIVE");
const dup=await handleStripeWebhook(await signedEvent("evt_create","customer.subscription.created",subscription("active")),env);
assert.equal(dup.duplicate,true);
assert.equal(eventCount(),1);
console.log("BILLING_SQLITE_ACTIVE_AND_DUPLICATE=PASS");

db.prepare(`INSERT INTO billing_webhook_events
  (event_id,provider,event_type,state,received_at_utc,claim_token,claim_expires_at_utc)
  VALUES (?,'STRIPE','customer.subscription.updated','PROCESSING',?,?,?)`)
  .run("evt_orphan", "2026-10-19T00:00:00Z", "dead-worker", "2026-10-19T00:02:00Z");
db.prepare("DELETE FROM entitlements WHERE entitlement_id=?").run("BILLING:"+tenant);
const reclaimed = await handleStripeWebhook(await signedEvent(
  "evt_orphan", "customer.subscription.updated", subscription("active")), env);
assert.equal(reclaimed.result_code,"SUBSCRIPTION_ACTIVE");
assert.equal(paid().state,"ACTIVE","retry after partial connection update restores paid access");
assert.equal(db.prepare("SELECT state,claim_token FROM billing_webhook_events WHERE event_id='evt_orphan'").get().state,"PROCESSED");
assert.equal(db.prepare("SELECT claim_token FROM billing_webhook_events WHERE event_id='evt_orphan'").get().claim_token,null);
console.log("BILLING_SQLITE_ORPHAN_PROCESSING=RECLAIMED");

db.prepare(`INSERT INTO billing_webhook_events
  (event_id,provider,event_type,state,received_at_utc,claim_token,claim_expires_at_utc)
  VALUES (?,'STRIPE','customer.subscription.updated','PROCESSING',?,?,?)`)
  .run("evt_busy", new Date().toISOString(), "live-worker", new Date(Date.now()+60_000).toISOString());
await assert.rejects(handleStripeWebhook(await signedEvent(
  "evt_busy", "customer.subscription.updated", subscription("active")), env), /BILLING_WEBHOOK_IN_PROGRESS/);
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_busy'").get().state,"PROCESSING");
console.log("BILLING_SQLITE_LIVE_PROCESSING=RETRYABLE_ERROR");

const delayedCheckout=await handleStripeWebhook(await signedEvent("evt_checkout","checkout.session.completed",checkout),env);
assert.equal(delayedCheckout.result_code,"CHECKOUT_LINKED");
assert.equal(connection().state,"ACTIVE","checkout delivered after active subscription must not downgrade billing state");
assert.equal(paid().state,"ACTIVE");
console.log("BILLING_SQLITE_OUT_OF_ORDER_CHECKOUT=PASS");

canonical.set(subId, subscription("past_due"));
const fail=await handleStripeWebhook(await signedEvent("evt_failed","invoice.payment_failed",
  {customer,subscription:subId}),env);
assert.equal(fail.result_code,"INVOICE_PAYMENT_FAILED");
assert.equal(paid().state,"SUSPENDED");
console.log("BILLING_SQLITE_PAYMENT_FAILURE=PASS");

canonical.set(subId, subscription("active"));
const recover=await handleStripeWebhook(await signedEvent("evt_recover","customer.subscription.updated",subscription("active")),env);
assert.equal(recover.result_code,"SUBSCRIPTION_ACTIVE");
assert.equal(paid().state,"ACTIVE");
console.log("BILLING_SQLITE_RECOVERY=PASS");

let releaseOldRead;
let oldReadEntered;
const oldReadStarted = new Promise((resolve) => {oldReadEntered=resolve;});
const delayedOldRead = handleStripeWebhookWithFetcher(await signedEvent(
  "evt_delayed_provider_read", "customer.subscription.updated", subscription("past_due")), env,
async () => {
  oldReadEntered();
  await new Promise((resolve) => {releaseOldRead=resolve;});
  return new Response(JSON.stringify(subscription("past_due")), {status:200});
});
await oldReadStarted;
await assert.rejects(handleStripeWebhook(await signedEvent(
  "evt_parallel_projection", "customer.subscription.updated", subscription("active")), env),
  /BILLING_PROJECTION_IN_PROGRESS/);
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_parallel_projection'").get().state,"FAILED");
db.prepare("UPDATE billing_projection_claims SET claim_expires_at_utc=? WHERE tenant_id=?")
  .run("2026-10-01T00:00:00.000Z", tenant);
const newerProjection = await handleStripeWebhook(await signedEvent(
  "evt_newer_projection", "customer.subscription.updated", subscription("active")), env);
assert.equal(newerProjection.result_code,"SUBSCRIPTION_ACTIVE");
releaseOldRead();
await assert.rejects(delayedOldRead,/BILLING_PROJECTION_CLAIM_LOST/);
assert.equal(paid().state,"ACTIVE","expired old projection owner cannot overwrite recovered state");
await handleStripeWebhook(await signedEvent(
  "evt_parallel_projection", "customer.subscription.updated", subscription("active")), env);
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_parallel_projection'").get().state,"PROCESSED");
console.log("BILLING_SQLITE_PROJECTION_LOCK_AND_FENCE=PASS");

const recoveredFailure=await handleStripeWebhook(await signedEvent("evt_failed_late","invoice.payment_failed",
  {customer,subscription:subId}),env);
assert.equal(recoveredFailure.result_code,"INVOICE_STALE_IGNORED");
assert.equal(paid().state,"ACTIVE", "old failed invoice cannot suspend a recovered subscription");
console.log("BILLING_SQLITE_STALE_FAILURE_AFTER_RECOVERY=IGNORED");

// Stripe's item-level billing period is authoritative for scheduled
// cancellation. Access stays active until that paid period ends.
const paidPeriodEnd = Math.floor(Date.now()/1000) + 3600;
const scheduled = subscription("active");
delete scheduled.current_period_end;
scheduled.cancel_at_period_end = true;
scheduled.items.data[0].current_period_end = paidPeriodEnd;
canonical.set(subId, scheduled);
const scheduledResult = await handleStripeWebhook(await signedEvent(
  "evt_cancel_scheduled", "customer.subscription.updated", scheduled), env);
assert.equal(scheduledResult.result_code, "SUBSCRIPTION_ACTIVE");
assert.equal(paid().state, "ACTIVE");
assert.equal(paid().valid_until_utc, new Date(paidPeriodEnd*1000).toISOString());
console.log("BILLING_SQLITE_SCHEDULED_CANCEL_RETAINS_PAID_ACCESS=PASS");

const oldUpdate = await handleStripeWebhook(await signedEvent(
  "evt_old_active_after_schedule", "customer.subscription.updated", subscription("active")), env);
assert.equal(oldUpdate.result_code, "SUBSCRIPTION_ACTIVE");
assert.equal(paid().valid_until_utc, new Date(paidPeriodEnd*1000).toISOString(),
  "old subscription snapshot cannot clear current cancellation deadline");
assert.equal(connection().subscription_status, "active");
assert.equal(db.prepare("SELECT cancel_at_period_end FROM billing_connections WHERE tenant_id=?").get(tenant).cancel_at_period_end, 1);
console.log("BILLING_SQLITE_STALE_UPDATE_AFTER_SCHEDULE=RECONCILED");

canonical.set(subId, subscription("active"));
const resumed = await handleStripeWebhook(await signedEvent(
  "evt_cancel_reversed", "customer.subscription.updated", subscription("active")), env);
assert.equal(resumed.result_code, "SUBSCRIPTION_ACTIVE");
assert.equal(paid().valid_until_utc, null);
console.log("BILLING_SQLITE_CANCEL_REVERSAL_CLEARS_EXPIRY=PASS");

canonical.set(subId, subscription("canceled"));
const cancel=await handleStripeWebhook(await signedEvent("evt_cancel","customer.subscription.deleted",subscription("canceled")),env);
assert.equal(cancel.result_code,"SUBSCRIPTION_REVOKED");
assert.equal(paid().state,"REVOKED");
assert.equal(connection().state,"REVOKED");
console.log("BILLING_SQLITE_CANCELLATION=PASS");

// Stripe events may arrive out of order; canceled subscriptions must not be
// reactivated by an older update delivered late.
await handleStripeWebhook(await signedEvent("evt_old_update","customer.subscription.updated",subscription("active")),env);
assert.equal(paid().state,"REVOKED","late old subscription update must not resurrect canceled access");
console.log("BILLING_SQLITE_STALE_UPDATE_AFTER_CANCEL=IGNORED");

// A new checkout is allowed after cancellation. Older subscription/invoice
// events must never revoke/suspend this newer subscription under same customer.
await handleStripeWebhook(await signedEvent("evt_checkout_new","checkout.session.completed",
  {...checkout, subscription:"sub_new"}),env);
canonical.set("sub_new", {...subscription("active"),id:"sub_new"});
await handleStripeWebhook(await signedEvent("evt_created_new","customer.subscription.created",
  {...subscription("active"),id:"sub_new"}),env);
assert.equal(connection().external_subscription_id,"sub_new");
assert.equal(paid().state,"ACTIVE");
await handleStripeWebhook(await signedEvent("evt_old_checkout","checkout.session.completed",checkout),env);
assert.equal(connection().external_subscription_id,"sub_new",
  "late Checkout from previous subscription must not replace newer subscription");
assert.equal(connection().state,"ACTIVE");
await handleStripeWebhook(await signedEvent("evt_old_invoice","invoice.payment_failed",
  {customer,subscription:subId}),env);
assert.equal(paid().state,"ACTIVE","old invoice must not suspend new subscription");
await handleStripeWebhook(await signedEvent("evt_old_deleted","customer.subscription.deleted",subscription("canceled")),env);
assert.equal(paid().state,"ACTIVE","old canceled subscription must not revoke new one");
console.log("BILLING_SQLITE_OLD_SUBSCRIPTION_EVENTS=IGNORED");

const wrong={...subscription("active"),id:"sub_new"};
wrong.items.data[0].price.id="price_unknown";
canonical.set("sub_new", wrong);
await assert.rejects(handleStripeWebhook(await signedEvent("evt_bad_price","customer.subscription.updated",wrong),env),
  /BILLING_PRICE_MISMATCH/);
assert.equal(paid().state,"ACTIVE");
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_bad_price'").get().state,"FAILED");
console.log("BILLING_SQLITE_UNKNOWN_PRICE=DENIED");

canonical.set("sub_new", {...subscription("active"),id:"sub_new"});
providerUnavailable = true;
await assert.rejects(handleStripeWebhook(await signedEvent("evt_provider_down","customer.subscription.updated",
  {...subscription("active"),id:"sub_new"}),env), /BILLING_PROVIDER_UNREACHABLE/);
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_provider_down'").get().state,"FAILED");
assert.equal(paid().state,"ACTIVE");
providerUnavailable = false;
const retryAfterOutage = await handleStripeWebhook(await signedEvent("evt_provider_down","customer.subscription.updated",
  {...subscription("active"),id:"sub_new"}),env);
assert.equal(retryAfterOutage.result_code,"SUBSCRIPTION_ACTIVE");
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_provider_down'").get().state,"PROCESSED");
console.log("BILLING_SQLITE_PROVIDER_OUTAGE_RETRY=PASS");

canonical.set("sub_new", {...subscription("active"),id:"sub_new",livemode:true});
await assert.rejects(handleStripeWebhook(await signedEvent("evt_canonical_wrong_mode",
  "customer.subscription.updated", {...subscription("active"),id:"sub_new"}),env),
  /BILLING_SUBSCRIPTION_BINDING_INVALID/);
canonical.set("sub_new", {...subscription("active"),id:"sub_new",
  metadata:{tenant_id:"OTHER_TENANT",plan_code:"STANDARD"}});
await assert.rejects(handleStripeWebhook(await signedEvent("evt_canonical_wrong_tenant",
  "customer.subscription.updated", {...subscription("active"),id:"sub_new"}),env),
  /BILLING_SUBSCRIPTION_BINDING_INVALID/);
assert.equal(paid().state,"ACTIVE");
canonical.set("sub_new", {...subscription("active"),id:"sub_new"});
console.log("BILLING_SQLITE_CANONICAL_BINDING_MISMATCH=DENIED");

const founderTenant = "HARA-TENANT-FOUNDER-SEPARATE";
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)")
  .run(founderTenant, "Founder fixture", "ACTIVE", "DEV", "2026-10-10T00:00:00Z");
db.prepare("INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc) VALUES (?,?,?,?,?,?,?)")
  .run("FOUNDER:E2E", founderTenant, null, "FOUNDER_INTERNAL", "ACTIVE", "2026-10-10T00:00:00Z", null);
let founderCheckoutFetches = 0;
await assert.rejects(createBillingCheckout(
  new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", { method: "POST" }),
  env,
  { tenant_id: founderTenant, subject_id: "S-FOUNDER", role: "OWNER" },
  "STANDARD",
  () => { founderCheckoutFetches++; throw Error("FOUNDER_CHECKOUT_SHOULD_NOT_FETCH"); },
), /BILLING_FOUNDER_INTERNAL_SEPARATE/);
assert.equal(founderCheckoutFetches, 0);
const founderEvent = subscription("active");
founderEvent.metadata.tenant_id = founderTenant;
founderEvent.id = "sub_founder_fixture";
founderEvent.customer = "cus_founder_fixture";
const founderResult = await handleStripeWebhook(await signedEvent(
  "evt_founder_separate", "customer.subscription.created", founderEvent), env);
assert.equal(founderResult.result_code, "FOUNDER_INTERNAL_SEPARATE");
const founderCheckout = await handleStripeWebhook(await signedEvent(
  "evt_founder_checkout", "checkout.session.completed",
  {...checkout,client_reference_id:founderTenant,metadata:{tenant_id:founderTenant,plan_code:"STANDARD"}}), env);
assert.equal(founderCheckout.result_code,"FOUNDER_INTERNAL_SEPARATE");
const founderCancel = await handleStripeWebhook(await signedEvent(
  "evt_founder_cancel", "customer.subscription.deleted", {...founderEvent,status:"canceled"}), env);
assert.equal(founderCancel.result_code,"FOUNDER_INTERNAL_SEPARATE");
assert.equal(db.prepare("SELECT state FROM entitlements WHERE entitlement_id='FOUNDER:E2E'").get().state, "ACTIVE");
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM entitlements WHERE tenant_id=? AND plan_code='STANDARD'").get(founderTenant).n, 0);
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM billing_connections WHERE tenant_id=?").get(founderTenant).n, 0);
const founderBilling = await billingStatus(env, {tenant_id: founderTenant, role:"OWNER"});
assert.equal(founderBilling.founder_internal,true);
assert.equal(founderBilling.plans.STANDARD.checkout_ready,false);
console.log("BILLING_SQLITE_FOUNDER_INTERNAL_SEPARATE=PASS");

const futureFounderTenant="HARA-TENANT-FUTURE-FOUNDER";
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)")
  .run(futureFounderTenant,"Future Founder","ACTIVE","DEV","2026-10-10T00:00:00Z");
db.prepare("INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc) VALUES (?,?,?,?,?,?,?)")
  .run("FOUNDER:FUTURE",futureFounderTenant,null,"FOUNDER_INTERNAL","ACTIVE",
    new Date(Date.now()+86_400_000).toISOString(),null);
const futureFounderSub={...subscription("active"),id:"sub_future_founder",customer:"cus_future_founder",
  metadata:{tenant_id:futureFounderTenant,plan_code:"STANDARD"}};
canonical.set(futureFounderSub.id,futureFounderSub);
await handleStripeWebhook(await signedEvent("evt_future_founder_paid",
  "customer.subscription.created",futureFounderSub),env);
assert.equal(db.prepare("SELECT state FROM entitlements WHERE entitlement_id='FOUNDER:FUTURE'").get().state,"ACTIVE",
  "paid sync must never expire a Founder row even if its validity starts later");
console.log("BILLING_SQLITE_FOUNDER_ROW_NEVER_EXPIRED_BY_PAID_SYNC=PASS");
assert.ok(providerReads > 0);
console.log("BILLING_SQLITE_REAL_PROVIDER_REQUESTS=0");
