#!/usr/bin/env python3
"""Guard the operator identity boundary; optionally run isolated PowerShell 5.1.

Missing or unreadable process identity must reject the stale session without
crashing startup. Dynamic fixtures never operate on the installed profile/task.
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
DEFAULT_SOURCE = ROOT / "apps/commander/release-bundles/commercial-0.3.51-v11-rc/agent/windows.ps1"
HARNESS = Path(__file__).resolve().parent / "test_windows_operator_session_startup_fixture_051.ps1"
SCOPE = "REAL_AST_SESSION_LOOKUP_AND_TOP_LEVEL_START_DISPATCH_SYNTHETIC_PROFILE_AND_BOUNDARIES"
LABELS = (
    "CANDIDATE_ACTUAL_TOP_LEVEL_START_NULL_METADATA_RETURNS",
    "CANDIDATE_INVALID_STALE_SESSION_REQUESTS_FRESH_CONSOLE_BOUNDARY",
    "ACTUAL_START_DISPATCH_STALE_IDENTITY_NOT_REAUTHORIZED_OR_REWRITTEN",
    "START_TIME_NULL_DENIED_NULL",
    "START_TIME_MISSING_DENIED_NULL",
    "START_TIME_GETTER_THROWS_DENIED_NULL",
    "VALID_ALIVE_DATETIME_VALID_SESSION_PRESERVED",
    "OWNER_PID_INVALID_TEXT_DENIED_NULL",
    "PID_REUSE_MARKER_MISMATCH_DENIED_NULL",
)


def function(source: str, name: str) -> str:
    match = re.search(r"(?m)^function " + re.escape(name) + r"(?=[(\s{])", source)
    if not match:
        raise AssertionError("WINDOWS_OPERATOR_STARTUP_FUNCTION_MISSING:" + name)
    following = re.search(r"(?m)^function ", source[match.end():])
    end = match.end() + following.start() if following else len(source)
    return source[match.start():end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--execute", action="store_true",
                        help="also execute the isolated fixture in Windows PowerShell 5.1")
    args = parser.parse_args()
    source_path = args.source.resolve(strict=True)
    if args.source.is_symlink() or not source_path.is_file():
        raise AssertionError("WINDOWS_OPERATOR_STARTUP_SOURCE_NOT_REGULAR")
    raw = source_path.read_bytes()
    source = raw.decode("utf-8-sig")
    body = function(source, "Get-OperatorSession")
    checks = []

    def need(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError("WINDOWS_OPERATOR_STARTUP_" + name)
        checks.append(name)

    need("ACTIVE_CANDIDATE_051", '$AgentVersion = "0.3.51"' in source)
    need("SESSION_FILE_SCHEMA_AND_AGE_BOUNDARY_PRESERVED", all(item in body for item in (
        "Test-Path -LiteralPath $SessionPath -PathType Leaf", "ConvertFrom-Json",
        "hara.commander-operator-session.v1", "started_at_utc", "SessionMaxHours")))
    guards = list(re.finditer(r"try\s*\{(?P<guard>.*?)\}\s*catch\s*\{\s*return\s+\$null\s*\}",
                             body, re.S))
    identity_guards = [match for match in guards if "$ownerPid=[int]$session.owner_pid" in match.group("guard")]
    need("IDENTITY_LOOKUP_CATCH_RETURNS_NULL", len(identity_guards) == 1)
    identity = identity_guards[0].group("guard")
    ordered = (
        "$ownerPid=[int]$session.owner_pid",
        "if ($ownerPid -le 1) { return $null }",
        "$proc=Get-OperatorProcess $ownerPid",
        "if (-not $proc) { return $null }",
        "$ownerStarted=$proc.StartTime",
        "if ($ownerStarted -isnot [DateTime]) { return $null }",
        '$marker=$ownerStarted.ToUniversalTime().ToString("o")',
        "if ($marker -ne [string]$session.owner_started_at_utc) { return $null }",
    )
    need("IDENTITY_VALIDATED_BEFORE_RETURN", all(item in identity for item in ordered))
    positions = [identity.index(item) for item in ordered]
    need("PID_AND_DATETIME_CHECK_PRECEDE_CONVERSION", positions == sorted(positions))
    need("STARTTIME_SINGLE_SNAPSHOT_INSIDE_GUARD",
         body.count("$proc.StartTime") == 1 and identity.count("$proc.StartTime") == 1
         and "$proc.StartTime.ToUniversalTime()" not in body)
    need("NO_SESSION_RETURN_INSIDE_IDENTITY_GUARD", "return $session" not in identity)
    suffix = body[identity_guards[0].end():].strip()
    need("VALID_IDENTITY_ONLY_RETURNS_SESSION", bool(re.fullmatch(r"return\s+\$session\s*\}", suffix)))
    process = function(source, "Get-OperatorProcess")
    need("PROCESS_LOOKUP_FAILS_CLOSED", all(item in process for item in (
        "$OwnerPid -le 1", "Get-Process -Id $OwnerPid -ErrorAction Stop", "catch { return $null }")))
    manual = function(source, "Start-ManualOperatorConsole")
    approval = function(source, "Invoke-LocalActionApproval")
    need("START_AND_APPROVAL_STILL_REQUIRE_OPERATOR_IDENTITY",
         "$existing=Get-OperatorSession" in manual
         and "$session=Get-OperatorSession" in approval
         and 'if (-not $session) { throw "LOCAL_OPERATOR_SESSION_REQUIRED" }' in approval)
    need("PER_ACTION_POLICY_PRESERVED", 'else {"ASK_EVERY_ACTION"}' in source
         and not re.search(r'(?m)^\s*\$cfg\.approval_mode\s*=\s*"SESSION_TRUSTED"', source, re.I)
         and 'approval_mode="PERSISTENT_TRUSTED"' not in source)
    fixture = HARNESS.read_text(encoding="utf-8-sig")
    static_labels = tuple(label.removesuffix("_DENIED_NULL").removesuffix("_VALID_SESSION_PRESERVED")
                          for label in LABELS)
    need("NATIVE_FIXTURE_HAS_IDENTITY_NEGATIVES_AND_VALID_CONTROL",
         all(label in fixture for label in static_labels)
         and '"_DENIED_NULL"' in fixture and '"_VALID_SESSION_PRESERVED"' in fixture)
    need("NATIVE_FIXTURE_ISOLATION_AND_RUNTIME_BOUNDARY", all(item in fixture for item in (
        "Parser]::ParseFile", "STARTUP_FIXTURE_REQUIRES_PS51", SCOPE,
        "production_action_executed", "live_profile_touched", "real_task_touched",
        "source_main_loop_executed", "real_human_approval_proven")))
    dynamic = False
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if args.execute:
        if sys.platform != "win32":
            raise RuntimeError("WINDOWS_OPERATOR_STARTUP_DYNAMIC_WINDOWS_RUNTIME_REQUIRED")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(HARNESS),
             "-AgentSource", str(source_path), "-ExpectedBehavior", "Candidate051",
             "-ExpectedSourceSha256", source_sha256],
            text=True, capture_output=True, timeout=30, check=False,
        )
        if result.returncode:
            raise AssertionError("WINDOWS_OPERATOR_STARTUP_DYNAMIC_FIXTURE_FAILED")
        lines = [line for line in result.stdout.splitlines() if line.startswith('{"schema":')]
        if not lines:
            raise AssertionError("WINDOWS_OPERATOR_STARTUP_DYNAMIC_RECEIPT_MISSING")
        receipt = json.loads(lines[-1])
        if (receipt.get("schema") != "hara.commander-windows-operator-session-startup-fixture.v1"
                or receipt.get("state") != "PASS"
                or receipt.get("source_sha256") != source_sha256
                or receipt.get("scope") != SCOPE
                or receipt.get("actual_start_dispatch_child_exit_code") != 0
                or receipt.get("actual_start_dispatch_child", {}).get("args_start_dispatch") is not True
                or not set(LABELS).issubset(set(receipt.get("passed_checks", [])))
                or any(receipt.get(name) is not False for name in (
                    "production_action_executed", "live_profile_touched", "real_task_touched",
                    "source_main_loop_executed", "real_human_approval_proven"))):
            raise AssertionError("WINDOWS_OPERATOR_STARTUP_DYNAMIC_RECEIPT_INVALID")
        dynamic = True
    print(json.dumps({
        "schema": "hara.commander-windows-operator-startup-static.v1", "state": "PASS",
        "checks": len(checks), "passed_checks": checks, "source_sha256": source_sha256,
        "dynamic_powershell51_fixture_tested": dynamic,
        "production_action_executed": False, "real_human_approval_proven": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
