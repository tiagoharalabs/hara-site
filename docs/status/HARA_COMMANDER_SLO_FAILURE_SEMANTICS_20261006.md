# H.A.R.A. Commander — SLO failure semantics

Date: 2026-10-06
Agent candidate: 0.3.40

## Problem

The original INTERNAL_BETA_V1 SLO used raw tool outcome success as the
availability success signal.

That can incorrectly treat expected customer/action outcomes as downtime.

Observed on nucleo-a before this change:
- 1,369 completed operations
- 20 failed outcomes
- raw outcome success about 98.6%
- all 20 failures were action/policy semantics:
  - HTTP_400
  - FILENOTFOUNDERROR
  - EDIT_MATCH_AMBIGUOUS
  - PROCESS_SESSION_EXITED
- no service/runtime/network failure was present in that failure set

The old definition therefore opened a real SLO incident for a non-availability
condition.

## New semantics

Raw outcome visibility is preserved.

Summary now carries:
- success_rate_percent: all completed vs all failed outcomes
- availability_success_rate_percent: completed vs service-attributable failures
- client_failed
- policy_failed
- service_failed

The SLO declares:
- success_metric=availability_success_rate_percent

Explicit CLIENT_ACTION examples:
- HTTP_400
- HTTP_404/405/410/422
- FILENOTFOUNDERROR
- FILEEXISTSERROR
- ISADIRECTORYERROR
- NOTADIRECTORYERROR
- EDIT_MATCH_AMBIGUOUS
- PROCESS_SESSION_EXITED
- PROCESS_SESSION_NOT_FOUND

Explicit POLICY examples:
- HTTP_401
- HTTP_403
- HTTP_409
- HTTP_429
- LOCAL_OPERATOR_APPROVAL_DENIED
- APPROVAL_TIMEOUT

Fail-closed rule:
- unknown errors are SERVICE failures
- legacy snapshots without service_failed treat every failed outcome as SERVICE

Therefore the change cannot silently improve availability for unknown or legacy
failure classes.

## Cross-platform

Linux and Windows source implement the same classification.

The cloud Worker:
- allowlists the new aggregate counters/rate
- preserves raw outcome rate
- uses service_failed for tenant availability
- treats old snapshot failed count as service failure
- keeps p50/p95/p99 behavior unchanged

Portal:
- Activity continues to show raw success/outcome
- SLO card labels the SLO percentage as disponibilidade

## Dynamic regression

PASS:
- 25 completed + 4 client failures + 1 policy failure
- raw outcome success = 83.3%
- availability success = 100%
- service_failed = 0
- SLO = PASS

Then one unknown RUNTIME_ERROR:
- service_failed = 1
- availability success = 96.2%
- SLO = DEGRADED

This proves expected customer/action errors do not breach availability while an
unknown failure remains fail-closed.

## Source / preprod

PASS:
- Linux classification
- Windows classification
- legacy fail-closed fallback
- Worker tenant availability aggregation
- raw outcome retained
- portal availability label
- SLO probe availability/outcome split
- release signature 0.3.40
- one-click support
- support plane
- clean Linux lifecycle
- SLO incident/actions
- E2E
- full preprod readiness

## Promotion boundary

1. deploy 0.3.40 to DEV;
2. run live failure-semantics canary;
3. verify expected errors never open an incident;
4. verify service error opens only after breach hysteresis;
5. promote to PROD;
6. update Linux Agents;
7. allow natural PROD recovery hysteresis to resolve the historical incident.

## DEV live proof — 2026-10-06

The active DEV public release matched the canonical 0.3.40 asset set byte-for-byte
for the application, Linux/Windows Agents and installers, release manifest,
detached signature and SHA256SUMS.

The DEV-only canary credential was rotated through the canonical secure
provisioner after the older local canary credential returned 401. The value was
never printed or committed.

Live failure-semantics canary:

- expected client/policy failures: raw outcome success 83.3%
- availability success: 100.0%
- expected errors opened no incident: PASS
- one unknown RUNTIME_ERROR counted as SERVICE: PASS
- service failure opened only after the second breach: PASS
- test tenant/device cleanup: PASS

```text
COMMANDER_SLO_SEMANTICS_DEV_EXPECTED_ERRORS_NO_INCIDENT=PASS
COMMANDER_SLO_SEMANTICS_DEV_OUTCOME_RATE=83.3
COMMANDER_SLO_SEMANTICS_DEV_AVAILABILITY_RATE=100.0
COMMANDER_SLO_SEMANTICS_DEV_SERVICE_FAILURE_OPENS_AFTER_HYSTERESIS=PASS
COMMANDER_SLO_FAILURE_SEMANTICS_DEV=PASS
COMMANDER_SLO_FAILURE_SEMANTICS_DEV_CLEANUP=PASS
```

## PROD live proof — 2026-10-06

Canonical source at promotion:

- `local/commander-openai-desktop-parity-20261004`
- `c9f492620b2ba3b0c6b04d1adf5fabd78680e73c`

Production candidate:

- tag: `slo-failure-semantics-0.3.40`
- Worker Version: `c8cfc1d1-592c-4d71-8788-d237e07828c6`
- rollback: `a62fde0b-9c7d-4500-a97e-f31d9bdf9eac`

The candidate inherited the required PROD secrets and bindings. The canonical
versioned promotion helper passed rollback-current and target-secret guards,
promoted the candidate to 100%, synchronized triggers and read back the exact
Worker version.

Post-promotion:

- PROD runtime health: PASS
- PROD auth configured: PASS
- all tracked runtime assets: CURRENT
- detached release signature/public key/SHA256SUMS: CURRENT
- PROD fail-closed suite: PASS
- exact Worker deployment: PROVEN
- D1 migration 0009: APPLIED
- full `validate_preprod_readiness.py --live-readonly`: exit 0

```text
COMMANDER_PROD_RUNTIME_ASSETS=CURRENT
COMMANDER_PROD_WORKER_DEPLOYMENT=PROVEN
COMMANDER_PROD_WORKER_VERSION=c8cfc1d1-592c-4d71-8788-d237e07828c6
COMMANDER_PROD_FAIL_CLOSED=PASS
COMMANDER_SOURCE_PREPROD_READY=PASS
```

A drift found immediately before this promotion showed PROD serving the 0.3.39
asset set while the source had already advanced to 0.3.40. The promotion helper
is therefore hardened to require
`validate_prod_runtime_drift.py --expect-assets current` after the exact-version
readback. A versioned promotion cannot report PASS anymore while public assets
are stale or mixed.

## Linux Agent rollout

Sentinela D was a safe rollout target: Agent 0.3.39 was active and its systemd
user-service cgroup contained only the Agent process.

Served PROD installer preflight:

- release_manifest=true
- release_signature=true
- stable_agent_version=0.3.40
- persistence_ready=true
- mutation_performed=false

Update result:

- 0.3.39 -> 0.3.40
- integrity PASS
- startup attestation PASS
- update PASS
- rollback-ready TRUE
- service active
- cgroup process count remains 1

Nucleo A intentionally remains on Agent 0.3.39 for now. Its Agent cgroup also
owns an active model-execution optimization worker; restarting the systemd user
service would kill unrelated in-flight work. Upgrade is deferred until that
child workload drains.

## Current state

```text
SLO_FAILURE_SEMANTICS_SOURCE=CLOSED_PASS
SLO_FAILURE_SEMANTICS_DEV_LIVE=CLOSED_PASS
SLO_FAILURE_SEMANTICS_PROD=CLOSED_PASS
PROD_RUNTIME_0340_ASSETS=CURRENT
PROD_ROLLBACK_READY=a62fde0b-9c7d-4500-a97e-f31d9bdf9eac
SENTINELA_D_AGENT_0340=CLOSED_PASS
NUCLEO_A_AGENT_0340=PENDING_SAFE_CHILD_DRAIN
```
