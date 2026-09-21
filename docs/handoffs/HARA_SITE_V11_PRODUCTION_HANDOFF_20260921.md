# H.A.R.A Site V11 — Production Handoff

Date: 2026-09-21
State: TERMINAL / PRODUCTION PASS

## Canonical outcome

The operator visually approved the H.A.R.A Site V11 and explicitly authorized production publication.

The approved corporate site is live on:

- https://haralabs.com.br/
- https://www.haralabs.com.br/

## Implementation lineage

- PR #20 — `feat: publish approved HARA corporate site v11`
  - head: `daabfb2c0f1b47625a569fea4fc662e28ab282d0`
  - merge: `c17a8b069eeeba4c1cb70d12975fac9923af8335`
- PR #21 — `docs: simplify HARA Site workflow to dev and prod`
  - head: `b2c023b954b38c5c5e3c53c3616e4d5be9703251`
  - merge / canonical main before this handoff: `80257effde5af9762dfd516024d2cc5cae447582`

## Environment law

`DEV -> PROD`

- DEV is the local engineering and visual-review workspace.
- PROD is the canonical Git `main` state proven live through Cloudflare.
- No permanent third-stage environment is used.
- Git does not keep durable DEV snapshot directories.

## Production verification

Both apex and www returned HTTP 200 and served the V11 content.

Verified production asset hashes:

- logo `assets/images/hara-logo-web.webp`
  - SHA256 `ba136d189dad05119a02a83b0c1d5c8dc741a6357f301f0ee3021cdd4bc1aac9`
- CSS `assets/css/styles.css`
  - SHA256 `c1961152d63c182c6104b5aa75d93ea006279be1e7de043b29d862567e6917b1`
- JS `assets/js/script.js`
  - SHA256 `a6cd579277047f38a4b87bc052efcb6475600b13e13215f16d4b3bb94a3385f3`

Live hashes matched the canonical production repository assets exactly.

## Governance / checks

- HARA Site Main Provenance Guard: PASS
- Workers Builds: hara-site: PASS
- post-merge provenance guard: PASS
- local production worktree: CLEAN
- root/public asset parity: PASS
- public sanitization: PASS
- Worker/API/R2/Cloudflare runtime configuration untouched by the V11 visual publication

## Closed fronts

- Issue #13 — Canonical flat branding + Commander assets — CLOSED / COMPLETED
- Issue #14 — Paradox V4 Medium visual language modernization — CLOSED / COMPLETED

## Terminal state

`OPERATOR_VISUAL_SIGNOFF=PASS`
`PUBLIC_DEPLOYMENT=PASS`
`PRODUCTION_READBACK=PASS`
`HARA_SITE_V11_TERMINAL=PASS`
