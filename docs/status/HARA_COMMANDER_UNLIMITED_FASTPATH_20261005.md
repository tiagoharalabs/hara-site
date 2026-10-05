# H.A.R.A. Commander — Unlimited plan read fast-path

Date: 2026-10-05

## User-visible defect

Authenticated PROD sessions could show:

- `Dados da conta não atualizados`
- plan/usage placeholders
- valid login/session remained active

The failure was not an authentication failure.

## Root cause

`dashboard`, `dashboardForSubject` and `customerUsage` always called the
`TENANT_QUOTA` Durable Object, including entitlements with:

- `period_kind=NONE`
- `unit_limit=NULL`

PROD has an active `FOUNDER_INTERNAL` entitlement with exactly that unlimited
policy. A live `hara_usage` call reproduced the failure before the fix with:

`Exceeded_allowed_rows_read_in_Durable_Objects_free_tier_`

At the same time device health/ping and authenticated product access were
healthy.

## Fix

Added one shared read path:

`productUsageForPolicy`

For `period_kind=NONE` it returns an unmetered usage projection immediately:

- `period_key=UNLIMITED`
- `limit=NULL`
- `consumed_units=NULL`
- `remaining_units=NULL`
- `metered=false`

No `TENANT_QUOTA` lookup is performed for unlimited-plan usage reads.

Metered plans continue through the canonical TenantQuota path.

This applies to:

- DEV dashboard
- authenticated portal dashboard
- customer `hara_usage`

Execution quota/idempotency behavior is intentionally unchanged in this patch;
TenantQuota is also an idempotency/receipt state machine on governed execution
paths and must not be bypassed without a separate replacement design.

## UI improvement

Unlimited plans render:

- `Ilimitado`
- `Sem limite`
- `Sem franquia mensal de chamadas`

The degraded dashboard banner no longer frames backend product-data failure as a
login problem. It now states that the session remains active and asks to refresh
the Commander data.

## Regression

PASS:

- dedicated unlimited fast-path validator
- device tool contract
- E2E harness
- preprod readiness
