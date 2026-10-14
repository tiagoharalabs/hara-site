# HARA Commander — Click & Go P0 / handoff 2026-10-13
## Product owner instruction
One-time pairing, no technical disclosures on the primary screen, centered setup, cloud Agent connected continuously while the computer is running, automatic safe reconnect after reboot/network loss; re-pair only after credential revocation or security incident. Keep action authorization separate from device pairing.

## Verified existing behavior
- Screenshot 4 screens: Devices 8 online / 5 historical, setup exposing transport/source and long commands, Commands & integrations extensive, Usage layout spread wide.
- Live Commander MCP: 8 ONLINE of 13 registered; ping on services/C/D PASS through product plugin, agents v0.3.54. Filesystem edits on Services exercised with preimage receipts; no secrets surfaced.
- C and Núcleo existing hara-commander-agent-v2.service active/running enabled and loginctl Linger=yes. Legacy local CLI status INACTIVE is distinct from active Cloud agent.
- Commercial Linux installer apps/commander/public/install/linux.sh explicitly disabled hara-commander-agent.service on install; caused manual boot policy UX.
- C CSOTN gameplay active; D P13 failed/77 with human STOP DRAIN and PAD UNKNOWN_DELIVERY 9643; DO NOT use Commander connectivity as CSOTN runtime override.

## Prepared source in isolated branch
- apps/commander/public/index.html: shortened onboarding language/navigation while preserving the one-use pairing workflow.
- apps/commander/public/styles.css: centered devices, install card, usage, plans, security; responsive 720px setup and copy-first action; raw installer text visually hidden while copy still uses original generated command.
- apps/commander/scripts/test_devices_setup_commands_ui.mjs updated for renamed headings.
- Installer candidate in working tree only (NOT_DEPLOY): enable --now on new installs with explicit OFF advanced option and best-effort linger; retain ASK_EVERY_ACTION and revocation. Clean lifecycle legacy assertions of manual-only are not yet updated; never ship until full harness and rollback/reboot witness.
- All product changes are separate from other dirty Commander worktree.

## Tests
- Nucleo A Node v18: test_devices_setup_commands_ui.mjs PASS all 10 assertions/blocks, test_devices_minimalist_ui.mjs PASS, test_plan_cards_centered_ui.mjs PASS; app.js node --check PASS.
- Services bash -n install/linux.sh PASS; git diff --check PASS.
- No browser screenshot / deploy or signed release acceptance yet. Node unavailable on Services; verified through Nucleo A.
- Linux full clean-lifecycle acceptance not passed; old policy expects manual startup. This is an explicit P0 gate, not a bypass.

## Release gates
1. Validate actual responsive rendering/browser screenshot; consider accessibility, focus and keyboard.
2. Reconcile legacy no-autostart test contract and optional user disable flow; run Linux clean lifecycle, revoked token, reboot network-loss recovery with independent witness. Test that explicit stop remains stopped and update does not awaken stopped agent.
3. Sign installer release, publish immutable artifacts and independently verify manifest, signing/rollback.
4. Accept ChatGPT remote HTTPS MCP OAuth end-to-end after reboot, without asking pairing again, with scoped approval for sensitive actions and durable revocation.
5. Validate Windows beta bootstrap separately; don't claim Windows 24x7 GA until completed.
6. Deploy portal with versioned CSS cache bust and production pre/post; keep old version rollback.
7. Keep CSOTN #38 STOP 9643 gate under HARA Services authority, separate from product deployment.

SOURCE_ONLY=true
PRODUCTION_DEPLOYED=false
AUTOSTART_LIFECYCLE_ACCEPTED=false
