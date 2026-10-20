#!/usr/bin/env node
// Real checkout-claim SQL, mocked Stripe only. No credentials or payments.
import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { createBillingCheckout, handleStripeWebhook } from "../src/billing.mjs";

const db = new DatabaseSync(":memory:");
for (const file of ["0001_product.sql", "0003_plan_grants.sql", "0005_devices.sql",
  "0013_billing_v1.sql", "0014_founder_internal_entitlement.sql",
  "0021_commercial_terms_20261005.sql", "0036_commander_prelaunch_commercial_terms.sql",
  "0037_billing_recovery_and_checkout_attempts.sql"]) {
  db.exec(fs.readFileSync(new URL(`../migrations/${file}`, import.meta.url), "utf8"));
}
for (const tenant of ["TENANT-CHECKOUT-RACE", "TENANT-CHECKOUT-RETRY"]) {
  db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)")
    .run(tenant, tenant, "ACTIVE", "DEV", "2026-10-10T00:00:00Z");
}
const env = {
  ENVIRONMENT: "DEV",
  STRIPE_SECRET_KEY: "sk_test_OfflineCheckout123",
  STRIPE_WEBHOOK_SECRET: "whsec_OfflineCheckout123",
  STRIPE_PRICE_STANDARD: "price_hara_pro_8000_brl",
  PRODUCT_DB: {
    prepare(sql) {
      const statement = db.prepare(sql);
      return {bind(...args) {return {
        async first() {return statement.get(...args) || null;},
        async run() {const r=statement.run(...args);return {meta:{changes:Number(r.changes)}};},
      };}};
    },
  },
};
const request = new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", {method:"POST"});
const session = (tenant) => ({tenant_id:tenant,subject_id:"SUBJECT-OWNER",role:"OWNER"});
const checkoutResponse = (id) => new Response(JSON.stringify({
  id, url:`https://checkout.stripe.com/c/pay/${id}`,
  expires_at:Math.floor(Date.now()/1000)+3600,
}), {status:200,headers:{"content-type":"application/json"}});
const attempt = (tenant) => db.prepare("SELECT attempt_id,state,checkout_session_id,claim_token FROM billing_checkout_attempts WHERE tenant_id=?").get(tenant);

let releaseFirst;
let enteredFirst;
const firstEntered = new Promise((resolve) => {enteredFirst=resolve;});
const raceCalls = [];
const slowStripe = async (url, options) => {
  assert.equal(url,"https://api.stripe.com/v1/checkout/sessions");
  raceCalls.push(options);
  enteredFirst();
  await new Promise((resolve) => {releaseFirst=resolve;});
  return checkoutResponse("cs_test_race");
};
const raceTenant="TENANT-CHECKOUT-RACE";
const first = createBillingCheckout(request,env,session(raceTenant),"STANDARD",slowStripe);
await firstEntered;
await assert.rejects(createBillingCheckout(request,env,session(raceTenant),"STANDARD",slowStripe),
  /BILLING_CHECKOUT_IN_PROGRESS/);
assert.equal(raceCalls.length,1,"two simultaneous requests cannot create two Stripe sessions");
releaseFirst();
const firstResult=await first;
const replay=await createBillingCheckout(request,env,session(raceTenant),"STANDARD",slowStripe);
assert.deepEqual(replay,firstResult);
assert.equal(raceCalls.length,1);
assert.equal(attempt(raceTenant).state,"READY");
assert.equal(attempt(raceTenant).claim_token,null);
assert.equal(raceCalls[0].headers["idempotency-key"],attempt(raceTenant).attempt_id);
console.log("BILLING_CHECKOUT_CONCURRENT_REQUESTS=ONE_PROVIDER_POST");

const retryTenant="TENANT-CHECKOUT-RETRY";
let initialKey;
let initialBody;
await assert.rejects(createBillingCheckout(request,env,session(retryTenant),"STANDARD",
  async (_url, options) => {
    initialKey=options.headers["idempotency-key"];
    initialBody=options.body;
    throw new Error("SIMULATED_PROVIDER_TIMEOUT");
  }),/BILLING_PROVIDER_UNREACHABLE/);
assert.equal(attempt(retryTenant).state,"UNCERTAIN");
let retryPosts=0;
const recovered=await createBillingCheckout(request,env,session(retryTenant),"STANDARD",
  async (_url, options) => {
    retryPosts++;
    assert.equal(options.headers["idempotency-key"],initialKey);
    assert.equal(options.body,initialBody,"idempotent retry must use identical Stripe parameters");
    return checkoutResponse("cs_test_recovered");
  });
assert.equal(recovered.checkout_session_id,"cs_test_recovered");
assert.equal(retryPosts,1);
const afterRecovery=await createBillingCheckout(request,env,session(retryTenant),"STANDARD",
  () => {throw new Error("REPLAY_SHOULD_NOT_POST");});
assert.deepEqual(afterRecovery,recovered);
console.log("BILLING_CHECKOUT_TIMEOUT_RETRY=SAME_IDEMPOTENCY_KEY_AND_SESSION");

db.prepare("UPDATE billing_checkout_attempts SET expires_at_utc=? WHERE tenant_id=?")
  .run("2026-10-01T00:00:00.000Z",retryTenant);
let replacementKey;
const replacement=await createBillingCheckout(request,env,session(retryTenant),"STANDARD",
  async (_url, options) => {
    replacementKey=options.headers["idempotency-key"];
    return checkoutResponse("cs_test_replacement");
  });
assert.notEqual(replacementKey,initialKey);
assert.equal(replacement.checkout_session_id,"cs_test_replacement");
console.log("BILLING_CHECKOUT_EXPIRED_SESSION=NEW_ATTEMPT");

const oldCheckoutEvent=JSON.stringify({
  id:"evt_old_checkout_attempt",type:"checkout.session.completed",
  created:Math.floor(Date.now()/1000),livemode:false,
  data:{object:{id:"cs_test_recovered",customer:"cus_old",subscription:"sub_old",
    client_reference_id:retryTenant,metadata:{tenant_id:retryTenant,plan_code:"STANDARD"}}},
});
const timestamp=Math.floor(Date.now()/1000);
const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(env.STRIPE_WEBHOOK_SECRET),
  {name:"HMAC",hash:"SHA-256"},false,["sign"]);
const signature=[...new Uint8Array(await crypto.subtle.sign("HMAC",key,
  new TextEncoder().encode(`${timestamp}.${oldCheckoutEvent}`)))]
  .map((v)=>v.toString(16).padStart(2,"0")).join("");
const oldResult=await handleStripeWebhook(new Request(
  "https://commander.haralabs.com.br/api/billing/stripe/webhook",{
    method:"POST",headers:{"stripe-signature":`t=${timestamp},v1=${signature}`},
    body:oldCheckoutEvent,
  }),env,()=>{throw new Error("CHECKOUT_WEBHOOK_SHOULD_NOT_FETCH");});
assert.equal(oldResult.result_code,"CHECKOUT_OTHER_ATTEMPT_IGNORED");
assert.equal(db.prepare("SELECT COUNT(*) AS n FROM billing_connections WHERE tenant_id=?").get(retryTenant).n,0);
console.log("BILLING_CHECKOUT_OLD_ATTEMPT_WEBHOOK=IGNORED");
console.log("BILLING_CHECKOUT_REAL_STRIPE_REQUESTS=0");
