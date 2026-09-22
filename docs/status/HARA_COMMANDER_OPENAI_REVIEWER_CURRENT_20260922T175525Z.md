# HARA Commander — OpenAI reviewer current — 2026-09-22

## Canonical OpenAI submission readiness

Canonical HARA Platform source:
- repo: `tiagoharalabs/hara-platform`
- main: `3663da95e7c4d6bca46cb1a0333b42569949881c`
- submission preflight: PASS
- tool review count: 5
- positive review tests: 5
- negative review tests: 3
- annotations and justifications: already canonical in HARA Platform
- demo recording: still external/pending
- publisher identity/apps write/domain challenge/country selection: still external/pending

Commander Product Plane:
- hara-site branch: `issue29-commander-dev-v3-auth`
- starting head for this reviewer provisioning lane: `1845bfaac709bc32b1f9248eb0461835b4893b91`
- MCP Product authorize/release/commit validator: PASS
- MCP Product validator rerun-safe: PASS

## Reviewer tenant provisioned in Commander DEV

- tenant id: `HARA-TENANT-REVIEW-0001`
- display name: `HARA Review`
- environment: `REVIEW`
- subject placeholder: `HARA-SUBJECT-REVIEW-0001`
- reviewer email: `openai-reviewer@haralabs.com.br`
- role: `REVIEWER`
- plan: `REVIEW`
- meter: `HARA_COMMANDER_GOVERNED_INVOKE`
- monthly unit limit: `100`
- grants:
  - `COMMANDER_DISCOVERY`
  - `COMMANDER_READ_ONLY_INVOKE`
  - `COMMANDER_RECEIPT_READ`
- entitlement: ACTIVE
- billing provider: `REVIEW_NO_BILLING`
- invite id: `HARA-INVITE-OPENAI-REVIEW-0001`
- invite state: `ACTIVE`
- invite expiry: 90 days from provisioning

Provisioner:
`apps/commander/scripts/provision_openai_reviewer_dev.py`

## Reviewer credential handling

A dedicated reviewer credential was generated locally on `nucleo-a`:

`~/Documents/.hara-identity/openai-reviewer.credentials`

Security:
- mode: `0600`
- password never printed by automation
- password not stored in Git
- username: `openai-reviewer@haralabs.com.br`

The HARA Identity provisioning helper is versioned at:

`apps/identity-login/scripts/provision_openai_reviewer_identity.py`

The operator executed it successfully.

Provisioned reviewer identity:
- user id: `391922351219933187`
- username/email: `openai-reviewer@haralabs.com.br`
- user state: ACTIVE
- email verified: TRUE
- password configured: TRUE
- password change required: FALSE
- preferred language: `en`
- no MFA/TOTP enrollment was provisioned
- credential value remains local-only and was not exposed in chat or Git

## Remaining reviewer gates

1. Perform one public browser login as `openai-reviewer@haralabs.com.br` through HARA Identity and let the Commander invite claim naturally.
2. Prove D1 invite `CLAIMED`, real reviewer OIDC subject, REVIEW session, tenant, entitlement and quota.
3. Log out once and prove session revocation.
4. Do not install or reconfigure a new Cloudflare IdP from assumption.
5. Create/open the actual OpenAI plugin draft and observe whether reviewer credentials are requested.
6. If reviewer credentials are required, test the existing Cloudflare Access login path first.
7. Only if the existing Access login cannot meet no-MFA/no-email/no-SMS review requirements, configure a bounded password-capable edge IdP path.
8. Run the canonical 5 positive + 3 negative probe using the reviewer identity/path.
9. Record demo.
10. Complete publisher verification/apps write/domain challenge/country selection in the OpenAI portal.
