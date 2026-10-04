# H.A.R.A. Commander Windows Acceptance CURRENT — 2026-10-03

This file supersedes `docs/status/HARA_COMMANDER_WINDOWS_ACCEPTANCE_CURRENT_20260926.md`
for the current Windows 11 acceptance path.

## Canonical VM

```text
HOST=nucleo-a
VM=commander-win11
IP=192.168.122.177
WINDOWS=Windows 11 Pro 10.0.26200
QEMU_GUEST_AGENT=RUNNING
WINDOWS_AUTOMATION_CHANNEL=QGA_LIVE
```

## Production hotfix 0.3.12

A live Windows acceptance run exposed a production-blocking syntax defect in the
stable Windows Agent. Pairing reached the backend and the installer verified the
downloaded Agent integrity, but Windows PowerShell 5.1 rejected the Agent before
installation.

Observed acceptance evidence before the repair:

```text
PAIRING_TOKEN_LEN=43
PAIRING_TOKEN_EXPOSED=FALSE
HARA_COMMANDER_AGENT_INTEGRITY=PASS
AGENT_INSTALL_SYNTAX_INVALID=TRUE
HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=PASS
```

The rollback revoked the temporary enrolled device and removed local installation
state, so the failed acceptance attempt did not leave a usable device credential
or installed Agent behind.

Two Windows PowerShell 5.1 parser defects were proven in the startup block:

1. an unbalanced parenthesis in the `Try-SetRuntimeStatus` startup condition;
2. a multiline startup-config condition with leading `-or` operators that the
   actual Windows PowerShell 5.1 parser rejected.

The installer was also hardened to trim the human-entered one-time pairing token
before enrollment so incidental leading/trailing whitespace cannot alter the
pairing hash.

## Source and release identity

```text
SOURCE_BRANCH=local/hara-commander-win0312-20261003
SOURCE_COMMIT=8d9cb609a161a3531761cd3df28cd7284f4f8aec
AGENT_VERSION=0.3.12
CLOUDFLARE_VERSION_ID=3fc6d776-00be-452d-af6a-d0d9fcf0ddc1
PROD_DOMAIN=https://commander.haralabs.com.br
```

Public release hashes:

```text
agent/linux.py        7c54ac2a2450c4ab2301023ab0256d57c523261158b48be8ad114fd7f44bddc0
agent/windows.ps1     81968ad758895ee601058b6538f7ab4a6d54352cee77fc58faef425c5840dccb
install/linux.sh      d90f58c3bc7db2ad1903bd4dccac32f0e31416728ecef15e092bfc88d41fcfe0
install/windows.ps1   0b6187c227260d0703fb31423dd5e6ab445a859229fdf0127e7834e5ec8fcfa3
```

The production `agent-manifest.json` reports `0.3.12` and the live files served
by the public domain hash exactly to those values.

## Validation

Source/package validation completed successfully on the Commander package,
including:

```text
COMMANDER_RELEASE_MANIFEST=PASS
COMMANDER_RELEASE_SHA256SUMS=PASS
WINDOWS_DEVICE_INSTALLER_STATIC=PASS
WINDOWS_INSTALLER_REDIRECT_FAIL_CLOSED=PASS
WINDOWS_INSTALLER_DEVICE_TOKEN_MEMORY_HYGIENE=PASS
COMMANDER_EXACT_FIVE_TOOL_AGENT=PASS
ARBITRARY_SHELL_EXPOSED=FALSE
COMMANDER_EVENT_V2_PRODUCTIZATION=PASS
COMMANDER_BILLING_V1_RELEASE_GATE=PASS
COMMANDER_PROD_CONFIG=PASS
```

The 0.3.12 candidate was then transferred to the actual Windows VM and tested
with the native Windows PowerShell runtime before production publication:

```text
WINDOWS_POWERSHELL_VERSION=5.1.26100.9444
WINDOWS_PS51_AGENT_PARSE_ERRORS=0
WINDOWS_PS51_INSTALLER_PARSE_ERRORS=0
COMMANDER_WINDOWS_OPERATOR_SESSION_GATE=PASS
COMMANDER_WINDOWS_CONSOLE_SANITIZATION=PASS
COMMANDER_WINDOWS_FIVE_TOOL_BRIDGE=PASS
COMMANDER_WINDOWS_ARBITRARY_FUNCTION=DENIED
COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS
WINDOWS_AGENT_0312_SELFTEST=PASS
```

After deployment, the VM downloaded the public production files again and
repeated the proof against the live bytes:

```text
LIVE_MANIFEST_VERSION=0.3.12
LIVE_AGENT_PARSE_ERRORS=0
LIVE_INSTALLER_PARSE_ERRORS=0
LIVE_WINDOWS_PS51_AGENT_PARSE=PASS
LIVE_WINDOWS_PS51_INSTALLER_PARSE=PASS
LIVE_WINDOWS_AGENT_SELFTEST=PASS
```

## Current gate

The code/release defect is closed. The next acceptance action is a fresh
operator-generated production pairing from the logged-in Windows user session.

```text
WINDOWS_0312_SOURCE=PASS
WINDOWS_0312_PROD_DEPLOY=PASS
WINDOWS_0312_PUBLIC_HASH_READBACK=PASS
WINDOWS_0312_PS51_PARSE=PASS
WINDOWS_0312_AGENT_SELFTEST=PASS
FRESH_PROD_PAIRING_RETEST=PENDING_HUMAN_ONE_TIME_INPUT
POST_PAIRING_TASK_ACL_DPAPI_HEARTBEAT=PENDING
REBOOT_RECONNECT=PENDING
OPENAI_SELECTED_DEVICE_E2E=PENDING
```

The one-time pairing secret must remain human-entered inside the Windows session;
it must not be copied into Git, chat, logs, or automation evidence.


## Windows portal bootstrap hotfix — 2026-10-03

A post-0.3.12 acceptance retest proved that the Agent/installer payloads were fixed,
but the portal's copied Windows bootstrap still executed the installer through
`Invoke-RestMethod` + `Invoke-Expression`. In the logged-in Windows PowerShell
session this failed immediately after secure pairing input with
`InvokeMethodOnNull`; the fresh D1 pairing remained unconsumed and no new device
row was created, proving the failure happened before `/api/device/enroll`.

The portal bootstrap was changed to fail-closed file execution:

```text
FETCH=Invoke-WebRequest -> unique TEMP .ps1
REDIRECTS=DENIED
EXECUTION=powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File
CHILD_EXIT=PROPAGATED
TEMP_FILE=REMOVED_IN_FINALLY
IEX=ABSENT
CANONICAL_ORIGIN_PIN=PASS
```

Regression coverage now requires the file-execution flow and explicitly denies the
old `iex ([string]$haraBootstrap)` / `$haraBootstrap=irm` path.

```text
SOURCE_COMMIT=9d1f9c1c59a5169ec606b9000049aef79a60e172
CLOUDFLARE_VERSION_ID=69ee4b70-839c-4c9c-a4ff-1e648f105083
COMMANDER_SUPPLY_CHAIN_WINDOWS_BOOTSTRAP_IEX_ABSENT=PASS
COMMANDER_SUPPLY_CHAIN_WINDOWS_BOOTSTRAP_FETCH_FAILURE_PROPAGATES=PASS
LIVE_IEX_COUNT=0
LIVE_FILE_EXEC_MARKERS_INDEX_AND_APP_JS=PASS
LIVE_HEALTH=PASS
```

The next operator action is to hard-refresh the Commander portal, generate a new
one-time pairing code and copy the newly served Windows command. Older copied
commands containing `iex` must not be reused.


## Windows installer temp-extension hotfix 0.3.13 — 2026-10-03

The 0.3.12 Agent and portal bootstrap were both healthy, but the real Windows
installer still failed its internal Agent self-test after successful pairing and
integrity verification.

A controlled Windows PowerShell 5.1 probe proved the exact cause:

```text
GOOD_PS1_EXIT=0
BAD_FILE=C:\Windows\Temp\hara-ext-bad.ps1.install
BAD_RESULT=PowerShell rejected -File because the filename did not end in .ps1
BAD_INSTALL_EXIT=1
```

The installer used:

```text
$InstallTmp = $Agent + ".install"
```

and then executed that file with `powershell.exe -File`. Windows PowerShell
5.1 refuses `-File` inputs whose final extension is not `.ps1`.

The 0.3.13 hotfix changes the temporary path to:

```text
$InstallTmp = $Agent + ".install.ps1"
```

and adds a regression guard that requires the `.ps1` suffix and denies the old
invalid extension.

Validation on the actual Windows acceptance VM:

```text
WINDOWS_POWERSHELL_VERSION=5.1.26100.9444
AGENT_PARSE_ERRORS=0
INSTALLER_PARSE_ERRORS=0
INSTALL_TMP_SELFTEST_EXIT=0
WINDOWS_INSTALL_TMP_PS1_SELFTEST=PASS
```

The live production release was then downloaded again by the VM and retested:

```text
LIVE_AGENT_SHA256=a9d9a9e6dbe57bf31e37aa8b053470da7f336545057cc09167d91173c43cdb5e
LIVE_INSTALL_TMP_SELFTEST_EXIT=0
LIVE_WINDOWS_INSTALL_TMP_PS1_SELFTEST=PASS
```

Release identity:

```text
SOURCE_COMMIT=46fbd05d3665911bdd3ccbb0cdb27a06793ebdc9
AGENT_VERSION=0.3.13
CLOUDFLARE_VERSION_ID=863cbd12-c187-4aa3-b3b4-c8e9ab28eb45
PUBLIC_AGENT_WINDOWS_SHA256=a9d9a9e6dbe57bf31e37aa8b053470da7f336545057cc09167d91173c43cdb5e
PUBLIC_INSTALL_WINDOWS_SHA256=9793c5523f93901ef6af44639ce71a85ffef7947a94f3c0e9a4e9149de68971c
```

The next gate is a fresh operator-generated production pairing using the final
0.3.13 installer. After success, continue with task/ACL/DPAPI/heartbeat,
reboot/reconnect and OpenAI selected-device E2E.


## Windows Scheduled Task hotfix 0.3.14 — 2026-10-03

The 0.3.13 install path reached Scheduled Task registration after successful
pairing, Agent integrity verification and Agent self-test. The real user-session
install then failed because the installer reused the typed top-level parameter
`[string]$Action` for the object returned by `New-ScheduledTaskAction`.
PowerShell converted/lost the expected CIM task-action object before
`Register-ScheduledTask`.

The installer now uses a dedicated `$TaskAction` variable and regression guards
deny reuse of `$Action` for Scheduled Task objects.

A real user-session probe on `HARA_WIN11\sarti` proved:

```text
USER=HARA_WIN11\sarti
PARAM_ACTION_TYPE=System.String
TASK_ACTION_TYPE=Microsoft.Management.Infrastructure.CimInstance
TRIGGER_USER=sarti
TASK_REGISTERED=True
TASK_STATE=Ready
USER_TASK_PROBE=PASS
TASK_CLEANUP=True
```

Release identity:

```text
SOURCE_COMMIT=189d5a6a90de1f1ad31166651e773e37d1f4b6e0
AGENT_VERSION=0.3.14
CLOUDFLARE_VERSION_ID=77c5a8ff-b53a-4174-9650-bc51fd29cf2f
PUBLIC_AGENT_WINDOWS_SHA256=acbe9f4e6c6ce782b02e581b7aa44a5ce007c680dd358d2ffc0bfb381ce709f4
PUBLIC_INSTALL_WINDOWS_SHA256=4b28491f9840ef27005a138e3050c08dd2bab3c8cce2b592c1637cb958f8996e
```

The production installer was read back from the public domain and confirmed to
contain `$TaskAction = New-ScheduledTaskAction` and
`Register-ScheduledTask ... -Action $TaskAction`; production health remained
PASS.

Next gate: one fresh production pairing on the canonical Windows VM, followed by
task/config custody, heartbeat, online/offline, reboot/reconnect and OpenAI
selected-device E2E.


## Successful Windows 0.3.14 production enrollment — 2026-10-03

The canonical Windows acceptance VM completed a fresh production enrollment with
the public 0.3.14 release.

Installer output:

```text
HARA_COMMANDER_AGENT_INTEGRITY=PASS
HARA_COMMANDER_AGENT_SELF_TEST=PASS
HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS
HARA_COMMANDER_DEVICE_ENROLLMENT=PASS
HARA_COMMANDER_AGENT_TASK=REGISTERED_INERT_UNTIL_LOCAL_SESSION
DEVICE_ID=HARA-DEVICE-64adbd7a-02b1-4890-acdb-9543e8b48d00
DEVICE_TOKEN_EXPOSED=FALSE
SESSION_AUTHORITY=LOCAL_OPERATOR_TERMINAL
```

D1 readback immediately after enrollment:

```text
DEVICE_STATE=ACTIVE
AGENT_VERSION=0.3.14
PLATFORM=WINDOWS
ARCHITECTURE=x64
TUNNEL_MODE=OUTBOUND_RELAY_OFFLINE
REVOKED_AT=NULL
```

The offline relay state is expected until the human operator opens the local
authorization session.

Post-install custody/persistence checks:

```text
SCHEDULED_TASK=HARA Commander Agent
TASK_PRINCIPAL_USER=sarti
TASK_PRINCIPAL_LOGON=Interactive
TASK_PRINCIPAL_RUNLEVEL=Limited
TASK_ACTION=powershell.exe ... hara-commander-agent.ps1
TASK_TRIGGER_USER=HARA_WIN11\sarti
SYSTEM_READ_COMMANDER_ROOT=DENIED
```

The first task execution was observed as interrupted with `0xC000013A`. Restarting
the already-installed Scheduled Task (without reinstall or re-pair) established
stable persistence:

```text
TASK_START_REQUEST=PASS
T+1..T+12=Running
PID=9284
FINAL_STATE=Running
LAST_RESULT=0x00041301
```

A later independent readback still showed:

```text
PROCESS_PID=9284
PROCESS_NAME=powershell.exe
TASK_STATE=Running
TASK_PRINCIPAL=sarti
TASK_LOGON=Interactive
TASK_RUNLEVEL=Limited
LAST_RESULT=0x00041301
```

Current gate:

```text
WINDOWS_0314_ENROLLMENT=PASS
WINDOWS_0314_AGENT_INTEGRITY=PASS
WINDOWS_0314_SELFTEST=PASS
WINDOWS_0314_STARTUP_ATTESTATION=PASS
WINDOWS_0314_TASK_PERSISTENCE=PASS
WINDOWS_0314_SYSTEM_CUSTODY_BOUNDARY=PASS
LOCAL_OPERATOR_SESSION=PENDING_HUMAN_OPEN
ONLINE_HEARTBEAT_AFTER_LOCAL_SESSION=PENDING
FIVE_TOOL_LIVE_E2E=PENDING
REBOOT_RECONNECT=PENDING
OPENAI_SELECTED_DEVICE_E2E=PENDING
```


## Windows live selected-device five-tool proof — 2026-10-03

After the operator opened the local authorization console, the canonical Windows
device transitioned from `OUTBOUND_RELAY_OFFLINE` to `OUTBOUND_RELAY` and the
Founder subject selection was moved to the Windows device.

```text
DEVICE_ID=HARA-DEVICE-64adbd7a-02b1-4890-acdb-9543e8b48d00
DEVICE_NAME=HARA_WIN11
AGENT_VERSION=0.3.14
DEVICE_STATE=ACTIVE
TUNNEL_MODE=OUTBOUND_RELAY
LOCAL_SESSION=AUTHORIZED
SELECTED_DEVICE=HARA_WIN11
```

A real device-level five-tool run through the production D1 queue and Agent
completed all five governed operations:

```text
hara.health=COMPLETED/PASS
hara.functions.list=COMPLETED/PASS
hara.functions.describe(device.info)=COMPLETED/PASS
hara.functions.invoke(device.info)=COMPLETED/PASS
hara.receipts.get(invoke receipt)=COMPLETED/PASS
```

Health result identified the exact Windows target:

```text
hostname=HARA_WIN11
platform=WINDOWS
architecture=x64
agent_version=0.3.14
powershell_version=5.1.26100.9444
tunnel_mode=OUTBOUND_RELAY
hara_services_state=PASS
services_bridge_state=PASS
```

The live invoke completed with process exit code 0 and generated receipt SHA:

```text
INVOKE_RECEIPT_SHA256=2fc0a2d1eb09741568b001f9c2a15244dcedaeb1d6ae9a6992996c5854f92355
INVOKE_FUNCTION=device.info
INVOKE_RISK_CLASS=READ_ONLY
INVOKE_MUTATION_PERFORMED=FALSE
```

The fifth tool retrieved the same invoke receipt and proved:

```text
schema=hara.commander-device-receipt.v1
device_id=HARA-DEVICE-64adbd7a-02b1-4890-acdb-9543e8b48d00
tool_id=hara.functions.invoke
function_id_if_any=device.info
transport_mode=OUTBOUND_RELAY
state=PASS
payload_values_persisted=false
result_binding=STDOUT_SHA256_V1
result_stdout_sha256=9b26cad74ad82c8914620b2d2d20e5638a13447a5b88619cd96c50318f66e666
```

OpenAI negative N3 was also executed against the live selected Windows device:

```text
REQUEST=hara.functions.invoke(function_id=shell.run, argv=[whoami])
FINAL_STATE=FAILED
ERROR_CODE=UNKNOWN_FUNCTION_ID
RESULT_STATE=DENIED
MUTATION_PERFORMED=FALSE
OPERATIONAL_AUTHORITY=LOCAL_OPERATOR_SESSION
```

This proves exact-function fail-closed behavior with no shell fallback.

The canonical customer-MCP harness remains pending because the local 0600
`mcp-product-prod-token` custody file is not materialized on Storage, Services
or nucleo-a. Existing handoff explicitly says not to repeat product-token
provisioning, so the PROD secret was not rotated.

Next gates:

```text
WINDOWS_SELECTED_DEVICE_FIVE_TOOL=PASS
WINDOWS_NEGATIVE_UNKNOWN_FUNCTION=PASS
WINDOWS_REBOOT_RECONNECT=PENDING
CUSTOMER_MCP_FIVE_TOOL_HARNESS=PENDING_TOKEN_CUSTODY_RECOVERY
OPENAI_EXTERNAL_CLIENT_E2E=PENDING
OPENAI_NEGATIVE_N1_ARBITRARY_SHELL=PREPARED
OPENAI_NEGATIVE_N2_CROSS_TENANT=PREPARED
OPENAI_NEGATIVE_N3_UNKNOWN_FUNCTION=LIVE_PASS
```


## Windows reboot/reconnect proof — 2026-10-03

The canonical VM was powered off and started again from nucleo-a. After Windows
login as the enrolled user, the QEMU Guest Agent and the Commander Scheduled Task
were both revalidated.

```text
VM_STATE=running
QGA=PASS
IPV4=192.168.122.177
INTERACTIVE_USER=HARA_WIN11\sarti
TASK_PRESENT=True
TASK_STATE=Running
TASK_LAST_RESULT=0x00041301
TASK_LAST_RUN_UTC=2026-10-03T23:02:08Z
AGENT_PROCESS_PID=3952
```

The PROD device record remained:

```text
DEVICE_STATE=ACTIVE
AGENT_VERSION=0.3.14
REVOKED_AT=NULL
TUNNEL_MODE=OUTBOUND_RELAY_OFFLINE
LAST_SEEN_AT=2026-10-03T23:02:28.763Z
```

`OUTBOUND_RELAY_OFFLINE` after reboot is expected until the operator explicitly
opens the local authorization session again. The Agent daemon itself restored
automatically from the Scheduled Task after user login.

```text
WINDOWS_REBOOT_RECONNECT=PASS
WINDOWS_AGENT_AUTOSTART_AFTER_LOGIN=PASS
WINDOWS_LOCAL_AUTH_SESSION_AUTO_REOPEN=DENIED_BY_DESIGN
```


## Overnight continuation checkpoint — 2026-10-03

Safe stop state before the next OpenAI/OAuth session:

```text
VM=commander-win11
VM_STATE=running
INTERACTIVE_USER=HARA_WIN11\sarti
COMMANDER_AGENT_TASK=Running
COMMANDER_AGENT_PID=3952
COMMANDER_AGENT_VERSION=0.3.14
PKCE_LISTENER_ACTIVE=false
WINDOWS_SELECTED_DEVICE_FIVE_TOOL=PASS
WINDOWS_REBOOT_RECONNECT=PASS
```

No local-operator authorization session was auto-opened after reboot; this remains
intentional and must be opened explicitly by the human operator before the
post-reboot `hara.health` proof.

The previously persisted PROD OAuth access token now receives HTTP 401 at MCP
`initialize`. No refresh token is stored in the safe OAuth session state, so a
fresh human PKCE authorization is required. The PROD MCP product secret was not
rotated or reprovisioned.

Wrangler/D1 operator access on Services also showed an intermittent Cloudflare
OAuth authentication error (code 10000) during the final readback; this is
operational tooling auth and is separate from the Commander customer OAuth path.

Exact continuation order:

```text
1. HUMAN_OPEN_LOCAL_OPERATOR_SESSION
2. POST_REBOOT_HARA_HEALTH
3. FRESH_HARA_IDENTITY_PKCE
4. OPENAI_SCAN_TOOLS_LOCAL_LIVE_PREFLIGHT
5. RECOVER_EXISTING_MCP_PRODUCT_TOKEN_CUSTODY_WITHOUT_ROTATION
6. CUSTOMER_MCP_FIVE_TOOL_HARNESS
7. OPENAI_EXTERNAL_CLIENT_E2E
8. OPENAI_NEGATIVE_N1_N2
9. OPENAI_PORTAL_SCAN_REVIEW_DEMO_SUBMIT
```
