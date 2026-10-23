# H.A.R.A. Commander — Live signed installer release blocker / owner handoff (2026-10-23)

## Scope
Independent **read-only public deployment** audit in response to Valky / HARA Codex installer divergence on hara-site#310. We did not operate or modify the reviewer VMs, installers, public release, Cloudflare, D1, signer or customer credentials.

## Observed publicly served assets (Cloudflare PROD, 2026-10-23T04:01Z)
- `/release/agent-manifest.json`: `agent_version=0.3.41`, SHA-256 `7e42f25404e414b74b375ccb47b7ed8ba7d8c572dc45db994d89012207f08f7c`.
- `/release/agent-manifest.sig.json`: valid RS256 over the **old** manifest using signer `commander-release-v1`. A valid signature does **not** imply that the current assets still match.
- Live `agent/linux.py`: version `0.3.43`; SHA `1572d70e60fb299edb262a8a817bd7aa1740a4c2dda3635d50beb2f3476ffe3b`; 220,422 bytes. Manifest declares 163,048 and another SHA.
- Live `agent/windows.ps1`: version `0.3.52`; SHA `817325667ea552136efa10d807148fa4dc6d035aca24046c884f444a4fb61ebc`; 98,717 bytes. Manifest declares 56,752 and another SHA.
- Live `install/linux.sh`: references 0.3.43, SHA `447fde76bdcee326dff70600f56b4b3be6cb9d2299e9265523b5d6e6baf88de1`; 36,564 bytes. Manifest declares 28,595 and another SHA.
- Live `install/windows.ps1`: references 0.3.49, SHA `6ba5c29e6d3a604750331d7699455ad609b4b0a8e191c03ad10503f7a5161c3c`; 23,604 bytes. Manifest declares 22,321 and another SHA.
- **Public package: 4/4 file SHA+size mismatches, Linux/Windows Agent version mismatch, signed manifest stale.** Canonical read-only `python3 scripts/build_release_manifest.py --check` in current source aborts `AGENT_VERSION_MISMATCH`.
- The Linux/Windows installers download the old signed manifest and validate Agent SHA/version. Thus first installation/update using this public set is blocked (expected fail-closed); do **not** submit OpenAI reviewer install flow until resolved.

## Controlled comparison — authentic signed 0.3.43 bundle
Location in source: `apps/commander/release-bundles/commercial-0.3.43-v2`.
- Valid RS256 `commander-release-v2`, with pinned public key in **both bundled installers** matching the bundled JWK, all four file SHA+sizes PASS, both Agents and manifest 0.3.43 PASS.
- With `--min-version 0.3.43`, local bundle gate PASS (exit0).
- Under release owner's current anti-downgrade floor (Linux >=0.3.54 and Windows >=0.3.55; common-version v1 manifest implies both >=0.3.55), this bundle correctly returns **HOLD** (exit5). It is a recovery reference, **not authorization to publish or downgrade fleet**.

## Reproducible guard introduced in isolated branch
`apps/commander/scripts/validate_public_signed_release.py`

Examples:
```bash
python3 apps/commander/scripts/validate_public_signed_release.py --url https://commander.haralabs.com.br --min-version 0.3.55
python3 apps/commander/scripts/validate_public_signed_release.py --root apps/commander/release-bundles/commercial-0.3.43-v2 --min-version 0.3.43
```
Validates exact 4 assets, RSA signature, pinned RSA public key in both installers, SHA, size, Linux/Windows source versions, and monotonic minimum. Exit **5** on any release HOLD; no writes.

## Owner action required
1. Reconcile hara-site#310 existing R3/R4 anti-downgrade kit and Windows acceptance hara-site#240. Do **not** replace R4 with a parallel unreviewed installer.
2. Compose a **single, authentic, same-version** public Linux+Windows release >=0.3.55 (or formally version the per-platform manifest schema), without relabeling an older Agent or repurposing Founder device-bound canary.
3. Produce/update the signed manifest, signature and pinned installer trust anchors as one atomic release. Validate Windows-native parser/E2E, Linux install/update/re-enroll, Agent capabilities, revocation, local approval and version monotonicity.
4. Bind this release integrity gate and the existing release floor/CI to the exact Cloudflare **candidate upload** and to the **public readback**. Do not permit further UI-only releases to carry stale bundled assets.
5. Stage 0% -> signed canary -> 100% only with rollback evidence and fresh complete public SHA/RS256/readiness proof. The active Worker can continue serving existing clients, but public installation is HOLD.

## OpenAI reviewer setup — independent but dependent on release fix
Existing identity mapping (from privileged read-only prior audit, **not live credential proof**):
- Tenant: `HARA Review` (`HARA-TENANT-REVIEW-0001`).
- Username: `openai-reviewer@haralabs.com.br`; distinct `REVIEWER` subject and entitlement exist.
- Login: `https://commander.haralabs.com.br/auth/login`.
- No password or token in this branch. Owner must verify current account/password, no MFA or out-of-band email code; enter password **only** in OpenAI Review details secure field.
- Test cases: five positive and three negative with real synthetic devices; demo video URL must be accessible. Never submit before genuine new-customer E2E/installer PASS and isolated reviewer proof.

## Observed platform draft at 2026-10-23 ~00:50 BRT
0.2.0 draft, domain verified, MCP configured and OAuth authorized, latest scan no findings, **Review info incomplete**, **Not submitted**.

No Cloudflare release, GitHub merge, Agent deployment, VM action, customer account change or secret access performed in this diagnostic.