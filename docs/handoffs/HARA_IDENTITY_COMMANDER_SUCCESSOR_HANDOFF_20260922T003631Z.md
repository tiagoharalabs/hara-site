# HARA Identity / Commander DEV — Successor Handoff

**UTC:** 2026-09-22T00:36:31Z  
**Status:** CONTINUE_FROM_COMMANDER_E2E  
**Branch:** `issue29-commander-dev-v3-auth`  
**Head before this handoff:** `f1c48b65018a520d9d20dcf3f3b2c4de34ad5100`

## Executive state

HARA Identity is publicly healthy and Commander DEV is configured against it.

Fresh public checks:

```text
https://auth.haralabs.com.br/debug/ready
  -> "ok"

https://hara-commander-dev-v2.tiago-sartori.workers.dev/api/portal/auth-config
  -> {"configured":true,"provider":"HARA Identity"}

GET https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/login
  -> HTTP 302
```

The normal human Commander user now exists, is active, has a verified e-mail, has a password configured, and its login name has been corrected to the intended e-mail address.

The current blocker moved from Identity provisioning to the Commander browser E2E / callback path.

## Identity runtime

Self-hosted HARA Identity remains operational on `storage`:

```text
ZITADEL=v4.16.0
ZITADEL_LOGIN=v4.16.0
TRAEFIK=v3.7.7
POSTGRES=17.10-alpine

public issuer=https://auth.haralabs.com.br/
origin bind=127.0.0.1:8080
Cloudflare tunnel=hara-identity
```

Do not recreate or redeploy the identity plane unless new evidence proves it is required.

## Organization / domains

```text
Organization=HARA Labs
Primary domain=haralabs.com.br
Technical org domain=hara-labs.auth.haralabs.com.br
```

The internal IAM project named `ZITADEL` must remain intact.

The administrative instance display name still shows `ZITADEL`; supported rename to `HARA Identity` remains cosmetic work, not an E2E blocker.

## Branding

Current applied branding remains:

```text
Light background #F4F8FB
Light primary    #F1B82D
Light warning    #FF7C7C
Light font       #0A2840

Dark background #061B2B
Dark primary    #F1B82D
Dark warning    #FF7C7C
Dark font       #F4F8FB

watermark_disabled=true
```

HARA logo/icon are applied.

Residual white-label issues remain:
- invitation e-mail subject/body still mentions ZITADEL;
- hosted login can still expose ZITADEL wording;
- runtime logs show missing Portuguese hosted-login/message translations and fallback behavior.

Handle these later through supported Message Texts / Login Interface Texts / custom Login UI mechanisms. Do not patch ZITADEL core or event-store rows directly.

## SMTP

Active SMTP:

```text
Provider=HARA Identity Zoho
Host=smtp.zoho.com:587
TLS=true
Sender=HARA Identity <identity@haralabs.com.br>
Reply-To=contato@haralabs.com.br
```

Invite and verification e-mails have been received successfully.

ZITADEL logs show the provider first attempts direct TLS and then falls back to STARTTLS on port 587; delivery has nevertheless succeeded. Do not rotate the SMTP app password unnecessarily.

## External Links — COMPLETE

HARA Site front delivered and merged PR #31.

Site evidence supplied by that front:

```text
Commit=9f097f74c98643319145cb793b6fff9aa9875a32
main merge=3b99905aa23bdf6b129de5fd09bd9db5df20be5f
Terms=HTTP 200
Privacy=HTTP 200
Support=HTTP 200
Provenance Guard=PASS
Workers Build=PASS
post-merge guard=PASS
PROD worktree=CLEAN
```

Persisted ZITADEL External Links verified from the identity database:

```text
Terms=https://www.haralabs.com.br/legal/termos/
Privacy=https://www.haralabs.com.br/legal/privacidade/
Help=https://www.haralabs.com.br/support/
Support Email=contato@haralabs.com.br
Docs=
Custom URL=https://www.haralabs.com.br/
Custom Text=H.A.R.A. Labs
```

Legal TODOs intentionally left by the site front:
- formal controller/DPO identification;
- formal retention matrix by category/product;
- forum/jurisdiction.

Do not fabricate these values.

## Password / lockout — current owner decision

The earlier target of 12 minimum characters is **superseded**.

Current persisted password complexity:

```text
minimum length=8
number=true
symbol=true
lowercase=true
uppercase=true
```

This is the current owner-approved policy. Do not automatically restore 12.

Lockout remains:

```text
max password attempts=5
max OTP attempts=5
```

## Human identities

### Technical administrator

The technical administrative login was restored to:

```text
hara-admin@zitadel.auth.haralabs.com.br
```

It is the infrastructure / break-glass identity and must not be used as the normal Commander product identity.

The admin contact e-mail became unverified during the profile restoration. Review/re-verify a usable recovery address later before relying on e-mail recovery for this break-glass account. Do not remove its admin roles.

### Normal Commander user

The separate human product user now exists with intended login:

```text
tiago.sartori@haralabs.com.br
```

Console evidence showed:
- status ACTIVE;
- login method = intended e-mail;
- invitation check succeeded;
- e-mail address verified;
- password changed / password check succeeded;
- username changed to the intended e-mail.

There were subsequent failed invitation/e-mail verification events caused by reusing old invite/verification codes after the successful onboarding. Those failed events are historical noise; do not recreate the user and do not reset its password again unless a fresh login failure proves it is necessary.

## Invitation / notification observations

The initial invitation e-mail was delivered but still used ZITADEL product wording.

The invitation flow produced both:
- successful invite verification / e-mail verification / password setup;
- later `Código é inválido` errors when stale invite or verification codes were reused.

Current user state is valid. Do not retry stale invitation links.

## Commander DEV browser issue found and patched

The user reached:

```text
https://hara-commander-dev-v2.tiago-sartori.workers.dev/#login
```

but the visible login card appeared to do nothing.

The backend was already healthy:
- auth-config configured=true;
- /auth/login returns 302;
- app.js had `startRemoteAuth()`.

The fragile point was the static login HTML:
- main login button was still a form `submit`;
- SSO button was still wired to a demo toast.

This was changed so both buttons explicitly enter the real OIDC flow:

```html
<button type="button" data-go="login">Entrar no Commander</button>
<button type="button" data-go="login">Entrar com SSO corporativo</button>
```

Canonical patch commit:

```text
f1c48b65018a520d9d20dcf3f3b2c4de34ad5100
fix(commander): route remote login buttons directly to OIDC
```

The patch is already live. Fresh public HTML inspection confirms the main login button now has:

```text
type="button" data-go="login"
```

Do not revert this to a simulated form submit.

## Commander / OIDC current invariants

```text
OIDC provider=HARA Identity
Authorization Code=true
PKCE=S256
confidential Web client=true
token endpoint auth=client_secret_basic
exact issuer+subject binding=true
browser DEV_ACCESS_TOKEN=false
email fallback after binding=false
```

OIDC callback:

```text
https://hara-commander-dev-v2.tiago-sartori.workers.dev/auth/callback
```

## D1 / Cloudflare CLI note

Earlier final evidence attempts from local Wrangler hit Cloudflare API:

```text
7403
The given account is not valid or is not authorized to access this service
```

This did not break the public Worker or Identity.

Before performing the terminal D1 evidence pass, verify/restore local Wrangler authorization for the intended Cloudflare account. Do not rotate application secrets as a first response.

## Canonical next sequence

1. Open Commander DEV in a fresh/private browser session.
2. Click `Entrar no Commander`.
3. Confirm immediate redirect to `auth.haralabs.com.br`.
4. Authenticate with the normal human product user, not the break-glass admin.
5. Confirm OIDC callback returns to Commander.
6. Confirm dashboard opens.
7. Restore Wrangler Cloudflare CLI authorization if 7403 persists.
8. Query D1 and prove:
   - product invite is CLAIMED;
   - claimed issuer is exactly HARA Identity public issuer;
   - claimed subject is the new human user's ZITADEL subject;
   - portal session exists;
   - tenant / entitlement / quota resolve.
9. Test logout and prove session revocation.
10. Only after terminal local-user E2E PASS:
    - add Google IdP;
    - then Microsoft/GitHub only if desired.
11. White-label e-mail/login wording.
12. Optionally rename instance display name `ZITADEL` -> `HARA Identity` through a supported API path.

## Do not redo

- Do not recreate the HARA Labs organization.
- Do not recreate the normal human user.
- Do not resend/reuse the stale invitation link.
- Do not reset the user's password again without a new reason.
- Do not recreate the Commander OIDC application.
- Do not regenerate the OIDC client secret.
- Do not modify the internal IAM project named `ZITADEL`.
- Do not redeploy the HARA Identity stack.
- Do not change the working tunnel/DNS.
- Do not revert password minimum to 12 unless the owner changes the decision.
- Do not revert the explicit `data-go="login"` OIDC button patch.
