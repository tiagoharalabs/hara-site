# H.A.R.A. Labs — institutional site

Public source for the H.A.R.A. Labs institutional site and the governed site-deployment lane.

```text
REPOSITORY_ROLE=PUBLIC_INSTITUTIONAL_SITE_SOURCE
DEPLOYMENT_TARGET=CLOUDFLARE
CURRENT_GOVERNANCE_AUTHORITY=TORRE_CONTROLE_HARA_V10
RUNTIME_AUTHORITY=0
GENERAL_GIT_PUBLICATION_TEMPLATE=0
```

## H.A.R.A. ecosystem

```text
hara-site
  public institutional presence and Cloudflare deployment lane

hara-platform
  source, contracts, schemas, policies and reviewed declarative state

hara-ops-evidence
  private sanitized evidence, manifests, receipts and remote readback

nucleo-a
  cockpit, staging and authorized requester

hara-services
  target operational control plane and global publication authority

observer
  passive observation and independent verification

storage
  durable artifacts, receipts and last-known-good recovery

TORRE_CONTROLE_HARA_V10
  current governance, sequencing and adjudication authority
```

This repository presents the company publicly. It does not replace the technical platform repository, operational receipts or private evidence mirror.

## Project structure

- `index.html`
- `styles.css`
- `assets/`
- `public/`
- `src/`
- `wrangler.jsonc`

## Site publication policy

Do **not** use this repository as a general example of:

```bash
git add .
git commit -m "update"
git push
```

An accepted update must use the site-deployment lane:

```text
EXACT_BASE_SHA
→ NON_MAIN_BRANCH
→ ALLOWED_PATHS
→ PUBLIC_CONTENT_AND_SECRET_CHECK
→ BUILD_OR_STATIC_VALIDATION
→ EXACT_DRAFT_PR
→ REVIEW
→ INTEGRATION_DECISION
→ CLOUDFLARE_DEPLOYMENT
→ DEPLOYMENT_READBACK
→ SITE_DEPLOYMENT_RECEIPT
```

Permanent boundaries:

```text
DIRECT_MAIN_PUSH=0
FORCE_PUSH=0
AUTO_MERGE=0
RAW_EVIDENCE_PUBLICATION=0
PRIVATE_CONFIG_PUBLICATION=0
AUTOMATIC_BRANCH_DELETION=0
```

Cloudflare deployment is a downstream effect of an accepted repository update. A successful Git push alone is not a complete deployment proof.

See [`HARA_SITE_DEPLOYMENT_POLICY.md`](HARA_SITE_DEPLOYMENT_POLICY.md).

## Local validation

Use the project scripts defined in `package.json` and validate that no private values from `.dev.vars` or local environments enter the public projection.

```text
PUBLIC_CONTENT_ONLY=1
SECRET_SCAN_REQUIRED=1
DEPLOYMENT_READBACK_REQUIRED=1
```

## Technical platform

The current technical architecture and Git publication contract are maintained in the private `tiagoharalabs/hara-platform` repository under Tower V10.

This README grants no runtime, merge or deployment authority by itself.