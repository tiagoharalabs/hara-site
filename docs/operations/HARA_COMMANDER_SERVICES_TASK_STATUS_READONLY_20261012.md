# H.A.R.A. Commander — read-only Services task-status adapter

**Date:** 2026-10-12  
**Scope:** H.A.R.A. Commander **product** (not Commander Baseline), Services node only.  
**Status:** live sidecar deployed and tested; incorporation into a future signed Agent release is proposed, not claimed.

## Problem and root cause

The product Agent 0.3.46 runs under a systemd unit with `NoNewPrivileges=yes`. Its terminal process inherits `NoNewPrivs=1`. The canonical Services command `hara agents tasks status` invokes the protected contact-task-queue helper through `sudo -n`; this elevation is unavailable inside the Agent process. The adapter's JSON parser then maps the sudo diagnostic output to `HOLD_HELPER_OUTCOME_UNKNOWN / QUEUE_OUTPUT_INVALID`.

A read on the **native Services host** with the canonical CLI returns `READY`. Therefore the issue is the MCP Agent's privilege boundary, not evidence that the native task queue is damaged.

## Implemented safe read-only sidecar

On Services, the operator-owned sidecar lives at:

- `~/.local/share/hara-commander/adapters/services_tasks_readonly_v1.py`
- `~/.local/bin/hara-commander-services-tasks` (alias to the above)

From the **H.A.R.A. Commander product MCP**, target computer `services` and execute:

```bash
hara-commander-services-tasks status
```

This invokes an exact, fixed **read-only** Services-native CLI through existing authenticated SSH. It verifies the SSH host key, hostname, schema `hara.contact-tasks.result.v1`, authority `HARA_SERVICES`, non-mutating flags and queue-count types before emitting the **unmodified** canonical response.

The code admits no arbitrary remote command, queue writes, alternate queue, raw queue-file access, unsigned Agent modification or `sudo` privilege inside the Agent sandbox. `submit`, `get`, `review-submit`, `review-get` and unrecognized inputs are rejected with `READ_ONLY_STATUS_ONLY` and exit code 2.

## Validation

- Product MCP call against `services`: **READY**, exit code 0.
- Results exactly equal to the canonical native Services response.
- Nine offline unit tests: **PASS**, including rejected commands, bad host identity, bad schema/authority, invalid counters, mutation flags, SSH failure and timeout.
- Agent release 0.3.46 verifier: public trust anchor, RS256 signature, seven pinned artifacts, founder canary and no embedded secret key all **PASS**.
- Canonical Services command SHA256 remained `083a6444b43b0f31670bea5116568b6b2103843e9106b134515d8c24b7010aea`.
- `NoNewPrivileges=yes` remains active; no Agent restarts or Services live canonical-registry writes were made.

## Follow-on signed integration

This PR versions the sidecar and tests in the product repository. It **does not change the signed Agent 0.3.46 or automatically extend the MCP tool schema**.

For the next product release, incorporate an explicitly named first-class read-only Services-status capability through the approved signing and release pipeline, retaining the strict validation and negative-path tests. Do not silently rewrite arbitrary `start_process` commands or shadow the globally canonical `hara` executable.

The unqualified command `hara agents tasks status` still fails inside the restricted Agent sandbox. Consumers should use the product sidecar until the signed tool integration is admitted. Canonical task queue writes remain under the existing Services authorizations.

This is a product execution-context adaptation, not a second authoritative queue, policy, or privilege plane.
