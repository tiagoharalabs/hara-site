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
