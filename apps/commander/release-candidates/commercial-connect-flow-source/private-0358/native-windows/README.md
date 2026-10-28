# Windows .58 signed update and explicit runtime recovery

This attempt is scoped to the already-paired `CommanderQA` installation on domain `hara-review-win11-restoretest-20261024`. It admits the exact original .56 Agent, unchanged production binding and approval mode, and an existing product task in `Ready` state. Root is the only remote operator.

The .57 attempt restored .56 bytes but could not restart the Agent. A separate native startup diagnostic confirmed `System.Security.AccessControl.PrivilegeNotHeldException` at the enrollment directory's full `Set-Acl` call. The new .58 Agent applies only the intended DACL, leaving owner and group unchanged. The installer also waits for confirmed task stop and new runtime startup in its update and rollback branches. Frozen .56/.57 artifacts remain unchanged.

## Frozen native inputs

- `Invoke-Private0358Recovery.ps1`: `a06f95f316b5f7f69a33fc2ad85db6731452fbbf5ee99592fd6d38320095e58c`, 31,365 bytes.
- `native_upgrade_driver.py`: `969d7791cf81abc720fd7481676a354a08d9dc3089dbaf412951532465bd3049`, 6,334 bytes.
- Embedded `Recovery-Checks.ps1`: `1b91089fb6ef8b044e5d872899c6f60313a1c6105da7fe7647b68dc3cc2b8da1`.
- Signed release base: `https://192.168.10.23:18445/releases/0.3.58`.
- Manifest: `0c48cf879e5a8e564bb6554299c940a6414da64baf3477861450c6ee18be88dd`.
- Windows Agent: `bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d`.
- Windows installer: `27c856bb2b8ce8a100d8b258c8de544d99eb076ae8a0c6494110b17574ccfbc2`.

The coordinator's actions are `stage`, `run` and `result`. Stage verifies the source hash and parses the PowerShell file natively. It creates an isolated diagnostic task using the existing QA user's limited interactive token. It never changes execution policy.

## Ordered acceptance

1. Verify the existing binding, exact original executable, policies and task definition.
2. Download and verify the pinned v2 signed .58 manifest and payloads with normal TLS validation.
3. Extract only the selected functions from the verified Agent AST and run three enrollment-directory ACL initializations in a private synthetic directory. Require preserved owner/group, protected QA/SYSTEM rules and an identical DACL on repeated application. No Agent entry point or product directory is executed by this regression.
4. Run the verified installer with explicit `update` and noninteractive stdin. Monitor to natural completion; do not kill the signed transaction. Require exact .58 bytes, exact .56 rollback preimage, unchanged binding/configuration/task/policy and the original stopped state.
5. Explicitly start the verified product task once for the separately authorized recovery. Require a new .58 runtime, authenticated binding and heartbeat.
6. Observe the same supervisor and heartbeat/executor/alerts worker processes for at least 40 seconds, verify ownership and parent relationships, and read the recovery outbox without mutations. Require no persisted access block or new stalled/degraded events.
7. Verify unchanged owner/group and exact effective DACL on the actual enrollment directory. Run the frozen connection controller against the same signed release and require `CONNECTED` / `ALREADY_CURRENT` without pairing or another update.
8. Repeat final exact-state, task, runtime, authentication and preservation attestation.

The full success state is `PASS_PRIVATE_SIGNED_0358_UPDATE_AND_RECOVERY`. It represents a direct signed update, explicit runtime recovery and current-version connection. It is not evidence of automatic discovery from the default public catalog. A harmless Commander command by root remains the independent functional executor probe; the receipt identifies that check as pending until root supplies its own evidence. Historical persisted alert events are not represented as a new acknowledgement.

Native runtime outcomes belong in separate receipts. Source review or staging alone is not PASS. Raw child output and private error logs remain in the QA user's protected temporary directory; collect only the sanitized receipt/progress JSON. The coordinator caches the final sanitized report at `private-0358/native-windows/native-result.json` on B and removes only its completed diagnostic task.
