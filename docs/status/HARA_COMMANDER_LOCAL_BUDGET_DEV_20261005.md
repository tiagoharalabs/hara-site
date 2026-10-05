# H.A.R.A. Commander — local budget blocks DEV proof

Date: 2026-10-05
Branch: local/commander-local-budget-lease-20261005
Agent release: 0.3.35

## Objective

Keep cloud authority for identity, entitlement, billing and the monthly
commercial ceiling while removing a per-call Durable Object quota transaction
from compatible metered Linux devices.

## Contract

Cloud:
- authoritative plan / entitlement / grants
- issues a bounded device budget block
- stores only the hash of the block lease token
- enforces each cloud call against the block with D1 triggers
- caps total allocations against the plan monthly limit
- reconciles monotonic committed-unit reports

Device:
- stores product lease, budget block and request debits in operations.sqlite3
- reserves / commits / releases individual units locally
- does not mint its own commercial capacity
- requests a new block only when necessary
- reports committed units on lease refresh

## Current sizing

- Free commercial monthly limit: 10,000 calls
- local block size: 100 calls
- product lease TTL: 6 hours
- normal lease refresh: 4 hours

At full Free usage this reduces the commercial allocation path from potentially
10,000 per-call quota decisions to at most about 100 block allocations, while
the existing cloud call INSERT remains the hard block ceiling.

## Compatibility

LOCAL_BUDGET requires:
- metered calendar-month entitlement
- Linux device
- Agent >= 0.3.35
- non-Event-V2 tunnel
- active, non-expired block

Fallback:
- old Agent -> CLOUD_QUOTA
- Windows -> CLOUD_QUOTA
- no active block -> CLOUD_QUOTA
- mixed / incompatible fresh fleet -> no fresh zero baseline
- period_kind=NONE -> UNMETERED

## Safety / race gates

PASS:
- migration replay 0001 -> 0025
- one active block per device/period
- tenant allocation sequence uniqueness
- cloud slot validation trigger
- cloud slot issue trigger
- failed/cancelled/expired call releases issued slot
- fourth call rejected when a three-unit test block is full
- released slot can be reused
- local replay guard
- monotonic budget reports
- lease-token hash verification
- local tamper cloud ceiling
- mixed-mode shared monthly ceiling
- raw payload/result absent from local budget tables
- full E2E harness
- full source preprod readiness

## Fresh-tenant DEV canary

The live DEV canary used a new isolated tenant, entitlement and Linux Agent
downloaded from the live DEV Worker.

PASS:
- block issued: 100 units
- baseline source: FRESH_TENANT_ZERO
- legacy Durable Object reads for baseline: 0
- 3 governed calls completed from one block
- 3 local SQLite debits committed
- cloud units_issued: 3
- Agent restarted
- cloud units_reported reconciled to 3
- block count remained 1
- cleanup PASS

Markers:
- LOCAL_BUDGET_DEV_BLOCK_ISSUE=PASS
- LOCAL_BUDGET_DEV_BLOCK_UNITS=100
- LOCAL_BUDGET_DEV_BASELINE=FRESH_TENANT_ZERO
- LOCAL_BUDGET_DEV_LEGACY_DO_READS_FOR_BASELINE=0
- LOCAL_BUDGET_DEV_THREE_CALLS_ONE_BLOCK=PASS
- LOCAL_BUDGET_DEV_LOCAL_DEBITS=3
- LOCAL_BUDGET_DEV_CLOUD_ISSUED=3
- LOCAL_BUDGET_DEV_CLOUD_REPORTED=3
- LOCAL_BUDGET_DEV_BLOCK_COUNT=1
- LOCAL_BUDGET_DEV_CANARY=PASS
- LOCAL_BUDGET_DEV_CLEANUP=PASS

## Cross-platform release gate

Windows VM, DEV-served 0.3.35:
- SHA matches manifest
- operator-session gate PASS
- console sanitization PASS
- starter read PASS
- five-tool bridge PASS
- arbitrary function DENIED
- self-test exit 0

Windows does not use LOCAL_BUDGET in this slice.

## State

LOCAL_BUDGET_SOURCE=CLOSED_PASS
LOCAL_BUDGET_DEV=CLOSED_PASS
LOCAL_BUDGET_FRESH_TENANT_ZERO_BASELINE=CLOSED_PASS
AGENT_0_3_35_RELEASE=CLOSED_PASS
PROD_PROMOTION=PENDING

## Successor security gate

Do not promote the 0.3.35 local-budget release to PROD.

The audited successor branch local/commander-local-budget-audit-20261005
hardens the product lease with a cloud-signed RS256 token and raises the
LOCAL_BUDGET Agent gate to 0.3.36.

The DEV successor gate is now closed:
- PRODUCT_LEASE_PRIVATE_JWK provisioned as a Worker secret without exposing it;
- signed Worker DEV live;
- Agent 0.3.36 signed-lease canary PASS;
- explicit LOCAL_BUDGET_DEV_SIGNED_LEASE_VERIFIED=PASS;
- Windows 0.3.36 release self-test PASS.

PROD remains on the prior safe 0.3.34 release until the same signing key is
configured as a PROD secret and the signed successor is promoted deliberately.

Successor source/test commit lineage:
bc25de10bda3b1aaea856121056ba748c1eec76a
