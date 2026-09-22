# HARA Commander — Clarus V1 — 2026-09-22

## Intent

`Clarus` is the canonical HARA Commander light theme.

The visual target is **technical premium paper**, not a blue-tinted dashboard. Dark mode remains the stronger reference; Clarus must preserve the same hierarchy, density and brand character while using a lighter neutral canvas.

## Core rule

Keep the navigation rail dark. Lighten the workspace, not the entire identity.

Avoid:
- large pale-blue page washes;
- white-on-white cards with invisible borders;
- excessive cyan/sky accents;
- decorative gradients in ordinary workspace screens.

Prefer:
- neutral cold off-white workspace;
- white cards;
- stronger 1px structural borders;
- restrained soft shadow;
- navy typography;
- gold only for HARA emphasis / primary action;
- sky blue only for links, focus and secondary state.

## Canonical token direction

Suggested Clarus tokens:

```css
--clarus-bg: #f3f6f8;
--clarus-surface: #ffffff;
--clarus-surface-soft: #f8fafb;
--clarus-border: #d5e0e6;
--clarus-border-strong: #c2d1da;
--clarus-ink: #0b2d49;
--clarus-muted: #607887;
--clarus-navy: #082c4a;
--clarus-navy-deep: #061d2e;
--clarus-sky: #2f9fd6;
--clarus-gold: #e9b128;
--clarus-success: #2bb983;
```

These are direction tokens, not permission to fork the existing HARA design system. Reuse canonical HARA Site variables where equivalents already exist.

## Surface hierarchy

1. topbar: near-white `#fafcfd`, thin lower border, minimal shadow;
2. sidebar: keep canonical dark navy;
3. page canvas: `#f3f6f8` or equivalent neutral cold gray;
4. cards/panels: solid white;
5. secondary inset surfaces: `#f8fafb`;
6. borders: visibly stronger than current light mode;
7. shadows: low-opacity navy shadow only on elevated surfaces.

## Brand usage

Gold:
- primary CTA;
- short eyebrow rule;
- selected premium/recommended emphasis;
- never as a large background.

Sky:
- links;
- focus ring;
- small selected icons;
- secondary informational state.

Green:
- actual connected/healthy/success state only.

Navy:
- primary text;
- sidebar;
- active navigation;
- high-priority information.

## Typography and density

- titles remain navy and high contrast;
- body copy must be darker than the current washed light mode;
- metadata may use muted blue-gray, but never below practical readability;
- preserve current compact enterprise density;
- do not enlarge cards simply to create visual breathing room;
- use spacing and border contrast instead.

## Acceptance

Clarus is accepted when:

- the sidebar visually anchors the page in both themes;
- cards are immediately distinguishable from the page canvas;
- primary/secondary text hierarchy is obvious without relying on color saturation;
- no customer screen looks like a NOC/observability console;
- no normal customer state uses `Degradado`;
- light/dark mode preserve the same layout and semantics;
- all interactive controls remain identifiable without hover;
- the product feels consistent with HARA Site rather than like a separate SaaS template.

## Product boundary

Clarus work must not distract from the V1 functional blocker.

The product mission remains:

`Account -> Device -> Commander Agent -> outbound HARA relay -> ChatGPT/Codex -> governed five-tool bridge`.

The next engineering blocker is the portable local governed five-tool bridge and public MCP routing to the selected online device.
