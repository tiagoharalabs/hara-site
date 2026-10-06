# H.A.R.A. Commander — Preprod localhost validator repair — 2026-10-06

## Scope

This checkpoint repairs a false-negative in `validate_localhost_activity_refresh.py` discovered while following the successor contract to run `validate_preprod_readiness.py` before new Commander changes.

Starting canonical:

- `local/commander-openai-desktop-parity-20261004`
- `c91f11a48776d8a54654ff3d579c791346deba99`

## Finding

The runtime itself was healthy. The localhost validator loaded `public/agent/linux.py` through `runpy.run_path()` and then mutated the returned namespace dictionary. The dynamically loaded function resolves globals from its own `__globals__` mapping, so the requested ephemeral port (`LOCAL_PORTAL_PORT = 0`) was not reaching `start_local_portal_server()`.

That made the proof attempt to bind the normal `127.0.0.1:32145` listener and produced the false failure:

`COMMANDER_LOCALHOST_ACTIVITY_DYNAMIC_SERVER_START=FAIL`

The newer one-click support validator already used the correct `function.__globals__` pattern.

## Change

`validate_localhost_activity_refresh.py` now mutates:

`ns["start_local_portal_server"].__globals__`

for its isolated temporary data paths and ephemeral local port.

No Commander runtime, production asset, network policy, authentication behavior, local-first behavior, or customer data path changed.

## Proof

Isolated validator:

- `COMMANDER_LOCALHOST_ACTIVITY_REFRESH=PASS`
- dynamic server start = PASS
- local SQLite source = PASS
- CORS/PNA = PASS
- bad origin denial = PASS
- secret-content absence checks = PASS

Full source gate:

- `python3 apps/commander/scripts/validate_preprod_readiness.py`
- `COMMANDER_SOURCE_PREPROD_READY=PASS`

Expected live/operator-only states remain `LIVE_READBACK_REQUIRED` / `PENDING_OPERATOR_GATE` and are not altered by this repair.

## Successor rule

Treat this as a validator-harness repair only. Do not reinterpret it as a runtime regression or reopen localhost-direct/local-first architecture work.