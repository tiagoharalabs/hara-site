# H.A.R.A. Commander — P0 Live Multitenant Isolation

Date: 2026-10-05
Environment: DEV only
Canonical branch at probe start: `85db66dc35bcaec92e6a9aba4655123225ebffa4`

## Stage A — DEV precondition

A false DEV readback drift was found: the live Worker had secret binding `HARA_IDENTITY_MCP_DCR_CLIENT_ID`, but `commander_dev_deployment_readback.py` did not include it in `REQUIRED_SECRETS`.

Fix:
- added the binding name to the expected DEV secret set;
- no secret value was read or printed;
- no secret was rotated in this stage.

Readback after correction:
- `COMMANDER_DEV_CONFIG_LIVE=PASS`
- `COMMANDER_DEV_D1_LIVE=DEV_ONLY`
- `COMMANDER_DEV_SECRETS_LIVE=PASS`
- `COMMANDER_DEV_DEVICE_CHANNEL_LIVE=PASS`
- `COMMANDER_DEV_HEALTH=PASS`
- OIDC redirect / PKCE / transaction cookie / account switch live checks PASS.

Commit: `85db66dc35bcaec92e6a9aba4655123225ebffa4`

## Stage B — current DEV baseline

Before live fixtures:
- critical Simple MCP/device/privacy/multitenant-source regressions PASS;
- DEV D1 backup created;
- migrations `0014` through `0020` applied;
- no DEV migrations pending;
- canonical Worker deployed to DEV.

DEV D1 backup:
- file: `/tmp/hara-commander-dev-before-mt-20261005T043141Z.sql`
- SHA-256: `c35be81c24833ec6f041b13e51eadf335ae6c601a18fb01c52dc8492ee5cad18`

DEV Worker:
- version: `221befc9-ebce-4dff-9ea1-9a6396121af4`

A DEV-only canary MCP token was provisioned/rotated using the canonical provisioner:
- file mode: `0600`
- value exposed: FALSE
- PROD secret/config untouched.

## Stage C — live A/B isolation probe

Reusable probe:
`apps/commander/scripts/commander_multitenant_live_dev_probe.py`

Properties:
- DEV-only;
- creates two random tenant/user/device/session/identity fixtures;
- uses real HTTPS portal/internal routes;
- uses session hashes exactly as production auth (SHA-256 base64url);
- does not print session/canary tokens;
- releases quota reservations when created;
- deletes all fixtures in `finally`;
- verifies cleanup count is zero.

### Live PASS evidence

- tenant A device enumeration: PASS; no tenant B device visible;
- tenant B device enumeration: PASS; no tenant A device visible;
- cross-tenant device enqueue: HTTP 404 / no call inserted;
- caller-supplied `tenant_id` override: ABSENT; successful A call persisted under tenant A;
- cross-tenant call-status read: HTTP 404;
- own call-status read: PASS;
- cross-tenant receipt-target request: HTTP 404 / no call inserted;
- fixture cleanup: PASS after every run.

### Capacity-blocked gates

Portal mutation path:
- cross-tenant select: HTTP 503;
- code: `STRICT_RATE_LIMIT_CHECK_FAILED`;
- tenant A selection remained unchanged;
- no data leak/mutation occurred, but tenant-isolation logic was not reached far enough to count as live DENY proof.

Portal revoke path:
- cross-tenant revoke: HTTP 503;
- code: `STRICT_RATE_LIMIT_CHECK_FAILED`;
- tenant B device remained ACTIVE;
- no data leak/mutation occurred, but tenant-isolation logic was not reached far enough to count as live DENY proof.

Tenant quota path:
- `/api/internal/mcp/authorize` for tenant A: HTTP 500 / `INTERNAL_ERROR`;
- quota namespace proof could not execute.

Correlated infrastructure observation:
- during this same continuation, the H.A.R.A. Commander execution path returned Cloudflare error `Exceeded_allowed_rows_read_in_Durable_Objects_free_tier_`.

Conclusion:
`MULTITENANT_ISOLATION_LIVE_DEV=BLOCKED_DO_CAPACITY`

This is not classified as an isolation failure. The state-bound tests that reached tenant-scoped device/call logic passed. Public-beta P0 remains open until Durable Object capacity is restored/upgraded and the same probe closes select/revoke/quota as live PASS.

## Next action

1. Resolve/upgrade Durable Object capacity or account plan and measure actual DO consumption.
2. Re-run this exact probe without changing expected tenant behavior.
3. Require:
   - portal select cross-tenant DENIED with state unchanged;
   - portal revoke cross-tenant DENIED with state unchanged;
   - same `request_id` independently reservable under tenant A and tenant B quota namespaces;
   - cleanup PASS.
4. Only then change backlog state to `MULTITENANT_ISOLATION_LIVE_DEV=PASS`.

## Continuation - reconciled DO candidate on current canonical

Candidate source:
- base f7f7d37c880230e526bc1e12c1ea78a7214ea7fb
- TenantQuota candidate 5c06765c16b3427680a01998602a4a87958d92f9
- reconciled successor HEAD before acceptance fix/docs 4157dff806514e9192bcfcc7d4fd5d2f5c17de69

Source/regression battery after reconciliation:
- TenantQuota storage efficiency PASS
- quota reservation TTL PASS
- Event V2 quota source probe PASS
- rate-limit resilience PASS
- SecurityRateLimit test PASS
- multitenant source model PASS
- fresh-customer source validation PASS
- full E2E harness PASS

DEV-only deployment:
- first candidate Worker 043d155b-baf7-4556-a663-b7871fd696d2
- readback PASS
- previous rollback version 942f32e3-cad0-41b1-ba02-036ba5f2457e
- canonical DEV canary MCP token was reprovisioned without exposing its value
- resulting Worker version 122cd8ce-8abc-4b7f-9d06-5fe2340245ce
- rollback version after secret update 043d155b-baf7-4556-a663-b7871fd696d2

Latest live probe:
- tenant A/B enumeration PASS
- cross-tenant select HTTP 404 DEVICE_NOT_FOUND, selection unchanged: DENIED
- cross-tenant revoke HTTP 404 DEVICE_NOT_FOUND, target device remained ACTIVE: DENIED
- cross-tenant enqueue HTTP 404 and no call inserted: DENIED
- caller-supplied tenant override ABSENT
- cross-tenant call status HTTP 404: DENIED
- same-tenant call status PASS
- cross-tenant receipt target HTTP 404: DENIED
- fixture cleanup PASS

Therefore the portal-mutation gates are now live-proven:
- MULTITENANT_LIVE_DEVICE_SELECTION=DENIED
- MULTITENANT_LIVE_DEVICE_REVOKE=DENIED

The remaining multitenant blocker is specifically the independent TenantQuota namespace proof:
- tenant A internal MCP authorize: HTTP 500 INTERNAL_ERROR
- MULTITENANT_LIVE_QUOTA_NAMESPACE=BLOCKED_DO_CAPACITY

A filtered DEV Worker tail captured the platform exception directly in both SecurityRateLimit and TenantQuota Durable Objects:
Exceeded allowed rows read in Durable Objects free tier.

Current state:
- MULTITENANT_SELECT_REVOKE_LIVE=CLOSED_PASS
- MULTITENANT_TENANT_QUOTA_NAMESPACE=PENDING_CAPACITY_RESET_OR_UPGRADE
- MULTITENANT_ISOLATION_LIVE_DEV=BLOCKED_DO_CAPACITY

Do not rerun the quota proof repeatedly while the daily account budget is exhausted. Re-run the unchanged canonical probe after capacity resets or the account tier is upgraded.
