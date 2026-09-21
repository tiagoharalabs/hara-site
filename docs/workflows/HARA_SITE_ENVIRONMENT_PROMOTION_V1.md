# HARA Site Environment Promotion V1

## Model

HARA Site adopts the same three-stage publication model used by PARADOX:

DEV -> HOMOLOG -> PROD

The stages are logical publication environments, not permanent Git snapshot archives.

## DEV

DEV is the local engineering workspace.

- source may change frequently;
- local artifacts and preview builds are disposable;
- DEV snapshots are not archived in Git;
- work begins from an updated clean main and proceeds on a short-lived branch.

## HOMOLOG

HOMOLOG is the review surface.

For HARA Site, HOMOLOG may be:
- the Cloudflare preview associated with a pull request or branch; or
- a local preview when external publication is not needed.

Rules:
- HOMOLOG must not be treated as production;
- qualitative visual review happens here;
- screenshots or ad-hoc preview exports are local evidence unless a specific production closeout requires them;
- HOMOLOG snapshot directories must not be accumulated in Git.

## PROD

PROD is the state merged to main and proven live on the production Cloudflare endpoints.

Current production identity:
- Git branch: main
- public site: haralabs.com.br and www.haralabs.com.br
- deployment authority: Cloudflare integration attached to the repository

Only PROD state is durable project state in Git.

## Git policy

DEV_SNAPSHOT_ARCHIVE=DENY
HOMOLOG_SNAPSHOT_ARCHIVE=DENY
PROD_STATE_IN_GIT=ALLOW
SHORT_LIVED_BRANCH_PR=ALLOW
WORKFLOW_DOCS_AND_TOOLING=ALLOW

A pull-request branch is transport/review state, not a durable environment archive.

## Promotion path

### DEV -> HOMOLOG

1. refresh main;
2. make the scoped change on a branch;
3. run local validation;
4. publish or obtain a review preview;
5. verify the preview actually serves the candidate;
6. perform qualitative review.

### HOMOLOG -> PROD

1. explicit qualitative approval when visual acceptance is required;
2. PR review and CI/provenance checks;
3. merge to main;
4. wait for production deployment;
5. read back apex and www;
6. verify expected HTML/CSS/assets and production commit lineage;
7. only then mark the change terminal.

## Non-goals

Do not:
- keep dev/ or homolog/ release archives under the repository;
- treat a Cloudflare preview as production;
- merge solely because automated visual gates pass;
- bypass the main provenance guard;
- rewrite canonical branding in a visual front that does not own branding.

## Repository cleanliness

This contract is documentation-only. It does not create or retain DEV/HOMOLOG release directories inside the repository; local publication artifacts remain ignored and disposable.
A preview URL is review evidence only and is never production authority.
