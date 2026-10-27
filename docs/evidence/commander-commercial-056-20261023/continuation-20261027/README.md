# Commander 0.3.56 — native installation continuation, 2026-10-27

This record appends verified execution to the existing `local/commander-beta-0356-review-20261023` work. It does not promote the candidate or replace earlier STOP records.

## Confirmed in this checkpoint

- The existing v2 custodian signed the exact 766-byte manifest. An independent verification checked the RSA-3072 signature and all four unchanged product artifacts. The private key was not exported. The verification JSON deliberately records signing scope only; it is not an installation acceptance result.
- Native signer tests: 12 passed on Services. Native cold-recovery helper tests: 20 passed on physical Sentinela B.
- The original Ubuntu QA VM was shut down gracefully. A cold qcow2 checkpoint and a materialized restored copy matched the complete source hash. The restored disk booted under the original libvirt definition and normal emulator. Guest identity, baseline Agent, enrollment configuration and systemd unit matched their preimages. Other guests were unchanged. State: `PASS_COLD_RESTORE_AND_BASELINE_BOOT`.
- The official pinned Linux installer downloaded over verified private HTTPS and completed `update` as `commanderqa` UID 2000. It reported integrity PASS, update PASS and rollback ready.
- The installed Agent is 0.3.56, 265620 bytes, SHA-256 `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`. Configuration and unit hashes were preserved. The rollback file is the exact prior 0.3.53 Agent.
- Because the QA service was manually stopped, the updater preserved that state and explicitly skipped runtime attestation. A separate authorized native start then produced PID 1072, `active/running`, version 0.3.56 and a fresh start at 2026-10-27T22:16:59.950807Z. Autostart stayed disabled.
- This native start did **not** prove a new remote heartbeat: the saved heartbeat was historical. The QA account remains ASK_EVERY_ACTION. No operator session, persistent trust or successful remote operation is fabricated in this record.

The complete native result is in [native-linux-evidence.json](native-linux-evidence.json). The signing result is in [private-signature-verification.json](private-signature-verification.json).

## Private distribution and bounded access

Eight pinned release files were verified over private HTTPS. The temporary server exposed only those files, had an external two-hour process limit, and dropped privileges after loading them. Its QA certificate is added only to each installer process's CA bundle; system trust is unchanged.

The first two guest downloads timed out before any installation. Native diagnosis found UFW plus the separate QA input guard. A finite exception allows only the Ubuntu QA address to the host's private release port; the forward isolation rules remain unchanged. UFW access for the fleet is restricted to its local subnet. A cleanup timer was registered before the temporary rules were added. At 2026-10-27T22:49:56Z the server and cleanup timer were stopped, the listener was absent, both temporary UFW rules and the temporary nft exception were removed, and the original QA guard rules were restored. UFW remained active. State: `PASS_PRIVATE_DISTRIBUTION_CLOSED`; the readback is included in the fleet closeout below.

## Fleet continuation and release state

All nine fleet hosts completed the private 0.3.56 update: Sentinelas A/B/C/D, Nucleo-A, Ninja-Blue, Observer ARM64, Storage and Services. Each has native runtime verification, a fresh start and heartbeat, `device.info` reporting 0.3.56, and a real `id -u` execution with exit0 through the principal Commander. Existing enrollment and `PERSISTENT_TRUSTED` policy were preserved. Legacy V2/pinned ExecStart paths and CLI links were migrated with retained preimages. The initial Nucleo CLI conflict, the initial Storage observation race, the independently verified restorations and the later successful attempts remain separately recorded. See [the fleet closeout](fleet-rollout/README.md) and [sanitized evidence](fleet-rollout/fleet-rollout-summary.json).

Windows QA installation remains pending an actual login to the existing QA account. The VM has no signed-in user; SYSTEM is not used as a substitute for the user's execution-policy and protected-state validation. The provisioner did not retain the QA password.

Public release remains NO-GO. Native Windows acceptance, the remaining recovery/product gates, ChatGPT OAuth refresh end-to-end evidence, dependency findings, and OpenAI review/publication requirements remain separate from the Linux installation above. The supplied portal screenshot showed a configured MCP, incomplete review information, not submitted and not published.

The previous custom R2 STOP and FD-hold diagnosis remain intact. The normal libvirt restoration above is a separate successful recovery route; it does not retroactively turn that campaign into a PASS.
