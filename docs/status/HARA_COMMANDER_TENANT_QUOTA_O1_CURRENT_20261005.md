# H.A.R.A. Commander — TenantQuota O(1) current candidate

Date: 2026-10-05
Base: current Commander canonical after signed-lease/local-first PROD rollout

## Change

TenantQuota hot-path storage was reconciled onto the current canonical without
changing signed lease, local budget, Windows local-store, billing or MCP
contracts.

Added inside the Durable Object:
- composite stale-reservation index on state + updated_at_utc
- period_usage aggregate table keyed by period
- quota_meta usage schema marker
- atomic INSERT / UPDATE / DELETE accounting triggers
- one-time aggregate backfill for existing Durable Object state

Changed status hot path:
- before: SUM(units) across historical RESERVED/COMMITTED rows
- after: indexed single-row period_usage lookup

## Preserved semantics

PASS:
- reservation TTL remains 600 seconds
- stale reservations auto-release
- fresh reservations preserved
- committed requests preserved
- replay/idempotency behavior preserved
- receipt binding preserved
- ambiguous execution reconciliation preserved
- local budget gates preserved
- signed product lease gates preserved
- unlimited-plan DO bypass preserved
- Windows local Activity store preserved

## Source/regression

PASS:
- TenantQuota expiry index
- aggregate backfill
- trigger accounting
- hot-path SUM absent
- status complexity O(1)
- quota reservation TTL
- Event V2 quota source contract
- local budget full validator
- signed product lease validator
- Windows local Activity validator
- unlimited-plan fast-path validator
- full E2E harness
- full preprod readiness

## Promotion boundary

This candidate is not authorized for PROD solely from source tests.

Required:
1. deploy current candidate to DEV only;
2. rerun live multitenant isolation probe;
3. rerun fresh-customer DEV acceptance;
4. confirm DEV deployment/config readback;
5. confirm no regression in signed lease/local-budget canary;
6. inspect Durable Object live behavior/cost if analytics is available;
7. only then decide PROD promotion.

## DEV live proof

Worker:
- 8fa82e3d-00d6-441f-aa6a-9e650a52b616
- rollback: cf7e6b97-d3c3-4ec9-9e95-edbb76925d16

Deployment/config readback:
- DEV config PASS
- DEV-only D1 PASS
- required secrets PASS
- DeviceChannel PASS
- public health PASS
- login redirect/PKCE/cookie/account switch PASS

Live multitenant isolation:
- tenant A enumeration PASS
- tenant B enumeration PASS
- cross-tenant select DENIED
- cross-tenant revoke DENIED
- cross-tenant enqueue DENIED
- caller-supplied tenant override ABSENT
- cross-tenant call status DENIED
- same-tenant call status PASS
- cross-tenant receipt read DENIED
- quota A HTTP 200 / ALLOW
- quota B HTTP 200 / ALLOW
- tenant derivation A/B PASS
- independent TenantQuota namespace PASS
- fixture cleanup PASS
- overall MULTITENANT_ISOLATION_LIVE_DEV=PASS

Fresh-customer acceptance:
- identity/tenant PASS
- pairing/enrollment PASS
- 24 Simple MCP tools
- no public hara.* prefix
- zero-relay local path PASS
- filesystem PASS
- process PASS
- local Activity PASS
- privacy-safe receipts PASS
- fixture cleanup PASS

Remote metered execution is covered by the signed local-budget canary rather than
duplicating a per-call cloud quota flow in the fresh-customer harness.

Signed local-budget canary on the same O(1) Worker:
- block issue PASS
- block size 100
- FRESH_TENANT_ZERO baseline
- legacy DO baseline reads 0
- signed lease verified locally PASS
- 3 governed calls / 3 local debits
- cloud issued 3
- cloud reported 3
- block count 1
- cleanup PASS

## Current state

TENANT_QUOTA_O1_SOURCE=CLOSED_PASS
TENANT_QUOTA_O1_PREPROD=CLOSED_PASS
TENANT_QUOTA_O1_DEV_LIVE=CLOSED_PASS
MULTITENANT_ISOLATION_LIVE_DEV=CLOSED_PASS
SIGNED_LOCAL_BUDGET_O1_DEV=CLOSED_PASS
PROD_PROMOTION=PENDING_VERSIONED_SIGNING_SECRET
