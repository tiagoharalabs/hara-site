#!/usr/bin/env python3
"""Fail-closed 0.3.45 Windows approval/process contract, offline only."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
# Historical 0.3.45 source is immutable and authenticated by validate_signed_windows_045_v5_rc.py.
# Candidate expiry fixes have a separate guard; never relax this Read-Host historical contract.
SOURCE=(ROOT/"apps/commander/release-bundles/commercial-0.3.45-v5-rc/agent/windows.ps1").read_text(encoding="utf-8")
WORKER=(ROOT/"apps/commander/src/worker.js").read_text(encoding="utf-8")
def check(code, condition):
 if not condition:raise AssertionError("WINDOWS045_"+code)
 print("WINDOWS045_"+code+"=PASS")

check("AGENT_VERSION", '$AgentVersion = "0.3.45"' in SOURCE)
check("USER_DEFAULT_NOT_DOWNGRADED", 'else {"ASK_EVERY_ACTION"}' in SOURCE and "WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED" not in SOURCE)
check("ONLY_OPERATOR_PROCESS_APPROVES", 'owner_pid -ne $PID' in SOURCE and '$response=Read-Host' in SOURCE)
check("APPROVAL_CHALLENGE_REQUIRED", 'APROVAR "+[string]$pending.challenge' in SOURCE and '$response -ceq' in SOURCE)
check("ACTION_BINDING_HASH", 'arguments_sha256' in SOURCE and 'request_id -cne' in SOURCE and 'nonce -cne' in SOURCE)
check("ACTION_TIMEOUT_AND_DENIAL", '$ApprovalTimeoutSeconds = 30' in SOURCE and 'HUMAN_ACTION_APPROVAL_DENIED' in SOURCE and 'LOCAL_ACTION_APPROVAL_EXPIRED' in SOURCE)
check("DENY_WITHOUT_LOCAL_SESSION", 'if (-not $session) { throw "LOCAL_OPERATOR_SESSION_REQUIRED" }' in SOURCE)
check("NO_GLOBAL_APPROVAL_MODE_REWRITE", not re.search(r'(?m)^\s*\$cfg\.approval_mode\s*=\s*"SESSION_TRUSTED"',SOURCE))
check("FILE_CAS", 'FILE_PRECONDITION_FAILED' in SOURCE and 'Get-FileHash -LiteralPath $full -Algorithm SHA256' in SOURCE)
check("FILE_REPARSE_DENIED", 'FILESYSTEM_SYMLINK_DENIED' in SOURCE)
check("ATOMIC_FILE_REPLACE", '[IO.File]::Replace($temporary,$full,$backup,$true)' in SOURCE and 'Move($temporary,$full)' in SOURCE)
check("MANAGED_SESSIONS", 'HaraWindowsProcessSession' in SOURCE and 'ProcessSession' in SOURCE)
check("MANAGED_LIMITS", 'MaxLines = 5000' in SOURCE and 'MaxChars = 2 * 1024 * 1024' in SOURCE and '$script:WindowsSessionMaxActive=8' in SOURCE)
check("PROCESS_START_MUST_APPROVE", 'Start-WindowsManagedSession($Cfg,$Call,' in SOURCE and 'Assert-StarterMutationAuthorized $Cfg $Call' in SOURCE)
check("PROCESS_INTERACT_MUST_APPROVE", 'Send-WindowsManagedSessionInput($Cfg,$Call,' in SOURCE and 'Assert-StarterMutationAuthorized $Cfg $Call' in SOURCE)
check("PROCESS_KILL_MUST_APPROVE", 'Stop-WindowsManagedSession($Cfg,$Call,' in SOURCE and 'Assert-StarterMutationAuthorized $Cfg $Call' in SOURCE)
check("PERSISTENT_LOG_PREVIEW_REDACTED", 'action_summary=$null' in SOURCE)
check("PRIVACY_SELFTEST_ADDED", 'SELF_TEST_LOCAL_CONSOLE_PRIVATE_COMMAND_PERSISTED' in SOURCE)
check("EPHEMERAL_PROMPT_SHOWS_START", '@("hara.process.run","hara.process.start")' in SOURCE)
check("EPHEMERAL_PROMPT_SHOWS_INTERACT", 'if ($tool -eq "hara.process.interact")' in SOURCE)
check("EPHEMERAL_PROMPT_SHOWS_KILL", 'if ($tool -eq "hara.process.kill")' in SOURCE)
check("RECEIPT_APPROVAL_EXPLICIT", 'LOCAL_INDIVIDUAL_APPROVAL' in SOURCE)
check("WORKER_VERSION_GATED", 'if (managed.includes(toolId)) return semverAtLeast(device.agent_version,44)' in WORKER)
check("WINDOWS_OLD_VERSION_NO_NEW_TOOLS", 'if (semverAtLeast(device.agent_version,44))' in WORKER)
check("WINDOWS_NO_UNAPPROVED_LOCAL_CONFIG", 'approval_mode="PERSISTENT_TRUSTED"' not in SOURCE)
print("WINDOWS045_OFFLINE_APPROVAL_POLICY=FAIL_CLOSED")
