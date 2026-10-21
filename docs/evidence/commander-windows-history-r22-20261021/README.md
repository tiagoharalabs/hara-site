# R22 — Windows 0.3.55 signed Founder canary and clean operator console

This package documents a real in-place update of the enrolled Windows 11 VM from Agent 0.3.53 to **0.3.55**, using an official v2-signed **one-device Founder canary**. It is not the commercial Windows installer published to customers. The public Cloudflare Worker, the Linux Founder Agents, and the Windows VM OS were not rebooted or modified.

The source fix starts the live console at EOF, consumes bounded new, complete UTF-8 JSONL lines and never replays earlier history automatically. The preserved local SQLite history is accessible through `hara-commander history [limit [before_id]]`, with bounded pagination and without arguments or action summaries. An operator window opened before the upgrade must be closed and reopened by its owner to display the new presentation.

A synthetic fixture executed through HARA Commander on the real VM passed thirteen checks plus a final PASS marker. The exact Agent 0.3.55 script passed its complete Windows --self-test. The locally installed `history 3` command passed, without displaying private markers. The 0.3.53 backup is retained with verified SHA, and the one-time updater task was removed after the 0.3.55 Agent became reachable. Signing private key stayed on Services.

The connected hosted MCP Worker still advertises 19 tools even though 0.3.55 source/contract supports 22; read_many and search return UNKNOWN_FUNCTION_ID, edit_block AGENT_UPGRADE_REQUIRED. This needs hosted Worker/version readback and rollout approval, **not another Agent reinstall**. Current public Windows/Linux commercial package remains 0.3.43. Do not claim fleet-wide single version.

Includes `windows_live_history_fixture.ps1` (synthetic only), `live-acceptance.json` (sanitized evidence), and SHA256SUMS. No private key, token, user history contents, or device configuration was committed. See `docs/operations/HARA_COMMANDER_WINDOWS55_HISTORY_R22_20261021.md`.
