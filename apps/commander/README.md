# H.A.R.A. Commander app — DEV

This is the standalone product-plane Worker intended to become
`commander.haralabs.com.br` after operator approval.

DEV only.

## Boundaries

- No production Cloudflare resources are created by this package.
- D1 is local-only during current validation.
- Durable Object SQLite is local-only during current validation.
- No password is stored in H.A.R.A.
- No payment provider is connected.
- No customer data is used.
- HARA Services remains the operational authority.
- The Cloudflare Tunnel request counter is not commercial quota.

## Local data model

D1:
- tenants
- users
- plans
- entitlements
- billing_connections

Durable Object SQLite per tenant:
- request_state
- monthly/lifetime quota consumption
- RESERVED / COMMITTED / RELEASED / DENIED
- request idempotency

## Local run

Apply D1 schema and seed to local storage, then run Wrangler using the app config.

The Worker exposes DEV-only endpoints:

- GET /api/dev/health
- GET /api/dev/dashboard
- POST /api/dev/quota/reserve
- POST /api/dev/quota/commit
- POST /api/dev/quota/release

Production deployment is intentionally deferred.
