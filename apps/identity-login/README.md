# HARA Identity Login

Production-like white-label layer for the self-hosted ZITADEL Login V2 used at `auth.haralabs.com.br`.

## Runtime contract

- Upstream: `ghcr.io/zitadel/zitadel-login:v4.16.0`
- HARA image: `hara-identity-login:v4.16.0-hara.7`
- Public route: `/ui/v2/login`
- Identity issuer remains `https://auth.haralabs.com.br/`
- ZITADEL API, Session API, OIDC, PKCE and the login-client PAT are unchanged.

The overlay only changes visible vendor text, fallback logos, favicon assets, help link and theme metadata. A companion `zitadel-assets` service uses the same HARA image to serve the absolute static paths `/favicon*`, `/hara-logo-*.svg` and legacy `/zitadel-logo-*.svg` without changing the Login V2 runtime.
## Build

```bash
docker build -t hara-identity-login:v4.16.0-hara.7 apps/identity-login/overlay
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
- Verify Email, Password Reset, Password Change, Init and Domain Claimed message texts

SMTP transport is intentionally outside this script. The live provider is already HARA-branded:
`identity@haralabs.com.br`, sender name `HARA Identity`, reply-to `contato@haralabs.com.br`.

## Live validation

```bash
python3 apps/identity-login/scripts/validate_live_white_label.py
```

The validator proves HARA public assets, manifest, visible branding, absence of visible vendor copy, Commander OIDC redirect, PKCE S256 and explicit account selection.

## Rollback

Revert the login service image to `ghcr.io/zitadel/zitadel-login:v4.16.0`, remove the `zitadel-assets` service/router, recreate only `zitadel-login`, and keep the API/Postgres containers untouched.
