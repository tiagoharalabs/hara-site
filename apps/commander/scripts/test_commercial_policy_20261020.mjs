import assert from "node:assert/strict";
import {
  APPROVED_COMMERCIAL_TERMS,
  billingStatus,
  createBillingCheckout,
  stripePlanForPrice,
  subscriptionEntitlementState,
} from "../src/billing.mjs";

const evaluation = APPROVED_COMMERCIAL_TERMS.TRIAL;
assert.equal(evaluation.period_kind, "LIFETIME");
assert.equal(evaluation.functional_calls_total, 5_000);
assert.equal(evaluation.active_device_limit, 5);

const paid = APPROVED_COMMERCIAL_TERMS.STANDARD;
assert.equal(paid.currency, "BRL");
assert.equal(paid.price_amount_cents, 8_000);
assert.equal(paid.billing_interval, "month");
assert.equal(paid.period_kind, "CALENDAR_MONTH");
assert.equal(paid.functional_calls_per_month, 1_000_000);
assert.equal(paid.active_device_limit, 5);
assert.equal(paid.usage_unlimited, false);

const founder = APPROVED_COMMERCIAL_TERMS.FOUNDER_INTERNAL;
assert.equal(founder.period_kind, "NONE");
assert.equal(founder.usage_unlimited, true);
assert.equal(founder.active_device_limit, null);

const env = {
  STRIPE_PRICE_STANDARD: "price_standard_fixture",
  STRIPE_PRICE_SCALE: "price_scale_fixture",
};
assert.equal(stripePlanForPrice(env, "price_standard_fixture"), "STANDARD");
assert.equal(stripePlanForPrice(env, "price_scale_fixture"), null);
assert.equal(subscriptionEntitlementState("active"), "ACTIVE");
assert.equal(subscriptionEntitlementState("past_due"), "SUSPENDED");
assert.equal(subscriptionEntitlementState("canceled"), "REVOKED");

let requests = 0;
const staleEnv = {
  ENVIRONMENT: "DEV",
  STRIPE_SECRET_KEY: "sk_test_StaleCatalogFixture123",
  STRIPE_WEBHOOK_SECRET: "whsec_StaleCatalogFixture123",
  STRIPE_PRICE_STANDARD: "price_standard_fixture",
  PRODUCT_DB: {
    prepare(sql) {
      return { bind() { return { async first() {
        if (sql.includes("FROM plans")) return {
          plan_code: "STANDARD", state: "ACTIVE",
          period_kind: "NONE", unit_limit: null, active_device_limit: null,
        };
        return null;
      } }; } };
    },
  },
};
const owner = { tenant_id: "T", subject_id: "S", role: "OWNER" };
const status = await billingStatus(staleEnv, owner);
assert.equal(status.plans.STANDARD.catalog_active, false);
assert.equal(status.activation.first_checkout_ready, false);
await assert.rejects(createBillingCheckout(
  new Request("https://commander.haralabs.com.br/api/portal/billing/checkout", { method: "POST" }),
  staleEnv, owner, "STANDARD", () => { requests++; throw Error("SHOULD_NOT_FETCH"); },
), /BILLING_PLAN_UNAVAILABLE/);
assert.equal(requests, 0);
console.log("COMMANDER_COMMERCIAL_POLICY=PASS");
