# H.A.R.A. Commander — Public product boundary

Date: 2026-10-06
State: SOURCE/PREPROD CLOSED_PASS

## Product definition

The public H.A.R.A. Commander is the MCP bridge between:
- the user's computer running the Commander Agent; and
- ChatGPT, Claude Code, Codex, Cursor, VS Code or another compatible MCP client.

It is not the H.A.R.A. internal control plane.

Fleet/lab observability such as Sentinela hosts, internal SLO incidents, p95/p99,
transport diagnostics, top tools/errors and detailed execution ledgers belongs
to a separate internal Commander/control-plane workstream.

## Public UI boundary

Removed from the public Usage page:
- transaction diagnostics;
- success-rate cards;
- average latency;
- transport mode;
- internal SLO;
- incident acknowledge/escalate actions;
- top tools;
- top errors;
- recent transaction ledger;
- advanced diagnostic details.

The Usage page now shows product usage/plan capacity only, plus privacy copy
that detailed diagnostics stay on the local Agent.

## Cloud boundary

Public Commander no longer:
- persists Agent activity snapshots in heartbeat;
- accepts detailed activity into D1;
- runs the internal SLO cron;
- serves portal activity/SLO endpoints.

The legacy public endpoints fail closed with:
- HTTP 404
- INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT

The two remote diagnostic MCP tools that previously read cloud history now fail
closed with AGENT_UPGRADE_REQUIRED until the signed local-activity Agent path is
promoted.

## Local boundary

Detailed execution history remains local in the Agent SQLite store:
- tool identifiers;
- sanitized error codes;
- durations;
- local receipts/traces;
- local action summaries.

Raw commands, arguments, payloads and results remain excluded from support/cloud
telemetry contracts.

## Heartbeat write reduction

Agent heartbeat request cadence remains 30 seconds for connectivity.

D1 presence persistence is coalesced to:
- at most once per 120 seconds; or
- immediately when relevant device metadata changes.

The non-Event-V2 online grace is 240 seconds, preserving online semantics while
reducing D1 write amplification.

## Legacy Agent boundary

Agent 0.3.40 still includes the historical activity_snapshots field in its
heartbeat request. The new Worker ignores that field and never persists it.

Agent 0.3.41 source already removes the field at the origin. Its rollout remains
blocked only on completing the governed release-signature chain. Do not deploy
an unsigned Agent release.

## Existing D1 legacy data

Read-only inventory before purge:
- device rows with legacy activity snapshots: 2
- SLO state rows: 1
- SLO incident rows: 1

Prepared cleanup:
- apps/commander/scripts/commander_purge_product_diagnostics.py

The purge is dry-run by default and requires an explicit confirmation string.
It is intentionally not executed while D1 write enforcement is active.

## Auth recovery hardening

D1 write-limit recovery now requires the explicit error text
"daily row write limit"; generic SQLite/D1 code 7500 alone is not sufficient,
because Cloudflare also uses code 7500 for unrelated SQLite failures.

## Gates

- validate_product_boundary.py
- validate_preprod_readiness.py
- validate_local_activity_store.py
- validate_prod_static.py

COMMANDER_PUBLIC_PRODUCT=MCP_BRIDGE
COMMANDER_INTERNAL_CONTROL_PLANE=SEPARATE_WORKSTREAM
PUBLIC_INTERNAL_DIAGNOSTICS=ABSENT
PUBLIC_SLO_CRON=DISABLED
CLOUD_ACTIVITY_DETAIL_PERSISTENCE=DISABLED
HEARTBEAT_PERSIST_SECONDS=120
DEVICE_ONLINE_GRACE_SECONDS=240
LEGACY_AGENT_DETAIL_REJECTED_BY_CLOUD=TRUE
AGENT_ORIGIN_DETAIL_UPLOAD=PENDING_SIGNED_0_3_41
LEGACY_D1_DIAGNOSTIC_PURGE=PENDING_WRITE_PLANE_RECOVERY
