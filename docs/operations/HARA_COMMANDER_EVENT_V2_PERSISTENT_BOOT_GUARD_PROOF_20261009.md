# H.A.R.A. Commander — Persistent Event V2 Founder boot and local failover proof

Date: 2026-10-09 (America/Sao_Paulo)
Authoritative branch: `local/commander-product-current`

## Result and scope

**NUCLEO_A_EVENT_V2_USER_BOOT_PERSISTENCE=PASS**
**NUCLEO_A_EVENT_V2_LOCAL_GUARD=ACTIVE**
**NUCLEO_A_COMMERCIAL_MCP_AFTER_CONTROLLED_SERVICE_RESTART=PASS**
**FULL_HOST_OS_REBOOT=NOT_PERFORMED** (protect unrelated Núcleo workloads)

Only `nucleo-a`, the already authenticated and signed Founder Event V2 canary, was changed. This is NOT public rollout to all devices, NOT Windows parity, and NOT authorization to clone the Founder canary's device token to other hardware.

Previously, the old signed 0.3.41 user service was enabled on boot while new signed 0.3.44 Event V2 was running but disabled at boot. A reboot would have reverted the device to polling V1. Now the **single Event V2 service is enabled on boot**, signed V1 is disabled at boot but preserved in its original path, and a local-only systemd timer monitors healthy execution.

## Signed customer execution and credential hygiene

- `hara-commander-agent-v2.service`: `active`, `enabled`; starts `0.3.44` signed Event V2 package, runs `verify_release_v2.py` before every process start, and uses explicit `HARA_COMMANDER_EVENT_V2_OPT_IN=1`.
- `hara-commander-agent.service`: `inactive`, `disabled` for boot, **not masked or deleted**. Signed v1 executable remains byte-exact SHA-256 `e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730`. A failed v2 startup can reenable the original unit and restore `OUTBOUND_RELAY`.
- User `sartorius` on Núcleo has `loginctl Linger=yes`, permitting the enabled user manager to start after host reboot without interactive login. No OS reboot was performed here.
- systemd v2 service drop-in `10-exclusive.conf` declares `Conflicts=hara-commander-agent.service`, `StartLimitIntervalSec=180` and `StartLimitBurst=5`; systemd live readback confirmed the mutual exclusion.
- No private v2 RSA signing key was copied to the Núcleo. Production Agent config remains permission **0600**, guard script **0700**, guard units **0600**, guard's health-state file **0600**. Existing signed release files and OAuth credentials were not overwritten.

## Watchdog/fallback semantics

Canonical source: `apps/commander/scripts/commander_event_v2_persistent_guard.py`.
Offline sandbox: `apps/commander/scripts/validate_event_v2_persistent_guard.py`.
User systemd templates: `apps/commander/candidate/hara-commander-v2-guard.service`, `apps/commander/candidate/hara-commander-v2-guard.timer`, and `apps/commander/candidate/hara-commander-agent-v2-exclusive.conf`.

Installed locally at:
- `~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py`;
- `~/.config/systemd/user/hara-commander-v2-guard.service`;
- `~/.config/systemd/user/hara-commander-v2-guard.timer`;
- `~/.config/systemd/user/hara-commander-agent-v2.service.d/10-exclusive.conf`.

Guard timer: approximately every **120 seconds**, with a 105-second process-startup grace. No HTTP calls, no Cloudflare polling, and no device tokens accessed. Locally examines user systemd process/boot state, the signed Agent's protected WebSocket status (requiring a connection timestamp from the current v2 process), and an established owned TCP socket. To avoid fallback for brief reconnection noise, noncritical failure requires **two consecutive unhealthy checks**. If both Agents are active, it escalates immediately.

On confirmed failure, it disables/stops v2, verifies it is no longer active **before** enabling/starting signed v1, records a sanitized rollback outcome and stops/disables its own watchdog timer. This avoids a dual-Agent condition. For human rollback on the Núcleo:
`python3 ~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py --rollback`.

The sandbox tests confirmed: failure-count gate, recovery command ordering, old Agent never started while new remains active, startup grace, stale status, and absence of HTTP polling. Production fallback was **not deliberately fault-injected**; the above is tested code and a live read-only health validation, not a claim of a real fault event.

## Acceptance tests

1. Current signed v2 package independently verified on Núcleo: pinned public v2 RSA-3072 fingerprint, manifest signature and six file hashes **PASS**.
2. Guard source self-test **PASS** and mock multi-failure/recovery integration tests **PASS** on Services.
3. Guard script SHA-256 source-to-deployment readback **PASS**.
4. v2, v1 and timer systemd states read back after the boot switch: **v2 active/enabled; v1 inactive/disabled; timer active/enabled; Conflicts enforced; Linger=yes**.
5. Controlled `systemctl --user restart hara-commander-agent-v2.service`: **PASS**. New process PID, WebSocket status updated to `connected=true`; no v1 startup.
6. After the controlled service restart, actual **H_A_R_A__Commander commercial ChatGPT plugin** `ping`, `get_device_info` and `read_file(/etc/os-release)` all **PASS**, reporting `0.3.44`, `EVENT_V2` and `HARA_COMMANDER_AGENT`. Their local receipts were verified via SHA-256 and resolved to **three exact `COMPLETED` production D1 `commander_device_calls` rows** for the Founder device. `EVENT_V2_PERSISTENCE_RESTART_COMMERCIAL_D1_3OF3=PASS`.
7. Timer fired an actual guard service invocation with `STARTUP_GRACE=PASS`, and the next timer occurrence was scheduled. A subsequent live `--check` and `--run` after the grace period produced `EVENT_V2_GUARD_HEALTH=PASS` and state `HEALTHY` with 0600 permissions.
8. All relevant Event V2 wiring, WebSocket, signed release, multi-tenant source model and shutdown regression tests **PASS**. Only read-only D1 verifications and ordinary commercial tool executions occurred after the deployment; the v2 persistent guard does not query D1.

## Known limits and next checks

- **Full OS reboot was not performed**, to avoid disrupting ongoing H.A.R.A. GPU/ML workloads on the Núcleo. Persistence is attested by enabled systemd units, linger and a controlled service restart. A future maintenance-window cold-boot test will provide an additional end-to-end confirmation.
- The watchdog's live forced-failure fallback was not intentionally triggered on production; a deterministic mock failover test passed. Real recovery after an outage should be watched.
- Source-level v2 has **no repeated idle HTTP queue polling**. Actual Cloudflare billed request and Durable Objects duration reduction cannot be claimed without comparable usage analytics over time.
- The v2 signing private key remains only in Services custody. The public v2 key and signed Founder release can be used for this specific node; other computers require separately qualified per-device packages, tenant policies, platform parity and allowlist changes.
- **Do not run `systemctl enable --now hara-commander-agent.service` while v2 is healthy.** Manual rollback must stop/disable v2 first. The v2 exclusive `Conflicts=` is an additional safety net, not a substitute for orderly rollback.

## Watchdog PID visibility correction (same acceptance session)

The first periodic guard test after the controlled v2 restart recorded **one false `EVENT_V2_TCP_CONNECTION_MISSING`** while the signed Event V2 Agent was otherwise healthy. The watchdog's prior service used `PrivateTmp=yes`. Read-only `systemd-run --user` trials reproduced the issue precisely: plain systemd and `NoNewPrivileges=yes` both returned `EVENT_V2_GUARD_HEALTH=PASS`, whereas `PrivateTmp=yes` alone prevented `ss -tnp` from associating the socket with the Agent PID. No customer code, Agent transport or credential was defective.

**Safe resolution:** the watchdog timer was immediately stopped before the second-strike fallback; the v2 commercial Agent stayed active. The guard systemd service template was changed to remove `PrivateTmp=yes`, **keeping `NoNewPrivileges=yes`**. A regression assertion now prevents that incompatible mount isolation from returning unnoticed. The corrected unit was transferred to Núcleo A with exact source SHA-256 readback, systemd reloaded, and the **actual guard oneshot** returned `HEALTHY` and reset the false strike to zero. The watchdog timer was then rearmed and its enabled/active state confirmed. The signed v2 bundle, client Agent, token and Cloudflare PROD were unchanged.

Commands/proofs: `GUARD_UNIT_EXACT_SOURCE=PASS`, `PrivateTmp=no`, `NoNewPrivileges=yes`, `FALSE_ALERT_RESET_WITH_REAL_ONESHOT=PASS`, `EVENT_V2_GUARD_TIMER_REARMED=PASS`, `EVENT_V2_COMMERCIAL_SERVICE_PRESERVED=PASS`. The temporary suspension/rearm was local and bounded; there was **no fallback to the old Agent**.
