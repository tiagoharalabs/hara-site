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

## Metered read resilience

Read-only usage projection for metered plans now degrades independently if the
quota read backend is temporarily unavailable.

Instead of failing the authenticated dashboard, the Worker returns a bounded
usage projection with metered=true, available=false, the known plan period and
limit, and error_code=USAGE_TEMPORARILY_UNAVAILABLE. It does not invent consumed
or remaining values.

The UI keeps the authenticated workspace, plan, devices and operational
activity available and marks only usage as temporarily unavailable.

Execution reserve, commit and release behavior is unchanged and remains
fail-closed.

## Browser cache delivery

The portal app.js cache key was advanced to 20261005-unlimited1 so existing
browser sessions load the corrected frontend on a normal page refresh.

## PROD live proof

Final PROD Worker:
- 3c20f2ff-34ea-4d2c-9007-a19e694b36f3

Rollback Worker:
- d50332d1-c343-40c8-a0ee-2d990afebc6b

Live authenticated proof after deploy:
- hara_usage: PASS
- plan_code: FOUNDER_INTERNAL
- period_kind: NONE
- usage period_key: UNLIMITED
- usage metered: false
- usage available: true
- nucleo-a health: PASS

Public runtime proof:
- app.js cache key 20261005-unlimited1: PASS
- unlimited UI copy: PASS
- partial usage degradation copy: PASS
- stale login-oriented banner copy absent: PASS
- session-active copy: PASS
- Free 10k copy: PASS
- Pro R$ 80 copy: PASS
- PROD fail-closed suite: PASS

The observed user-facing issue is CLOSED_PASS.
