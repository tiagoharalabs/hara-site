# HARA Site — Front A successor handoff — Canonical flat branding + H.A.R.A. Commander assets

Date: 2026-09-21  
Issue: #13 — `[HARA SITE][FRONT A] Canonical flat branding + H.A.R.A. Commander assets`  
State: **READY FOR SUCCESSOR EXECUTION**

## Mission

Make the operator-approved **flat / matte / non-mirrored capybara mark** the canonical visual identity for the H.A.R.A. Labs public site and the H.A.R.A. Commander app/plugin family.

This front is primarily about **asset canonization + reference cleanup**, not a broad visual redesign.

## Current repository baseline

```text
repo=tiagoharalabs/hara-site
main=a158f100dfb6bba0bab2a81e453fb83c304bec33
issue=13
deployment=Cloudflare Worker/Assets
assets_dir=./public
```

Authoritative deploy config:

`wrangler.jsonc`

Current authoritative/deploy copies that must remain synchronized:

```text
index.html
public/index.html

assets/css/styles.css
public/assets/css/styles.css
```

Current hashes at handoff creation:

```text
index.html/public/index.html
git_blob=fcb925f7d2842df2627e0c1953493221996ce36f

assets/css/styles.css/public/assets/css/styles.css
git_blob=be4807e90e36a6fae78eb3954d0f441592b89fa4

public/assets/images/hara-commander-logo.png
git_blob=056acfdd9c7cd57559d85fcde65bc65bc28084c8

public/assets/images/hara-logo-premium.webp
git_blob=5c9e9f5a1560ee7dc9ced4d3383a2c910ea05cba
```

## Operator decision

Primary identity direction:

```text
PRIMARY_STYLE=FLAT_MATTE
CAPYBARA_ORIENTATION=NON_MIRRORED
METALLIC_3D_PRIMARY=FALSE
HIGH_GLOW_PRIMARY=FALSE
FULL_MARK_VISIBLE=TRUE
OBJECT_FIT=CONTAIN
```

The currently deployed `hara-commander-logo.png` is **not automatically the final approved asset** merely because it exists in Git.

The successor must use the operator-approved newer flat/matte capybara asset from the supplied visual set.

If the exact source image is not present in the successor conversation or accessible file context, retrieve/locate the latest operator-approved flat/matte non-mirrored source before replacing the active asset. Do not infer that the legacy/current repo asset is approved.

## Work already completed

PR #12 was merged before this handoff and fixed rendering robustness:

- header uses H.A.R.A. Labs premium branding instead of Commander asset;
- root-relative image paths;
- cache-busting;
- Commander fallback image;
- `object-fit: contain` to avoid cropping;
- apex + `www` live readback was PASS.

Do **not** redo these fixes unless a regression is proven.

## Required execution

1. Locate/confirm the exact operator-approved flat/matte, non-mirrored capybara source.
2. Create/commit a canonical source asset in the repo.
3. Generate only the derivatives actually required by current surfaces.
4. Replace stale active references.
5. Review all current image references across:
   - header;
   - Commander section;
   - favicon;
   - OpenGraph/social preview;
   - app/plugin icon source;
   - fallback path.
6. Preserve root/public HTML and CSS parity where the repo currently duplicates them.
7. Keep logo rendering as `contain`; do not crop the triangle/capybara.
8. Use versioned/cache-busted URLs where useful for Cloudflare/browser propagation.
9. Run repo validation/provenance guard.
10. Merge through PR.
11. Confirm live Cloudflare readback on:
    - `https://haralabs.com.br/`
    - `https://www.haralabs.com.br/`
    - canonical logo asset URL(s).
12. Capture final live screenshots.
13. Update issue #13 with asset SHAs, PR, deploy readback and terminal decision.

## Acceptance criteria

```text
CANONICAL_FLAT_SOURCE_ASSET=PASS
NON_MIRRORED_PRIMARY=PASS
LEGACY_ACTIVE_REFERENCES=0
HEADER_BRANDING=PASS
COMMANDER_BRANDING=PASS
FAVICON_APP_ICON_REVIEWED=PASS
OG_SOCIAL_REVIEWED=PASS
NO_CROPPING=PASS
ROOT_PUBLIC_PARITY=PASS
CI_PROVENANCE=PASS
CLOUDFLARE_LIVE_READBACK=PASS
OPERATOR_VISUAL_ACCEPTANCE=PASS
```

## Boundaries

This front MUST NOT change:

- `mcp.haralabs.com.br` authentication;
- Cloudflare Access/OAuth policy;
- H.A.R.A. Commander five-tool MCP surface;
- HARA Services authority;
- READ_ONLY publication boundary;
- Paradox runtime.

This front must not invent a second logo family.

## Dependency relationship

Front B = issue #14.

Front B consumes the canonical flat/matte identity established here and must not introduce a competing asset.

Front B may analyze palette/layout in parallel, but **final visual signoff must use Front A's canonical asset**.

## First action for successor

Before mutating files:

1. `git fetch origin main`;
2. compare current main with this baseline;
3. inspect issue #13 and its newest comments;
4. locate the operator-approved flat/matte source asset;
5. enumerate all active logo/image references in root + `public/`;
6. publish the intended replacement map in the issue/PR before merge.

## Suggested opening message for the new front

> Continue Hara Site Front A from issue #13 and the canonical handoff `docs/handoffs/HARA_SITE_FRONT_A_BRANDING_SUCCESSOR_HANDOFF_20260921.md`. Refresh `hara-site main` first. Canonize the operator-approved flat/matte, non-mirrored capybara identity, replace stale Commander/site assets, keep root/public parity, preserve the existing MCP/OAuth/runtime boundary, validate through PR/CI, then prove the Cloudflare live deployment with asset hashes and screenshots. Do not treat the currently deployed legacy/current Commander PNG as automatically approved.
