# H.A.R.A. Commander — Commercial terms PROD live proof

Date: 2026-10-05
Canonical source: local/commander-openai-desktop-parity-20261004
Source commit before evidence: 9c19c3c888376e1fb8f25e2ca698d0d3e9a65cb3

## Approved terms

Customer-facing:
- Free: R$ 0
- Free allowance: 10,000 governed Commander calls per calendar month
- Free reset: monthly
- Pro: R$ 80/month
- Pro Commander call allowance: unlimited

Stable internal plan codes:
- Free -> TRIAL
- Pro -> STANDARD

## PROD D1 migration

Applied:
- 0021_commercial_terms_20261005.sql

Pre-migration D1 export was created with file mode 0600.

Live plan readback:
- TRIAL: display_name=Free, period_kind=CALENDAR_MONTH, unit_limit=10000, state=ACTIVE
- STANDARD: display_name=Pro, period_kind=NONE, unit_limit=NULL, state=ACTIVE

## PROD Worker

Previous Worker:
- 3ddbc2c4-5f42-4320-adb3-4b1e90340219

Current Worker:
- 25f4c5cf-bdbf-4223-a628-e8272dd64d77

Deployment:
- 2b17f05a-fc3e-4f4b-a57d-c594c64c6706

Rollback Worker:
- 3ddbc2c4-5f42-4320-adb3-4b1e90340219

The experimental TenantQuota O(1) candidate was explicitly checked and is not an ancestor of the PROD source. It remains DEV-only.

## Live acceptance

PASS:
- PROD deployment readback
- fail-closed session/dashboard/devices/pairing/device/MCP routes
- public Free 10,000/month copy
- public monthly-reset copy
- public Pro R$ 80/month copy
- public Pro unlimited copy
- stale 100/month copy absent
- live D1 Free quota aligned to 10,000
- live D1 Pro quota model unlimited

Markers:
- COMMANDER_PROD_FREE_10K=PASS
- COMMANDER_PROD_FREE_MONTHLY_RESET=PASS
- COMMANDER_PROD_PRO_BRL80=PASS
- COMMANDER_PROD_PRO_UNLIMITED=PASS
- COMMANDER_PROD_STALE_100_ABSENT=PASS
- TRIAL_LIVE_ALIGNED=TRUE
- STANDARD_LIVE_UNLIMITED=TRUE

## Stripe boundary

Commercial terms are approved and live in the Commander catalog/UI.

Stripe checkout is not active yet because the following runtime configuration remains pending:
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- STRIPE_PRICE_STANDARD

The real STRIPE_PRICE_STANDARD must point to a recurring BRL 80/month Stripe Price before checkout readiness is allowed.

Current:
- COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE
- BILLING_CONNECTIONS=0
- BILLING_WEBHOOK_EVENTS=0

No Stripe identifier or secret was invented or committed.

## Remaining commercial gate

Create/configure the real Stripe Pro price at exactly BRL 80/month, configure webhook credentials, then prove:
checkout -> signed webhook -> STANDARD entitlement -> customer portal -> payment failure/recovery -> cancellation.
