# HARA Commander R11 — read-only public distribution verification

Run from the isolated clone root: `python3 -B docs/evidence/commander-install-compat-r11-20261020/peer_public_release_integrity.py`

This downloads six PUBLIC HTTPS files to memory under a byte cap; no redirects, enrollment, credentials or installer execution. It verifies the actual served Linux installer pinned RSA key against the served signature/manifest, then every public asset SHA. It also checks the old local Git v1 pin separately to explain misleading local PASS.

Exit 2 means the LIVE distribution is incoherent and an installer must fail closed; it is NOT an acceptance pass. The recorded 20 Oct 2026 public run had valid legacy v1 signature, but a live v2 pin and four mismatched public assets.

host-preflight.json contains safe machine versions and path existence, not tokens or system configuration values. Storage Fedora43 and Observer Ubuntu22.04 syntax-only probes passed; no unsigned script was executed. The owner had attempted three installs as recorded in Codex progress. No external readback is a PROD deployment authorization.

The report is docs/operations/HARA_COMMANDER_INSTALL_FAILURE_R11_20261020.md. The Codex implementation stays on its own branch.
