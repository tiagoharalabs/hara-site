# H.A.R.A. Commander — Rate-limit / Brute-force Resilience

**Owner:** hara-site#189
**Gate:** RATE_LIMIT_BRUTE_FORCE_RESILIENCE
**Scope:** Commander Worker edge guards; no PROD mutation in this source change.

## Security contract

The Worker uses Cloudflare native Rate Limiting bindings before or around sensitive
operations. Rate-limit keys are SHA-256 digests; raw client IPs, pairing tokens,
MCP product tokens, tenant IDs and subject IDs are not placed in the limiter
keyspace.

The protected paths are:

- `GET /auth/login`: 30 initiations/minute per hashed client address.
- `POST /api/device/enroll`: 60 attempts/minute per hashed client address.
- `POST /api/device/enroll`: 10 attempts/minute per hashed pairing-token value.
- portal device mutations: 60 mutations/minute per hashed tenant+subject actor.
- invalid internal MCP/device product-token authentication: 20 failures/minute
  per hashed client address and hashed supplied token.
## Failure behavior

Rate limiting is fail-closed:

- exhausted limiter -> HTTP 429 with `Retry-After: 60`;
- missing limiter binding -> HTTP 503;
- limiter infrastructure/check failure -> HTTP 503;
- valid MCP product tokens are checked before the invalid-auth failure limiter,
  so normal authorized internal traffic is not charged to the brute-force bucket.

The source does not add a D1 migration, Durable Object class, customer-content
telemetry, public Agent change, Event V2 transport change, or visual change.

## Environment isolation

PROD and DEV use distinct rate-limit namespace IDs. The limits are equal across
environments, while counters remain isolated. DEV retains the existing Event V2
bindings and PROD retains the existing V1 production transport state.

## Operational limitation

Cloudflare Workers Rate Limiting counters apply within a Cloudflare location.
These guards therefore provide bounded edge resistance and workload protection,
not a claim of globally exact distributed-attempt accounting. Broader edge/WAF
and upstream Identity controls remain defense-in-depth layers.

## Validation

Required source checks:

- Wrangler PROD dry-run recognizes all five rate-limit bindings.
- Wrangler DEV dry-run recognizes all five rate-limit bindings.
- key privacy unit test passes.
- fail-closed unit test passes.
- route/config validator passes.
- existing multi-tenant, origin, PROD contract and fail-closed validators pass.
## Live acceptance still required

Do not declare `RATE_LIMIT_RESILIENCE=PASS` from source validation alone.

A bounded DEV campaign must still prove, without exposing credentials:

- login initiation reaches 429 at the configured boundary;
- invalid enrollment is bounded by client and token keys;
- invalid MCP product-token attempts are bounded;
- authenticated portal device mutations are bounded using an isolated fixture;
- successful legitimate requests still work below threshold;
- Worker health remains available;
- no PROD mutation occurs;
- test fixtures/state are cleaned where applicable.

The live campaign must not rotate or consume #163 Event V2 canary credentials.
