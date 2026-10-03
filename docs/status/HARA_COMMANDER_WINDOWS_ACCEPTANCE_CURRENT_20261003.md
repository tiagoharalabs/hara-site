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
