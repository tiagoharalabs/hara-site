# H.A.R.A. Commander Billing V1

State: **SOURCE READY / COMMERCIAL CATALOG NOT ACTIVATED**

Billing is deliberately separated from execution authority.

```text
Customer
  -> HARA Identity
  -> Commander portal
  -> Stripe Checkout / Customer Portal
  -> signed webhook
  -> billing_connections
  -> entitlement state
  -> existing plan grants + quota
  -> selected-device execution path
```

Stripe never becomes the runtime authority for device execution. It only
reports commercial subscription state. Commander remains authoritative for
tenant identity, entitlement, quota, grants, selected device and receipts.

## Provider contract

Billing V1 uses Stripe's hosted Checkout and Customer Portal through the Stripe
HTTPS API. No Stripe SDK or plugin is required by the Worker.

Runtime-only configuration:

```text
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_STANDARD
STRIPE_PRICE_SCALE
STRIPE_API_VERSION        # optional pin
```

None of these values are committed to Git. Without the secret key and webhook
secret the billing endpoints fail closed with `BILLING_NOT_CONFIGURED`.
Without an active Commander plan plus a configured price ID, checkout remains
unavailable.
## Public and authenticated endpoints

```text
POST /api/billing/stripe/webhook
GET  /api/portal/billing
POST /api/portal/billing/checkout
POST /api/portal/billing/portal
```

Checkout and Customer Portal creation require:
- an authenticated Commander portal session;
- OWNER or ADMIN role;
- same-origin mutation validation;
- the existing portal mutation rate limiter.

The webhook does not rely on portal authentication. It requires a valid
`Stripe-Signature` HMAC-SHA256 signature over the exact raw body, allows a
maximum 5-minute timestamp skew, rejects payloads over 512 KiB and claims each
Stripe event idempotently before applying state transitions.

## Subscription state mapping

```text
active / trialing
  -> billing connection ACTIVE
  -> paid entitlement ACTIVE

incomplete / past_due / unpaid / paused
  -> billing connection SUSPENDED
  -> paid entitlement SUSPENDED

canceled / incomplete_expired
  -> billing connection REVOKED
  -> paid entitlement REVOKED
```

When the first paid entitlement becomes ACTIVE, prior active Trial
entitlements for the tenant are expired. The paid entitlement is tenant-wide
(`subject_id = NULL`) so authorized tenant members inherit the commercial
plan through the existing entitlement lookup.

A cancellation never deletes the tenant, user, paired devices or receipts.
It removes execution authority by changing entitlement state.
## Webhook events

Billing V1 handles:

```text
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_failed
```

Other correctly signed Stripe events are acknowledged and recorded as ignored.

The subscription's Stripe price ID is mapped to the internal plan through
`STRIPE_PRICE_STANDARD` or `STRIPE_PRICE_SCALE`. Metadata alone cannot
override that mapping. A mismatched or unknown price fails closed.

## Commercial activation gate

This source delivery does **not** invent H.A.R.A. pricing or quotas. Standard
and Scale remain unavailable until the commercial catalog is explicitly
activated.

Activation sequence:

1. create the H.A.R.A. Commander product and recurring prices in a Stripe
   sandbox;
2. configure the Stripe Customer Portal in the sandbox;
3. create a webhook endpoint targeting
   `https://commander.haralabs.com.br/api/billing/stripe/webhook`;
4. store the sandbox secret key and webhook signing secret as Worker secrets;
5. store the sandbox price IDs as runtime configuration;
6. add/activate the matching Commander `STANDARD` / `SCALE` plan rows with
   explicitly approved quota limits and grants;
7. run the H.A.R.A. Labs first-customer checkout, payment, webhook,
   entitlement and quota proof;
8. prove cancel, payment failure, suspension and reactivation;
9. only then repeat the catalog in Stripe live mode and replace the sandbox
   runtime secrets/price IDs.

Production price and quota decisions are therefore auditable product gates,
not hidden constants in application source.

## First-customer acceptance

H.A.R.A. Labs is the first tenant to validate the commercial loop:

```text
TRIAL
  -> choose STANDARD
  -> Stripe Checkout
  -> subscription webhook
  -> entitlement STANDARD/ACTIVE
  -> quota/grants readback
  -> hara commander start
  -> OpenAI/ChatGPT governed call
  -> receipt
  -> Customer Portal
  -> cancel/reactivate proof
```

The billing proof is independent from HARA Services customer traffic. Customer
device execution continues through the Commander customer path and local
operator session gate.
