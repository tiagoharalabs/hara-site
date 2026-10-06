# H.A.R.A. Commander — Windows local Activity store DEV proof

Date: 2026-10-05
Branch: local/commander-windows-local-store-v2-20261005
Agent release: 0.3.37

## Architecture

Windows now follows the same local-first operational boundary as Linux.

Local:
- operations.sqlite3
- detailed Activity events
- action summaries
- latency/error metadata
- recent operational history

Cloud:
- identity / tenant / entitlement / billing / grants / revocation
- bounded aggregate Activity snapshot only

The Windows implementation uses the native Windows 11 winsqlite3.dll. It does
not require Python, sqlite3.exe, a bundled database runtime or an additional
downloaded dependency.

## Source / preprod

PASS:
- native winsqlite3 binding
- prepared/parameterized SQL
- activity_events schema
- no payload_json column
- no result_json column
- one-time JSONL migration marker
- local snapshot source LOCAL_SQLITE
- heartbeat carries bounded snapshots
- customer_content_synced=false
- action summaries local-only
- command-secret redaction
- Windows local-store validator
- signed product lease validator
- local budget validator
- E2E harness
- full preprod readiness

## DEV runtime

DEV Worker at acceptance:
- cf7e6b97-d3c3-4ec9-9e95-edbb76925d16

DEV served release:
- Agent 0.3.37
- PRODUCT_LEASE_PRIVATE_JWK secret present
- DEV health/login/PKCE/cookie/account-switch readback PASS

Fresh Free signed-budget canary on 0.3.37:
- block issue PASS
- block size 100
- FRESH_TENANT_ZERO baseline
- legacy DO baseline reads 0
- signed lease verified locally PASS
- 3 calls / 3 local debits
- cloud issued 3
- cloud reported 3
- one block
- cleanup PASS

## Windows 11 VM live-served canary

The Agent and manifest were downloaded from the live DEV Worker into the real
commander-win11 VM.

PASS:
- manifest version 0.3.37
- windows.ps1 SHA matches manifest
- operator-session gate
- console sanitization
- starter read
- local SQLite Activity
- raw customer content absent
- local snapshot privacy
- five-tool bridge
- arbitrary function denied
- Agent self-test
- self-test exit 0
- QGA exit 0

## State

WINDOWS_LOCAL_ACTIVITY_SOURCE=CLOSED_PASS
WINDOWS_LOCAL_ACTIVITY_DEV=CLOSED_PASS
AGENT_0_3_37_RELEASE_GATE=CLOSED_PASS
SIGNED_PRODUCT_LEASE_DEV=CLOSED_PASS
LOCAL_BUDGET_FREE_DEV=CLOSED_PASS
PROD_PROMOTION=PENDING_PROD_SIGNING_SECRET_AND_ROLLOUT
