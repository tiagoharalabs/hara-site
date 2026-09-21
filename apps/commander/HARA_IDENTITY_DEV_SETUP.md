# H.A.R.A. Commander DEV V3 - HARA Identity / OIDC setup

Issue: #29
Identity platform issue: hara-platform#880

Identity authority: self-hosted HARA Identity on storage, backed by ZITADEL and
a dedicated PostgreSQL database.

Target issuer:
https://auth.haralabs.com.br/

Commander DEV callback:
https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback

The Commander OIDC implementation remains provider-neutral: authorization-code
plus PKCE, state, nonce, discovery, JWKS, RS256 verification, exact issuer plus
subject binding, and HttpOnly portal sessions.

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
