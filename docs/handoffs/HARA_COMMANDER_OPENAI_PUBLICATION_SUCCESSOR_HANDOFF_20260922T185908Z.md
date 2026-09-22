# HARA Commander — OpenAI publication successor handoff — 2026-09-22 18:59:08Z

## Canonical product runtime

Commander DEV:
`https://hara-commander-dev-v2.tiago-sartori.workers.dev/`

HARA Identity:
`https://auth.haralabs.com.br/`

Public MCP:
`https://mcp.haralabs.com.br/mcp`

Branch:
`issue29-commander-dev-v3-auth`

Current product code before this handoff:
`39b870e28bad52a5e8d53ef23bcf22d53c3fd568`

Current DEV Worker:
`f3956f3e-abb0-4868-906f-ead85f6eff18`

HARA Platform canonical main:
`3663da95e7c4d6bca46cb1a0333b42569949881c`

## What is proven

### Owner / first-customer path
- `tiago.sartori@haralabs.com.br` logged in through HARA Identity.
- OIDC subject `391814630923567107`.
- Commander owner subject `HARA-SUBJECT-DEMO-0001`.
- invite CLAIMED.
- tenant `HARA Labs`.
- plan `STANDARD`.
- entitlement ACTIVE.
- quota 10000.

### Dedicated OpenAI reviewer path
- `openai-reviewer@haralabs.com.br`.
- HARA Identity user id `391922351219933187`.
- Identity ACTIVE.
- email verified TRUE.
- password change required FALSE.
- no MFA/TOTP enrollment provisioned.
- Commander subject `HARA-SUBJECT-REVIEW-0001`.
- tenant `HARA Review`.
- role `REVIEWER`.
- plan `REVIEW`.
- quota 100.
- entitlement ACTIVE.
- invite `HARA-INVITE-OPENAI-REVIEW-0001` CLAIMED.
- claimed at `2026-09-22T18:04:17.955Z`.
- claimed issuer `https://auth.haralabs.com.br/`.
- claimed subject `391922351219933187`.
- portal session ACTIVE / not revoked.
- reviewer browser login PASS.

Reviewer credential remains only at:
`~/Documents/.hara-identity/openai-reviewer.credentials`
with mode `0600`. Never commit or paste the password.

## Product-plane closure

PASS:
- HARA Identity OIDC callback/userinfo resolution.
- identity invite claim.
- tenant/plan/entitlement resolution.
- quota status.
- MCP Product discovery authorization.
- invoke reservation.
- release.
- terminal behavior after release.
- commit.
- commit idempotency.
- product token hygiene.
- Cloudflare secondary identity binding implementation.
- non-destructive DEV seed.
- rerun-safe validator.

No production mutation was performed by the DEV validators.

## Portal/UI closure

PASS:
- canonical HARA Site V13 light/dark theme.
- sidebar readability.
- explicit alternate-account login.
- authenticated topbar.
- logged-in user + role shown globally.
- logout action shown globally.
- Security real subject/tenant/role.
- demo activity removed.
- real TenantQuota ledger activity.
- empty state for zero-activity tenant.
- fake active-connection count removed.
- fake browser/location and fake ChatGPT OAuth rows removed.
- textContent-safe ledger renderer.

## OpenAI submission package already canonical in hara-platform

Existing and validated:
- exact five-tool surface.
- required annotations.
- annotation justifications.
- five positive tests.
- three negative tests.
- review probe.
- submission payload.
- public site/privacy/terms/support references.
- domain challenge runbook.

Do not duplicate these artifacts in hara-site.

## Immediate test sequence

### Gate A — reviewer portal final E2E
1. Open/refresh:
   `https://hara-commander-dev-v2.tiago-sartori.workers.dev/#dashboard`
2. Confirm topbar shows `OpenAI Reviewer / REVIEWER`, not `Entrar / Criar conta`.
3. Visit:
   - Dashboard
   - Usage & quota
   - Plan
   - Connections
   - Security
4. Confirm:
   - quota `0/100` until real operations occur;
   - no fake receipts;
   - zero connection count until an actual client connects;
   - Security has real subject, tenant and role.
5. Click `Sair` exactly once.
6. Query D1 and prove latest reviewer session has non-null `revoked_at_utc`.
7. Optional: login reviewer again to prove clean re-authentication.

### Gate B — actual OpenAI portal draft
Manual portal action required because current Plugin Management actions do not expose draft creation/import.

In the OpenAI portal:
1. confirm publisher/business identity state;
2. confirm Apps Management Write / `api.apps.write`;
3. create/import the HARA Commander draft;
4. MCP URL: `https://mcp.haralabs.com.br/mcp`;
5. run the portal tool scan;
6. record exact portal validation errors, if any;
7. observe whether reviewer credentials are required;
8. do not add a new Cloudflare IdP before the portal demonstrates a need.

### Gate C — reviewer edge auth
If the draft requires reviewer credentials:
1. try the existing Cloudflare Access OAuth path first;
2. verify the reviewer can authenticate without MFA/email/SMS/private network;
3. only if that fails, design the smallest bounded IdP adaptation.

### Gate D — review assets
- publish exact OpenAI domain challenge token only when issued;
- record demo:
  1. authentication
  2. `hara.health`
  3. list
  4. describe `fleet.list`
  5. invoke `fleet.list`
  6. receipt roundtrip
  7. fail-closed negative case
- host demo URL;
- select countries/availability;
- submit for review.

## Billing boundary

Do not add payment-provider complexity before:
- reviewer logout/revocation proof;
- real OpenAI draft creation;
- successful tool scan;
- ordinary ChatGPT/Developer Mode MCP E2E.

The internal commercial primitives already exist:
plan → entitlement → grants → quota → usage/receipt.
Billing later attaches payment state to entitlement activation.

## Manual actions currently required from Tiago

1. Reviewer visual check + one logout.
2. OpenAI portal draft creation/readback.
3. Domain challenge token copy when issued.
4. Demo recording later.

Everything else should continue backend-first with Git/evidence.
