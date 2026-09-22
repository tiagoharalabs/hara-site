# HARA Identity Login

Production-like white-label layer for the self-hosted ZITADEL Login V2 used at `auth.haralabs.com.br`.

## Runtime contract

- Upstream: `ghcr.io/zitadel/zitadel-login:v4.16.0`
- HARA image: `hara-identity-login:v4.16.0-hara.1`
- Public route: `/ui/v2/login`
- Identity issuer remains `https://auth.haralabs.com.br/`
- ZITADEL API, Session API, OIDC, PKCE and the login-client PAT are unchanged.

The overlay only changes visible vendor text, fallback logos, help link and theme metadata.
## Build

```bash
docker build -t hara-identity-login:v4.16.0-hara.1 apps/identity-login/overlay
```

Apply the values in `compose.fragment.yml` to the existing `zitadel-login` service and recreate only that service.

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

## Rollback

Revert the login service image to `ghcr.io/zitadel/zitadel-login:v4.16.0`, recreate only `zitadel-login`, and keep the API/Postgres containers untouched.
