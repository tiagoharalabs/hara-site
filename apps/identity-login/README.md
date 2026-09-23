# HARA Identity Login

Production-like white-label layer for the self-hosted ZITADEL Login V2 used at `auth.haralabs.com.br`.

## Runtime contract

- Upstream: `ghcr.io/zitadel/zitadel-login:v4.16.0`
- HARA image: `hara-identity-login:v4.16.0-hara.8`
- Public route: `/ui/v2/login`
- Identity issuer remains `https://auth.haralabs.com.br/`
- ZITADEL API, Session API, OIDC, PKCE and the login-client PAT are unchanged.

The overlay only changes visible vendor text, fallback logos, favicon assets, help link and theme metadata. A companion `zitadel-assets` service uses the same HARA image to serve the absolute static paths `/favicon*`, `/hara-logo-*.svg` and legacy `/zitadel-logo-*.svg` without changing the Login V2 runtime.
## Build

```bash
docker build -t hara-identity-login:v4.16.0-hara.8 apps/identity-login/overlay
```

Apply the values in `compose.fragment.yml` to the existing stack and recreate only `zitadel-login` and `zitadel-assets`. The assets service is a restricted Node static server bundled in the same image; it exposes only the HARA favicon/logo allowlist.

## Administrative white-label policy

`scripts/apply_hara_identity_white_label.py` requires a PAT with `IAM_OWNER` / `iam.policy.write`.
It does not store or create credentials.

```bash
python3 apps/identity-login/scripts/apply_hara_identity_white_label.py \
  --pat-file /secure/path/identity-owner.pat
```
The policy sets:

- instance display name: `HARA Identity`
- allowed languages: Portuguese and English
- Hosted Login V2 visible translations
- Verify Email, Verify Phone, Password Reset, Password Change, Init and Domain Claimed message texts

The live SMTP provider is HARA-branded:
`identity@haralabs.com.br`, sender name `HARA Identity`, reply-to `contato@haralabs.com.br`.

The applicator also supports an optional SMTP transport alignment for Zoho implicit TLS:

```bash
python3 apps/identity-login/scripts/apply_hara_identity_white_label.py \
  --pat-file /secure/path/identity-owner.pat \
  --align-smtp
```

This changes only the SMTP endpoint to `smtp.zoho.com:465` with TLS enabled and preserves the stored SMTP password. Use `--smtp-test-recipient <address>` to request a provider test after alignment.

## Password recovery UX

Password recovery preserves ZITADEL's anti-enumeration behavior (`ignoreUnknownUsernames`): the public flow must not disclose whether an arbitrary identifier belongs to a real account. HARA hosted-login translations make that behavior explicit instead of falsely implying that an email was definitely sent.

For Portuguese and English, the recovery success copy states that instructions are sent only when the supplied identifier maps to an account with a registered recovery email, and advises users who entered an alias or username to retry with the email registered on the account. The failure copy provides the same actionable guidance without exposing account existence.

On ZITADEL v4.16.0, `pt` hosted-translation readback is a known upstream capability gap because the backend system locale is absent; the applicator reports this explicitly as deferred and must never label it PASS. `en` still requires exact hosted-translation readback. On ZITADEL v4.17+ both `pt` and `en` must read back successfully.

## Live validation

Public white-label validation:

```bash
python3 apps/identity-login/scripts/validate_live_white_label.py
```

Backend drift validation (run on the Identity host):

```bash
sudo python3 /srv/hara/identity/tools/validate_identity_backend.py
```

The public validator proves HARA assets, manifest, visible branding, absence of visible vendor copy, Commander PROD OIDC redirect, PKCE S256, explicit account selection, and that the Login V2 server-rendered `defaultRedirectUri` matches the Commander production origin.

The backend validator proves instance policy, administrative roles, PAT hygiene, complete PT/EN mail-template coverage including Verify Phone, absence of active vendor text, SMTP branding and runtime container health. It also reports the current SMTP transport alignment state without mutating it.

## Rollback

Revert `zitadel-login` and `zitadel-assets` to `hara-identity-login:v4.16.0-hara.7` and recreate only those two services. Keep the ZITADEL API and Postgres containers untouched. The upstream unbranded image remains the deeper emergency rollback, not the normal hara.8 rollback target.

## v4.16.0 backend limitation

ZITADEL v4.16.0 Login V2 contains a Portuguese frontend locale, but its backend `internal/query/v2-default.json` does not contain `pt`. `GetHostedLoginTranslation(locale=pt)` therefore returns `HostedLoginTranslationNotFound-pt` before instance-level custom translations can be merged. HARA login variant `hara.8` patches only the bundled PT/EN recovery fallback copy so the user-facing flow remains accurate and anti-enumeration-safe while the backend stays on v4.16.0.

The upstream backend default includes `pt` starting in ZITADEL v4.17.0. Upgrading the Identity API to v4.17+ is a separate migration gate because it includes backend migrations and must not be coupled to this UX-only login image change.
## Commander login default redirect

The instance Login Policy default redirect must be `https://commander.haralabs.com.br/`. This is the safe fallback when Login V2 loses the OIDC request context (for example through a direct login/password-recovery path). A DEV Worker URL must never remain as the instance default redirect in production.

Canonical aligner:

`python3 apps/identity-login/scripts/align_login_default_redirect.py --pat-file <secure-owner-pat>`

The script reads the existing policy, preserves its supported fields, changes only `defaultRedirectUri`, and reads the policy back. `validate_identity_backend.py` fails on redirect drift.
