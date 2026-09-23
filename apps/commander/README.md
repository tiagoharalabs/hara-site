# H.A.R.A. Commander — production package

Canonical standalone product-plane Worker for:

`https://commander.haralabs.com.br`

## Production boundaries

- Cloudflare Worker: `hara-commander`.
- D1: `hara-commander-product-prod`.
- D1 production data is never seeded from DEV.
- Durable Object quota state is isolated in the production Worker namespace.
- HARA Identity remains the OIDC issuer at `https://auth.haralabs.com.br/`.
- HARA Services remains the operational authority.
- No arbitrary shell, SSH or generic filesystem surface is exposed.
- Billing activation remains separate from runtime publication.
- Passwords are never stored by Commander.

## Current product direction

Canonical current product/visual status:

docs/status/HARA_COMMANDER_PRODUCT_DIRECTION_CURRENT_20260922.md

The Commander visual baseline is approved enough to inform the future HARA Labs institutional-site update, while the product remains under active implementation. Production OIDC login is active and the first real production tenant/user/TRIAL onboarding has completed successfully. The next product gate is first real device pairing and selected-device E2E.

## Agent lifecycle

Current lifecycle status and homologation evidence:

`docs/status/HARA_COMMANDER_P1_AGENT_LIFECYCLE_CURRENT_20260923.md`

Agent lifecycle commands now cover status, doctor, rollback-safe update and self-revoking uninstall.

## Release integrity

Agent distribution is bound to a deterministic stable-channel release manifest:

- `/release/agent-manifest.json`
- `/release/SHA256SUMS`

`apps/commander/scripts/build_release_manifest.py` derives Agent version and SHA-256/size metadata from the canonical Linux/Windows Agents and installers. `--check` fails if any release artifact drifts without regenerating the manifest. Linux and Windows installers verify the downloaded Agent SHA-256 and declared Agent version before install/update, then run their existing validation/rollback path.

This is integrity metadata, not code-signing. Native Windows EXE/MSI packaging and publisher signing remain a later distribution gate after the Linux selected-device path is terminal and before an external Windows canary is sent to a third party.

## Runtime surface

Production health:

- `GET /api/health`

Authenticated portal:

- `GET /api/portal/session`
- `GET /api/portal/dashboard`
- `GET /api/portal/devices`
- `POST /api/portal/devices/pairing`
- `POST /api/portal/devices/revoke`
- `POST /api/portal/devices/select`

Device Agent:

- `POST /api/device/enroll`
- `POST /api/device/heartbeat`
- `POST /api/device/revoke-self`
- `POST /api/device/calls/next`
- `POST /api/device/calls/complete`

Internal MCP/device routes require the product token.

## DEV isolation

The runtime accepts `DEV` and `PROD`, but every `/api/dev/*` route calls
`requireDev()`. In PROD these routes fail closed with `DEV_ENDPOINT_DISABLED`.

No top-level `public/dev/commander` tree is part of canonical PROD. Assets live
inside `apps/commander/public` and are deployed only by the Commander Worker.

## Identity publication gate

Before the custom-domain deployment is considered terminal, the existing
Commander OIDC application must allow both:

- `https://commander.haralabs.com.br/auth/callback`
- `https://commander.haralabs.com.br/`

The DEV callback/logout URIs remain valid during transition. Update identity
configuration through the supported ZITADEL API/console; do not modify the
ZITADEL event store directly.
