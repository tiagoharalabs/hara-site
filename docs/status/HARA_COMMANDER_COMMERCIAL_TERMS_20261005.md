# H.A.R.A. Commander — Approved commercial terms

Date: 2026-10-05
Authority: product owner approval in active Commander continuation

## Approved customer-facing plans

### Free

Internal plan code: `TRIAL`

- price: R$ 0
- allowance: 10,000 governed Commander calls
- reset: every calendar month
- quota model: `CALENDAR_MONTH`
- unit limit: `10000`

### Pro

Internal plan code: `STANDARD`

- price: R$ 80/month
- Commander call allowance: unlimited
- quota model: `NONE`
- unit limit: `NULL`
- billing interval: monthly
- currency: BRL

## Compatibility

Internal plan codes remain unchanged so existing entitlement and Stripe webhook
logic does not require a plan-code migration.

Migration `0021_commercial_terms_20261005.sql` reconciles the plan catalog.

## Stripe boundary

Commercial values are approved, but Stripe credentials and identifiers are not
stored in Git.

`STRIPE_PRICE_STANDARD` must correspond to the real recurring BRL 80/month
Stripe Price before checkout readiness can become true.

SCALE remains roadmap and does not block first Pro checkout.
