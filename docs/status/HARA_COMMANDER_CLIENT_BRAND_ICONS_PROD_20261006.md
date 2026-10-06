# H.A.R.A. Commander — Client brand icons PROD

Date: 2026-10-06
State: CLOSED_PASS

## Scope

Small UI polish in the "Onde usar" client list.

Changed:
- ChatGPT placeholder `AI` badge -> official ChatGPT/OpenAI app icon;
- Claude placeholder `AI` badge -> official Claude icon.

Intentionally unchanged:
- Windows device badge remains `WIN`;
- Linux device badge remains `LIN`;
- generic MCP badge remains textual `MCP`;
- no "powered by", partnership, endorsement or co-branding copy was added.

The icons remain subordinate to the H.A.R.A. Commander identity: 26px artwork
inside the existing 34px client badge.

## Source / validation

Canonical UI commit:
- `228a64d6968887e60ec39eacd9ceb8d01b9316b0`

Production-isolated release commit:
- `efbe54394305f427a25121446e7d761782d0767a`

The release was deliberately rebuilt on the already-live 0.3.40 production
runtime lineage so the source/preprod-only SLO external alert-delivery runtime
was not promoted as a side effect of this visual change.

Preprod:
- COMMANDER_PREPROD_UI=PASS
- COMMANDER_SOURCE_PREPROD_READY=PASS

## PROD

Candidate Worker:
- `5f6f29aa-e333-4898-a11b-e7cc29c77f12`

Rollback:
- `c8cfc1d1-592c-4d71-8788-d237e07828c6`

Versioned promotion:
- required secret guard PASS;
- rollback-current guard PASS;
- Worker promotion PASS;
- trigger synchronization PASS;
- exact-version readback PASS;
- runtime assets CURRENT.

Public HTML readback:
- `styles.css?v=20261006-clientbrands1` present;
- ChatGPT icon path present;
- Claude icon path present;
- generic MCP text badge preserved.

Live asset SHA-256:
- ChatGPT: `bd18745b777ba0febad179ad581abbb7584951e0eea7c17d7a450b5838175ace`
- Claude: `059e22f525d67c6258c4f64514f0b0e717c914df8a706936d0299d5e6b8082d9`

COMMANDER_CLIENT_BRAND_ICONS_SOURCE=CLOSED_PASS
COMMANDER_CLIENT_BRAND_ICONS_PROD=CLOSED_PASS
WINDOWS_LINUX_DEVICE_BADGES=UNCHANGED
GENERIC_MCP_BADGE=UNCHANGED
SLO_ALERT_DELIVERY_SIDE_EFFECT_PROMOTION=FALSE
PROD_WORKER=5f6f29aa-e333-4898-a11b-e7cc29c77f12
PROD_ROLLBACK=c8cfc1d1-592c-4d71-8788-d237e07828c6
