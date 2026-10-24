#!/usr/bin/env node
// Offline integration using the real D1 SQL and Stripe webhook handler.
// No Stripe credential, network access, or production DB changes.
import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { handleStripeWebhook } from "../src/billing.mjs";

const db = new DatabaseSync(":memory:");
const root = new URL("../migrations/", import.meta.url);
for (const file of ["0001_product.sql", "0013_billing_v1.sql", "0021_commercial_terms_20261005.sql"]) {
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
  id:subId, customer, status, metadata:{tenant_id:tenant,plan_code:"STANDARD"},
  items:{data:[{price:{id:env.STRIPE_PRICE_STANDARD}}]}, current_period_end:1794200000,
  cancel_at_period_end:false,
});
const checkout={id:"cs_test_e2e",customer,subscription:subId,
  client_reference_id:tenant, metadata:{tenant_id:tenant,plan_code:"STANDARD"}};
const connection=()=>db.prepare("SELECT state,subscription_status,external_customer_id,external_subscription_id FROM billing_connections WHERE tenant_id=?").get(tenant);
const paid=()=>db.prepare("SELECT state,plan_code FROM entitlements WHERE entitlement_id=?").get("BILLING:"+tenant);
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

const delayedCheckout=await handleStripeWebhook(await signedEvent("evt_checkout","checkout.session.completed",checkout),env);
assert.equal(delayedCheckout.result_code,"CHECKOUT_LINKED");
assert.equal(connection().state,"ACTIVE","checkout delivered after active subscription must not downgrade billing state");
assert.equal(paid().state,"ACTIVE");
console.log("BILLING_SQLITE_OUT_OF_ORDER_CHECKOUT=PASS");

const fail=await handleStripeWebhook(await signedEvent("evt_failed","invoice.payment_failed",
  {customer,subscription:subId}),env);
assert.equal(fail.result_code,"INVOICE_PAYMENT_FAILED");
assert.equal(paid().state,"SUSPENDED");
console.log("BILLING_SQLITE_PAYMENT_FAILURE=PASS");

const recover=await handleStripeWebhook(await signedEvent("evt_recover","customer.subscription.updated",subscription("active")),env);
assert.equal(recover.result_code,"SUBSCRIPTION_ACTIVE");
assert.equal(paid().state,"ACTIVE");
console.log("BILLING_SQLITE_RECOVERY=PASS");

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
await assert.rejects(handleStripeWebhook(await signedEvent("evt_bad_price","customer.subscription.updated",wrong),env),
  /BILLING_PRICE_MISMATCH/);
assert.equal(paid().state,"ACTIVE");
assert.equal(db.prepare("SELECT state FROM billing_webhook_events WHERE event_id='evt_bad_price'").get().state,"FAILED");
console.log("BILLING_SQLITE_UNKNOWN_PRICE=DENIED");
