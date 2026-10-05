# H.A.R.A. Commander — signed lease + local-first PROD proof

Date: 2026-10-05
Canonical source: 4e45df70c58f1894503321cdd49cfb22a3bf6970

## PROD Worker

Current:
- a4f72df7-b3c1-47b4-bc10-46d007aa7639
- tag: signed-lease-win-local-0.3.37-secret

Rollback:
- 3e4aab17-74c0-4331-84ae-5ab31dbb71e1

Deployment:
- 100% current version
- signed lease private key present as Worker version secret
- fail-closed suite PASS

Public release:
- Agent version 0.3.37
- Linux asset SHA matches manifest
- Windows asset SHA matches manifest

## Linux rollout

### nucleo-a

- upgraded 0.3.34 -> 0.3.37 with canonical updater
- updater integrity PASS
- startup attestation PASS
- rollback-ready PASS
- service active
- H.A.R.A. Commander health PASS
- signed product lease persisted locally
- signed lease token present
- plan FOUNDER_INTERNAL
- usage mode UNMETERED
- period kind NONE
- local budget blocks 0
- local budget debits 0
- bounded Activity snapshot present in PROD D1

### sentinela-d

- upgraded 0.3.34 -> 0.3.37 with canonical updater
- updater integrity PASS
- startup attestation PASS
- rollback-ready PASS
- service active
- H.A.R.A. Commander health PASS
- signed product lease persisted locally
- signed lease token present
- plan FOUNDER_INTERNAL
- usage mode UNMETERED
- period kind NONE
- local budget blocks 0
- local budget debits 0
- bounded Activity snapshot present in PROD D1

Founder usage readback remains:
- period_key=UNLIMITED
- limit=NULL
- metered=false
- available=true

## PROD local-budget allocation state

At acceptance:
- budget blocks: 0
- allocated units: 0
- issued units: 0
- reported units: 0
- active fresh baselines: 0

No Free local capacity was allocated silently during rollout.

The Free path remains cloud-authoritative for block allocation and can consume
only units issued by the cloud. Signed-lease Agent 0.3.37 is the minimum local
budget generation.

## Windows 0.3.37

Source/preprod:
- native winsqlite3.dll store PASS
- parameterized SQLite API PASS
- activity_events local store PASS
- raw payload/result columns absent
- bounded aggregate heartbeat snapshot PASS
- command-secret redaction PASS
- full preprod PASS

Real Windows 11 VM, DEV-served Agent 0.3.37:
- manifest version PASS
- SHA match PASS
- local SQLite Activity PASS
- raw customer content absent PASS
- snapshot privacy PASS
- five-tool bridge PASS
- arbitrary function denied
- self-test exit 0

PROD VM runtime state:
- old cloud enrollment HARA_WIN11 remains preserved and offline
- Scheduled Task remains present
- task points to profile sarti
- local Agent/config files for that enrollment are absent
- no recoverable local device token exists
- updater correctly refused with DEVICE_NOT_ENROLLED
- no destructive revoke/re-enroll was attempted

Therefore Windows production live enrollment requires a new pairing/enrollment
through the allowed customer/admin channel. The current H.A.R.A. Commander
connector exposes device reads but no pairing creation action, so this remains a
human/operator gate.

## Architecture state

ACTIVE:
- Cloud authority for identity / tenant / entitlement / billing / grants /
  revocation
- signed product lease for local authorization cache
- local-first Linux Activity
- local budget capability for eligible Free Linux devices
- Windows local Activity implementation and release proof
- cloud bounded aggregate snapshots / fallback

PENDING:
- Windows production re-enrollment on the real VM
- first natural Free PROD customer using LOCAL_BUDGET

## Acceptance markers

SIGNED_LEASE_PROD_WORKER=CLOSED_PASS
SIGNED_LEASE_LINUX_PROD=CLOSED_PASS
LOCAL_FIRST_LINUX_PROD=CLOSED_PASS
LOCAL_BUDGET_PROD_INFRA=CLOSED_PASS
LOCAL_BUDGET_PROD_ALLOCATION_AT_ROLLOUT=ZERO
WINDOWS_LOCAL_ACTIVITY_RELEASE=CLOSED_PASS
WINDOWS_LOCAL_ACTIVITY_VM_SELFTEST=CLOSED_PASS
WINDOWS_PROD_REENROLLMENT=PENDING_OPERATOR_GATE
