import assert from "node:assert/strict";
import {
  createBillingCheckout,
  stripeBillingConfigured,
  stripePlanForPrice,
  stripePriceForPlan,
  subscriptionEntitlementState,
  verifyStripeWebhookSignature,
} from "../src/billing.mjs";

const env = {
  STRIPE_SECRET_KEY: "fixture-secret-key",
  STRIPE_WEBHOOK_SECRET: "fixture-webhook-secret",
  STRIPE_PRICE_STANDARD: "price_standard_fixture",
  STRIPE_PRICE_SCALE: "price_scale_fixture",
};

assert.equal(stripeBillingConfigured(env), true);
assert.equal(stripePriceForPlan(env, "STANDARD"), "price_standard_fixture");
assert.equal(stripePlanForPrice(env, "price_scale_fixture"), "SCALE");
assert.equal(stripePlanForPrice(env, "price_unknown"), null);

assert.equal(subscriptionEntitlementState("active"), "ACTIVE");
assert.equal(subscriptionEntitlementState("trialing"), "ACTIVE");
assert.equal(subscriptionEntitlementState("past_due"), "SUSPENDED");
assert.equal(subscriptionEntitlementState("unpaid"), "SUSPENDED");
assert.equal(subscriptionEntitlementState("canceled"), "REVOKED");

async function signatureFor(secret, timestamp, raw) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const bytes = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(String(timestamp) + "." + raw),
  );
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

const raw = JSON.stringify({ id: "evt_fixture", type: "ping", data: { object: {} } });
const timestamp = 1800000000;
const signature = await signatureFor(env.STRIPE_WEBHOOK_SECRET, timestamp, raw);
assert.equal(
  await verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${signature}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 10,
  ),
  true,
);

await assert.rejects(
  verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${"0".repeat(64)}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 10,
  ),
  /BILLING_WEBHOOK_SIGNATURE_INVALID/,
);

await assert.rejects(
  verifyStripeWebhookSignature(
    raw,
    `t=${timestamp},v1=${signature}`,
    env.STRIPE_WEBHOOK_SECRET,
    timestamp + 301,
  ),
  /BILLING_WEBHOOK_TIMESTAMP_INVALID/,
);

const queries = [];
env.PRODUCT_DB = {
  prepare(sql) {
    queries.push(sql);
    return {
      bind(...args) {
        return {
          async first() {
            if (sql.includes("FROM plans")) {
              return {
                plan_code: args[0],
                display_name: args[0],
                meter_id: "HARA_COMMANDER_GOVERNED_INVOKE",
                period_kind: "CALENDAR_MONTH",
                unit_limit: 1000,
                state: "ACTIVE",
              };
            }
            if (sql.includes("FROM billing_connections")) return null;
            return null;
          },
        };
      },
    };
  },
};

let checkoutRequest = null;
const fakeFetch = async (url, options) => {
  checkoutRequest = { url, options };
  return new Response(JSON.stringify({
    id: "cs_test_fixture",
    url: "https://checkout.stripe.com/c/pay/cs_test_fixture",
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
};

const result = await createBillingCheckout(
  new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", {
    method: "POST",
  }),
  env,
  {
    tenant_id: "HARA-TENANT-FIXTURE",
    subject_id: "HARA-SUBJECT-FIXTURE",
    email: "fixture@example.invalid",
    role: "OWNER",
  },
  "STANDARD",
  fakeFetch,
);

assert.equal(result.plan_code, "STANDARD");
assert.equal(result.secret_material_exposed, false);
assert.equal(checkoutRequest.url, "https://api.stripe.com/v1/checkout/sessions");
const form = new URLSearchParams(checkoutRequest.options.body);
assert.equal(form.get("mode"), "subscription");
assert.equal(form.get("line_items[0][price]"), "price_standard_fixture");
assert.equal(form.get("metadata[tenant_id]"), "HARA-TENANT-FIXTURE");
assert.equal(form.get("subscription_data[metadata][plan_code]"), "STANDARD");
assert.equal(form.get("tax_id_collection[enabled]"), "true");
assert.equal(checkoutRequest.options.headers.authorization, "Bearer fixture-secret-key");

const evilFetch = async () => new Response(JSON.stringify({
  id: "cs_test_fixture",
  url: "https://evilstripe.com/not-allowed",
}), {
  status: 200,
  headers: { "content-type": "application/json" },
});
await assert.rejects(
  createBillingCheckout(
    new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", {
      method: "POST",
    }),
    env,
    {
      tenant_id: "HARA-TENANT-FIXTURE",
      subject_id: "HARA-SUBJECT-FIXTURE",
      email: "fixture@example.invalid",
      role: "OWNER",
    },
    "STANDARD",
    evilFetch,
  ),
  /BILLING_CHECKOUT_RESPONSE_INVALID/,
);

console.log("COMMANDER_BILLING_V1_SIGNATURE=PASS");
console.log("COMMANDER_BILLING_V1_PLAN_MAPPING=PASS");
console.log("COMMANDER_BILLING_V1_CHECKOUT_CONTRACT=PASS");
console.log("COMMANDER_BILLING_V1_SECRET_COMMIT=ABSENT");
