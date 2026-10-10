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
