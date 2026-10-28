# Windows connect flow — source candidate

This directory contains a standalone connect controller, its isolated native
fixture harnesses, and a generated installer source candidate. It does not modify
the previously signed `0.3.56` installer or publish a release.

## Behavior

The default connect flow reads the current user's existing device configuration
strictly. A present but malformed, unreadable, or incomplete configuration is a
hold; it is never treated as a clean machine. Existing origin, credentials,
approval mode, task ownership and manual-start policy are preserved.

For an enrolled machine, connect submits an authenticated heartbeat using the
**actual installed Agent version** and requires the expected device ID. It then
verifies the current runtime and checks the latest signed release. A current
version is left alone. A newer verified version uses that release's verified
installer update transaction. An older release channel never causes a downgrade.

A release-discovery failure can return `CONNECTED_UPDATE_HOLD` when the existing
connection has been independently validated. This is distinct from successful
update and from a failed binding. A same-version local Agent hash mismatch is a
hold and is not reported as a trustworthy local connection. Failed updates must
independently re-establish preserved credentials, a known Agent hash and runtime
before the controller can report the connection as recovered.

For an unpaired machine, release verification happens before the secure code
prompt. Clean installation uses the verified install action. Existing unpaired
Agent files require the signed installer's `HARA_COMMANDER_PAIR_EXISTING=1`
capability. An existing credential can enter re-enrollment only after an explicit
`401 DEVICE_AUTH_INVALID`; timeouts, other HTTP errors and mismatched responses
are holds. Windows re-enrollment additionally requires the signed installer's
`HARA_COMMANDER_REENROLL=1` capability.

## Shared signed release discovery contract

1. Fetch the configured Commander origin's `/release/agent-manifest.json` and
   adjacent `.sig.json` through normal HTTPS with redirects disabled.
2. Verify the pinned `commander-release-v2` signature and the exact manifest
   schema, product, stable channel, semantic version and four-file inventory.
3. Derive the immutable origin `/releases/<agent_version>`. Its signed manifest
   must be byte-identical to the signed discovery manifest.
4. Download the Windows Agent and Windows installer from that immutable path.
   Verify both against their signed byte lengths and SHA-256 values, and verify
   the Agent's declared version.
5. Execute only the verified installer for an explicit action. The default
   connect path never executes a mutable, unverified latest installer.

The explicit `-QaReleaseBaseUrl` override is for a known, version-specific QA
distribution. Its path must match `/releases/<signed version>` and every signature,
manifest and payload check still applies. It does not establish that the public
latest channel is fixed or that future updates will be discoverable there.

## Preserving an installed but unpaired machine

`Preserved-Pairing.ps1` implements the next installer's `pair-existing` and
`re-enroll` actions. The helper verifies and caches the signed target Agent before
asking for a code. It records private preimages of the files and task definition,
and checks DPAPI readiness. It does not recursively delete the product directory.

After enrollment, the new credential is encrypted for the current Windows user
and a private recovery receipt is flushed to disk before product changes. The new
credential must authenticate before local commit. An existing task is preserved;
a missing task is registered without `-Force`. Failure revokes the new enrollment
when possible, restores the precise old configuration and Agent bytes and ACLs,
and restores the previous task state. An inactive re-enrollment remains inactive
until the outer explicit connect action requests a start.

If revocation or rollback cannot be confirmed, private preimages and the encrypted
recovery receipt remain in the printed private staging directory. The receipt is
marked `NEEDS_RECONCILIATION`: an operator must reconcile the actual current
device/configuration before deciding whether to revoke a pending enrollment.
It must not be copied into GitHub evidence or printed with decrypted credentials.

## Files and verification scope

- `Connect-Commander.ps1`: standalone controller, default connect behavior.
- `Test-ConnectController.ps1`: native-ready isolated orchestration, credential
  classification, RSA signature and immutable-release fixture tests. Its RSA
  key is ephemeral and unrelated to the pinned production verification key.
- `Preserved-Pairing.ps1`: source-only transactional pairing helpers.
- `Test-PreservedPairing.ps1`: isolated temporary-file transaction fixtures with
  actual Windows ACL and DPAPI checks. Enrollment, network, tasks and execution
  are mocked; the tests never use production device credentials or product paths.
- `build_windows_candidate.py`: deterministic source generator. It accepts the
  pinned original installer from the local source layout or the repository's
  `commercial-0.3.56-source/install/windows.ps1` sibling, derives the pinned
  payload-preflight changes, and embeds the exact controller and pairing helper.
- `windows.source-only-candidate.ps1`: generated unsigned installer source. Its
  default action is `connect`; explicit install/update actions prevent recursion
  when the controller delegates to the matching signed installer.
- `source-candidate-report.json`: source provenance and release limitations.

Run the harnesses from this directory in Windows PowerShell 5.1 in an isolated
native test session. Pass explicit source paths to avoid parameter-default
binding differences in Windows PowerShell hosts:

```powershell
$controllerPath = (Resolve-Path .\Connect-Commander.ps1).Path
$helperPath = (Resolve-Path .\Preserved-Pairing.ps1).Path
powershell.exe -NoLogo -NoProfile -File .\Test-ConnectController.ps1 -Controller $controllerPath
powershell.exe -NoLogo -NoProfile -File .\Test-PreservedPairing.ps1 -Controller $controllerPath -Helper $helperPath
```

Native results are recorded separately by the deployment operator. Generating the
candidate or passing fixture tests does not prove real account enrollment, a real
upgrade to a newer signed release, or public release readiness.

### Native validation reported by the deployment operator

The 23 controller fixture cases passed in Windows PowerShell on 28 October 2026
at **17:09:09 UTC / 14:09:09 Brasilia**, with exit code 0 and no stderr. The real
product configuration, Agent and CurrentUser execution policy were unchanged.
The final generated candidate (`68f0a769...`), pairing helper and transaction
harness passed native parsing. The actual production controller
run finished at **17:10:31 UTC / 14:10:31 Brasilia** with a validated existing
connection, a fresh heartbeat at **17:10:16 UTC**, and the update held because the
public channel could not pass verification. It preserved the real configuration,
Agent and execution policy. The final transaction run passed **14 of 14 cases**
from **17:37:14.436 to 17:37:24.389 UTC / 14:37 Brasilia**, exit code 0 and no
stderr. Real product configuration, Agent and CurrentUser execution policy stayed
unchanged. These are isolated fixture results; the candidate's real-account
`pair-existing`/re-enrollment and newer signed upgrade remain unexecuted at this
checkpoint. `validation-status.json` records the version-specific status.

The first controller fixture run exposed a test-only Windows compatibility issue:
assigning `RSA.Create().KeySize` raised a read-only-property error. The fixture now
constructs an ephemeral `RSACng(2048)` directly and verifies its size. The pinned
production verification key and controller bytes were not changed. The original
failure and corrected native run belong to the deployment evidence.

The first transaction fixture invocation also stopped before its cases because
its parameter defaults attempted to use an empty `PSScriptRoot`. The fixture now
resolves missing sibling paths in its body, with `MyInvocation.MyCommand.Path` as
a fallback; explicit source arguments are recommended in the commands above.

The transaction diagnostic then identified `PrivilegeNotHeldException` while
reapplying a complete `Get-Acl` object with `Set-Acl`. Bytes had been restored, but
restoring the complete security descriptor requested unavailable privileges.
The correction creates a new `FileSecurity` object containing only the saved
access-rule section, applies it through `File.SetAccessControl`, and verifies
unchanged owner/group plus exact ACE bytes, order and protection. It never takes ownership
or edits audit rules. This follows Microsoft's documented
[section-specific security-descriptor API](https://learn.microsoft.com/en-us/dotnet/api/system.security.accesscontrol.objectsecurity.setsecuritydescriptorsddlform?view=netframework-4.8.1)
and [ACL-copy procedure](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.setaccesscontrol?view=netframework-4.8.1).
The existing rollback fixtures now require full file/ACL/runtime restoration and
absence of retained temporary stages for a confirmed successful rollback.
The follow-up native diagnostic proved that Windows normalized only the DACL
descriptor's `AUTO_INHERITED` bookkeeping bit (`0x400`). Readback comparison now
permits only that observed metadata difference; every ACE byte, inherited-ACE
flag, protection bit and other descriptor flag—including auto-inherit-required
`0x100`—must still match. The final 14-case native pass includes those stronger
rollback assertions and CurrentUser-DPAPI recovery checks.

## Before publication

The generated installer still inherits the `0.3.56` source constants. Choose a new
coherent release version and update/sign the complete release bundle before
publishing. Do not replace bytes inside the existing immutable signed `0.3.56`
release. The website should invoke the new installer's default connect flow only
after that coherent release has been verified end to end.
