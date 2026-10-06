# H.A.R.A. Commander — P0 Fresh Customer Acceptance

Date: 2026-10-05
Environment: DEV only
Canonical branch: `local/commander-openai-desktop-parity-20261004`

## Goal

Prove a customer can start from a fresh identity/tenant/device and reach a useful Simple MCP session without maintainer repair.

Target acceptance path:

1. fresh tenant + owner identity;
2. fresh TRIAL entitlement;
3. fresh one-time pairing token;
4. normal `/api/device/enroll` call;
5. isolated Linux XDG config with `PERSISTENT_TRUSTED`;
6. local Simple MCP JSON-RPC initialize + 24-tool discovery;
7. zero-relay `write_file -> read_file -> edit_block -> start_process`;
8. privacy-safe local Activity + receipts;
9. fixture cleanup.

Reusable probe:

`apps/commander/scripts/commander_fresh_customer_dev_acceptance.py`

The probe:
- uses DEV origin/database only;
- generates random tenant/user/device/pairing identities;
- never prints pairing or device tokens;
- stores device config only in a temporary XDG root;
- never edits the stable PROD Agent config/service;
- uses the normal public enrollment API;
- talks to `python3 agent/linux.py mcp` over JSON-RPC stdio;
- expects exactly 24 Simple MCP tools and no public `hara.*` names;
- checks local MCP zero-relay accounting;
- checks filesystem/process execution and local receipt privacy;
- deletes all DEV fixtures in `finally`.

## Live execution

First execution:
- fixture seed: created;
- enrollment: HTTP 503;
- fixture cleanup: PASS.

Second diagnostic execution with sanitized error-code capture:
- enrollment: HTTP 503;
- Worker code: `STRICT_RATE_LIMIT_CHECK_FAILED`;
- fixture cleanup: PASS;
- pairing/device token output: ABSENT.

Current result:

`FRESH_CUSTOMER_ACCEPTANCE=BLOCKED_DO_CAPACITY`

The acceptance path did not fail because of pairing-token validation, Agent behavior, Simple MCP, filesystem, process execution, or receipts. The request was rejected earlier by the same strict rate-limit / Durable Object capacity failure observed by the live multitenant probe.

## Shared blocker with multitenant P0

The following P0s now share one infrastructure blocker:

- live multitenant select/revoke/quota proof;
- fresh-customer enrollment and therefore downstream Simple MCP acceptance;
- normal H.A.R.A. paths that depend on the strict rate-limit / TenantQuota Durable Object.

Observed correlated errors:
- `Exceeded_allowed_rows_read_in_Durable_Objects_free_tier_`
- `STRICT_RATE_LIMIT_CHECK_FAILED`
- quota authorize `INTERNAL_ERROR`

## Next action

1. Restore/upgrade Durable Object capacity or move DEV to a capacity tier that can execute the canonical probes.
2. Re-run `commander_multitenant_live_dev_probe.py` unchanged.
3. Re-run `commander_fresh_customer_dev_acceptance.py` unchanged.
4. Fresh-customer P0 closes only when the probe reaches:
   - identity/tenant PASS;
   - pairing/enrollment PASS;
   - 24 Simple MCP tools / no `hara.*` public names;
   - zero relay PASS;
   - filesystem PASS;
   - one-shot process PASS;
   - Activity metadata-only PASS;
   - local receipts PASS;
   - fixture cleanup PASS.
5. Remote Simple MCP + cloud Usage is a subsequent acceptance step after DO capacity is restored.

No PROD customer/device/Agent state was mutated by this probe.

## Continuation - local fresh-customer path CLOSED_PASS

After feec164, the live probe progressed through:
- identity/tenant PASS
- pairing/enrollment PASS
- Simple MCP tools exactly 24
- public hara.* prefix ABSENT
- local MCP zero-relay PASS
- filesystem write/read/edit PASS

The remaining LOCAL_MCP_PROCESS_INVALID was a probe assertion-shape defect, not an Agent execution failure.

Actual Local MCP contract:
1. start_process returns the governed bridge envelope
2. the governed function result is under result
3. result.stdout contains the JSON payload returned by process_run
4. that inner payload carries state EXITED, exit_code 0 and bounded output text

The acceptance probe was corrected to normalize this existing contract while still requiring:
- governed function process.run
- bridge process_exit_code 0
- inner process state EXITED or COMPLETED
- inner exit code 0 when present
- expected bounded output marker

Latest live result:
- FRESH_CUSTOMER_LOCAL_MCP_PROCESS=PASS
- FRESH_CUSTOMER_LOCAL_MCP_ACTIVITY=PASS
- FRESH_CUSTOMER_LOCAL_MCP_RECEIPTS=PASS
- FRESH_CUSTOMER_ACCEPTANCE_LOCAL_PATH=PASS
- FRESH_CUSTOMER_DEV_FIXTURE_CLEANUP=PASS

Receipt privacy checks remained enabled and PASS; the probe does not print pairing/device tokens.

The only unexercised part is cloud-backed remote Usage:
FRESH_CUSTOMER_REMOTE_USAGE_PATH=NOT_EXERCISED_DO_CAPACITY

Current state:
- FRESH_CUSTOMER_LOCAL_PATH=CLOSED_PASS
- FRESH_CUSTOMER_REMOTE_USAGE=PENDING_DO_CAPACITY
