# H.A.R.A. Commander DEV V3 — Auth0 operator setup

Issue: #29

The Commander Worker is already deployed in DEV at:

```text
https://hara-commander-dev-v2.tiago-sartori.workers.dev
```

The current portal serves its approved static UI and Product API from the same
origin. OIDC is deliberately fail-closed until Auth0 credentials are configured.

## 1. Create the Auth0 DEV tenant/application

Use the Auth0 Free plan for DEV.

Create an application named:

```text
H.A.R.A. Commander DEV
```

Application type:

```text
Regular Web Application
```

Configure:

```text
Allowed Callback URLs:
https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback

Allowed Logout URLs:
https://hara-commander-dev-v2.tiago-sartori.workers.dev

Allowed Web Origins:
https://hara-commander-dev-v2.tiago-sartori.workers.dev
```

Security requirements:

- OIDC-conformant authorization-code flow;
- RS256 ID-token signing;
- Client Secret (Post) for token endpoint authentication;
- database/password or passwordless connection may be enabled at Auth0;
- H.A.R.A. never receives or stores the user's password.

A custom `auth.haralabs.com.br` domain is not required for DEV. The Auth0
tenant domain is acceptable until production cutover is explicitly authorized.

## 2. Copy only these values locally

From Auth0 Application Settings:

- Domain / issuer
- Client ID
- Client Secret

Do not paste the client secret into GitHub or chat.

## 3. Configure from the operator terminal

Run:

```bash
cd /tmp_hara/hara-site-dev-v3
python3 apps/commander/scripts/configure_auth0_dev.py \
  --issuer "https://YOUR_AUTH0_DOMAIN/" \
  --client-id "YOUR_CLIENT_ID"
```

The script prompts for the Client Secret with hidden terminal input.

It stores:

```text
apps/commander/.generated/auth0-dev.json
apps/commander/.generated/auth0-client-secret
```

Both are ignored by Git. The secret file is chmod 0600.

Then run:

```bash
python3 apps/commander/scripts/bootstrap_remote_dev.py
```

The bootstrap uploads `AUTH_CLIENT_SECRET` as a Cloudflare Worker Secret and
adds only the non-secret issuer/client ID/provider label as Worker vars.

## 4. First login binding

The Owner DEV invite is already provisioned in D1.

First successful Auth0 login:

```text
verified invited email
  -> one-time invite claim
  -> bind actual Auth0 issuer + subject
  -> mark invitation CLAIMED
```

Every subsequent login:

```text
issuer + subject
  -> exact users lookup
```

Email is never used as an identity fallback after the first explicit invite
claim.

## 5. Session

Portal session is:

- opaque random token;
- stored only as a SHA-256 hash in D1;
- cookie is Secure + HttpOnly + SameSite=Lax;
- 8-hour DEV lifetime;
- revocable through logout.

The browser never receives `DEV_ACCESS_TOKEN`.

## Boundaries

```text
PASSWORD_STORAGE_IN_HARA=FALSE
EMAIL_IDENTITY_FALLBACK=FALSE
REMOTE_BROWSER_DEV_ACCESS_TOKEN=FALSE
PRODUCTION_CUSTOM_DOMAIN=FALSE
REAL_BILLING=FALSE
HARA_SERVICES_OPERATIONAL_AUTHORITY=UNCHANGED
```
