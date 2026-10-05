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
| Live multitenant isolation | PARTIAL LIVE PASS: enumerate A/B, cross-tenant enqueue, call-status, receipt-target and caller tenant override proved; portal select/revoke + quota currently blocked by Durable Object capacity | Restore/upgrade DO capacity, rerun canonical live probe, require select/revoke state-bound DENY + independent tenant quota reservations | sellability |
| Fresh customer acceptance | Components exist (3-step onboarding, quickstart, Simple MCP, persistent trust) | New identity -> new tenant/invite -> pair fresh device -> connect Simple MCP -> read -> write -> process -> Usage visible, with no maintainer repair | sellability / beta-sales |
| Windows current live canary | Starter branch exists with filesystem/process starter toolset; not yet reconciled with current canonical head | Rebase/reconcile `commander-windows-starter-20261005`, run full regression, upgrade/enroll fresh Windows host, prove read/write/process/receipt through Simple MCP | windows-starter |
| Self-serve Standard checkout | Billing source/schema/webhook/idempotency/entitlement bridge PASS; Pro Beta access requests are now captured in-product; no price invented | Configure Stripe secret + webhook secret + Standard Price ID; prove checkout -> webhook -> STANDARD entitlement -> portal -> cancel/update lifecycle | beta-sales / human commercial config |
| Durable Object capacity | DEV portal mutations return `STRICT_RATE_LIMIT_CHECK_FAILED`; TenantQuota authorize returns 500; H.A.R.A. execution path also observed Cloudflare free-tier rows-read exhaustion | Remove free-tier capacity blocker (account capacity and/or measured DO cost), then rerun multitenant + normal H.A.R.A. canaries | sellability / infra |

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
