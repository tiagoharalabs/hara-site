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

SMTP transport is HARA-branded:

- sender: `identity@haralabs.com.br`
- sender name: `HARA Identity`
- reply-to: `contato@haralabs.com.br`
- provider: HARA Identity Zoho

The supported API applicator completed successfully with an IAM_OWNER preflight.

Applied state:
- instance display name: `HARA Identity`
- default language: `pt`
- allowed languages: `pt,en`
- public organization registration: disabled
- Hosted Login translations: PT + EN
- Verify Email: PT + EN
- Verify Phone: PT + EN
- Password Reset: PT + EN
- Password Change: PT + EN
- Init / Account Activation: PT + EN
- Domain Claimed: PT + EN

German default rows remain in the projection but are dormant because `de` is not an allowed language.
## Administrative credential boundary

Current roles:

- `hara-admin@zitadel.auth.haralabs.com.br` = `IAM_OWNER`
- `login-client` = `IAM_LOGIN_CLIENT` only
- `hara-identity-admin` = `IAM_OWNER`

The dedicated service account `hara-identity-admin` is now the maintenance identity for instance administration.
Its PAT was validated read-only before mutation and is stored on `storage` at:
`/srv/hara/identity/secrets/identity-owner.pat`
with mode `0600`, owner `root:root`.

The preserved `first-admin-password` is stale. Exactly one controlled Session API check was attempted and returned `COMMAND-3M0fs` (invalid password), failedAttempts=1. Do not retry it.

A temporary System API User bootstrap was prepared earlier but fully reverted:
- no `ZITADEL_SYSTEMAPIUSERS` remains active
- temporary RSA private/public keys were removed
- API returned healthy after rollback
## Real mail test and next action

A real PasswordReset notification was triggered through User API v2 for the human subject `391814630923567107`.
The API returned HTTP 200 and the activity log recorded the request successfully.
No password was changed.

SMTP first attempted direct TLS, logged a handshake warning, and then automatically fell back to STARTTLS.

Inbox delivery was visually confirmed. The received message showed:
- subject: `Redefina sua senha — HARA Labs`
- HARA logo
- Portuguese HARA body copy
- `Redefinir senha` button
- HARA Labs footer

The password reset link was not used and no password was changed.

Credential hygiene was also rechecked:
- `login-client`: exactly 1 active PAT
- `hara-identity-admin`: exactly 1 active PAT
- active PT/EN mail templates: zero visible `Zitadel/ZITADEL` residue

Remaining optional improvement:
- align Zoho SMTP from port 587 + STARTTLS fallback to port 465 + implicit TLS to eliminate the warning while preserving the currently working mail flow.

Keep `login-client` restricted to `IAM_LOGIN_CLIENT` and `hara-identity-admin` as the dedicated instance-maintenance identity.

Do not modify ZITADEL projections/event store directly.
