# H.A.R.A. Commander Billing — Production Activation Runbook

State: **SOURCE READY / PROD COMMERCIAL ACTIVATION PENDING**

Issue: hara-site #296

This runbook activates the already-implemented Stripe Billing V1 without
inventing commercial pricing or changing the current Trial quota.

## Current commercial direction

```text
TRIAL_CURRENT_PROD_MONTHLY_UNITS=100
TRIAL_TARGET_MONTHLY_UNITS=10000
TRIAL_PROD_CHANGE_NOW=FALSE
```

The 10,000-unit Trial is the future commercial target. Production remains at
100 units/month during first-customer billing and OpenAI homologation.

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

## Commercial decisions required before checkout

The following values must be explicitly approved outside application source:

```text
STANDARD recurring price
SCALE recurring price
STANDARD monthly unit limit
SCALE monthly unit limit
currency
billing interval
tax configuration
```

Application code must not infer or invent these values.
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

Expected before Stripe activation:

```text
COMMANDER_BILLING_PROD_SCHEMA=PASS
TRIAL_CURRENT_PROD_UNITS=100
TRIAL_TARGET_MONTHLY_UNITS=10000
STANDARD_CATALOG_ACTIVE=FALSE
SCALE_CATALOG_ACTIVE=FALSE
STRIPE_SECRET_KEY=PENDING
STRIPE_WEBHOOK_SECRET=PENDING
STRIPE_PRICE_STANDARD=PENDING
STRIPE_PRICE_SCALE=PENDING
COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE
PROD_MUTATION=FALSE
```
## Stripe test-mode activation

1. Create the H.A.R.A. Commander product in Stripe test mode.
2. Create recurring STANDARD and SCALE prices using approved commercial values.
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
7. Store the exact test price IDs as runtime configuration.
8. Activate matching STANDARD/SCALE Commander plans with approved quota limits.
9. Run the live preflight again.

Do not expose Stripe webhook secret, API key, Checkout session secrets or
customer payment data in GitHub evidence.
## First-customer canary — H.A.R.A. Labs

The first paid tenant is H.A.R.A. Labs.

Acceptance order:

1. tenant starts on TRIAL/100;
2. OWNER opens the Commander Plan page;
3. select STANDARD;
4. Commander creates a Stripe hosted Checkout session;
5. complete a test-mode payment;
6. verify `checkout.session.completed` is recorded once;
7. verify subscription event maps the exact Stripe price to STANDARD;
8. verify `billing_connections` contains customer + subscription IDs;
9. verify paid entitlement becomes STANDARD/ACTIVE;
10. verify prior active Trial entitlement is expired;
11. verify quota/grants reflect STANDARD;
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
