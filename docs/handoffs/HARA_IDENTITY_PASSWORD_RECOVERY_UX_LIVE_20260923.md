# H.A.R.A. Identity — password recovery UX live handoff — 2026-09-23

## Live state

- Public issuer: `https://auth.haralabs.com.br/`
- Identity engine: ZITADEL `v4.16.0`
- Live HARA Login image: `hara-identity-login:v4.16.0-hara.8`
- Live services changed: `zitadel-login`, `zitadel-assets` only
- API/Postgres/users/passwords/SMTP/OIDC apps: unchanged
- Rollback image: `hara-identity-login:v4.16.0-hara.7`

## Recovery contract

The public recovery flow preserves account anti-enumeration. Unknown aliases or usernames do not receive a literal `email not registered` disclosure. Instead, the UI states that recovery instructions are sent only when the supplied identifier maps to an account with a registered recovery email, and tells users who used an alias/username to retry with the email registered on the account.

## Live proof

- Login/assets hara.8: healthy
- ZITADEL API v4.16.0: healthy
- backend identity validator: PASS
- public branding/OIDC/PKCE/account-selection validator: PASS
- `/ui/v2/login/password?loginName=qa-alias-does-not-exist`: HTTP 200
- corrected Portuguese recovery copy present
- old false-success copy absent

## Known remaining item

SMTP remains operational on port 587 with STARTTLS fallback and is HARA-branded. A later transport-only cleanup may align Zoho to implicit TLS/465. This is not a password-recovery blocker.

ZITADEL v4.17+ should later be evaluated as a separate migration to remove the v4.16 backend `HostedLoginTranslationNotFound-pt` limitation.
