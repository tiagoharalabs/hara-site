# H.A.R.A. Commander — Click & Go UI / release gate (13 Oct 2026)
## Acceptance
- Owner requested a centered, minimal, click-and-go onboarding and retained single enrollment identity across normal reconnects.
- New interface: centered 720px install card, centered devices (1020px), centered Usage/Plans/Settings, responsive CSS, Advanced separated; primary steps choose OS, one-time pairing code, copy official installer.
- CSS cache key: 20261013-click-go-centered-v2. The HTML/JS UI is sourced from the repository; no pretend token value or automatic authorization.
- Clean UI-only branch: local/commander-click-go-ui-release-20261013, deliberately excludes dirty Linux autostart candidate from adjacent worktree.
- Source tests: validate_prod_static.py PASS; bash -n original installer PASS; four Node18 UI scripts PASS on Nucleo A. Real Brave headless preview of candidate at 1440x900 created on Nucleo; screenshot is a candidate, not production.
- Live product MCP: list_devices 13 registered/8 ONLINE/5 REVOKED and actual eight device.ping calls PASS including HARA_WIN11 (Windows result shape distinct). Linux services verified enabled/lingering on Services, Ninja Blue, C/D and Nucleo; historical A/B from earlier preflight.
- Signed staging: /tmp_hara/commander-click-go-signed-stage-20261013-v2 using stage_signed_commercial_assets.py; eight signed artifacts verified; public commercial-0.3.43-v3 distribution retained.
- Live asset parity: commander_click_go_live_asset_preflight.py against original staging PASS (9 exact: app.js and eight signed assets), including Linux installer SHA 534e14433da9f86eb4342c6d9400e89ecf164545605e02e22f1646510284aba5.
- Production site still serves old index.html / styles.css; UI IS NOT LIVE.

## Mandatory production promotion gates
1. Resolve exact deployed Cloudflare Worker version and source byte parity before uploading. Compared to historical PROD runtime 29067c28..., this branch's worker.js differs by 273 lines (213 insertions, 60 deletions) — NO blind full-worker deploy.
2. Create a version based on the exact currently deployed runtime/source while injecting ONLY new UI HTML/CSS and the signed staging assets. Never serve raw source installer.
3. Run scope approval by Services, signed manifest verification, app.js + eight sensitive assets exact readback, Worker D1/bindings/Identity regression, rollback/current version capture.
4. Upload candidate with Wrangler versions upload, inspect assets/secrets/bindings, promote only on PASS, verify live CSS cache marker, responsive screenshot, OAuth MCP and 9/9 parity. If any failure, rollback to preserved exact prior version.
5. Linux always-on new-client installer remains a separate source-only candidate in local/commander-click-go-ux-20261013 (uncommitted). Do not publish before clean-lifecycle regression, revoked identity, reboot/reconnect, explicit stop and signed release acceptance.
6. Windows reboot and first-customer end-to-end remain separate launch gates.

SOURCE_QUALITY=PASS
SIGNED_STAGE_PARITY=PASS
RUNTIME_DEPLOY_ADMISSION=PENDING
PUBLIC_UI_LIVE=false
