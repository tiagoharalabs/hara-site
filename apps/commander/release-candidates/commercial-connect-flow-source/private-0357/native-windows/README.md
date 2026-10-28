# Windows private 0.3.57 upgrade driver

This is a one-device QA execution driver, not a public installer. It performs the already authorized, signed private `0.3.56` to `0.3.57` update for the existing CommanderQA binding. It does not permit install, pair-existing, or re-enroll actions, and does not prompt for a token.

## Fixed scope

- Account SID: `S-1-5-21-1207901905-1500652706-889822281-1005`, profile `C:\Users\CommanderQA`.
- Existing device: `HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12`.
- Credential origin remains `https://commander.haralabs.com.br`.
- Artifact source is explicitly `https://192.168.10.23:18444/releases/0.3.57`, with normal HTTPS certificate verification and the controller's pinned v2 release signature verification.
- The existing `Connect-Commander.ps1` on the QA desktop must have SHA256 `2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da`. Its bytes are not modified.
- Installed Agent must initially be exactly `0.3.56`, SHA256 `a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620`, with its existing task running.
- CurrentUser and effective execution policy must be `RemoteSigned`, with no Process override.

The new Agent, installer and manifest hashes are fixed in the driver and matched against the built private release. Configuration bytes, device ID, approval mode, task XML, relevant Commander environment and execution-policy scopes must remain unchanged. The final version is read from the actual Agent; preserved configuration may retain historical version metadata.

## Native execution

First parse this file using the Windows PowerShell 5.1 native parser. Then stage and run it through the existing limited, interactive CommanderQA scheduled-task wrapper. The only parameter is a fresh JSON receipt path directly under the existing shared results directory:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -File "<staged-driver-path>" -NativeReceiptPath "C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\upgrade-0357-native.json"
```

The sanitized result and its `.progress.json` sibling inherit that directory's existing ACL, so the root SYSTEM wrapper can read them. Complete child stdout/stderr and error details stay in a newly created CurrentUser-only TEMP directory. They are not exported into the sanitized receipt.

The driver dot-sources the frozen controller and runs its core. Temporary in-process overrides constrain artifact URLs and exact hashes, refuse every action except one noninteractive `update`, capture private child logs, and make runtime recovery observation-only. They do not edit the controller on disk or weaken its signature checks.

The signed installer owns its normal update transaction and rollback. The driver never performs an additional rollback after a successful update. It also never kills the child halfway through its transaction: progress updates occur every 15 seconds, with a `long_running` flag after 240 seconds. The root operator must monitor the existing task wrapper and progress receipt; do not apply a short automatic wrapper timeout during the update.

Success requires the exact 0.3.57 Agent hash, a new matching runtime start, a fresh Agent heartbeat, an independently authenticated credential heartbeat, and all preservation checks. Event V2 is reported only when an explicit supported runtime field exists; otherwise the result is `NOT_OBSERVED`. It is not an invented release gate.

## Validation status

Local checks confirm the driver pins match the built 0.3.57 manifest and that the frozen controller hash is unchanged. Windows PowerShell 5.1 native parsing and the actual private update are pending. No native success is claimed by this directory.
