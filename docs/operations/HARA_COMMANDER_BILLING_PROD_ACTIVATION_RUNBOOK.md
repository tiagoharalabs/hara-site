# H.A.R.A. Commander — Commercial billing activation

State: **local candidate only; Stripe TEST account, DEV canary and PROD promotion pending**. Coordination: hara-site #296 and #310. This document describes acceptance work; it does not authorize remote D1 migration, Worker deployment or Stripe LIVE configuration.

## Approved product terms

```text
TRIAL_INTERNAL_PLAN_CODE=TRIAL
TRIAL_TARGET_TOTAL_UNITS=5000
TRIAL_RESET=LIFETIME
CUSTOMER_ACTIVE_DEVICE_LIMIT=5
STANDARD_INTERNAL_PLAN_CODE=STANDARD
STANDARD_APPROVED_PRICE=R$80_MONTH
STANDARD_APPROVED_CALENDAR_MONTH_UNITS=1000000
FOUNDER_INTERNAL_USAGE=UNLIMITED
```

Calls are functional MCP invocations shared by one organization. Heartbeat, polling, keepalive and portal traffic do not consume this allowance. No per-user cap is defined. OpenAI billing is separate. A canceled subscription stays entitled through its already paid period and stops at its end. Founder/Internal uses its own unlimited entitlement and is not a commercial installation canary.

`TRIAL` and `STANDARD` remain internal codes for compatibility. Migration `0036_commander_prelaunch_commercial_terms.sql` changes the existing catalog without editing applied migrations. Its remote application requires separate authorization and a usage baseline for existing tenants: a switch from historical monthly Trial counters to `LIFETIME` must not issue an extra 5,000 calls to a tenant with prior usage.

Migration `0037_billing_recovery_and_checkout_attempts.sql` adds webhook claim expiry/fencing, per-tenant projection claims and one pending Checkout attempt per organization. Apply it before using this Worker revision. In-flight webhook claims return a retryable non-2xx response; completed event IDs remain idempotent. A checkout timeout retries only with the same attempt key and byte-identical parameters while Stripe's idempotency window is safely open; an older uncertain attempt requires reconciliation before another purchase opportunity. The source preflight checks these structures, and the live preflight must report false until the authorized migration is present.

## Quota period decision for promotion

The current implementation uses the calendar month as the **only** paid quota reset. Stripe's subscription billing period controls payment and paid access, not a second usage reset. The owner must confirm calendar-month reset versus subscription-cycle reset before commercial promotion. A cycle-based decision requires one coordinated schema and code change to replace the calendar reset; never run both. Scheduled cancellation uses Stripe's item-level `current_period_end` when present, with subscription-level fallback for older API payloads.

## Read-only preflight

From the repository root:

```bash
python3 apps/commander/scripts/billing_prod_activation_preflight.py
python3 apps/commander/scripts/billing_prod_activation_preflight.py --live
```

The first command reads local source. `--live` reads only Worker secret names, PROD D1 table/catalog metadata and counts. It does not apply the new migration. Missing columns or credentials must produce `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`.

Required runtime names for an authorized Stripe TEST activation are `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_STANDARD`. The price must be a recurring BRL 80/month Stripe TEST price. Keys, Price IDs and customer payment data stay out of Git and evidence. The TEST account and credentials have not been provided; mock tests are the current evidence, not a real Stripe payment.

## First clean customer acceptance in DEV and Stripe TEST

1. Coordinate a clean Linux and Windows commercial installation with the owner. Use the new signed bundle only after official signing and four-asset hash, size, version and installer-pin verification; v4 is rollback-only with a known Linux PTY drain regression.
2. Apply authorized additive D1 migration after reconciling existing Trial lifetime usage. Verify catalog values, Founder isolation and fifth/sixth device behavior, including concurrent enrollment and replacement after revocation.
3. Configure Stripe TEST product, price, Customer Portal and webhook. Subscribe to `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, and `invoice.payment_failed`.
4. Start with a new Trial tenant at 5,000 total functional calls. OWNER selects HARA Commander at R$ 80/month. Check a single hosted Checkout across double click and timeout retry, signature, exact Price ID, out-of-order event reconciliation, orphan claim recovery, paid entitlement and quota shared across users.
5. Check both clean operating systems, governed read-only and mutation paths, Event V2 wake/PONG/reconnect/claim/receipt, and the customer MCP endpoint `https://commander.haralabs.com.br/api/mcp`. The internal `https://mcp.haralabs.com.br/mcp` is a separate package/path.
6. Verify `invoice.payment_failed` suspends execution, recovery restores it, and `cancel_at_period_end` retains access until the paid end then denies access. Preserve tenant, paired device and receipt records.

## Promotion gate

Record signed candidate digest and rollback, DEV evidence and exact exit codes in `PROGRESS.md`. Seek specific owner approval for remote migration, Stripe TEST setup, DEV deployment and any later PROD promotion. No PROD deployment or Stripe LIVE operation occurs in this prelaunch patch session.
