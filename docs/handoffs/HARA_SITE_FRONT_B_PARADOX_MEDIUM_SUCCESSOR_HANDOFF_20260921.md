# HARA Site — Front B successor handoff — PARADOX V4 Medium visual modernization

Date: 2026-09-21  
Issue: #14 — `[HARA SITE][FRONT B] Paradox V4 Medium visual language modernization`  
State: **READY FOR SUCCESSOR ANALYSIS / IMPLEMENT AFTER SOURCE REFRESH**

## Mission

Modernize the H.A.R.A. Labs public site using the current **PARADOX V4 Medium** visual direction as a reference:

- deeper medium-blue canvas/surfaces;
- calmer gold;
- materially less glow;
- stronger hierarchy;
- denser, more professional enterprise presentation;
- consistent section ownership and spacing.

This is a Hara Site visual-system front. It is **not** a PARADOX promotion front.

## Hara Site baseline

```text
repo=tiagoharalabs/hara-site
main=a158f100dfb6bba0bab2a81e453fb83c304bec33
issue=14
front_a_dependency=issue_13
```

## PARADOX source refresh at handoff creation

```text
repo=tiagoharalabs/hara-platform
platform_main=1f01a685e832eaba187c2065586f5a167ef0b5d4
canonical_visual_handoff_pr=812
pr_812=MERGED
pr_812_merge_commit=5dd7ffc1bc53909f1b38d4a247a145d6dee6529b

separate_visual_line_pr_789=OPEN
pr_789_head=5c763d8339f38c4aa18c491e77e4f6839bdfdc3d
```

Canonical current handoff:

`docs/handoffs/HARA_PARADOX_VISUAL_V4_RAG_HEAVY_TRIAD_SUCCESSOR_HANDOFF_20260921.md`

Important truth from PR #812:

```text
V3_4_PROMOTION=REJECTED
DO_NOT_PROMOTE_V3_4_BY_INERTIA=TRUE
V4_STATE=WIP_AUTOMATED_PASS_QUALITATIVE_REVIEW_PENDING
V4_LIVE=FALSE
V4_PROMOTION_AUTHORIZED=FALSE
PARADOX_RUNTIME_MUTATION_BY_VISUAL_FRONT=FALSE
```

PR #789 remains a separate open V3.4 visual-polish line. It must **not** be treated as canonical over the newer merged #812 handoff.

## Mandatory refresh rule

Immediately before implementation:

1. refresh `hara-platform main`;
2. search for a successor to PR #812;
3. re-read the latest visual handoff;
4. update issue #14 if the source reference changed.

If a newer canonical Paradox visual handoff exists, use it instead of freezing this 2026-09-21 snapshot.

## Current V4 Medium reference tokens

Observed from the V4 candidate at handoff creation:

```text
canvas     #07131f
surface    #0a1b2a
surface-2  #0d2132
text       #e5f0f7
blue       #76bfee
gold       #d8b45d
```

These are reference values, not a requirement to copy literal CSS one-for-one.

## Current V4 design direction

Carry forward the design intent documented in PR #812:

- stronger route/context hierarchy;
- calmer sidebar/navigation;
- tighter spacing;
- consistent workspace headers;
- summary cards reduced in height and noise;
- technical identifiers visually demoted;
- empty/low-information surfaces suppressed;
- route-specific layout ownership;
- explicit bounded overflow.

Adapt those principles to a public institutional/product site, not cockpit density.

## Operator direction

```text
TARGET_FEEL=PARADOX_MEDIUM_INSPIRED
BLUE_DEPTH=MEDIUM_DARK
GOLD=RESTRAINED
GLOW=REDUCED
ENTERPRISE_OPERATIONAL_FEEL=INCREASED
DECORATIVE_NOISE=REDUCED
```

The public Hara Site should still feel like H.A.R.A. Labs, not like a literal copy of the PARADOX control room.

## Front A dependency

Front A = issue #13.

Final visual signoff must consume the **canonical flat/matte, non-mirrored capybara identity** produced by Front A.

Do not introduce a new logo variant in this front.

## Required execution

1. Refresh current PARADOX visual handoff.
2. Refresh issue #13 asset state.
3. Produce a site-specific token map:
   - canvas;
   - primary/secondary surfaces;
   - border hierarchy;
   - text/muted text;
   - blue accent;
   - gold accent;
   - success/warning/error where relevant;
   - shadow/glow policy.
4. Audit current Hara Site route/section hierarchy:
   - header/nav;
   - hero;
   - informational sections;
   - Commander;
   - diagnostic;
   - contact/footer;
   - legal pages.
5. Implement a coherent Medium-inspired visual pass.
6. Reduce high-luminance yellow/gold usage to brand emphasis/CTA hierarchy.
7. Remove unnecessary glow.
8. Preserve contrast/readability.
9. Keep responsive layouts and avoid horizontal overflow.
10. Keep root/public parity.
11. Run CI/provenance.
12. Merge through PR.
13. Prove live Cloudflare deployment on apex + `www`.
14. Capture before/after screenshots.
15. Require operator qualitative acceptance before issue closeout.

## Acceptance criteria

```text
PARADOX_SOURCE_REFRESHED_BEFORE_IMPLEMENTATION=PASS
FRONT_A_CANONICAL_ASSET_CONSUMED=PASS
SITE_TOKEN_MAP_DOCUMENTED=PASS
MEDIUM_BLUE_DEPTH=PASS
RESTRAINED_GOLD=PASS
GLOW_REDUCED=PASS
VISUAL_HIERARCHY_IMPROVED=PASS
ROOT_PUBLIC_PARITY=PASS
RESPONSIVE_REGRESSION=0
CI_PROVENANCE=PASS
CLOUDFLARE_LIVE_READBACK=PASS
OPERATOR_QUALITATIVE_ACCEPTANCE=PASS
```

## Boundaries

This front MUST NOT:

- promote PARADOX V4;
- mutate PARADOX live runtime;
- claim V4 qualitative acceptance;
- change H.A.R.A. Commander MCP/OAuth;
- modify HARA Services authority;
- create a second control/identity plane;
- modify a green H.A.R.A. runtime solely for presentation.

## First action for successor

Before CSS work:

1. `git fetch` both `hara-site` and `hara-platform`;
2. inspect issue #14 newest comments;
3. identify whether PR #812 has a newer successor;
4. read that successor if present;
5. read current issue #13 state;
6. document the exact palette/token delta proposed for Hara Site before implementation.

## Suggested opening message for the new front

> Continue Hara Site Front B from issue #14 and `docs/handoffs/HARA_SITE_FRONT_B_PARADOX_MEDIUM_SUCCESSOR_HANDOFF_20260921.md`. Before changing CSS, refresh both `hara-site main` and `hara-platform main`, find whether PR #812 has a newer canonical PARADOX visual successor, and update the source reference if so. Use the current V4 Medium direction only as design reference, not as live/final truth. Consume Front A issue #13's canonical flat/matte non-mirrored logo, keep MCP/OAuth/runtime untouched, implement through PR/CI, prove Cloudflare deployment, and require operator visual acceptance.
