# HARA Commander — R13 enrollment recovery handoff

State: local code candidate and QA only. No release signature, DEV enrollment, production deploy, remote D1 migration, or Agent replacement was performed in this front.

## Failure reproduced

The independent R13 review reproduced a registration committed by the Worker before initial device selection failed, leaving an active device without a delivered credential. It also reproduced a committed registration whose HTTP response was lost, and malformed enrollment responses that the Linux installer handled with a Bash `unbound variable` error. These are isolated local reproductions, not confirmed production incidents.

## Changes in this branch

- The Worker executes device insertion, pairing consumption, and initial selection in one D1 `batch`. A selection failure rolls back registration. A client-created 48-byte random credential lets a retry authenticate with both the original pairing token and the credential; D1 stores only its hash. A wrong credential, a legacy response without a client credential, and a revoked device cannot use that recovery query. The existing `/api/device/enroll` remains for older clients.
- New installers post to `/api/device/enroll-intent`. An older Worker lacks this route and cannot consume a pairing while silently ignoring `client_device_token`. Both enrollment routes share the existing client and pairing rate limits. The new route requires the client credential.
- The Linux candidate persists a pairing-bound intent in a user-owned `0600` file before POST, reuses it on retry, validates the full response and token equality, and reports uncertain acknowledgements without rerunning an already committed action blindly. A pending server revocation retains recovery material and makes uninstall return nonzero.
- The Windows candidate does the same with a 48-byte OS-random credential protected at rest by CurrentUser DPAPI and a restricted ACL. The probe uses an isolated QA directory and evaluates only the helper function, never the installer entrypoint.

The installers continue to authenticate the complete signed release before enrollment. The source candidate remains **unsigned**. Its commercial Agent versions are Linux 0.3.43 and Windows 0.3.43; the separate Windows 0.3.55 functional source is not silently mixed into this bundle. Founder Sentinela A 0.3.54 and the installed QA Windows Agent 0.3.53 are separate observations.

The exact R13 public source candidate was materialized at `/tmp/commander-prelaunch-r13-source-candidate-20261021-0100z` with manifest SHA-256 `115b85e6d7367a396e3148ccf9ede0c6b213a2201bd452692522ab760f04bcb9`, Linux installer SHA-256 `46b7b57c4080d5a93295cd9799ff787646c12697a179eed69dcc6c01a9524c71`, and Windows installer SHA-256 `69a6bf0c2a3c7c373d524dd63d2272511eae5b81665d5ecf0d625bcb31c5cdad`. It has **no signature**. The signed v4 bundle is a frozen source base and historical rollback reference, but its post-exit output regression makes it unsuitable as an automatic functional fallback. `/tmp` is transient; the candidate must be re-created and rechecked from these commits before any official signing.

## Evidence and limits

`test_device_enrollment_recovery.mjs` executes the real Worker function and SQL over the 40 local migrations in isolated SQLite. It covers transactional selection failure, lost acknowledgement recovery, wrong credential, and legacy-client compatibility. `test_linux_r13_enrollment_ack.py` uses an ephemeral signed QA release and localhost HTTP: missing token, missing ID, malformed JSON, invalid ID, lost ACK with same-intent retry, mismatched pairing, pending-uninstall preservation, and old-server route rejection. It does not enroll a hosted Cloudflare device.

On HARA_WIN11, a copy of the candidate under `C:\Users\Public\Documents\HARA_COMMANDER_QA_20261020_WIN11` had SHA-256 `69a6bf0c2a3c7c373d524dd63d2272511eae5b81665d5ecf0d625bcb31c5cdad`, equal to the branch source. The PowerShell parser and isolated DPAPI/retry/pairing/origin probe exited 0. It created and removed only a unique QA subdirectory. No install, HTTP enrollment, scheduled task, credential, or active Agent was changed.

The local SQLite/mock checks do not prove D1 hosted concurrency, multi-POP asset coherence, clean commercial installation, revocation under network loss, or installed Windows parity. A lost or deleted local intent still needs operator recovery or server-side revocation; the installer does not guess a new pairing. Keep the public distribution on HOLD while its served manifest/signature/pins/assets disagree. The isolated Observer HTTP 401 remains a separate observation without a reproduced cause.

## Promotion and rollback boundary

An official signer must approve the exact source bundle and issue a v2 signature. Promotion tooling now requires an exact signed stage, validates its functional regressions, and reads back the same stage plus served pins. The operator must obtain specific production authorization before upload/deploy. A rollback must select the previous complete Worker-and-assets version; the versioned intent route makes a saved new installer fail closed against an old Worker. A historical signed bundle with the post-exit output regression is not an acceptable new candidate solely because its signature verifies.

Before charging new customers, exercise the same enrollment and lost-ACK cases against authorized Cloudflare DEV in a commercial test tenant and a neighboring tenant, then qualify clean Linux/Windows installs with official signature, rollback, and readback. No DEV or PROD pass is claimed here.
