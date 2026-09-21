# H.A.R.A. Commander DEV V3 - HARA Identity / OIDC setup

Issue: #29
Identity platform issue: hara-platform#880

Identity authority: self-hosted HARA Identity on storage, backed by ZITADEL and
a dedicated PostgreSQL database.

Target issuer:
https://auth.haralabs.com.br/

Commander DEV callback:
https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback

The Commander OIDC implementation remains provider-neutral: Authorization Code
plus PKCE, client_secret_basic for confidential Web clients, state, nonce,
discovery, JWKS, RS256 verification, exact issuer plus subject binding, and
HttpOnly portal sessions.

Create the application in HARA Identity with these settings:

- Project: H.A.R.A. Commander DEV
- Application: Commander DEV
- Type: Web
- Authentication method: Basic
- Redirect URI: https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback
- Post-logout redirect URI: https://hara-commander-dev-v2.tiago-sartori.workers.dev/
- Development mode: disabled
- Login V2: instance default

The authorization request still uses PKCE S256 in addition to confidential
client authentication.

After creating the Commander OIDC application in HARA Identity, run:

cd /tmp_hara/hara-site-dev-v3
python3 apps/commander/scripts/configure_identity_dev.py   --issuer "https://auth.haralabs.com.br/"   --client-id "REAL_CLIENT_ID"

The Client Secret is entered through hidden terminal input and is never
committed. Generated local-only files:

apps/commander/.generated/identity-dev.json
apps/commander/.generated/oidc-client-secret

Then deploy:

python3 apps/commander/scripts/bootstrap_remote_dev.py

Boundaries:
PASSWORD_STORAGE_IN_HARA_SERVICES=FALSE
EMAIL_IDENTITY_FALLBACK=FALSE
BROWSER_DEV_ACCESS_TOKEN=FALSE
HARA_IDENTITY_SELF_HOSTED=TRUE
AUTH0_REQUIRED=FALSE
HARA_SERVICES_OPERATIONAL_AUTHORITY=UNCHANGED
