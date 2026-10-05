# H.A.R.A. Commander — Sellability Backlog

Date: 2026-10-05
Canonical branch: `local/commander-openai-desktop-parity-20261004`
Baseline at creation: `53d53c3b33028712d70ecfb3b18aef9858205210`

## Launch interpretation

- **Paid beta / invite / Linux:** READY.
- **Public beta:** PENDING P0 live-isolation + fresh-customer acceptance + Windows current-canary policy decision.
- **Self-serve paid:** PENDING Stripe runtime secrets + Price IDs + first real checkout lifecycle.
- **General availability:** PENDING public-beta gates plus SLO/support maturity.

## P0 — close before public beta

| Gate | Current truth | Next proof / delivery | Parallel ownership |
| --- | --- | --- | --- |
| Live multitenant isolation | PARTIAL LIVE PASS: enumerate A/B, cross-tenant enqueue, call-status, receipt-target and caller tenant override proved. `feec164` removed strict-rate-limit DO outages from interactive availability, but select/revoke/quota still need a clean rerun after TenantQuota optimization | Integrate/test DEV candidate `local/commander-do-capacity-20261005` @ `5c06765`; rerun canonical multitenant probe and require select/revoke DENY + independent tenant quota reservations | sellability / do-capacity |
| Fresh customer acceptance | ADVANCED AFTER `feec164`: DEV enrollment PASS; Simple MCP 24 tools; no public `hara.*`; zero relay PASS; filesystem acceptance PASS. Remaining probe failure is process-result shape/assertion, then Activity/receipts/cloud Usage | Fix/normalize process assertion/result shape in canonical fresh-customer probe; rerun to full PASS; then exercise remote Simple MCP + cloud Usage | sellability / beta-sales |
| Windows current live canary | Source/regression PASS on Agent 0.3.32. Real VM `commander-win11` is running and reachable through QEMU Guest Agent; published SHA + real Windows self-test PASS. PROD `HARA_WIN11` remains stale 0.3.14 | Finish isolated DEV enrollment/data-plane through an allowed administrative/human channel, then prove Simple MCP write/read/process/receipt; do not bypass connector credential restrictions | windows-starter |
| Self-serve Standard checkout | Billing source/schema/webhook/idempotency/entitlement bridge PASS; Pro Beta access requests are now captured in-product; no price invented | Configure Stripe secret + webhook secret + Standard Price ID; prove checkout -> webhook -> STANDARD entitlement -> portal -> cancel/update lifecycle | beta-sales / human commercial config |
| Durable Object capacity | Strict-rate-limit outage resilience is already canonical (`feec164`). Separate TenantQuota source candidate is published at `local/commander-do-capacity-20261005` @ `5c06765`: indexed expiry + persisted period aggregate + O(1) status, TTL/idempotency/E2E PASS | DEV-only deploy of `5c06765`, rerun multitenant + fresh-customer probes, measure DO behavior; merge/promote only after DEV proof | do-capacity / infra |

## P1 — close for reliable scale

| Gate | Current truth | Next proof / delivery |
| --- | --- | --- |
| SLO | Activity already measures queue/execution/total latency and success | Define first customer SLO, publish internal p50/p95/p99 + availability gate, alert on violations |
| Cost model | Transaction accounting exists; human 10k model still marks D1 duration cost PENDING live analytics | Run controlled 10k workload, measure Worker/D1/DO cost and calls-per-user economics |
| Support bundle | Device doctor/health/readiness exist | One sanitized bundle with version, health, last error classes, transport, receipt IDs and no command/payload content |
| Clean Linux acceptance | Linux live proven on existing hosts | Fresh VM install/update/uninstall/re-enroll acceptance with no developer state present |
| Bootstrap trust maturity | HTTPS origin + manifest + SHA + version + self-test + runtime attestation PASS | Add an independent release trust anchor/signature when moving beyond beta |

## Canonical product rules

1. Keep the customer surface simple. Improve capability inside existing Simple MCP commands before adding public names.
2. Simple MCP remains the default generic surface; governed H.A.R.A. details stay internal.
3. No persistent plaintext command history. Cloud raw payload is transient transport only; terminal state is redacted/hash-bound.
4. `PERSISTENT_TRUSTED` may authorize governed operations without repeated prompts; grants/tool schemas/receipts/rollback remain enforced.
5. Do not invent commercial price, quota, SLA or Stripe credentials in source.
6. Do not use stale Commander worktrees as continuation points. Sellability continuation starts from `commander-sellability-20261004` after Git verification.
7. Do not duplicate Windows work already present in `commander-windows-starter-20261005`.

## Recently closed

- PROD login regression CLOSED_PASS: /auth/login restored from 503 STRICT_RATE_LIMIT_CHECK_FAILED to 302 HARA Identity redirect via commit feec164; fast rate-limit remains mandatory and invalid MCP auth returns 401 again.

- Worktree hygiene: 124 prunable registrations removed; orphan HEAD preserved under local quarantine ref.
- Standard/Pro Beta catalog reconciled to canonical migration `0019_standard_beta_plan.sql`.
- Pro Beta access request flow delivered through canonical migration `0020_beta_access_requests.sql` and portal API.
- Full migration replay through 0019 PASS.
- Linux Agent 0.3.30 live with `PERSISTENT_TRUSTED`.
- Simple MCP 24-command surface live.
- Multi-device Linux proof on nucleo-a + sentinela-d.
- Device self-service, quickstart, customer-visible service health and paid-beta invite fallback delivered.
- DEV aligned through migration `0020` and current canonical Worker; DEV readback PASS after secret-binding validator correction.
- Canonical live multitenant probe added with automatic fixture cleanup; partial live isolation evidence captured.
