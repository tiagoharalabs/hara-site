# H.A.R.A. Commander — Auth / billing recovery when backend writes are unavailable

Date: 2026-10-06
State: SOURCE/PREPROD IMPLEMENTED

## Product invariant

Authentication is not workspace quota.

A user who successfully authenticates with HARA Identity must not be shown as
"logged out" merely because the Commander operational backend cannot persist
writes.

When the Worker detects Cloudflare D1 write-limit enforcement during login:

1. OIDC Authorization Code + PKCE still completes.
2. The login transaction falls back to a short-lived AES-GCM sealed cookie.
3. An existing HARA identity is resolved using read-only state.
4. Persistent portal-session creation is attempted.
5. If session persistence is rejected by D1 write-limit enforcement, the Worker
   issues a 30-minute encrypted recovery session.
6. Recovery session is authenticated but scoped:
   - workspace access: blocked;
   - device/control APIs: blocked;
   - billing/status: allowed;
   - billing checkout: allowed;
   - billing portal: allowed.
7. The UI routes the authenticated user to Plano e cobrança and shows an
   explicit backend/quota-degraded banner.

## Security boundary

- Recovery cookies are AES-GCM encrypted.
- Keys are domain-separated by purpose (OIDC_TX vs PORTAL_SESSION).
- Runtime secret source is AUTH_SESSION_RECOVERY_SECRET when configured, with
  AUTH_CLIENT_SECRET as the existing PROD fallback.
- OIDC state, PKCE verifier and nonce remain protected in the sealed cookie.
- Recovery sessions expire after 30 minutes.
- Recovery session cannot access normal workspace/device APIs.
- Logout clears recovery session without requiring a D1 write.

## D1 behavior

The fallback is only admitted for the explicit D1 row-write-limit condition,
including Cloudflare code 7500 / "daily row write limit" errors. Other database
or auth failures remain fail-closed.

## Billing boundary

Billing status and checkout paths remain available because they can operate on
D1 reads plus Stripe API calls. Stripe webhook persistence can still be delayed
while D1 writes are unavailable; entitlement synchronization remains
authoritative once the write plane recovers.

## Gates

- test_auth_degraded_recovery.mjs
- validate_auth_degraded_recovery.py
- validate_preprod_readiness.py

AUTH_PLANE_SEPARATED_FROM_WORKSPACE_WRITE_PLANE=IMPLEMENTED
DEGRADED_AUTH_SESSION_TTL_MINUTES=30
DEGRADED_WORKSPACE_ACCESS=BLOCKED
DEGRADED_BILLING_ACCESS=ALLOWED
D1_WRITE_LIMIT_LOGIN_FAILURE=RECOVERED
