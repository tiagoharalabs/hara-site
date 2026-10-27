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

Eight pinned release files were verified over private HTTPS. The temporary server exposes only those files, has an external two-hour process limit, and drops privileges after loading them. Its QA certificate is added only to each installer process's CA bundle; system trust is unchanged.

The first two guest downloads timed out before any installation. Native diagnosis found UFW plus the separate QA input guard. A finite exception allows only the Ubuntu QA address to the host's private release port; the forward isolation rules remain unchanged. UFW access for the fleet is restricted to its local subnet. A cleanup timer was registered before the temporary rules were added. Rule removal and server shutdown must be recorded at rollout closeout.

## Fleet and release state at this checkpoint

All nine fleet hosts answered authorized SSH after the requested wake operations. Native inventory found legacy active V2 units on Sentinelas A/B/C/D and pinned 0.3.54 ExecStart paths on Observer/Storage; installing only the default Agent path would not update those running processes. Fleet migration is a separate continuation and is not claimed as completed here.

Windows QA installation remains pending an actual login to the existing QA account. The VM has no signed-in user; SYSTEM is not used as a substitute for the user's execution-policy and protected-state validation. The provisioner did not retain the QA password.

Public release remains NO-GO. Native Windows acceptance, the remaining recovery/product gates, ChatGPT OAuth refresh end-to-end evidence, dependency findings, and OpenAI review/publication requirements remain separate from the Linux installation above. The supplied portal screenshot showed a configured MCP, incomplete review information, not submitted and not published.

The previous custom R2 STOP and FD-hold diagnosis remain intact. The normal libvirt restoration above is a separate successful recovery route; it does not retroactively turn that campaign into a PASS.
