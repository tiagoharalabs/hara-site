# H.A.R.A Labs — canonical gold capybara without pyramid (2026-10-14)

Operator-approved brand direction: single golden capybara facing right, transparent background, no triangle or pyramid.

## Source of truth

- Editable vector: `brand/hara-capybara-gold-transparent.svg`
- PNG master: `brand/hara-capybara-gold-transparent.png`
- Branding version: `20261014-goldmark1`
- The vector is traced/cleaned from the operator-provided transparent gold capybara image.

## Generated/updated surfaces

- Public marketing site: `public/assets/images/*` (and parity source `assets/images/*`)
- Existing logo URL: `/assets/images/hara-logo-web.webp?v=20261014-goldmark1`
- Header, footer, decorative logos, 404, illustrations, favicons, mark and old pyramid filenames
- Standalone H.A.R.A Commander: `apps/commander/public/assets/hara-commander-royal.webp`, with versioned HTML references
- Identity login overlay sources: H.A.R.A light/dark lockups, raster icons, ICO and SVG; separately deployed from the marketing site

## Reproduction and checks

```sh
python3 scripts/build_capybara_brand_assets.py
python3 scripts/validate_capybara_brand_assets.py
python3 apps/commander/scripts/validate_prod_static.py
git diff --check
```

The regeneration script uses ffmpeg with SVG (librsvg) and WebP support.
Root and public homepage HTML have independent preexisting content differences on the source branch; this change updates the same versioned brand references in both, without overwriting unrelated UI revisions.

## Deployment boundary

The marketing website is deployed as a Cloudflare Worker with `wrangler.jsonc`, serving `./public`. The Commander web application and identity overlay have their own deployment paths; committing their brand assets does not by itself prove they are live. The identity/authentication/MCP APIs and Cloudflare Access policies are unchanged.

This asset revision supersedes the earlier pyramid-bearing branding while preserving the existing filenames for backward compatibility.
