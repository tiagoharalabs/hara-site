# HARA Commander — Commercial Linux Auto-Reconnect, 2026-10-13

Owner request: one-time pairing, keep the cloud Agent alive after reboot and normal network loss. Re-pair only on revocation/security recovery. Keep local action approvals independent.

Scope: Linux commercial bootstrap defaults HARA_COMMANDER_AGENT_AUTOSTART=ON and systemctl --user enable --now. Enables user linger when logind allows. OFF advanced opt-out retained. Cloud OUTBOUND_RELAY and ASK_EVERY_ACTION unchanged. Direct tunnel auto-start remains OFF.

Windows signed commercial agent and installer remain exactly as before; Windows is beta and manual startup. This is NOT Windows 24/7 GA.

Agent Linux/Windows files are frozen byte-identical from signed commercial 0.3.43-v3. RSA-3072 v2 trust pin and private key residency at Services retained. New revision v4 signed manifest, not a new version of Agent binaries.

Isolated lifecycle tests PASS for install, default auto-enable, stopped update stays stopped, active update, revocation/re-enrollment, uninstall, unrelated file preservation. Real signed stage test PASS, private key not exported.

New signed Linux installer SHA256: 699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463.

Signed staging: /tmp_hara/commander-commercial-autoreconnect-signed-r2-20261013 ; site staging: /tmp_hara/commander-clickgo-commercial-autoreconnect-stage-20261013.

Staging diff vs public Click-Go assets: index.html, install/linux.sh, manifest JSON, manifest signature and SHA256SUMS ONLY. Worker code and 29 bindings must remain unchanged when uploading.

Reboot witness for existing Founder agents: Sentinela A a07bbf99 -> a95404f8; B 8d9f3012 -> b0872b61; Ninja f9b20948 -> 451a84d3. All active/enabled with Linger=yes after reboot. These are not clean commercial install tests.

Limitations: Some hosts may deny loginctl enable-linger: login-free 24/7 is not guaranteed under restrictive OS permissions. Existing v0.3.43 customers do not automatically upgrade. Clean commercial physical reboot and Windows always-on remain GA acceptance gates.

Production authority: HARA Services. Preserve current Worker version and rollback. No direct runtime authority inferred from this document.
