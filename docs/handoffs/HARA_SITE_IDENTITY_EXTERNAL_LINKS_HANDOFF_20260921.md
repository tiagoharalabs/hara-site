# HARA Site — Handoff: Legal / Support pages for HARA Identity

Date: 2026-09-21
Source front: HARA Identity / Commander DEV V3
Target front: HARA Site
Status: IMPLEMENTATION_READY

## Objective

Create the public pages required by HARA Identity / ZITADEL External Links so end users have valid, branded destinations for legal and support flows.

Required public routes:

- `/legal/termos/`
- `/legal/privacidade/`
- `/support/`

Expected canonical URLs:

- `https://www.haralabs.com.br/legal/termos/`
- `https://www.haralabs.com.br/legal/privacidade/`
- `https://www.haralabs.com.br/support/`

Support email already approved for use:

- `contato@haralabs.com.br`

Custom/home link:

- Label: `H.A.R.A. Labs`
- URL: `https://www.haralabs.com.br/`

## Why this is needed

HARA Identity is already operating at:

- `https://auth.haralabs.com.br`

The self-hosted identity stack is connected to Commander DEV through OIDC. ZITADEL External Links should point to real pages before Terms / Privacy links are saved and exposed in registration/login flows.

The organization domain is already:

- `haralabs.com.br` — verified and primary.

The SMTP sender is already:

- `HARA Identity <identity@haralabs.com.br>`
- Reply-To: `contato@haralabs.com.br`

## Product / visual requirements

Preserve the approved HARA Site / Commander visual language. Do not redesign the site globally as part of this task.

Canonical design tokens currently used by Commander and HARA Identity branding:

- Navy 950: `#041522`
- Navy 900: `#061B2B`
- Navy 850: `#08243A`
- Sky: `#31BDF4`
- Gold: `#F1B82D`
- Gold Deep: `#D99B12`
- Ink: `#0A2840`
- Paper: `#F4F8FB`
- Warning/Danger: `#FF7C7C`

The pages must be responsive and visually consistent with the current HARA Labs site.

## Legal-content constraint — mandatory

Do **not** invent or infer:

- CNPJ / corporate registration
- formal legal entity name
- physical/legal address
- DPO/controller identity
- statutory retention periods
- jurisdiction/venue clauses
- regulated-service representations
- commitments not already approved by the owner

If any of these are required for a legally complete policy, use a clearly marked placeholder / TODO in source and flag it in the handoff/evidence. Do not publish fabricated legal facts.

The content can be a production-quality operational draft, but must distinguish facts already known from fields that require owner/legal review.

## Page 1 — Terms of Use

Route:

`/legal/termos/`

Minimum sections:

1. Identification / scope of H.A.R.A. Labs services
2. Acceptance of terms
3. Account and authentication responsibilities
4. Authorized / prohibited use
5. Service availability and evolution
6. AI-generated output limitations
7. User responsibilities for prompts, data and actions
8. Security / abuse / suspension
9. Intellectual property
10. Third-party services / identity providers
11. Plans, quotas and billing language only where already supported by product
12. Termination / account closure
13. Changes to terms
14. Contact: `contato@haralabs.com.br`
15. Effective date / last updated date

Do not claim production billing if it is not active.

## Page 2 — Privacy Policy

Route:

`/legal/privacidade/`

Minimum sections:

1. Scope
2. Categories of data processed
3. Account / authentication data
4. Operational / security logs
5. Product usage / quota / receipt metadata
6. Cookies / session identifiers
7. Purposes of processing
8. Identity providers and third-party processors
9. Security practices at a high level
10. Data retention — only factual statements; no invented fixed periods
11. User rights / contact channel
12. International processing / subprocessors only if factually supported
13. Changes to policy
14. Contact: `contato@haralabs.com.br`
15. Effective date / last updated date

Important architectural fact for wording:
- HARA Identity is self-hosted and exposed at `auth.haralabs.com.br`.
- Commander does not receive/store the user's password when authentication is delegated to the identity provider.
- Do not overclaim that no data ever reaches third-party providers: Cloudflare and optional external IdPs such as Google may participate depending on the chosen flow.

## Page 3 — Support

Route:

`/support/`

Minimum content:

- HARA Labs / HARA Commander support heading
- Primary contact: `contato@haralabs.com.br`
- Categories:
  - Access / login
  - Account / identity
  - Commander connectivity
  - Plans / quotas
  - Security concern
  - General product question
- Clear statement that sensitive credentials, client secrets, passwords and recovery codes must never be sent by email.
- Link back to home.
- Links to Terms and Privacy.
- No fake SLA or response-time promise unless explicitly approved.

## HARA Identity External Links after deployment

Once the three routes are deployed and publicly validated, the Identity front should configure:

- Terms of Service:
  `https://www.haralabs.com.br/legal/termos/`

- Privacy Policy:
  `https://www.haralabs.com.br/legal/privacidade/`

- Help / Support:
  `https://www.haralabs.com.br/support/`

- Support email:
  `contato@haralabs.com.br`

- Custom label:
  `H.A.R.A. Labs`

- Custom URL:
  `https://www.haralabs.com.br/`

Documentation link can remain empty until public documentation exists.

## Acceptance gates

Do not report complete until all are true:

- [ ] Terms route returns HTTP 200 publicly
- [ ] Privacy route returns HTTP 200 publicly
- [ ] Support route returns HTTP 200 publicly
- [ ] Mobile/responsive rendering checked
- [ ] Header/footer/nav are consistent with HARA Site
- [ ] Cross-links between Terms / Privacy / Support work
- [ ] `contato@haralabs.com.br` is present where expected
- [ ] No fabricated legal identifiers or obligations
- [ ] No production billing claim unless factually active
- [ ] Existing HARA Site / Commander approved visual baseline remains intact
- [ ] Git commit / PR created
- [ ] CI / checks PASS
- [ ] Deployment evidence recorded
- [ ] Final public URLs returned to HARA Identity front

## Non-goals

- Do not modify HARA Identity / ZITADEL runtime.
- Do not change Cloudflare Tunnel or MCP records.
- Do not change Commander OIDC client settings.
- Do not redesign the main HARA Site.
- Do not create Google/Microsoft identity-provider integration as part of this task.

## Handoff back to Identity front

Return:

1. commit SHA
2. PR number / merge state
3. deployed public URLs
4. HTTP validation evidence
5. any unresolved legal placeholders
6. explicit statement whether External Links are safe to configure now


## Addendum — legal entity data supplied by owner (2026-09-21)

The owner supplied the following CNPJ registration details for use by the HARA Site legal-content front:

- CNPJ: `18.061.774/0001-98`
- Legal name: `IRMAOS SARTORI TECNOLOGIA DA INFORMACAO LTDA`
- Legal nature: `206-2 - Sociedade Empresária Limitada`
- Primary CNAE: `62.01-5-01 - Desenvolvimento de programas de computador sob encomenda`
- Opening date: `07/05/2013`
- Registration status reported by owner: `ATIVA`
- Address shown on supplied registration receipt: `R MURICI, 225, SALA 1, VILA CECILIA MARIA, SANTO ANDRE/SP, CEP 09.175-620`
- Email shown on supplied registration receipt: `SARTIAGO@GMAIL.COM`
- Phone shown on supplied registration receipt: `(11) 4453-6976`

Source note:
- The pasted registration receipt is dated `05/03/2021`.
- The owner states the company remains active and current with its accountant as of 2026-09-21.
- Before publishing legal pages, the site front MUST validate these details against a current official Receita Federal CNPJ registration receipt or equivalent authoritative source.
- Do not silently normalize or replace the legal name; preserve the official legal name from the current authoritative record.
- Public-facing support/contact should continue using `contato@haralabs.com.br` unless the owner explicitly changes that decision.
