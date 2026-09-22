# HARA Commander DEV — E2E current — 2026-09-22

## Runtime

- URL: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- HARA Identity issuer: `https://auth.haralabs.com.br/`
- Worker version: `f3956f3e-abb0-4868-906f-ead85f6eff18`
- branch: `issue29-commander-dev-v3-auth`
- product implementation commit: `39b870e28bad52a5e8d53ef23bcf22d53c3fd568`

## First customer / owner E2E

- email: `tiago.sartori@haralabs.com.br`
- real OIDC subject: `391814630923567107`
- Commander subject: `HARA-SUBJECT-DEMO-0001`
- invite: CLAIMED
- user: ACTIVE / OWNER
- tenant: `HARA Labs`
- plan: `STANDARD`
- entitlement: ACTIVE
- unit limit: `10000`
- login E2E: PASS

## OpenAI reviewer E2E

- email: `openai-reviewer@haralabs.com.br`
- Identity user id / real OIDC subject: `391922351219933187`
- Commander subject: `HARA-SUBJECT-REVIEW-0001`
- tenant: `HARA Review`
- role: `REVIEWER`
- plan: `REVIEW`
- entitlement: ACTIVE
- unit limit: `100`
- invite: CLAIMED
- session: ACTIVE / not revoked
- browser login E2E: PASS

## Product plane

- MCP Product discovery: PASS
- reserve/release: PASS
- released request terminal behavior: PASS
- commit: PASS
- commit idempotency: PASS
- token exposed: FALSE
- secondary identity binding path: implemented
- bootstrap seed: non-destructive after real identity claim
- validator rerun-safe: PASS

## Portal/UI

- HARA Site V13 light/dark alignment: PASS
- authenticated topbar: PASS
- real user/role binding: PASS
- Security real subject/tenant/role binding: PASS
- demo activity removed: PASS
- real activity ledger source: PASS
- fake connection count removed: PASS
- zero-use reviewer empty state: PASS

## Remote validation

- `PRODUCTION_LIKE_PUBLIC_UI=PASS`
- `PORTAL_AUTH_CONFIG=PASS`
- `PRODUCTION_LIKE_TENANT_NAME=PASS`
- `REMOTE_DEV_HEALTH=PASS`
- `REMOTE_DEV_ACCESS_TOKEN=PASS`
- `REMOTE_DEV_D1_READ=PASS`
- `REMOTE_DEV_QUOTA_DO_SQLITE=PASS`
- `REMOTE_DEV_CONCURRENCY=PASS`
- `REMOTE_DEV_QUOTA_EXCEEDED=PASS`
- `REMOTE_DEV_RELEASE=PASS`
- `REMOTE_DEV_COMMIT_IDEMPOTENCY=PASS`
- `REMOTE_DEV_RECEIPT_CONFLICT=PASS`
- `REMOTE_DEV_VALIDATOR_RERUN_SAFE=PASS`
- `AUTHENTICATED_TOPBAR_STATE=PASS`
- `REAL_ACTIVITY_LEDGER_UI=PASS`
- `PRODUCTION_MUTATION=FALSE`

## Next product test

1. Refresh the reviewer dashboard and visually confirm the authenticated topbar.
2. Navigate Dashboard → Usage → Plan → Connections → Security and confirm identity/session state persists.
3. Confirm reviewer shows 0/100 and no fake receipts/connections.
4. Click `Sair` exactly once.
5. Prove D1 `revoked_at_utc` is non-null.

After that, move to the real OpenAI draft/tool-scan flow.
