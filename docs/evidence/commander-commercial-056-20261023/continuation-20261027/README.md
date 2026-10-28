# Commander 0.3.56 — native installation continuation, 2026-10-27

This record appends verified execution to the existing `local/commander-beta-0356-review-20261023` work. It does not promote the candidate or replace earlier STOP records.

## Confirmed in this checkpoint

- The existing v2 custodian signed the exact 766-byte manifest. An independent verification checked the RSA-3072 signature and all four unchanged product artifacts. The private key was not exported. The verification JSON deliberately records signing scope only; it is not an installation acceptance result.
- Native signer tests: 12 passed on Services. Native cold-recovery helper tests: 20 passed on physical Sentinela B.
- The original Ubuntu QA VM was shut down gracefully. A cold qcow2 checkpoint and a materialized restored copy matched the complete source hash. The restored disk booted under the original libvirt definition and normal emulator. Guest identity, baseline Agent, enrollment configuration and systemd unit matched their preimages. Other guests were unchanged. State: `PASS_COLD_RESTORE_AND_BASELINE_BOOT`.
- The official pinned Linux installer downloaded over verified private HTTPS and completed `update` as `commanderqa` UID 2000. It reported integrity PASS, update PASS and rollback ready.
- The installed Agent is 0.3.56, 265620 bytes, SHA-256 `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`. Configuration and unit hashes were preserved. The rollback file is the exact prior 0.3.53 Agent.
- Because the QA service was manually stopped, the updater preserved that state and explicitly skipped runtime attestation. A separate authorized native start then produced PID 1072, `active/running`, version 0.3.56 and a fresh start at 2026-10-27T22:16:59.950807Z. Autostart stayed disabled.
- At this earlier checkpoint the saved heartbeat was historical and the QA account used ASK_EVERY_ACTION. The later official policy change, real local MCP calls and fresh heartbeat are recorded in the current QA section below; the earlier evidence is retained unchanged.

The complete native result is in [native-linux-evidence.json](native-linux-evidence.json). The signing result is in [private-signature-verification.json](private-signature-verification.json).

## Private distribution and bounded access

Eight pinned release files were verified over private HTTPS. The temporary server exposed only those files, had an external two-hour process limit, and dropped privileges after loading them. Its QA certificate is added only to each installer process's CA bundle; system trust is unchanged.

The first two guest downloads timed out before any installation. Native diagnosis found UFW plus the separate QA input guard. A finite exception allows only the Ubuntu QA address to the host's private release port; the forward isolation rules remain unchanged. UFW access for the fleet is restricted to its local subnet. A cleanup timer was registered before the temporary rules were added. At 2026-10-27T22:49:56Z the server and cleanup timer were stopped, the listener was absent, both temporary UFW rules and the temporary nft exception were removed, and the original QA guard rules were restored. UFW remained active. State: `PASS_PRIVATE_DISTRIBUTION_CLOSED`; the readback is included in the fleet closeout below.

## Fleet continuation and release state

All nine fleet hosts completed the private 0.3.56 update: Sentinelas A/B/C/D, Nucleo-A, Ninja-Blue, Observer ARM64, Storage and Services. Each has native runtime verification, a fresh start and heartbeat, `device.info` reporting 0.3.56, and a real `id -u` execution with exit0 through the principal Commander. Existing enrollment and `PERSISTENT_TRUSTED` policy were preserved. Legacy V2/pinned ExecStart paths and CLI links were migrated with retained preimages. The initial Nucleo CLI conflict, the initial Storage observation race, the independently verified restorations and the later successful attempts remain separately recorded. See [the fleet closeout](fleet-rollout/README.md) and [sanitized evidence](fleet-rollout/fleet-rollout-summary.json).

## Current QA results on the two existing VMs

The user confirmed the two current domains in `qemu:///system`: `hara-review-linux` and `hara-review-win11-restoretest-20261024`. The native results below belong to those exact machines. No VM was created or redefined for these tests.

- **Ubuntu QA:** installed 0.3.56 was tested as `commanderqa` UID 2000. Version and self-test passed. The official `approval-mode always` command changed only the approval setting to `PERSISTENT_TRUSTED`; configuration ownership and mode 0600 were preserved. Three real local MCP calls passed, including a nonce/hash/UID-verified process execution. After the authorized user-service restart, the service was active/running and reported a fresh heartbeat at 2026-10-28T00:13:28.640788Z, with no operator session active. Both tested HTTPS health endpoints returned 200/ok. Autostart remains disabled. See [Linux QA results](linux-native/README.md) and [selected evidence](linux-native/linux-native-summary.json).
- **Windows QA:** the existing standard account `CommanderQA` was signed in. Native PowerShell 5.1 accepted the pinned sources. Agent version and self-test passed; native Job Objects passed six checks and user-context/DPAPI/ACL/Task Scheduler passed thirteen. CurrentUser execution policy was temporarily RemoteSigned and restored to Undefined. Independent closeout confirmed zero temporary tasks, fixture processes or fixture directories, and the original disabled product task retained the same administrative XML hash. See [Windows QA results](windows-native/README.md) and [selected evidence](windows-native/windows-native-components-summary.json).
- **Scope still open:** Windows 0.3.56 was executed as a test artifact, not installed or paired in CommanderQA. The Linux QA cloud tool lookup returned DEVICE_NOT_FOUND by both hostname and its registered device ID; the available principal-Commander inventory still contains the nine fleet devices. This is a device-selection gap, with cause not established, and is not a failed Linux process execution. Local MCP, health HTTP and heartbeat do not substitute for authenticated cloud tool delivery to either QA VM.

The original Windows identity used earlier ceased to exist in the current libvirt inventory. Its first staging attempt stopped before guest mutation. The active Windows VM and its existing account were independently identified before new tests. The earlier cold-checkpoint copy timeout remains HOLD with verified normal reboot; it is not converted into a backup/restore PASS by the successful component tests.

The additional [fleet command exercise](fleet-concurrency/README.md) completed 27/27 functional commands across nine hosts and 9/9 subsequent pings. Two initial calls were dispatched concurrently; the remaining 25 were sequential after latency observations. It is bounded functional load, not maximum-capacity or hosted20k acceptance.

Public release remains NO-GO. Full Windows installation/enrollment and cloud tool delivery to the QA VMs, the remaining recovery/product gates, ChatGPT OAuth refresh end-to-end evidence, dependency findings, and OpenAI review/publication requirements remain open after the component results above. The supplied portal screenshot showed a configured MCP, incomplete review information, not submitted and not published.

The previous custom R2 STOP and FD-hold diagnosis remain intact. The normal libvirt restoration above is a separate successful recovery route; it does not retroactively turn that campaign into a PASS.
