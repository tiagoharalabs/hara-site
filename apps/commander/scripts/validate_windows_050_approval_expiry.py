#!/usr/bin/env python3
"""Offline guards for candidate consent expiry; historical signatures are separate.

This verifies source boundaries only. Real PowerShell 5.1 behavior is verified by
test_windows_local_approval_expiry.ps1 using isolated AST function fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = ROOT / "apps/commander/public/agent/windows.ps1"
SCRIPT_DIR = ROOT / "apps/commander/scripts"
FIELDS = (
    "schema", "nonce", "challenge", "request_id", "tool_id", "arguments_sha256",
    "owner_pid", "owner_started_at_utc", "consumer_pid", "consumer_started_at_utc",
    "created_at_utc", "expires_at_utc", "action_summary",
)


def function(source: str, name: str) -> str:
    pattern = r"(?m)^function " + re.escape(name) + r"(?=[(\s{])"
    match = re.search(pattern, source)
    if not match:
        raise AssertionError("WINDOWS_APPROVAL_FUNCTION_MISSING:" + name)
    following = re.search(r"(?m)^function ", source[match.end():])
    end = match.end() + following.start() if following else len(source)
    return source[match.start():end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--execute", action="store_true",
                        help="also require the isolated fixture on Windows PowerShell 5.1")
    args = parser.parse_args()
    source_path = args.source.resolve(strict=True)
    if args.source.is_symlink() or not source_path.is_file():
        raise AssertionError("WINDOWS_APPROVAL_SOURCE_NOT_REGULAR")
    raw = source_path.read_bytes()
    source = raw.decode("utf-8-sig")
    if not re.search(r'(?m)^\$AgentVersion = "0[.]3[.]50"$', source):
        raise AssertionError("WINDOWS_APPROVAL_SOURCE50_VERSION_MISSING")
    bodies = {name: function(source, name) for name in (
        "Invoke-WithLocalApprovalLock", "Test-LocalApprovalRequestCurrent",
        "Initialize-LocalApprovalConsoleInput", "Clear-LocalApprovalConsoleInput",
        "Read-LocalApprovalConsoleKey", "Read-LocalApprovalResponse",
        "Publish-LocalApprovalResponse", "Remove-LocalApprovalFiles",
        "Respond-ToLocalApprovalRequest", "Invoke-LocalActionApproval",
        "Assert-StarterMutationAuthorized", "Start-OperatorConsole",
        "Stop-OperatorSession", "Start-WindowsManagedSession",
        "Test-LocalApprovalConsumerAlive", "Start-ManualOperatorConsole",
    )}
    checks = []

    def need(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError("WINDOWS_APPROVAL_EXPIRY_" + name)
        checks.append(name)

    need("APPROVAL_WINDOW_15_MINUTES",
         bool(re.search(r'(?m)^\$ApprovalTimeoutSeconds = 900$', source)))
    lock = bodies["Invoke-WithLocalApprovalLock"]
    current = bodies["Test-LocalApprovalRequestCurrent"]
    initialize = bodies["Initialize-LocalApprovalConsoleInput"]
    key = bodies["Read-LocalApprovalConsoleKey"]
    read = bodies["Read-LocalApprovalResponse"]
    publish = bodies["Publish-LocalApprovalResponse"]
    cleanup = bodies["Remove-LocalApprovalFiles"]
    respond = bodies["Respond-ToLocalApprovalRequest"]
    worker = bodies["Invoke-LocalActionApproval"]
    authorize = bodies["Assert-StarterMutationAuthorized"]
    console = bodies["Start-OperatorConsole"]
    revoke = bodies["Stop-OperatorSession"]
    managed_start = bodies["Start-WindowsManagedSession"]
    consumer = bodies["Test-LocalApprovalConsumerAlive"]
    manual = bodies["Start-ManualOperatorConsole"]
    need("PER_ACTION_APPROVAL_DEFAULT_PRESERVED",
         'else {"ASK_EVERY_ACTION"}' in source
         and "Invoke-LocalActionApproval $Call" in source
         and "WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED" not in source)
    need("NO_GLOBAL_APPROVAL_MODE_REWRITE",
         not re.search(r'(?m)^\s*\$cfg\.approval_mode\s*=\s*"SESSION_TRUSTED"', source, re.I)
         and 'approval_mode="PERSISTENT_TRUSTED"' not in source)
    need("MUTEX_ACQUIRE_RELEASE_FINALLY",
         all(x in lock for x in ("Mutex", "WaitOne", "finally", "ReleaseMutex", "Dispose")))
    need("PENDING_COMPLETE_BINDING", all(x in current for x in FIELDS))
    need("PENDING_DEADLINE_REVALIDATED",
         "expires_at_utc" in current and "[DateTime]::UtcNow" in current)
    need("OWNER_PID_AND_START_REVALIDATED",
         "Get-OperatorSession" in current and "owner_pid" in current
         and "owner_started_at_utc" in current)
    need("CONSUMER_PID_AND_START_ALIVE",
         "Get-OperatorProcess" in consumer
         and "consumer_pid" in consumer and "consumer_started_at_utc" in consumer
         and "StartTime.ToUniversalTime()" in consumer and "-ceq" in consumer
         and "Test-LocalApprovalConsumerAlive" in current)
    need("CONSUMER_BOUND_IN_RESPONSE_AND_ACCEPTANCE",
         all(x in publish and x in worker for x in ("consumer_pid", "consumer_started_at_utc")))
    need("MUTEX_CALLBACK_PRIVATE_NAMES",
         'Alias("Action")' in lock and "$ApprovalCriticalSection" in lock
         and "$approvalMutexObject" in lock and "& $Action" not in lock)
    need("REDIRECTED_INPUT_FAILS_CLOSED",
         "IsInputRedirected" in initialize and "LOCAL_APPROVAL_CONSOLE_UNAVAILABLE" in initialize)
    need("NONBLOCKING_MANUAL_INPUT",
         "[Console]::KeyAvailable" in key and "[Console]::ReadKey" in key
         and "Read-Host" not in read + respond and "ReadLine" not in read + respond)
    need("SILENCE_EXPIRES",
         "EXPIRED" in read and "Test-LocalApprovalRequestCurrent" in read
         and "Start-Sleep" in read)
    need("INPUT_BOUNDED_AND_EDITABLE",
         "Backspace" in read and "Enter" in read and "$text.Length -lt 64" in read)
    need("STALE_INPUT_DRAINED",
         read.count("Clear-LocalApprovalConsoleInput") >= 2 and "finally" in read)
    need("PUBLICATION_UNDER_SAME_LOCK",
         "Invoke-WithLocalApprovalLock" in publish and "Test-LocalApprovalRequestCurrent" in publish)
    need("ATOMIC_REPLY_AND_TEMP_CLEANUP",
         "[IO.File]::Move" in publish and "finally" in publish and "Remove-Item" in publish)
    need("CLEANUP_PRESERVES_FOREIGN_NONCE",
         "Invoke-WithLocalApprovalLock" in cleanup and "nonce" in cleanup and "-ceq" in cleanup)
    need("CONSOLE_GRANTS_ONLY_PUBLISHED",
         "Publish-LocalApprovalResponse" in respond and "=ENVIADA" in respond
         and "=CONCEDIDA" not in respond
         and "SUBMITTED" in respond and "Read-LocalApprovalResponse" in respond)
    need("ONLY_OWNER_WITH_EXACT_CHALLENGE",
         "owner_pid -ne $PID" in respond and "APROVAR " in respond and "-ceq" in respond)
    need("WORKER_RECHECKS_REQUEST_AND_RESPONSE",
         "LOCAL_ACTION_APPROVAL_REQUEST_CHANGED" in worker
         and "Test-LocalApprovalRequestCurrent" in worker
         and "responded_at_utc" in worker and "owner_started_at_utc" in worker)
    need("WORKER_OWNED_CLEANUP", "Remove-LocalApprovalFiles" in worker)
    need("SESSION_CREATE_REVOKE_SAME_MUTEX",
         console.count("Invoke-WithLocalApprovalLock") >= 2
         and "Invoke-WithLocalApprovalLock" in revoke
         and "Set-Content -LiteralPath $SessionPath" in console
         and "Remove-Item -Force -LiteralPath $SessionPath" in revoke)
    need("CONSOLE_SESSION_CLEANUP_OWNERSHIP_BOUND",
         "finally" in console
         and "owner_pid -eq $PID" in console
         and "owner_started_at_utc -ceq" in console)
    need("REVOKED_AFTER_APPROVAL_CLEANUP_DENIED",
         authorize.index("$approvedSession=Get-OperatorSession")
         < authorize.index("Invoke-LocalActionApproval $Call")
         < authorize.index("$active=Invoke-WithLocalApprovalLock { Get-OperatorSession }")
         and "$approvedSession.owner_pid" in authorize
         and "$approvedSession.owner_started_at_utc" in authorize
         and "LOCAL_OPERATOR_SESSION_REQUIRED" in authorize)
    need("MANAGED_START_COMPILE_BEFORE_CONSENT",
         managed_start.index("Initialize-WindowsManagedProcessType")
         < managed_start.index("Assert-StarterMutationAuthorized"))
    need("MANUAL_RESUME_RECHECKS_SESSION_AFTER_TASK_START",
         manual.count("Get-OperatorSession") >= 3
         and manual.index("Start-ScheduledTask") < manual.rindex("$existing=Get-OperatorSession")
         < manual.index("if ($existing) {")
         and "HARA_COMMANDER_AGENT=RESUMED" in manual)
    need("MANUAL_TASK_STOP_REQUIRES_OWNED_SESSION_AND_NO_OTHER_SESSION",
         "$startedHere -and $sessionOpenedHere" in manual
         and "([ref]$sessionOpenedHere)" in manual
         and "$SessionOpened.Value=$true" in console
         and "$currentTask -and -not $currentTask.Triggers -and -not $active" in manual)
    harness = SCRIPT_DIR / "test_windows_local_approval_expiry.ps1"
    fixture = harness.read_text(encoding="utf-8")
    need("HARNESS_ISOLATED_AST_ONLY",
         "Parser]::ParseFile" in fixture and "hara-synthetic-approval-" in fixture
         and "SYNTHETIC_FIXTURE_ONLY_NO_CUSTOMER_ACTION" in fixture
         and 'scope="ISOLATED_SYNTHETIC_AST_FUNCTIONS_ONLY"' in fixture
         and "FIXTURE_REQUIRES_WINDOWS_POWERSHELL_51" in fixture)
    need("HARNESS_DEADLINE_RACES_AND_RECOVERY",
         all(x in fixture for x in ("SILENCE_EXPIRES_WITHOUT_INPUT",
             "ENTER_AFTER_DEADLINE_DISCARDED", "NONCE_SWAP_DURING_INPUT",
             "PUBLISH_RACE_NEVER_REPORTS_SENT", "WORKER_NEXT_REQUEST_AFTER_CLEANUP",
             "CLEANUP_PRESERVES_NEXT_PENDING", "NO_PRODUCT_ACTION_EXECUTED")))
    need("HARNESS_POSTCLEANUP_REVOKE_AND_REPLACEMENT",
         all(x in fixture for x in (
             "ASSERT_VALID_APPROVAL_AFTER_CLEANUP_CONTINUES",
             "REVOKE_AFTER_CLEANUP_REMOVES_OWN_APPROVAL",
             "REPLACEMENT_SESSION_IS_ACTUALLY_ACTIVE",
             "ACTIVE_NEW_SESSION_NEVER_INHERITS_APPROVAL")))
    need("HARNESS_CONSUMER_DEATH_START_BINDING_AND_CHALLENGE",
         all(x in fixture for x in ("DISTINCT_CONSUMER_PROCESS_ALIVE",
             "CONSUMER_START_MARKER_MISMATCH_REJECTED", "DEAD_CONSUMER_REQUEST_REJECTED",
             "DEAD_CONSUMER_NEVER_PUBLISHES_REPLY", "APROVAR_WITHOUT_CHALLENGE_DENIED")))
    dynamic = False
    if args.execute:
        if sys.platform != "win32":
            raise RuntimeError("WINDOWS_APPROVAL_DYNAMIC_WINDOWS_RUNTIME_REQUIRED")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(harness),
             "-AgentSource", str(source_path)],
            text=True, capture_output=True, timeout=30, check=False,
        )
        if result.returncode:
            raise AssertionError("WINDOWS_APPROVAL_DYNAMIC_FIXTURE_FAILED")
        lines = [line for line in result.stdout.splitlines() if line.startswith('{"schema":')]
        if not lines:
            raise AssertionError("WINDOWS_APPROVAL_DYNAMIC_RECEIPT_MISSING")
        receipt = json.loads(lines[-1])
        if (receipt.get("state") != "PASS"
                or receipt.get("source_sha256") != hashlib.sha256(raw).hexdigest()
                or receipt.get("production_action_executed") is not False
                or receipt.get("real_human_positive_approval_proven") is not False):
            raise AssertionError("WINDOWS_APPROVAL_DYNAMIC_RECEIPT_INVALID")
        dynamic = True
    print(json.dumps({
        "schema": "hara.commander-windows-approval-expiry-static.v1",
        "state": "PASS", "checks": len(checks), "passed_checks": checks,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "dynamic_powershell51_fixture_tested": dynamic,
        "real_human_positive_approval_proven": False,
        "signed_release_validated": False,
        "production_action_executed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
