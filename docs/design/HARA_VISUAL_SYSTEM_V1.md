# H.A.R.A Visual System V1

Status: CANONICAL
Effective date: 2026-09-22
Authority: H.A.R.A Labs

## Purpose

This document defines the canonical visual language approved for H.A.R.A Labs public and product-facing surfaces.

The system is intentionally restrained: deep navy / petroleum surfaces, sky-blue information accents, matte gold identity accents, high legibility, and minimal visual noise.

## Design principles

1. Executive before decorative.
2. Dark surfaces use deep navy/petroleum, never flat black.
3. Gold is an identity accent, not a dominant fill.
4. Sky blue is used for information, interaction, flow, and technical emphasis.
5. Light mode remains soft ice-blue rather than pure white.
6. Dark mode must preserve information hierarchy, not merely invert colors.
7. Product and website surfaces should share the same identity while keeping context-specific density.
8. Motion must remain subtle and respect prefers-reduced-motion.

## Canonical light palette

- Navy primary: #082C4A
- Navy secondary: #0B3555
- Ink: #0B2D49
- Muted text: #607F96
- Ice background: #EEF8FD
- Ice secondary: #E7F5FC
- Sky: #39A2DF
- Sky light: #78C9F3
- Gold: #E9B128
- Line: #D4E7F2

## Canonical dark palette

- Base: #061721
- Surface: #081C29
- Raised surface: #0B2637
- Raised surface alternate: #0B2839
- Border: #1B4054
- Border strong: #244B61
- Primary text: #E5F2F9
- Muted text: #9BB5C5
- Interactive sky: #48BAF2
- Identity gold: #F1B82D

## Theme behavior

- Toggle location: header, adjacent to the primary CTA.
- Light mode displays a moon icon.
- Dark mode displays a sun icon.
- First visit respects prefers-color-scheme.
- User choice is persisted in localStorage under hara-theme.
- Theme is bootstrapped before stylesheet paint to avoid a visible theme flash.
- meta theme-color follows the active mode.
- Toggle must remain keyboard accessible and expose state through aria-pressed.

## Application rule

New H.A.R.A web/product surfaces should start from these tokens rather than creating independent palettes. Deviations require an explicit product-context reason and should preserve the H.A.R.A identity hierarchy.

The H.A.R.A Labs public site implementation is the reference implementation for V1.
