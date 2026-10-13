Linux54R2 native acceptance passed on the exclusive Ubuntu24.04 QA guest with real systemd, the official signed HTTPS installer and the installed public CLI. Agent and installer remained byte-pinned throughout.

| Phase | Result | Evidence |
|---|---|---|
| baseline-053-install | PASS | [baseline-053-install.json](baseline-053-install.json) |
| upgrade-054-r2 | PASS_NATIVE_053_TO_SIGNED_054_MANAGED53_MIGRATION | [upgrade-054-r2.json](upgrade-054-r2.json) |
| upgrade-core-054-r2 | PASS_NATIVE_LINUX54_LIFECYCLE_CORE | [upgrade-core-054-r2.json](upgrade-core-054-r2.json) |
| upgrade-rollback-054-r2 | PASS_NATIVE_SIGNED_UPDATE_ROLLBACK | [upgrade-rollback-054-r2.json](upgrade-rollback-054-r2.json) |
| upgrade-mcp-contract-r2-054-r2 | PASS_NATIVE_LINUX_MCP_54 | [upgrade-mcp-contract-r2-054-r2.json](upgrade-mcp-contract-r2-054-r2.json) |
| upgrade-uninstall-054-r2 | PASS_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP | [upgrade-uninstall-054-r2.json](upgrade-uninstall-054-r2.json) |
| fresh-install-054-r2 | PASS | [fresh-install-054-r2.json](fresh-install-054-r2.json) |
| fresh-core-054-r2 | PASS_NATIVE_LINUX54_LIFECYCLE_CORE | [fresh-core-054-r2.json](fresh-core-054-r2.json) |
| fresh-portal-revoke-054-r2 | PASS | [fresh-portal-revoke-054-r2.json](fresh-portal-revoke-054-r2.json) |
| fresh-re-enroll-054-r2 | PASS | [fresh-re-enroll-054-r2.json](fresh-re-enroll-054-r2.json) |
| fresh-mcp-054-r2 | PASS_NATIVE_LINUX_MCP_54 | [fresh-mcp-054-r2.json](fresh-mcp-054-r2.json) |
| fresh-uninstall-054-r2 | PASS_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP | [fresh-uninstall-054-r2.json](fresh-uninstall-054-r2.json) |

The public wrapper forwarded approval-mode session correctly. A real bounded QA CLI session authorized the local MCP matrix, then closed and restored ASK. Both matrices proved initial20+retained100=120 numbered PTY lines exactly once, bounded20, UTF8 file/input roundtrips, staleSHA rejection without mutation and unique receipts for successful executions. The managed53 wrapper migrated with its original inode preserved in a0600 preimage. Real systemd crash injection proved installer rollback. Both uninstall phases revoked their own devices and removed wrapper/config/unit/data while preserving unrelated user files.

Two earlier harness failures remain recorded; their contract checks were corrected in a separate QA helper. They did not modify signed product files. The Linux portal fixture used a seeded2h QA cookie; this evidence does not claim OAuth login or cloudTRIAL mutation permission. Long24h/72h evidence is separate and still running. Existing53 holder identity/source/session were preserved.

Machine-readable pins, phase hashes and scope: [native-054-r2-lifecycle-summary.json](native-054-r2-lifecycle-summary.json).
