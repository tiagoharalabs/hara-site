# HARA Identity / Commander DEV V3 — Successor Handoff

**Timestamp:** 2026-09-21T23:12Z  
**Front:** HARA Identity + Commander DEV V3  
**Status:** ACTIVE / WAITING_HARA_SITE_EXTERNAL_LINKS  
**Primary repos:** `tiagoharalabs/hara-site`, `tiagoharalabs/hara-platform`

## Executive state

The self-hosted HARA Identity plane is operational and publicly reachable. Commander DEV is configured against HARA Identity and the OIDC authorization entrypoint is live.

Current public validation:

```text
https://auth.haralabs.com.br/debug/ready
  -> "ok"

https://hara-commander-dev-v2.tiago-sartori.workers.dev/api/portal/auth-config
  -> {"configured":true,"provider":"HARA Identity"}

GET /auth/login
  -> HTTP 302 to https://auth.haralabs.com.br/oauth/v2/authorize
```

No Auth0 dependency is required.

## Identity runtime

Primary host:

```text
storage = 192.168.10.40
```

Runtime:

```text
ZITADEL=v4.16.0
ZITADEL_LOGIN=v4.16.0
TRAEFIK=v3.7.7
POSTGRES=17.10-alpine
DOCKER_ENGINE=29.8.1
DOCKER_COMPOSE=5.5.1
```

Architecture:

```text
Internet
  -> Cloudflare Edge
  -> auth.haralabs.com.br
  -> dedicated Cloudflare Tunnel hara-identity
  -> storage
  -> Traefik localhost proxy / h2c
  -> ZITADEL API + Login
  -> dedicated PostgreSQL
```

Local proxy binding remains localhost-only:

```text
127.0.0.1:8080
```

Systemd / persistence previously validated:

```text
hara-identity.service = ENABLED_ACTIVE
hara-identity-backup.timer = ENABLED_ACTIVE
encrypted off-host backup to services = PASS
POSTGRES_PUBLIC_PORT = FALSE
HARA_SERVICES_DB = UNTOUCHED
HARA_SERVICES_OPERATIONAL_AUTHORITY = UNCHANGED
```

## Cloudflare edge

Dedicated tunnel:

```text
name = hara-identity
tunnel_id = e726f391-1fb6-4957-8166-195968a3bc72
public_hostname = auth.haralabs.com.br
origin = http://127.0.0.1:8080
```

Public discovery/JWKS/login path were already validated earlier in this front.

## ZITADEL instance / organization state

### Instance

Current instance name is still:

```text
ZITADEL
```

This is a cosmetic/administrative pending item. If renamed, use a supported ZITADEL instance update path and rename it to:

```text
HARA Identity
```

**Do not rename or alter the internal IAM project named `ZITADEL`.**

Instance default language is already:

```text
pt
```

### Organization

Exactly one organization exists:

```text
name = HARA Labs
org_id = 391782241182744579
```

Organization domains:

```text
haralabs.com.br                 verified=true  primary=true
hara-labs.auth.haralabs.com.br  verified=true  primary=false
```

The second domain is the technical domain generated after the organization rename. It is not an error and should not be deleted casually.

### Internal / product projects

Internal IAM project remains intact:

```text
project = ZITADEL
project_id = 391782241182810115
```

HARA project:

```text
project = H.A.R.A. Commander DEV
project_id = 391790365465640963
```

Apps:

```text
Commander DEV = ACTIVE
internal Management-API / Admin-API / Auth-API / Management Console = intact
```

## Branding

Instance-level branding is applied.

Verified current values:

```text
Light Primary    #F1B82D
Light Warning    #FF7C7C
Light Background #F4F8FB
Light Font       #0A2840

Dark Primary     #F1B82D
Dark Warning     #FF7C7C
Dark Background  #061B2B
Dark Font        #F4F8FB

Hide login-name suffix = false
Watermark disabled     = true
```

HARA logo/icon have been uploaded through the console.

Residual ZITADEL wording in the hosted login is a white-label cleanup item, not a runtime blocker. Handle with supported Login Interface Texts/custom Login UI mechanisms; do not modify ZITADEL core/event store directly.

## SMTP / notifications

Generic SMTP provider is active:

```text
description   = HARA Identity Zoho
host          = smtp.zoho.com:587
TLS           = true
username      = tiago@haralabs.com.br
sender        = HARA Identity <identity@haralabs.com.br>
reply-to      = contato@haralabs.com.br
```

The SMTP credential is an application-specific Zoho password and must remain secret / outside Git and chat.

Zoho alias:

```text
identity@haralabs.com.br
```

is associated with the existing mailbox.

## Login Behavior and Security

Current default login policy is saved as:

```text
Local authentication allowed       = true
User Registration allowed          = true
External Login allowed             = false
Force MFA                           = false
Force MFA local-only                = false
Password Reset hidden              = false
Domain Discovery allowed           = false
Ignore unknown Usernames           = true
Disable Email Login                = false
Disable Phone Login                = true
Default Redirect URI               = https://hara-commander-dev-v2.tiago-sartori.workers.dev/
```

Passkey remains allowed but MFA is not forced for the first E2E.

### Password complexity

Current persisted policy:

```text
minimum length = 8
lowercase      = required
uppercase      = required
symbol         = required
number         = required
```

**Pending:** raise minimum length from 8 to 12.

### Lockout

Current persisted policy:

```text
max password attempts = 5
max OTP attempts      = 5
show failure          = false
```

This is already in the target state.

## External Links — BLOCKED ON HARA SITE FRONT

Current ZITADEL External Links are still empty.

Required public targets after the HARA Site front completes:

```text
Terms of Service:
https://www.haralabs.com.br/legal/termos/

Privacy Policy:
https://www.haralabs.com.br/legal/privacidade/

Help / Support:
https://www.haralabs.com.br/support/

Support Email:
contato@haralabs.com.br

Custom Label:
H.A.R.A. Labs

Custom URL:
https://www.haralabs.com.br/
```

Documentation URL may remain empty until public documentation exists.

Site-front handoff:

```text
docs/handoffs/HARA_SITE_IDENTITY_EXTERNAL_LINKS_HANDOFF_20260921.md
```

Latest legal-data addendum commit before this handoff:

```text
ce4212cdef032efe870202d19e71a5f77759b3e9
```

The handoff includes owner-supplied company registration data but requires validation against a current official Receita Federal CNPJ receipt before legal publication.

## Commander DEV V3

Remote DEV URL:

```text
https://hara-commander-dev-v2.tiago-sartori.workers.dev
```

OIDC application:

```text
Application Type      = Web
Grant                  = Authorization Code
Authentication Method  = Basic
PKCE request layer      = S256
Redirect URI            = https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback
Post Logout URI         = https://hara-commander-dev-v2.tiago-sartori.workers.dev/
```

OIDC client secret is stored outside Git and uploaded to Cloudflare as a Worker Secret.

Runtime code affecting the deployed auth UX was committed through:

```text
98b0a0d652115863579b30391af0a303c175b3ef
```

Deployed Worker version:

```text
dacd7e33-6946-4740-b18e-1b13b87d7090
```

Validated:

```text
HARA_IDENTITY_DEV_METADATA=PASS
OIDC_CLIENT_SECRET=PASS
REMOTE_DEV_D1_MIGRATIONS=PASS
REMOTE_DEV_SYNTHETIC_SEED=PASS
REMOTE_DEV_WORKER_DEPLOY=PASS
REMOTE_DEV_HEALTH=PASS
REMOTE_DEV_ACCESS_TOKEN=PASS
REMOTE_DEV_D1_READ=PASS
REMOTE_DEV_QUOTA_DO_SQLITE=PASS
REMOTE_DEV_CONCURRENCY=PASS
REMOTE_DEV_QUOTA_EXCEEDED=PASS
REMOTE_DEV_RELEASE=PASS
REMOTE_DEV_COMMIT_IDEMPOTENCY=PASS
REMOTE_DEV_RECEIPT_CONFLICT=PASS
REMOTE_DEV_VALIDATOR_RERUN_SAFE=PASS
```

Portal behavior was also improved:

- remote Enter/Create-account actions go to real OIDC flow;
- callback failures redirect back to friendly portal UX instead of raw JSON.

## Human-user / E2E status

Current ZITADEL human-user count was validated as:

```text
1
```

That is the administrative bootstrap identity. A separate normal human Commander user has **not yet been created**.

The earlier browser E2E authenticated an identity but ended with:

```text
IDENTITY_NOT_PROVISIONED
```

This was consistent with the administrative identity being used instead of the invited product identity.

Last valid D1 inspection earlier on 2026-09-21 showed:

```text
identity invite = ACTIVE
claimed_at      = NULL
portal sessions = 0
```

The invite target is the existing DEV owner subject.

### New operational blocker discovered during final recheck

A fresh Wrangler D1 inspection at handoff time failed with:

```text
Cloudflare API code 7403
The given account is not valid or is not authorized to access this service
```

This did **not** affect the public Worker or HARA Identity:

```text
IDENTITY_READY = "ok"
COMMANDER_AUTH_CONFIG = configured:true / HARA Identity
COMMANDER_LOGIN_HTTP = 302
```

Before the next D1 CLI mutation/inspection, re-establish/verify the local Wrangler Cloudflare authorization for the intended account. Do not rotate application secrets unnecessarily.

## Pending sequence — canonical

### WAITING / external dependency

1. HARA Site front creates and deploys:
   - `/legal/termos/`
   - `/legal/privacidade/`
   - `/support/`
2. HARA Site returns HTTP 200 evidence and unresolved legal placeholders.

### Identity configuration after site handoff returns

3. Populate External Links in ZITADEL.
4. Raise password minimum length from 8 -> 12.
5. Optionally rename instance `ZITADEL` -> `HARA Identity` using supported API/console path.
6. Clean residual customer-facing ZITADEL wording through supported white-label mechanisms.

### First real user / terminal E2E

7. Create normal Human User using the exact email already invited by Commander.
8. Verify that email through HARA Identity SMTP.
9. Use a private/incognito browser session so the administrative SSO session is not reused.
10. Login through Commander.
11. Verify:
    - OIDC callback PASS
    - invite becomes CLAIMED
    - exact issuer + subject binding recorded
    - portal session created
    - tenant / entitlement / quota resolve
    - dashboard opens
    - logout revokes session
12. Re-run D1 evidence after Wrangler authorization is restored.

### After local E2E PASS

13. Add Google as an external Identity Provider.
14. Decide Microsoft/GitHub IdPs later.
15. Keep invitation/entitlement authorization separate from authentication.
16. Do not allow arbitrary social-login users to auto-create paid/authorized HARA tenants.

## Invariants

```text
AUTH0_REQUIRED=FALSE
HARA_IDENTITY_SELF_HOSTED=TRUE
PASSWORD_STORAGE_IN_HARA_SERVICES=FALSE
HARA_SERVICES_OPERATIONAL_AUTHORITY=UNCHANGED
OPNSENSE_APPLICATION_ROLE=NONE
BROWSER_DEV_ACCESS_TOKEN=FALSE
EMAIL_IDENTITY_FALLBACK=FALSE
PRODUCTION_CUSTOMER_DATA=FALSE
REAL_BILLING=FALSE
NO_ARBITRARY_SHELL=TRUE
NO_SECOND_CONTROL_PLANE=TRUE
```

## Do not redo

- Do not recreate the HARA Labs organization.
- Do not recreate the Commander DEV OIDC app.
- Do not regenerate the OIDC Client Secret unless it is actually compromised/lost.
- Do not alter the internal ZITADEL IAM project.
- Do not remove the technical org domain casually.
- Do not change the working `auth.haralabs.com.br` tunnel/DNS.
- Do not replace the approved Commander visual baseline.
- Do not rerun initial identity deployment/bootstrap unless evidence proves it is necessary.
