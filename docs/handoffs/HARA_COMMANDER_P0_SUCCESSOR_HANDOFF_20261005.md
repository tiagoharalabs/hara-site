# H.A.R.A. Commander — P0 successor handoff

Date: 2026-10-05
Canonical branch: `local/commander-openai-desktop-parity-20261004`
Canonical base before this handoff commit: `6bc9e60a0de3624d6765a5b83b1393d69a4d7508`

## Authoritative published refs

Canonical:
- branch: `local/commander-openai-desktop-parity-20261004`
- pre-handoff HEAD: `6bc9e60a0de3624d6765a5b83b1393d69a4d7508`
- local gateway and GitHub matched before the handoff edit.

Durable Object capacity candidate:
- branch: `local/commander-do-capacity-20261005`
- HEAD: `5c06765c16b3427680a01998602a4a87958d92f9`
- local gateway: published
- GitHub: published

Windows starter published branch:
- branch: `local/commander-windows-starter-20261005`
- HEAD: `73bbbe36d833aa0b6a0ab03704645425a2812efe`
- local gateway: published
- GitHub: published
- Windows implementation/fix is also already integrated into canonical history as `536d544`, `94d5176`, with status doc `debf2f9`.

Key canonical P0 commits:
- `d91fb60` — live multitenant DEV probe
- `b28db48` — fresh-customer DEV acceptance probe
- `94d5176` — Windows 0.3.32 real-self-test fix
- `feec164` — strict-rate-limit DO outage resilience
- `6bc9e60` — PROD login recovery evidence

## Current product truth

### PROD login

CLOSED_PASS.

`feec164` keeps the fast Cloudflare rate-limit layer mandatory and lets interactive paths survive only a strict Durable Object outage.

PROD proof:
- `/auth/login` -> 302 HARA Identity
- invalid internal MCP auth -> 401
- PROD fail-closed -> PASS
- PROD deployment/readback -> PASS

Do not remove the fast-layer mandatory guard.

### Fresh customer

The old `BLOCKED_DO_CAPACITY` status is superseded.

After `feec164`, DEV fresh-customer acceptance progressed through:
- fresh identity/tenant/pairing
- normal enrollment PASS
- Simple MCP tool count = 24
- public `hara.*` prefix absent
- zero-relay local MCP PASS
- filesystem acceptance PASS

Remaining issue:
- process assertion/result-shape mismatch in the fresh-customer probe
- then Activity/receipt/cloud Usage completion.

Canonical probe:
`apps/commander/scripts/commander_fresh_customer_dev_acceptance.py`

### Multitenant live isolation

Already live-proven:
- tenant A/B enumeration isolated
- cross-tenant enqueue denied
- caller-supplied tenant override absent
- cross-tenant call-status denied
- own call-status PASS
- cross-tenant receipt target denied
- fixture cleanup PASS

Still requires a clean rerun for:
- portal select
- portal revoke
- independent TenantQuota namespaces

Canonical probe:
`apps/commander/scripts/commander_multitenant_live_dev_probe.py`

### Windows

Agent 0.3.31 had a real PowerShell definition-order defect:
`Get-ApprovalMode` was referenced before declaration during `--self-test`.

Fixed release:
- Agent: 0.3.32
- real Windows VM SHA validation: PASS
- real Windows self-test exit 0
- operator session gate PASS
- console sanitization PASS
- starter read PASS
- five-tool bridge PASS
- arbitrary function DENIED
- Agent self-test PASS

Real canary host:
- libvirt domain: `commander-win11`
- host: nucleo-a
- VM running
- QEMU Guest Agent available
- `guest-exec` available
- guest DEV health PASS

PROD D1 still has stale Windows enrollment:
- `HARA_WIN11`
- Agent 0.3.14
- ACTIVE
- ASK_EVERY_ACTION
- last heartbeat 2026-10-03T23:02:28.763Z

Remaining Windows P0:
- isolated DEV enrollment/data-plane
- Simple MCP write/read/process/receipt proof.

The administrative connector blocked automated guest enrollment/device-token handling. No bypass was attempted. The temporary DEV fixture and guest root were cleaned completely.

### Durable Object capacity

Canonical `feec164` fixes availability when only the strict rate-limit DO is unavailable.

Separate TenantQuota source optimization is published at:
`local/commander-do-capacity-20261005@5c06765c16b3427680a01998602a4a87958d92f9`

That candidate adds:
- `idx_request_state_expiry(state, updated_at_utc)`
- persisted `period_usage(period_key, consumed_units)`
- versioned one-time aggregate backfill
- SQLite triggers for insert/update/delete accounting
- hot `TenantQuota.status()` O(1) lookup
- no hot-path `SUM(units)`

Regression after rebasing on canonical `6bc9e60`:
- storage efficiency P0.2 PASS
- quota TTL PASS
- Event V2 quota source probe PASS
- multitenant source model PASS
- fresh-customer source validation PASS
- strict-rate-limit resilience PASS
- full E2E harness PASS

No DO-capacity candidate has been promoted to PROD.

## Successor execution order

1. **Start from a clean worktree.**
   Fetch canonical + `local/commander-do-capacity-20261005`.
   Do not continue from a stale/dirty worktree.

2. **Integrate DO candidate into a temporary DEV candidate.**
   Merge/cherry-pick `5c06765` on current canonical.
   Re-run:
   - `validate_tenant_quota_storage_efficiency.py`
   - `validate_quota_reservation_ttl.py`
   - `commander_event_v2_dev_quota_probe.py --check`
   - `validate_rate_limit_resilience.py`
   - `test_security_rate_limit.mjs`
   - `validate_multitenant_isolation.py`
   - `validate_fresh_customer_acceptance.py`
   - `validate_e2e_harness.py`

3. **Deploy DO candidate to DEV only.**
   No PROD promotion before live proof.

4. **Rerun live multitenant probe.**
   Require:
   - select cross-tenant DENIED with A selection unchanged
   - revoke cross-tenant DENIED with B device ACTIVE
   - tenant A/B independent quota reserve behavior
   - fixture cleanup PASS.

5. **Rerun fresh-customer probe.**
   It should already pass enrollment under `feec164`.
   Fix/normalize only the process result-shape assertion if still failing.
   Require full filesystem/process/Activity/receipt cleanup PASS.

6. **Finish Windows data-plane.**
   Use `commander-win11`.
   Use an allowed administrative/human enrollment path.
   Preserve the existing PROD Scheduled Task/config.
   Prove isolated DEV:
   - write
   - read
   - list/search/info
   - process.run
   - receipt
   - cleanup.

7. **Commercial self-service remains human-config gated.**
   Do not invent Stripe secret, webhook secret, Price ID, price, quota or SLA.
   After real config, prove checkout -> webhook -> STANDARD entitlement -> portal -> cancel/update lifecycle.

8. **Only after the above close public-beta P0.**
   Then continue SLO, support bundle, cost analytics and GA gates.

## Do not repeat / do not regress

- Do not use Windows 0.3.31.
- Do not remove or weaken fast-layer rate limiting.
- Do not interpret a DO infrastructure 5xx as proof of tenant-isolation failure or success.
- Do not expose pairing/device/MCP tokens in logs.
- Do not bypass connector security restrictions around credentials.
- Do not deploy the TenantQuota optimization directly to PROD before DEV live probes.
- Do not overwrite the existing PROD Windows enrollment/task during DEV canary work.
- Do not invent commercial billing values.
- Do not use the dirty legacy `/home/sartorius/hara-site` checkout as authoritative continuation.

## Worktree caution

At handoff time, `/home/sartorius/hara-worktrees/commander-sellability-20261004` contains an uncommitted alternate TenantQuota optimization (`period_totals` design) authored by another concurrent front.

It is not canonical and is not the published DO-capacity candidate.

Do not commit or discard it blindly. Compare it deliberately against `local/commander-do-capacity-20261005@5c06765` if that front needs reconciliation.

Preferred successor sources:
- canonical branch for product truth
- DO-capacity branch for the tested quota optimization
- canonical Windows 0.3.32 history for Windows source
