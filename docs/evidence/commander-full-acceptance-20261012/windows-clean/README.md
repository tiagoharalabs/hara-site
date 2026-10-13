# Windows .54R2 acceptance — 2026-10-13

Status: **PASS for the signed Windows client lifecycle in DEV.** The former .53 running-update defect was reproduced, fixed and closed by an actual .54 update with the operator session active and a later heartbeat preserving the new startup timestamp.

The full evidence and receipt map is [windows-054-r2-acceptance-summary.json](windows-054-r2-acceptance-summary.json). The environment was a separate live libvirt disk clone of a provisioned Windows 11 OS. Commander profiles/tasks were sanitized before network attachment, a new HARAQA Windows user was created, and each .53/.54 installation started with the Commander profile absent. This is real clean application installation and normal customer enrollment; it does not claim a separately provisioned OS or an external customer.

| .54R2 operation | Result | Evidence |
| --- | --- | --- |
| Actual signed installer/manifest/Agent crypto, parser and self-test on PS5.1 | PASS, 17/17 | native-054-r2-signed-crypto-ps51.json |
| Exact signed .54 runtime-status functions on PS5.1 | PASS, 34 recorded cases | native-054-signed-runtime-regression-ps51.json |
| Normal HTTPS installer + organic QA2 portal pairing, clean profile | PASS, exit 0 | native-054-r2-clean-install-pass.json |
| Normal CLI start, actual QA console/process ownership | PASS | native-054-r2-normal-start-pass.json |
| Normal portal selection + actual OAuth MCP read/receipt/quota | PASS, one metered device_info call | ../real-oauth/normal_signup_windows54_mcp_read_receipt_proof.json |
| Update with task and operator session active | Client PASS, startup attestation PASS; later heartbeat/owner witness PASS | native-054-r2-running-update-later-heartbeat-pass.json |
| Normal local stop | PASS | native-054-r2-normal-stop-pass.json |
| Update while stopped | PASS; explicit SKIPPED_MANUAL_STOP attestation | native-054-r2-update-stopped-pass.json |
| Corrupted manifest through clone loopback | Exact AGENT_RELEASE_SIGNATURE_INVALID rejection; Agent/config/task XML unchanged | native-054-r2-signature-negative-pass.json |
| Normal uninstall + server revoke | PASS, installed root/config/Agent absent | native-054-r2-uninstall-revoke-pass.json |
| Independent SYSTEM/normal portal after uninstall | Task absent, fixture listener 0, harness inactive; device REVOKED/offline | native-054-r2-task-after-uninstall.json and ../real-oauth/qa2_windows54_uninstall_portal_readback.json |
| Owned VM/NVRAM/TPM/volume cleanup | PASS; primary VM remained running with original disk identity | owned-clone-cleanup-final.json |

DEV .54R2 was read back on worker 6f6e68e3-0777-4fb3-820d-a288ca5f7fab before pairing. Manifest SHA is e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d. Windows Agent SHA is fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62; installer SHA is ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7. Signed Windows bytes are unchanged between .54R1/R2; both native crypto proof histories remain preserved. R2 rechecks the final manifest/signature.

The actual signed running update exited 0 with HARA_COMMANDER_AGENT_UPDATE=PASS and HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS. Startup changed from 03:48:15.8005935Z to 03:52:40.9635804Z; heartbeat at 03:55:50.0248672Z retained the latter value. Operator PID 8028 and exact start 03:49:41.9800592Z stayed unchanged. The consumer restarted from PID 3116 to 5324, task remained HARAQA/Interactive/Limited with zero triggers, and task XML SHA e307ec1bdf6f77d619f90fdd19e31650d13948eb3de84bee3d9f046f70b158dd stayed unchanged.

The first running-update collector incorrectly waited 25 seconds for a second heartbeat; the source cadence is 60 seconds. Its FAIL is preserved in native-054-r2-update-running-client-pass-collector-short-wait-fail.json, including SIGNED_CLIENT_EXIT_CODE=0 and the client's PASS markers. A bounded read-only follow-up closed the later-heartbeat and exact owner-identity assertions without repeating the update or metered device_info call. This preserves the collector error and distinguishes it from the .53 product failure.

The real OAuth MCP receipt is 838b83140a61bd01d7718f9a1d1ee03bed3cc4e01a383fc202dd9516f304218e. It identifies HARAQA5312 / Agent .54 / actual Commander execution authority. QA2 signup, portal pairing and OAuth used normal paths with no D1 seed or Founder identity. Quota went from 1 to 2 total consumed units, one unit for this .54 call. Normal portal readback after uninstall confirmed device HARA-DEVICE-e55b1d52-f6aa-4c93-873b-f1c12412faf0 REVOKED, offline, active_count 0 and online_count 0.

Historical .53 installation/OAuth PASS, running-update FAIL/rollback PASS, frozen-function reproduction and the isolated fix candidate remain in cycle-053-and-candidate-054-summary.json and native-053-* artifacts. The failed rich .53 installation reporter is preserved too; independent actual-QA scalar collection, SYSTEM task metadata and normal OAuth closed installation.

Native fixture scope remains explicit. The runtime regression extracts only Set/Try functions into an isolated GUID fixture. It records the preexisting directory-as-runtime-target anomaly and makes no atomic durability, concurrent-writer, reparse or filesystem-hardening claim. Omitted status fields preserve history; explicit null/empty clears canonicalize to an empty string; successful heartbeat clears error fields explicitly. Runtime startup timestamps are historical evidence and are combined with actual task/process ownership to establish activity.

Private pairing data, cookies, tokens, credentials and raw logs are excluded from these artifacts. Signed release files and the primary Windows VM were preserved. The separate QA VM and private volume were removed after evidence capture. This lane performed no commit or publication; release-wide promotion remains with the release owner.
