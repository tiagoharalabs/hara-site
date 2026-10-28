# Windows QA launcher — existing CommanderQA session

These launchers target the existing standard `CommanderQA` account, SID
`S-1-5-21-1207901905-1500652706-889822281-1005`, profile
`C:\Users\CommanderQA`. They do not change a password, request elevation,
generate pairing authority, or modify the signed installer.

## Native outcome — 27 October 2026, Sao Paulo time

The root operator completed **R4 `PASS_NATIVE_PREFLIGHT`, exit 0**, through the
actual `Verificar-Commander.cmd` entry at **23:39:18**
(`2026-10-28T02:39:18Z`). It ran in native PowerShell 5.1 as the existing standard,
interactive CommanderQA account. Commander health, the exact .56 manifest and
signature, and task prerequisites passed. CurrentUser execution policy returned
to `Undefined`. This preflight did not install or pair the product:
`installed=false`, `paired=false`.

Earlier attempts did not establish unattended certificate import. The
CurrentUser `X509Store.Add` attempt waited on certificate trust confirmation;
the original progress logger also hid replacement errors, which initially made
the last visible stage misleading. After that logger was corrected, R3's
`certutil -user -f -addstore Root` attempt still reached its 45-second timeout and
was cleaned up. **Neither path is an unattended-import PASS on this VM.**

For R4, the authorized root operator temporarily provisioned the exact public QA
certificate in **LocalMachine Root on this dedicated Windows QA VM** using the
normal administrative certificate API. The active config's per-user certificate
fields are blank, so the successful wrapper run did not attempt a user trust
prompt. Normal HTTPS validation and signed-manifest verification remained active;
no validation callback or insecure TLS flag was used. An owned SYSTEM task is
scheduled to remove that temporary trust at **28 October 00:09 Sao Paulo time**
(`2026-10-28T03:09:00Z`) or at startup, preserving any recorded preexisting
certificate. Scheduling is not itself proof of cleanup; read
`results\admin-tls-cleanup.json` and the certificate store afterward.

At **23:42:30** (`2026-10-28T02:42:30Z`), the root operator preserved the old
disabled sarti task's XML and SDDL, removed that task, and recorded the product
task slot ready for CommanderQA. No old task was enabled or executed.

**Still required:** legitimate access to `openai-reviewer@haralabs.com.br` and a
fresh pairing token, then actual installation, enrollment and product lifecycle
checks. The existing account password was not recovered or changed. These
results do not approve public release.

## Added QA payload check after the public hash failure

The launcher now follows the real official manifest/signature preflight with a
raw-byte download from the same configured release URL. Before invoking any
pairing/install prompt, both `preflight` and fresh `install` require the Windows
Agent to be exactly **172,687 bytes**, SHA-256
`a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620`, and
declared version `0.3.56`. The result records `agent_payload_verified`, observed
bytes/hash/version, and cache cleanup. The temporary payload is created in the
owner-only QA run directory and removed in `finally`, including after a mismatch.
No pairing token is read or consumed by this check.

This is a **QA wrapper backstop**, not a repair of the public distribution. The
signed official installer and manifest remain unchanged. The official installer
still performs its own later verified download; this campaign therefore uses
the root operator's pinned, immutable private asset server. The previously
recorded R4 preflight did not contain this payload check and must not be cited as
native acceptance of the new guard. The updated wrapper needs native parser and
payload-preflight readback before that new result is claimed. An already valid
installed Agent retains its existing local-pin/start path without a remote fetch.

## Desktop files

Place these together with the already delivered installer:

- `Instalar-Commander.cmd`: double-click to install, or verify/start an existing
  exact .56 installation owned by CommanderQA. The console remains open on
  success or failure.
- `Verificar-Commander.cmd`: double-click for the genuine official installer
  preflight; it never invokes enrollment or mutates the product task.
- `Instalar-ou-verificar-Commander.ps1`: hash-pinned by both CMD launchers.
- `instalar-commander-0.3.56.ps1`: existing official installer, SHA-256
  `2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401`.

The CMD entry checks the account and wrapper hash, records the prior policy in
memory, explicitly applies CurrentUser `RemoteSigned`, and invokes the wrapper.
The wrapper persists that prior value in its private run directory. Neither
entry uses `Bypass` or a Process policy override. A configured `AllSigned` or
unexpected Process policy is refused; a controlling policy that prevents
RemoteSigned is not overridden.

Preflight and unsuccessful fresh installation restore the original CurrentUser
policy. A verified existing/new installation retains RemoteSigned so its real
scheduled task can start later. The existing product has no logon/startup trigger.

## Administrator configuration

Root must stage a real configuration at:

`C:\ProgramData\HARA-QA\windows-install-0356-20261028\config\install-config.json`

The `HARA-QA` directory, installation directory, config directory, config file,
and optional certificate must be owned by SYSTEM or Administrators, with no
write/delete/DACL/owner permissions granted to other principals. CommanderQA
needs read/execute access. Reparse components are refused.

`install-config.example.json` is intentionally incomplete: its release URL is
empty and task clearance is `PENDING`. Supply an explicitly approved HTTPS
release URL with path `/releases/0.3.56`; there is no default private endpoint.
The root's tested temporary endpoint is
`https://192.168.10.23:18443/releases/0.3.56`; this is an operator configuration,
not a permanent public distribution endpoint.

The public DER used in this campaign has SHA-256
`919ef57067af12ae157a742a871edaa7bb03f661d437accc4639c0d71a207933`.
The included DER is the public certificate converted from the root-supplied PEM.
No private key is present or transferred. **For the tested R4 configuration,
leave `tls_certificate_file` and `tls_certificate_sha256` blank:** administrative
temporary trust has already been provisioned as described above. Do not switch
back to the timed-out CurrentUser import path and describe it as tested success.

The retained optional per-user import code pins the DER and records a preimage,
uses native certutil with asynchronous output draining and a 45-second bound,
verifies exact store bytes, and attempts cleanup of its own partial addition.
That implementation is retained for diagnosis; its R3 timeout remains a HOLD.
No certificate-validation callback is used. Independent native store readback is
required after any trust cleanup; process termination can prevent `finally`.

For fresh installation only, root must first preserve/archive the old disabled
sarti task and clear the global product-task name. Then set
`task_slot_clearance: "EMPTY_FOR_COMMANDERQA"` with the actual verification time
in `task_slot_verified_utc`. Clearance older than four hours is refused. This
admin-owned attestation complements the standard user's task query, because a
foreign task may be invisible to that user. Preflight does not require clearance.
The current campaign has completed that task-slot preparation. The temporary
distribution/trust window ends before the four-hour slot-clearance limit; if it
has ended, the operator must renew the authorized QA preparation before install.

## Actual install and verification

Fresh installation runs the unmodified installer and uses its real secure
pairing-token prompt. The token must come from legitimate authenticated access
to the intended `openai-reviewer@haralabs.com.br` account. The Identity password
is not a pairing token. No authentication, enrollment response, signature,
scheduled task, or heartbeat is mocked.

An existing installation is accepted only with the exact Agent hash, expected
config origin/version/approval mode, and CommanderQA Limited/Interactive task
with the expected action and no triggers. It skips ephemeral distribution/TLS
setup, starts the task if needed, and checks recent heartbeat. It never enrolls
that installation again. Partial files/task state are reported for operator
repair instead of being deleted.

Sanitized results and policy preimage are written under
`%LOCALAPPDATA%\HARA Commander QA\run-...\`, in a new owner-only directory.
The wrapper removes the child's temporary private error stream and reports an
error code/stage. It does not put passwords or plaintext tokens in its reports.
The official product stores its own encrypted device token in its normal config.

## Native evidence and remaining acceptance

The root operator's native records are under
`C:\ProgramData\HARA-QA\windows-install-0356-20261028`:

- `results\preflight-r4-result.json` and `preflight-r4-console.txt`: actual CMD
  preflight and wrapper result.
- `results\task-slot-ready.json`: controlled old-task migration and empty slot.
- `backup\sarti-agent-task.xml`, `sarti-agent-task.sddl`, and
  `task-migration-preimage.json`: preserved old task.
- `backup\admin-tls-preimage.json`: administrative trust preimage and deadline.
- `results\admin-tls-cleanup.json`: cleanup result when the scheduled operation
  executes; this file's success must be checked independently.

The native parser and R4 preflight have already passed; do not relabel them as
installation. Remaining acceptance is genuine pairing and installation under
CommanderQA, exact installed Agent/task/config/runtime checks, then the required
product lifecycle/rollback checks. The launcher author performed local code work;
the root operator performed the native execution and supplied the result above.
