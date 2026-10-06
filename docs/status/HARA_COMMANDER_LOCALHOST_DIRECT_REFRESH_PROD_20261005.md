# H.A.R.A. Commander — localhost direct refresh PROD live proof

Date: 2026-10-05
Canonical source before evidence: 1a2e14f5101d5bd7dd9d8328479e7a3400317a31

## Product boundary

Cloud remains authoritative for:
- identity
- tenant / roles
- entitlement / grants
- billing
- revocation
- enrollment
- authenticated portal session

The customer machine is authoritative for operational Activity detail.

## PROD Worker

Current:
- 3e4aab17-74c0-4331-84ae-5ab31dbb71e1

Rollback:
- bb1e2a9f-af25-4ca9-b77d-37598c696e7c

No D1 migration was required for this slice.

Live Worker gates:
- deployment readback PASS
- fail-closed suite PASS
- cache key 20261005-localdirect1 PASS
- CSP exact 127.0.0.1:32145 PASS
- upgrade-insecure-requests absent PASS
- browser loopback permission gate PASS
- targetAddressSpace=loopback PASS
- explicit-refresh permission behavior PASS
- release manifest Agent 0.3.34 PASS

## Browser UX

Modern browsers gate access from a public HTTPS site to loopback/local services.

Commander does not request this permission automatically when entering the page.

Behavior:
1. default page load uses cloud authority and bounded local snapshots;
2. first explicit Activity refresh may request loopback permission;
3. if granted, direct local detail is available from the Agent;
4. if denied or Agent is absent, cloud fallback remains functional;
5. cloud 401/session authority always overrides the local accelerator.

## nucleo-a

Updater:
- 0.3.33 -> 0.3.34
- canonical updater
- startup attestation PASS
- rollback-ready PASS
- service active/enabled
- PERSISTENT_TRUSTED preserved

Live loopback:
- bind: 127.0.0.1:32145 only
- /v1/activity HTTP 200
- source LOCAL_SQLITE
- local_direct true
- computer nucleo-a
- 7d total at acceptance: 1,800
- detailed events returned locally
- forbidden secret/raw-content keys: NONE
- exact PROD Origin allowed
- foreign Origin -> 403 LOCAL_ORIGIN_DENIED

H.A.R.A Commander health:
- PASS
- Agent 0.3.34

## sentinela-d

Updater:
- 0.3.33 -> 0.3.34
- canonical updater
- startup attestation PASS
- rollback-ready PASS
- service active
- PERSISTENT_TRUSTED preserved

Live loopback:
- bind: 127.0.0.1:32145 only
- source LOCAL_SQLITE
- local_direct true
- computer sentinela-d
- 7d total at acceptance: 4
- forbidden secret/raw-content keys: NONE
- foreign Origin -> 403 LOCAL_ORIGIN_DENIED

H.A.R.A Commander health:
- PASS
- Agent 0.3.34

## Cloud fallback remains healthy

PROD D1 device snapshots after Agent rollout:
- nucleo-a Agent 0.3.34, snapshot present
- sentinela-d Agent 0.3.34, snapshot present

Cloud receives bounded aggregate snapshots only. Detailed action history remains local.

## Release cross-platform gate

Windows DEV-served 0.3.34 asset was validated inside the real Windows 11 VM:
- SHA matches manifest
- operator-session gate PASS
- console sanitization PASS
- starter read PASS
- five-tool bridge PASS
- arbitrary function DENIED
- self-test exit 0

Windows local SQLite/localhost parity was intentionally not introduced in this slice.

## State

LOCALHOST_DIRECT_REFRESH_LINUX_PROD=CLOSED_PASS
LOCALHOST_LOOPBACK_SECURITY_PROD=CLOSED_PASS
AGENT_0_3_34_LINUX_PROD=CLOSED_PASS
CLOUD_AUTHORITY_LOCAL_OPERATIONS_ARCHITECTURE=ACTIVE
WINDOWS_LOCAL_STORE_PARITY=PENDING
LOCAL_ENTITLEMENT_LEASE=PENDING
FREE_LOCAL_BUDGET_BLOCKS=PENDING
