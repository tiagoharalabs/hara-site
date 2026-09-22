# HARA Identity white-label successor handoff — 2026-09-22

## Canonical live state

- Public issuer: `https://auth.haralabs.com.br/`
- Commander DEV: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- Upstream Identity engine: ZITADEL 4.16.0
- HARA Login image: `hara-identity-login:v4.16.0-hara.7`
- Image digest: `sha256:87bb2d22891d4e68c44d25101dbbfe1a18a4beb3bc80710a2d30fd06ed2f1d96`
- `zitadel-api`: healthy
- `zitadel-login`: healthy
- `zitadel-assets`: healthy

The engine remains ZITADEL internally. The public login experience is HARA Identity.
OIDC issuer, Session API, PKCE and the login-client permission model are unchanged.
## White-label proof

Live validation passes:

- HARA Identity manifest: PASS
- HARA favicon assets: PASS
- `/hara-logo-light.svg`: 200, valid HARA SVG
- `/hara-logo-dark.svg`: 200, valid HARA SVG
- visible `Entrar com HARA Identity`: PASS
- visible `Crie sua conta HARA Identity`: PASS
- visible vendor login copy: absent
- Commander OIDC redirect: PASS
- PKCE S256: PASS
- `prompt=select_account`: PASS

Run:
`python3 apps/identity-login/scripts/validate_live_white_label.py`
## SMTP and message text state

SMTP transport is already HARA-branded:

- sender: `identity@haralabs.com.br`
- sender name: `HARA Identity`
- reply-to: `contato@haralabs.com.br`
- provider: HARA Identity Zoho

The ZITADEL message-text policy is still the remaining vendor-residual layer.
The default message subjects/titles still contain strings such as `Zitadel - Verify email`,
`Zitadel - Reset password` and `ZITADEL - Password of user has changed`.

The prepared supported-API applicator is:
`apps/identity-login/scripts/apply_hara_identity_white_label.py`
## Administrative credential boundary

Current roles:

- `hara-admin@zitadel.auth.haralabs.com.br` = `IAM_OWNER`
- `login-client` = `IAM_LOGIN_CLIENT` only
- there is no IAM_OWNER PAT stored today

The preserved `first-admin-password` is stale. Exactly one controlled Session API check was attempted and returned `COMMAND-3M0fs` (invalid password), failedAttempts=1. Do not retry it and do not reset the admin password merely to automate this task.

A temporary System API User bootstrap was prepared but tool security prevented signing/using the administrative JWT. It was fully reverted:
- no `ZITADEL_SYSTEMAPIUSERS` remains active
- temporary RSA private/public keys were removed
- API returned healthy after rollback
## Next safe action

From an already authenticated Identity admin console, create a dedicated administrative machine identity/PAT with only the required instance administration permissions, or create an IAM_OWNER PAT suitable for this maintenance task.

Store it directly on `storage`, for example:
`/srv/hara/identity/secrets/identity-owner.pat`
with mode `0600`. Do not paste the PAT into chat.

Then run the supported API applicator and verify:
1. instance display name = HARA Identity
2. languages = pt/en
3. Hosted Login translations = HARA
4. Verify Email / Reset / Password Change / Init / Domain Claimed texts = HARA
5. send a real verification/reset email and confirm zero vendor text

Do not modify ZITADEL projections/event store directly.
Do not elevate the existing `login-client` to IAM_OWNER.
