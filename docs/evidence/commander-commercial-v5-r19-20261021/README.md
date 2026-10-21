# R19 — H.A.R.A. Commander officially signed v5, OFFLINE only

The official RSA-3072 v2 commercial manifest for the **exact frozen** 0.3.43 v5 tar was signed on Services under custodial key protections. No private key, device token, customer material or Cloudflare credential is in this folder. The public signature and four asset hashes were verified independently on Nucleo, Fedora43 Storage and Ubuntu22 ARM64 Observer.

Artifacts: signature-custody-receipt.json = the public receipt, signed-stage-receipt.json = 17-file stage SHA, upload-preflight.json = VERIFIED_NOT_UPLOADED, offline-worker-build.json = Wrangler --dry-run only, linux-agent-regressions.json = nine current 0.3.43 tests, storage-signed-verify.json and observer-signed-verify.json = actual signed release in both architectures, cloud-current-baseline.json = readonly deployment listing.

offline-gate-before-test-update.json recorded 158/160. Its two failing tests contained OLD assertions requiring the v5 signature to be absent. Those tests were updated to prove v5 present and old v4 stage rejected; both focused suites then passed 13/13 and 16/16. Refer to offline-gate-final.json if recorded later.

Cloudflare public PROD is still **HOLD**: served public manifest 0.3.41/kid v1 with mismatched Linux/Windows files. No hosted version upload, 0%/100% traffic mutation or clean commercial installation has been executed. Release stage local only. The 0.3.43 channel is not the Founder 0.3.54 fleet.

The signed bundle is confined to this separate review branch as eight **public** files. Services keeps the private signing key locally. Source documents: docs/operations/HARA_COMMANDER_V5_SIGNED_P1_R19_20261021.md.
