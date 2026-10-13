# Real DEV ramp and soak — 2026-10-12

The real HTTPS → Cloudflare DEV → WSS → Linux Agent path passed at 2, 10, 25 and 100 concurrent registered QA Agents with 100 distinct tenants. These Agents run in separate owner-only configuration/data directories on one physical Services host. Identities were preseeded for QA in DEV; this is not a proof of 100 physical machines, 100 OAuth customer logins, PROD load, or the 1,000-customer capacity target.

| Stage | Successful Agents | Invoke p95 | Invoke p99 |
| --- | ---: | ---: | ---: |
| 2 | 2/2 | 1.833 s | 1.833 s |
| 10 | 10/10 | 2.304 s | 2.304 s |
| 25 | 25/25 | 2.096 s | 2.113 s |
| 100 | 100/100 | 2.332 s | 3.565 s |

Each stage executed `device.info` through transient RPC and replayed the same request. The responses reported COMMITTED usage, REPLAY_ONLY on replay, identical receipt binding, and no persisted cloud customer payload/result. The probe validates the returned selected device for each independent tenant. A separate quota acceptance test is responsible for exact quota ledger balance and cross-tenant negative cases.

The 100-Agent peak used 4,183,265,280 bytes of Agent RSS, with 26,301,067,264 bytes available and 1-minute load 1.195 on 12 CPUs. Probe concurrency was capped at 20. The stage gates require success >=99%, p95 <=6 seconds and p99 <=12 seconds, and halt on the first error. Existing Founder Agents, customer devices, fleet processes and shared plan/grant/budget configuration were not changed.

98 QA Agent processes, private credentials and tenants were removed after the ramp. The two retained fixtures began the first pilot, then were also cleaned after the pilot detected a disconnected sample. No fixture from run 001 remains active. Their process restart and a 3-second stop/start both preserved the local replay ledger and receipt. This stop/start is a process outage; it is not a network fault proof.

A separate isolated QA Agent passed an actual local TLS socket shutdown. Its normal Event V2 loop reconnected without changing PID, then replayed the same request with the same receipt and unchanged local ledger. Recovery including verification took 11.056 seconds. That temporary tenant, Agent and credentials were cleaned. The QA-only socket-fault wrapper does not change any release source bytes.

## First pilot and next observation

Run: `soak-20261012-root-001`.

Owned service: `hara-commander-acceptance-soak-20261012-001.service`.

Service invocation ID: `20fd06264d8a4c2ebdb5cd6834e63819`.

Main PID at launch: `2327056`.

The first continuity observation began at `2026-10-12T23:59:57Z` (20:59:57 BRT). Run 001 stopped at the disconnected sample after three healthy observations, reported FAIL with `SOAK_AGENT_DISCONNECTED`, and cleaned all 100 QA fixtures. A disconnected sample alone does not establish a permanent failure; Windows QA elsewhere recovered in seven seconds around the same interval. The current runner measures a 30-second reconnect grace with before/after codes, timestamps and down duration, failing if the Agent exits or recovery exceeds that window. Its boundary tests cover a seven-second recovery, a permanently disconnected Agent, a recovery too late at 31 seconds, and process death. A real negative PID command test also proves that a different command is refused without terminating it. A new pilot will start only after the next pinned DEV deployment. It requires an actual 20-minute pilot before state SOAK_STARTED. The pilot is part of the measured continuity duration. 24-hour and 72-hour flags remain false until those intervals have actually elapsed. The service has an independent 73-hour maximum runtime, no automatic restart, and a 72-hour observation deadline counted from the first pilot observation.

Live evidence: `soak-20261012-root-001/status.json`.

Network-loss evidence: `soak-network-20261012-root-001/status.json`.

The runner stops and cleans its own exact PID/command/UID-bound Agent processes and its own HARA-ACCEPT tenant IDs in finally, including on SIGTERM. Credential files are owner-only. A failed cloud cleanup is explicitly recorded as FAIL and must be reconciled; it is not reported as complete. The explicit application HTTP and administrative D1 command budget is 3,000. WSS transport control frames and Agent liveness/reconnection messages are not included in that client-side counter.

Probe traffic consists of metadata-only `hara.health` requests every 10 minutes after the pilot. Function invoke/replay is confined to ramp, recovery and final verification to conserve the unchanged TRIAL quota. The pilot probes once per minute. Only aggregate timings/resource statistics and request/receipt bindings are exported; local replay entries may contain this QA Agent's device.info result and are removed with each fixture.

## Operation

From Services, inspect the owned unit with:

```sh
systemctl --user show hara-commander-acceptance-soak-20261012-001.service --property=MainPID,ActiveState,SubState,Result
```

Inspect the exact live JSON path:

```text
/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/real-dev-soak/soak-20261012-root-001/status.json
```

Run 001 is now inactive. If a future observation needs to be stopped, use its exact owned unit, not a fleet service. The archived run-001 target was:

```sh
systemctl --user stop hara-commander-acceptance-soak-20261012-001.service
```

Do not generalize the stop to Founder/fleet Agent services. Do not promote a STARTED or PILOT_RUNNING record to a 24/72-hour PASS.

Reusable sources:

- `apps/commander/scripts/commander_full_acceptance_real_dev_soak.py`
- `apps/commander/scripts/commander_full_acceptance_network_recovery_dev.py`

All five Agent source files are copied into a run-specific private directory and their SHA-256 values are bound in evidence. No Worker deployment or public installer publication was performed by this lab.
