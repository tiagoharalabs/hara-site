# H.A.R.A. Commander — PROD Login Regression Recovery

Date: 2026-10-05
Canonical branch: `local/commander-openai-desktop-parity-20261004`

## Symptom

Clicking **Entrar** in the Commander portal returned the generic protected-access error screen instead of redirecting to HARA Identity.

Direct PROD probe before fix:

- `GET /auth/login?return_to=/#devices`
- HTTP: `503`
- code: `STRICT_RATE_LIMIT_CHECK_FAILED`

The request failed before OIDC redirect.

## Root cause

The visual **Acesso protegido** UX was introduced earlier and was not itself the failing component.

History:
- `f62fe1a...` introduced/reconciled the protected-access portal UX.
- `a3e2754...` added bounded brute-force rate limits using the fast Cloudflare rate-limit binding only.
- `462552b...` added a strict deterministic Durable Object rate-limit layer to the same login path.

When the `SecurityRateLimit` Durable Object exhausted/failed under current account capacity, `/auth/login` failed closed with HTTP 503 before `beginLogin()` could redirect to HARA Identity.

This correlated with the same Durable Object capacity symptoms observed by:
- live multitenant probe;
- fresh-customer enrollment probe;
- H.A.R.A. Commander execution path.

## Fix

Commit:
`feec1648965024a460a5663a90a9eff371f101b7`
`fix(commander): survive strict rate-limit DO outages`

Behavior:
- the fast Cloudflare rate-limit binding remains mandatory;
- if the fast layer denies/fails, the request still fails closed;
- if only the strict Durable Object layer is unavailable, interactive customer surfaces temporarily continue under the fast binding;
- strict denials still deny;
- no endpoint becomes un-rate-limited.

Applied to all six layered rate-limit call sites so invalid MCP auth also returns the intended auth denial instead of an infrastructure 503.

Regression markers:
- `COMMANDER_RATE_LIMIT_LAYERED_ENFORCEMENT=PASS`
- `COMMANDER_RATE_LIMIT_STRICT_OUTAGE_FALLBACK=FAST_LAYER_ONLY`
- `COMMANDER_RATE_LIMIT_FAST_LAYER_FAIL_CLOSED=PASS`
- `COMMANDER_RATE_LIMIT_FAIL_CLOSED=PASS`
- `COMMANDER_AUTH_RECOVERY_SOURCE_REGRESSION=PASS`

## DEV live proof

DEV Worker:
`942f32e3-cad0-41b1-ba02-036ba5f2457e`

After fix:
- `/auth/login` -> HTTP `302`;
- redirect target: `https://auth.haralabs.com.br/oauth/v2/authorize`;
- PKCE/state/nonce present;
- OIDC transaction cookie issued.

Fresh-customer probe also progressed past the previous enrollment blocker:
- identity/tenant: PASS;
- pairing/enrollment: PASS;
- Simple MCP tools: 24;
- public `hara.*` prefix: absent;
- local MCP zero relay: PASS;
- filesystem acceptance: PASS.

The remaining fresh-customer process assertion is a separate probe/result-shape issue and not a login/enrollment failure.

## PROD live proof

PROD Worker:
`3ddbc2c4-5f42-4320-adb3-4b1e90340219`

Deployment:
`1cd00afe-27b5-461a-bb40-65db434fe9bf`

Rollback:
`98d99914-7a4a-4c30-8ad5-12bd65c58d61`

After fix:
- `/auth/login` -> HTTP `302`;
- redirect target: HARA Identity;
- callback: `https://commander.haralabs.com.br/auth/callback`;
- invalid internal MCP auth -> `401 MCP_PRODUCT_ACCESS_DENIED`;
- `COMMANDER_PROD_FAIL_CLOSED=PASS`;
- deployment readback: PASS.

## Status

`COMMANDER_PROD_LOGIN_REGRESSION=CLOSED_PASS`

Durable Object capacity remains a separate P0 for multitenant/quota scale and should still be optimized/upgraded; this hotfix restores customer availability without removing the mandatory fast rate-limit layer.
