# HARA Commander DEV — E2E current — 2026-09-22

## Human identity E2E

- Commander DEV: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- HARA Identity issuer: `https://auth.haralabs.com.br/`
- Human identity: `tiago.sartori@haralabs.com.br`
- Real OIDC subject: `391814630923567107`
- Invite `HARA-INVITE-OWNER-DEV-0001`: `CLAIMED`
- D1 subject row retained: `HARA-SUBJECT-DEMO-0001`
- User state: `ACTIVE`
- Role: `OWNER`
- Portal session: active, not revoked
- Tenant: `HARA Labs`
- Entitlement: `ACTIVE`
- Plan: `STANDARD`
- Meter: `HARA_COMMANDER_GOVERNED_INVOKE`
- Period: `CALENDAR_MONTH`
- Unit limit: `10000`

The human login completed through HARA Identity and the Commander dashboard rendered the real user identity.

## Visual system alignment

Commander DEV now consumes the canonical HARA Site V13 theme behavior and palette from main:
- source commit: `5e2e04d` (`feat: add canonical HARA dark theme and visual system v1`)
- persistent key: `hara-theme`
- system preference fallback: `prefers-color-scheme`
- canonical light palette: navy/blue/green/gold from HARA Site
- canonical dark palette: `#061721 / #081c29 / #0a2231`
- theme toggle: moon / sun, same accessibility behavior as HARA Site
- sidebar width: `260px`
- sidebar primary navigation: `12px`
- workspace/sidebar labels increased for readability

## Runtime validation

Remote validation after deployment:
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
- `PRODUCTION_MUTATION=FALSE`

Cloudflare DEV version: `8c9443c0-6d8b-4994-93da-2c91ce907295`

## Remaining E2E closure

Keep the human portal session active until visual review is complete. Then perform one explicit logout and verify `portal_sessions.revoked_at_utc` becomes non-null.
