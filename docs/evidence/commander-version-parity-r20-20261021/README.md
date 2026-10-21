# HARA Commander R20 — fleet and release-train QA, no production mutation

Source: real H.A.R.A. Commander pings/config/read/short process on all seven Linux
hosts; per-host public-key RSA and file-hash verifications; Windows 0.3.55 candidate
source and Worker capability contract on the Núcleo; four independent public
HTTPS readbacks from Núcleo, Services, Storage and Observer. The Windows VM was
shut off and was not started.

The intended common version 0.3.55 is provisional. Current commercial *signed*
v5 0.3.43 is not the latest audited Windows candidate and cannot be relabeled.
Two signed Founder 0.3.54 loop implementations remain; identical displayed
version does not imply identical build or runtime behavior.

Reproduce safely:
  python3 -B apps/commander/scripts/test_release_train_parity_gate.py
  node apps/commander/scripts/analyze_cross_platform_capabilities.mjs
  python3 -B apps/commander/scripts/commander_release_train_parity_gate.py --target 0.3.55
Expected: tests 8/8 PASS; parity gate exit 2/HOLD until the missing real
release, signed installers, public readback, Windows VM tests and fleet
reconciliation have completed. The gate uses only on-disk evidence, has no
network calls and cannot authorize deployment by itself.

These files contain no device tokens, private keys or customer data. Do not
upgrade signed device-specific Agents by copying another host's source.
Detailed report: docs/operations/HARA_COMMANDER_RELEASE_PARITY_R20_20261021.md.
