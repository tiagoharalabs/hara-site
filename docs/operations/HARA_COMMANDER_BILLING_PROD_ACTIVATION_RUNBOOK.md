# H.A.R.A. Commander Billing — Production Activation Runbook

State: **SOURCE READY / PROD COMMERCIAL ACTIVATION PENDING**

Issue: hara-site #296

This runbook activates the already-implemented Stripe Billing V1 using the
commercial terms approved by the product owner on 2026-10-05. Stripe secret
material and Price IDs remain runtime-only configuration.

## Current commercial direction

```text
FREE_INTERNAL_PLAN_CODE=TRIAL
FREE_MONTHLY_CALLS=10000
FREE_RESET=CALENDAR_MONTH
TRIAL_PROD_CHANGE_NOW=TRUE

PRO_INTERNAL_PLAN_CODE=STANDARD
STANDARD_APPROVED_PRICE=R$80_MONTH
STANDARD_APPROVED_USAGE=UNLIMITED
STANDARD_PERIOD_KIND=NONE
```

The Free tier receives 10,000 governed calls per calendar month. The allowance
resets every month. The Pro/Standard tier is R$ 80 per month with no Commander
monthly call quota.

Internal plan codes remain `TRIAL` and `STANDARD` to preserve existing
entitlements, webhook mappings and billing compatibility.

## Existing product path

```text
HARA Identity
  -> Commander portal
  -> Stripe Checkout
  -> Stripe subscription
  -> signed webhook
  -> billing_connections
  -> entitlement
  -> quota/grants
  -> selected local computer
  -> local operator session
  -> OpenAI / MCP
```

Stripe reports commercial state only. It does not become execution authority.
## Runtime configuration

Required Worker secrets/configuration:

```text
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_STANDARD
STRIPE_PRICE_SCALE
```

Optional:

```text
STRIPE_API_VERSION
```

No secret value belongs in Git, issue comments, receipts or support bundles.

The first activation should use Stripe test mode. Live-mode keys and live price
IDs are installed only after the complete first-customer acceptance succeeds.

## Approved terms and remaining Stripe configuration

Approved product terms:

```text
Free = 10,000 calls / calendar month
Pro  = BRL 80 / month
Pro usage = unlimited
```

These values are no longer pending commercial decisions.

Still required outside application source:

```text
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_STANDARD
tax configuration
```

The configured `STRIPE_PRICE_STANDARD` must point to the Stripe recurring price
for exactly BRL 80/month before checkout is activated. The Price ID itself is
never committed to Git.

SCALE remains roadmap and does not block first Pro checkout.

## Read-only preflight

From the repository root:

```bash
python3 apps/commander/scripts/billing_prod_activation_preflight.py
python3 apps/commander/scripts/billing_prod_activation_preflight.py --live
```

The live command reads only:
- Worker secret **names**, never values;
- PROD plan catalog rows;
- billing table presence;
- billing connection/event counts.

It performs no PROD mutation.

Expected after migration `0021_commercial_terms_20261005.sql` and before Stripe activation:

```text
COMMANDER_BILLING_PROD_SCHEMA=PASS
TRIAL_CURRENT_PROD_UNITS=10000
TRIAL_LIVE_ALIGNED=TRUE
TRIAL_TARGET_MONTHLY_UNITS=10000
COMMERCIAL_TERMS_AUTHORIZED=TRUE
STANDARD_APPROVED_BRL_MONTHLY_CENTS=8000
STANDARD_APPROVED_USAGE=UNLIMITED
STANDARD_LIVE_UNLIMITED=TRUE
STANDARD_CATALOG_ACTIVE=TRUE
STRIPE_SECRET_KEY=PENDING
STRIPE_WEBHOOK_SECRET=PENDING
STRIPE_PRICE_STANDARD=PENDING
COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE
PROD_MUTATION=FALSE
```
## Stripe test-mode activation

1. Create the H.A.R.A. Commander product in Stripe test mode.
2. Create the recurring STANDARD price at exactly BRL 80/month. SCALE remains roadmap.
3. Configure Stripe Customer Portal for subscription management.
4. Create webhook endpoint:
   `https://commander.haralabs.com.br/api/billing/stripe/webhook`.
5. Subscribe the endpoint to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
6. Store the test secret key and signing secret as Worker secrets.
7. Store the exact STANDARD test Price ID as runtime configuration.
8. Verify Free remains 10,000/mmonth and STANDARD remains unlimited.
9. Run the live preflight again.

Do not expose Stripe webhook secret, API key, Checkout session secrets or
customer payment data in GitHub evidence.
## First-customer canary — H.A.R.A. Labs

The first paid tenant is H.A.R.A. Labs.

Acceptance order:

1. tenant starts on Free (`TRIAL` internally) with 10,000 calls/month;
2. OWNER opens the Commander Plan page;
3. select Pro (`STANDARD` internally), displayed as R$ 80/month and unlimited;
4. Commander creates a Stripe hosted Checkout session;
5. complete a test-mode payment;
6. verify `checkout.session.completed` is recorded once;
7. verify subscription event maps the exact Stripe price to STANDARD;
8. verify `billing_connections` contains customer + subscription IDs;
9. verify paid entitlement becomes STANDARD/ACTIVE;
10. verify prior active Trial entitlement is expired;
11. verify STANDARD has `period_kind=NONE`, `unit_limit=NULL` and the expected grants;
12. run `hara-commander start`;
13. execute one governed OpenAI/MCP read-only call;
14. verify receipt correlation;
15. open Stripe Customer Portal and return safely to Commander.

No customer execution traffic may be routed through HARA Services as part of
this billing canary.
## Negative billing acceptance

Prove each state transition independently.

### Payment failure

```text
invoice.payment_failed
-> billing state SUSPENDED
-> paid entitlement SUSPENDED
-> MCP execution denied
```

### Recovery

Use Stripe's canonical subscription update after payment recovery:

```text
customer.subscription.updated status=active
-> billing state ACTIVE
-> paid entitlement ACTIVE
-> governed execution restored
```

### Cancellation

```text
customer.subscription.deleted
-> billing state REVOKED
-> paid entitlement REVOKED
-> MCP execution denied
```

Tenant, users, paired computers and historical receipts remain intact.
## Live-mode promotion

Only after the test-mode canary is terminal:

1. recreate Products/Prices in Stripe live mode;
2. create live webhook endpoint/signing secret;
3. replace test Worker secrets and price IDs with live values;
4. rerun read-only preflight;
5. perform one low-risk H.A.R.A. Labs live subscription;
6. verify exact entitlement/quota outcome;
7. verify Customer Portal;
8. publish STANDARD in the customer-facing catalog;
9. keep SCALE gated until its commercial quota and support boundary are approved.

## Stop conditions

Stop activation and restore the prior catalog/configuration if any of these occur:

- Stripe webhook signature cannot be verified;
- duplicate Stripe events apply state twice;
- price ID does not map exactly to an approved Commander plan;
- payment failure leaves entitlement ACTIVE;
- cancellation leaves execution authority ACTIVE;
- secrets appear in logs or Git;
- checkout can be initiated by MEMBER/REVIEWER;
- billing changes device execution authority outside entitlement/quota;
- customer traffic is relayed through HARA Services.

## Completion markers

```text
STRIPE_TEST_MODE_CHECKOUT=PASS
STRIPE_WEBHOOK_SIGNATURE=PASS
STRIPE_WEBHOOK_IDEMPOTENCY=PASS
BILLING_CONNECTION=PASS
PAID_ENTITLEMENT_ACTIVE=PASS
PAYMENT_FAILURE_SUSPENSION=PASS
CANCELLATION_REVOCATION=PASS
CUSTOMER_PORTAL=PASS
OPENAI_MCP_AFTER_PAYMENT=PASS
SECRET_MATERIAL_EXPOSED=FALSE
FIRST_CUSTOMER=HARA_LABS
```
