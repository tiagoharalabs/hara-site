# HARA Site Environment Promotion V2

## Model

HARA Site uses two canonical environments:

DEV -> PROD

DEV is local engineering/review state. PROD is the durable state in Git and the live Cloudflare deployment.

The publication model intentionally has no third environment.

## DEV

DEV is the local engineering and visual-review workspace.

- source may change frequently;
- local artifacts and preview builds are disposable;
- DEV snapshots are not archived in Git;
- work begins from an updated clean `main` and proceeds on a short-lived branch;
- operator visual approval may be performed against the local DEV URL before promotion.

Current local convention:

- `/srv/hara/sites/hara-site/dev` = DEV candidate;
- `/srv/hara/sites/hara-site/prod` = local readback/copy of canonical PROD.

These local paths are operational state and are never committed as environment directories.

## PROD

PROD is the state merged to `main` and proven live on the production Cloudflare endpoints.

Production identity:

- Git branch: `main`;
- public site: `haralabs.com.br` and `www.haralabs.com.br`;
- deployment authority: Cloudflare integration attached to the repository.

Only production source and production workflow documentation are durable project state in Git.

## Git policy

DEV_SNAPSHOT_ARCHIVE=DENY
PROD_STATE_IN_GIT=ALLOW
SHORT_LIVED_BRANCH_PR=ALLOW
WORKFLOW_DOCS_AND_TOOLING=ALLOW

A pull-request branch is transport/review state, not a persistent environment.

## Promotion path

### DEV -> PROD

1. refresh `main`;
2. make the scoped change in DEV and/or on a short-lived branch;
3. run local validation;
4. obtain explicit operator visual approval when visual acceptance is required;
5. translate the approved DEV candidate into the canonical repository structure;
6. open a pull request;
7. require CI/provenance checks to pass;
8. merge to `main`;
9. allow the Cloudflare production deployment to complete;
10. read back apex and `www`;
11. verify expected HTML/CSS/JS/assets and production commit lineage;
12. only then mark the change terminal.

## Non-goals

Do not:

- keep `dev/` release archives under the repository;
- introduce a permanent third-stage preview tree;
- treat a branch/preview URL as production;
- merge solely because automated checks pass when operator visual approval is required;
- bypass the main provenance guard;
- rewrite canonical branding in a front that does not own branding.

## Repository cleanliness

This contract is documentation-only. It does not create or retain DEV release directories inside the repository.

A local DEV URL is review evidence only. Production authority remains `main` plus verified live Cloudflare readback.
