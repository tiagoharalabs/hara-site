# H.A.R.A. Commander — v2 rotated signing key and signed Linux Founder Event V2 canary

Date: 2026-10-09 (America/Sao_Paulo)

## Security and trust

Owner explicitly authorized a formally documented signing-key rotation and gradual rollout of the whole fleet. The initial key-creation ceremony was executed by the human owner on Services and produced the public fingerprint:

`93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`

- `kid=commander-release-v2`, RSA-3072, RS256.
- Private key is under `~/.config/hara-commander-release/v2/release-signing-private.jwk` on **Services only**, verified file mode 0600. **Never distribute or commit.**
- Public signing key `apps/commander/public/release/v2/release-signing-public.jwk` matches the fingerprint byte-for-byte by canonical JSON SHA-256. Public file only.
- v1 trust root, public install paths, signed Agent 0.3.41 manifest and four signed v1 binaries remain unchanged. An old v1 updater cannot verify v2; no unprompted in-place upgrade is permitted.

## Signed package: completed (Services)

Builder `apps/commander/scripts/event_v2_signed_release_v2.py` generated a separate, Founder-specific Linux release with six content-addressed files, patched local baseline Agent version 0.3.44 (from candidate 0.3.43 without modifying v1), Event V2 WebSocket client, durable loop, full-tool adapter and a Founder-only launcher.

Staging path (Services):
`/tmp_hara/commander-event-v2-0.3.44-founder-signed-v2`

Manifest SHA-256:
`178795df2b8cf4739d285c50c65370265ef5cceca0e5bfd08271243cb3523a49`

Signatures:
- Signer holds private-key material in memory only and emits a RS256 signature over the canonical manifest.
- `EVENT_V2_V2_RELEASE_SIGNED=PASS`
- `EVENT_V2_V2_SIGNATURE_VERIFIED=PASS`
- `EVENT_V2_V2_RELEASE_CONTENT_VERIFIED=PASS`
- `EVENT_V2_V2_PRIVATE_JWK_EXPORTED=FALSE`
- Independent pinned-fingerprint verifier `apps/commander/scripts/verify_event_v2_bundle_v2.py` also returned PASS.
- Source selftest under signed staging returned `EVENT_V2_SIGNED_FOUNDER_CANARY_SELF_TEST=PASS` and all full Agent 32 tools were recognized.
- No unsigned installer, no automatic updater path or Windows v2 release is published.

## Nukleo A: signed staging verified (no cutover)

Versioned isolated path:
`/home/sartorius/.local/share/hara-commander/releases/0.3.44-founder-event-v2`

Only public files were copied via SSH from Services; private key remains Services-only. The independent verifier ran **on nucleo-a**, using a pinned public fingerprint and did not consult the private key:

- `NUCLEO_V2_RSA3072_SIGNATURE=PASS`
- `NUCLEO_V2_MANIFEST_6_FILES=PASS`
- `NUCLEO_V2_KEY_PIN=PASS`
- launcher full-tool `--self-test` PASS
- Existing `hara-commander-agent.service` remains `active` and `enabled`; existing Agent version 0.3.41, config 0600, device identity exactly the Founder allowlist; approved local mode PERSISTENT_TRUSTED retained.

**No cutover was performed in this stage.** Attempts to write a new systemd unit through the remote access tool were blocked by security settings; the block was not circumvented. A human-administered controlled handoff, with verified rollback, is the next execution gate. Do not run two Agent loops with the same device token simultaneously.

## Gate for real polling reduction

1. User or authorized admin creates an independent `hara-commander-agent-v2.service`, with `ExecStartPre` verifying the v2 signed manifest and an explicit `HARA_COMMANDER_EVENT_V2_OPT_IN=1` environment marker.
2. Pre-arm independent fallback to `hara-commander-agent.service`. Stop old, start v2 only once. Confirm locally Event V2 `connected=true` plus Cloudflare PROD D1 `tunnel_mode=EVENT_V2`.
3. Invoke the **commercial H.A.R.A. Commander ChatGPT plugin** to `ping`/`get_device_info` on nucleus, validate both v2 transport and receipt correlation to the PROD D1 `HARA-CUSTOMER-MCP-...` request.
4. Only then make the service switch persistent; otherwise restore Agent v1 (signed 0.3.41) and D1 transport will re-identify as OUTBOUND_RELAY after its heartbeat.
5. Measure idle Cloudflare request rate for a comparable window, keep OAuth, quota, D1 receipt integrity and revocation guards; expand the allowlist/device fleet only after this Founder success.
6. Windows parity and multi-tenant Free quota exhaustion remain separate gates; neither is silently waived by the owner authorizing the signing-key rotation.

The new key is created and the canary package is legitimately signed; public customer migration and operational request savings are still **not yet demonstrated**.

## 2026-10-09 23:00 BRT — Founder PROD cutover completed and commercial ChatGPT MCP proven

**FINAL CURRENT TRUTH:** Signed Linux Agent v2 0.3.44 is running on `nucleo-a`, connected through authenticated `EVENT_V2` to the production Cloudflare hibernating `DeviceChannel`. Only this Founder device was migrated; the remaining fleet remains on its existing transports. The 15-minute protective rollback timer was **armed by the human**, then **cancelled after commercial tool, receipt and D1 correlation passed**. It is **not** still armed.

Detailed observed sequence:
- The human operator executed the prepared, fail-closed SSH handoff, verified RSA-3072 manifest signature and the six file hashes, stopped the old service, started `hara-commander-agent-v2.service`, and observed `EVENT_V2_CONNECTED=PASS`.
- The real `H_A_R_A__Commander` **commercial ChatGPT Plugin** (not Services administration) returned **PASS** on `ping(nucleo-a)`, `get_device_info(nucleo-a)`, `read_file(/etc/os-release)` and `list_processes(nucleo-a)`. Results reported Agent `0.3.44`, `EVENT_V2`, `operational_authority=HARA_COMMANDER`, `execution_authority=HARA_COMMANDER_AGENT`; each operation generated a SHA-256 receipt. `get_usage_stats()` PASS as Founder/Internal unlimited. No Services MCP data relay was used.
- The `ping` and `get_device_info` receipts were independently SHA-256 verified on the Núcleo A filesystem and their `HARA-CUSTOMER-MCP-...` request IDs matched **exactly two D1 PROD `commander_device_calls` rows**, both `COMPLETED`, same Founder device, `UNMETERED`. Separate D1 reads confirmed `hara.files.read` and `hara.processes.list` also `COMPLETED`.
- PROD `commander_devices.tunnel_mode=EVENT_V2` confirmed live. The prior `agent_version=0.3.41` remained stale because the WebSocket handshake does not update Agent version. After verifying the signed v2 install and runtime 0.3.44, a **single conditional PROD D1 metadata update** changed only this device from 0.3.41 to 0.3.44 under `state=ACTIVE AND tunnel_mode=EVENT_V2`. Exact readback: `agent_version=0.3.44`, `tunnel_mode=EVENT_V2`, `state=ACTIVE`. A restart of the legacy v1 Agent will automatically restore its own metadata on normal authenticated heartbeat; future v2 upgrades need a productized authenticated version-attestation channel.
- User-manager readback on Núcleo: `hara-commander-agent-v2.service active`, PID 600142, `NRestarts=0`; old `hara-commander-agent.service inactive` and **enabled**; `hara-commander-v2-failsafe.timer inactive`. The v2 loop had **one established TCP connection** during the readback. The old v1 executable and complete signed bundle remain intact.
- The v2 service is **not currently enabled at boot**; the signed 0.3.41 legacy unit is enabled. On reboot/user-manager restart, the machine intentionally reverts to v1 unless the persistent v2 rollout is separately qualified and committed. During the active session, event-driven Event V2 has **no fixed idle HTTP polling**; it drains durable D1 only on initial connect and WebSocket `CALL_AVAILABLE`. Protocol PING is not a repeated HTTP poll.
- **No billing claim yet:** the previous code-model estimate was ~10,086 idle infrastructure HTTP requests/day/Agent under old V1. The new client source eliminates fixed idle calls, but actual Cloudflare paid Workers/DO invocation and billed-duration savings have **not** been empirically compared over a representative 24-hour window. Do not convert the source-level reduction into claimed observed cost savings.

**NEXT GATES:** (1) longer soak and reboot-safe Event V2 failover supervisor; (2) quantitative Cloudflare request/DO and D1 usage comparison; (3) further authenticated negative/cross-tenant and meter quota tests; (4) sign Windows and multi-platform release; (5) only then expand per-device Cloudflare allowlist and fleet rollout. Do not install the Founder-only signed Linux bundle on Sentinelas/Ninja: its launcher and Worker explicitly allow only the Nucleo Founder device.

**ROLLBACK while v2 active:** Stop `hara-commander-agent-v2.service` and start `hara-commander-agent.service`; the old Agent reclaims `OUTBOUND_RELAY` on heartbeat. Do not run both against one token, and do not touch D1 history/quotas for rollback. A reboot automatically restores v1 while the current enabling configuration remains unchanged.
