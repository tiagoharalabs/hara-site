# H.A.R.A. Commander — Sellability Backlog

Date: 2026-10-05
Canonical branch: `local/commander-openai-desktop-parity-20261004`
Baseline at creation: `53d53c3b33028712d70ecfb3b18aef9858205210`

## Launch interpretation

- **Paid beta / invite / Linux:** READY.
- **Public beta:** PENDING Windows production re-enrollment/current data-plane canary; live multitenant isolation and fresh local customer acceptance are CLOSED_PASS.
- **Self-serve paid:** PENDING Stripe runtime secrets + Price IDs + first real checkout lifecycle.
- **General availability:** PENDING public-beta/clean-lifecycle gates plus live external alert destination, cost analytics and commercial billing activation; internal SLO/support maturity and external-alert source/preprod transport are CLOSED_PASS.

## P0 — close before public beta

| Gate | Current truth | Next proof / delivery | Parallel ownership |
| --- | --- | --- | --- |
| Live multitenant isolation | CLOSED_PASS on current DEV O(1): A/B enumeration, cross-tenant select/revoke/enqueue/call-status/receipt deny, tenant override absent, independent quota A/B HTTP 200 ALLOW, tenant derivation PASS, cleanup PASS | Preserve as regression gate; no remaining DO-capacity blocker for this proof | sellability / do-capacity |
| Fresh customer acceptance | LOCAL PATH CLOSED_PASS: DEV enrollment, 24 Simple MCP tools, no public hara.*, zero relay, filesystem, governed process, Activity and privacy-safe receipts PASS. Signed local-budget canary separately proves metered cloud allocation + local debit/reconcile on fresh tenant | Preserve both harnesses as release gates; Windows remains separate | sellability / beta-sales |
| Windows current live canary | Source/regression PASS on Agent 0.3.32. Real VM `commander-win11` is running and reachable through QEMU Guest Agent; published SHA + real Windows self-test PASS. PROD `HARA_WIN11` remains stale 0.3.14 | Finish isolated DEV enrollment/data-plane through an allowed administrative/human channel, then prove Simple MCP write/read/process/receipt; do not bypass connector credential restrictions | windows-starter |
| Self-serve Pro checkout | COMMERCIAL TERMS PROD LIVE: Free 10.000 calls/month with monthly reset; Pro/Standard R$ 80/month unlimited. PROD D1 + public UI aligned; fail-closed PASS. Stripe checkout remains disabled because runtime secret/webhook/Standard Price ID are pending | Create/configure the real Stripe Standard recurring Price at exactly BRL 80/month, configure secret + webhook, then prove checkout -> signed webhook -> STANDARD entitlement -> portal -> failure/recovery -> cancellation | beta-sales / human Stripe config |
| Durable Object capacity | CLOSED_PASS: TenantQuota O(1) is live in PROD Worker 7491e096; expiry index + period_usage aggregate + atomic triggers; DEV multitenant independent quota namespace PASS; signed local-budget canary PASS; PROD fail-closed/health PASS | Monitor first natural Free/local-budget usage and collect cost analytics when read-only token is available | do-capacity / infra |

## P1 — close for reliable scale

| Gate | Current truth | Next proof / delivery |
| --- | --- | --- |
| SLO | INTERNAL_BETA_V1 live. Persistent incidents + 2-breach/2-recovery hysteresis + ack/escalation L1/L2/L3 are live in PROD. External notification source/preprod transport is now CLOSED_PASS with durable idempotent outbox, OPENED/ESCALATED/RESOLVED events, HTTPS-only delivery, HMAC-SHA256 signing, retry and privacy-bounded aggregate payload. Agent/Worker 0.3.40 separates raw tool outcome from service availability and is live in PROD at `c8cfc1d1-592c-4d71-8788-d237e07828c6` | Select an explicit HTTPS destination + signing secret, run DEV receiver-side signature canary, then promote the transport to PROD; thresholds remain internal, not contractual SLA |
| Cost model | Local-first unit economics CLOSED_PASS: full Free 10k old quota plane 20,000 RPCs vs <=100 block allocations (99.5% reduction); 100-user and 1,000-user rungs modeled. USD intentionally unclaimed | Obtain read-only Cloudflare Analytics and measure Worker CPU, DO requests/duration, D1 rows/egress on 100 -> 1,000 user campaign |
| Support bundle | support-report.v2 live on Linux 0.3.38 plus tenant-scoped support-plane live in PROD: OWNER/ADMIN submit/list/delete, server allowlist sanitization, 16KiB cap, 30d retention, cross-tenant deny, no raw command/payload/result | Add optional external ticket/export integration only if needed; current in-product retention/support evidence is closed |
| Clean Linux acceptance | Hermetic clean-home lifecycle PASS with official installer + local HTTP backend: install, support v2, update/rollback-ready, revoked credential re-enroll, uninstall, token non-exposure and clean home | Repeat once on a truly fresh external VM before GA; lifecycle logic itself is now a permanent preprod gate |
| Bootstrap trust maturity | Release/update independent RS256 manifest trust anchor CLOSED_PASS in PROD. Linux now also has a CLOSED_PASS dual-origin bootstrap path: immutable GitHub verifier compares the live Commander installer and release key byte-for-byte against a GitHub copy pinned to canonical commit `35d9a5e`; live verify-only and tamper-deny PASS. Windows initial bootstrap remains canonical HTTPS only | Extend the same dual-origin bootstrap pattern to Windows before GA if the threat model requires symmetric first-install trust; Linux no longer depends on a single web origin for the verified path |
| MCP client interoperability | Simple MCP V1.1 source/preprod CLOSED_PASS across 2025-06-18, 2025-11-25 and 2026-07-28 with the same 24 vendor-neutral tools. RFC 8414 is PROD CLOSED_PASS. Guarded DCR is now live behind HARA admission/rate guards; registration_endpoint is advertised; strict generic auto OAuth discovery PASS; disposable register/read/delete lifecycle PASS with no client secret and no residual client. CIMD remains deliberately not advertised. | Run the real VS Code / Claude Code / Cursor / MCP Inspector smoke matrix. Core protocol + generic OAuth onboarding no longer need architecture work before those client tests. |

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
