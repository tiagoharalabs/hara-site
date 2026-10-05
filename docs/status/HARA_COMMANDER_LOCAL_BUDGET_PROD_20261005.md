# H.A.R.A. Commander — local budget blocks PROD live proof

Date: 2026-10-05
Canonical source before evidence: bcba7febba751ff1c9d6eab6751cf586edeb3d5f
Agent release: 0.3.35

## PROD safety

Pre-migration D1 export:
- local file mode: 0600
- sha256: 858265d8243e44e8dd71dc64daf821c3b8dafcd286fd112b03eca72b965f9aa7

Applied migrations:
- 0023_device_local_budget_blocks.sql
- 0024_local_budget_cloud_ceiling.sql
- 0025_local_budget_fresh_baseline.sql

Post-migration:
- commander_device_budget_blocks table present
- commander_tenant_budget_baselines table present
- local-budget validate/issue/release triggers present
- commander_device_calls usage metadata columns present
- no pending migrations

## PROD Worker

Current:
- df72804e-7a51-4308-9a63-321bf1cbee4f

Rollback:
- 3e4aab17-74c0-4331-84ae-5ab31dbb71e1

Acceptance:
- deployment readback PASS
- fail-closed suite PASS

## Linux rollout

nucleo-a:
- 0.3.34 -> 0.3.35
- canonical updater integrity PASS
- startup attestation PASS
- service active/enabled
- localhost Activity preserved
- product lease present
- plan FOUNDER_INTERNAL
- usage mode UNMETERED
- period kind NONE
- local budget blocks 0
- local budget debits 0
- H.A.R.A. Commander health PASS

sentinela-d:
- 0.3.34 -> 0.3.35
- canonical updater integrity PASS
- startup attestation PASS
- service active
- localhost Activity preserved
- product lease present
- plan FOUNDER_INTERNAL
- usage mode UNMETERED
- period kind NONE
- local budget blocks 0
- local budget debits 0
- H.A.R.A. Commander health PASS

Founder usage readback remains:
- period_key=UNLIMITED
- limit=NULL
- metered=false
- available=true

## PROD allocation state at rollout

- budget blocks: 0
- allocated units: 0
- issued units: 0
- reported units: 0
- fresh local-budget baselines: 0

No active customer was silently moved onto a local budget during deployment.

The capability will activate only when an eligible metered calendar-month
entitlement uses a compatible Linux 0.3.35+ device and the cloud successfully
issues a block.

## Commercial effect

For Free at 10,000 calls/month:
- block size: 100 calls
- theoretical full-month block allocations: <= 100
- individual calls are debited locally
- cloud call insertion still enforces the issued-block ceiling
- cloud remains authoritative for plan, entitlement, allocation and revocation

This removes the normal per-call Durable Object quota transaction from the
compatible local-budget path while retaining a hard cloud ceiling.

## State

LOCAL_BUDGET_PROD_INFRA=CLOSED_PASS
LOCAL_BUDGET_AGENT_0_3_35_PROD=CLOSED_PASS
LOCAL_BUDGET_FOUNDER_UNMETERED_REGRESSION=CLOSED_PASS
LOCAL_BUDGET_FREE_DEV_CANARY=CLOSED_PASS
LOCAL_BUDGET_PROD_FIRST_REAL_FREE_TENANT=PENDING_NATURAL_USAGE
WINDOWS_LOCAL_BUDGET=FALLBACK_CLOUD_QUOTA
