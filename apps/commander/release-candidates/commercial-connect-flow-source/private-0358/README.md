# Private QA candidate 0.3.58

This directory prepares a separate four-file candidate after native QA exposed a Windows startup failure and an update-task synchronization defect. Frozen 0.3.56 and 0.3.57 sources, signatures and receipts remain unchanged.

## Exact source admission

- Linux Agent: pinned 0.3.56 source; change its single version literal to 0.3.58.
- Linux installer: frozen connection-flow source; change its eight version literals to 0.3.58.
- Windows Agent: reviewed `source/windows-agent.ps1`, admitted unchanged. Its startup directory-permission operation uses an access-only DACL update so a normal account need not restore owner/group privileges.
- Windows installer: reviewed `source/windows.source-only-candidate.ps1`, admitted unchanged. Update and rollback confirm task termination before replacing files and poll for the expected restarted runtime.

The frozen connection controllers and Windows pairing helper remain embedded byte for byte. Windows derivation evidence lives in `source/DERIVATION-REPORT.json` and the two source patches.

`build_private_0358.py` takes `--source056`, `--connect-source`, `--windows-source`, `--public-jwk` and `--output`. The Windows source argument points to this directory's `source` folder. It verifies fixed input/output pins before creating an output directory outside the repository. It never signs or deploys.

The pinned manifest SHA-256 is `0c48cf879e5a8e564bb6554299c940a6414da64baf3477861450c6ee18be88dd`.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `agent/linux.py` | 265620 | `c63cf76c3953e029f650227ec25cc167a95f93f145ef3c41f0379d07cc1b007d` |
| `agent/windows.ps1` | 173192 | `bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d` |
| `install/linux.sh` | 72524 | `1e900f9d9accb11635cb2d5e8a2a7a1ad12b83fae644afde696c7f42a4f44bcd` |
| `install/windows.ps1` | 77495 | `27c856bb2b8ce8a100d8b258c8de544d99eb076ae8a0c6494110b17574ccfbc2` |

## Signing and distribution

`sign_private_commander_0358_v2.py` preserves the previous signer's custody, trust and readback checks. Its only AST changes are the module description, version, manifest pin and four artifact pins. The operator runs it in the existing native signing environment. No key is generated, exported or included in this directory.

The isolated distribution is scoped to the two QA guest addresses, `192.168.252.113/32` and `192.168.252.130/32`, on `virbr96`, serving port 18445 under a new unit/tag. Its hard deadline is **18:50Z on 28 October 2026**, with a maximum lifetime of 2700 seconds and automatic firewall cleanup. The existing public QA certificate remains unchanged; the previously scheduled Windows trust cleanup is not extended.

The server pins the actual signature-file SHA-256 `5735e88c87c27fdad7660751ef40e0689554c1c27c7adcc09385c0b417a6769e`; the distribution controller pins the final server source SHA-256 `2473223e3c671d2bc4b8b84f9ec7c65c9b20df57c0fdcd7eb1076155b981def0`. `distribution/SOURCE-REVIEW.json` records the exact derivation and unchanged custody/cleanup controls. Native build, signing and independent signature readback have separate receipts. A valid signature or active QA server alone does not establish native acceptance or public-release readiness.

Only sanitized receipts may be committed. Private credentials, raw native logs, temporary transfer bundles and signing keys are excluded.
