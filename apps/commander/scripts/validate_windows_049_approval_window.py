#!/usr/bin/env python3
"""Guard the 15-minute approval contract; optional isolated native PS5.1 proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = ROOT / "apps/commander/release-bundles/commercial-0.3.49-v9-rc/agent/windows.ps1"
HARNESS = Path(__file__).with_name("test_windows_049_approval_window_fixture.ps1")
LABELS = (
    "SOURCE_TIMEOUT_LITERAL_900_SECONDS",
    "CURRENT_AT_899_999_SECONDS",
    "REAL_PUBLICATION_AT_899_999_SECONDS",
    "SILENCE_EXPIRES_AT_900_SECONDS",
    "FIFTEEN_MINUTES_SIMULATED_WITHOUT_WALL_CLOCK_WAIT",
    "FULL_PHRASE_ACCEPTED_IN_DELAYED_CHUNKS_BEFORE_900",
    "ENTER_AT_EXACT_900_DISCARDS_FULL_PHRASE",
    "RESPONDER_REQUIRES_FULL_PHRASE_AND_CODE",
    "REAL_INVOKE_CREATES_900_SECOND_DEADLINE",
    "REAL_INVOKE_BINDS_TOOL_REQUEST_AND_PAYLOAD_SHA256",
    "REAL_INVOKE_CONSUMES_HUMAN_INPUT_FIXTURE_AT_899_999",
    "CONCURRENT_REQUEST_AFTER_TWO_MINUTES_PRESERVES_LIVE_PENDING",
    "ORIGINAL_REQUEST_STILL_APPROVABLE_AT_TEN_MINUTES",
    "POLICY_REMAINS_ASK_EVERY_ACTION",
    "DENIAL_NEVER_PROMOTES_DEVICE_OR_SESSION_POLICY",
    "SOURCE_IMMUTABLE_AFTER_AST_CLOCK_FIXTURE",
    "EXPIRED_EXACT_PAIR_CLEANUP_REQUIRES_FRESH_APPROVAL",
    "ORPHAN_REPLY_YOUNGER_THAN_900_SECONDS_PRESERVED",
    "APPROVAL_WAIT_SENDS_FOURTEEN_HEARTBEATS_OVER_FAKE_900_SECONDS",
    "HEARTBEAT_NEVER_PROMOTES_ASK_EVERY_ACTION",
    "FAILED_HEARTBEAT_DOES_NOT_ADVANCE_SHARED_LAST_HEARTBEAT",
    "VALID_REPLY_AT_895_ACCEPTED_BEFORE_DUE_HEARTBEAT",
    "READY_REPLY_ACCEPTANCE_NEVER_BLOCKED_BY_NETWORK_HEARTBEAT",
)


def function(source: str, name: str) -> str:
    match = re.search(r"(?m)^function " + re.escape(name) + r"(?=[(\s{])", source)
    if not match:
        raise AssertionError("WINDOW49_FUNCTION_MISSING:" + name)
    end = source.find("\n}", match.end())
    if end < 0:
        raise AssertionError("WINDOW49_FUNCTION_END_MISSING:" + name)
    return source[match.start():end + 2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    source_path = args.source.resolve(strict=True)
    if args.source.is_symlink() or not source_path.is_file():
        raise AssertionError("WINDOW49_SOURCE_NOT_REGULAR")
    raw = source_path.read_bytes()
    source = raw.decode("utf-8-sig")
    fixture = HARNESS.read_text(encoding="utf-8-sig")
    invoke = function(source, "Invoke-LocalActionApproval")
    reader = function(source, "Read-LocalApprovalResponse")
    responder = function(source, "Respond-ToLocalApprovalRequest")
    current = function(source, "Test-LocalApprovalRequestCurrent")
    policy = function(source, "Assert-StarterMutationAuthorized")
    heartbeat = function(source, "Send-LocalApprovalConsumerHeartbeat")
    checks: list[str] = []

    def need(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError("WINDOW49_" + name)
        checks.append(name)

    need("ACTIVE_CANDIDATE_049", bool(re.search(r'(?m)^\$AgentVersion = "0[.]3[.]49"$', source)))
    assignments = re.findall(r"(?m)^\$ApprovalTimeoutSeconds\s*=\s*([^\r\n]+)$", source)
    need("SINGLE_TIMEOUT_LITERAL_900", assignments == ["900"])
    need("PENDING_DEADLINE_DERIVED_FROM_CENTRAL_TIMEOUT",
         bool(re.search(r"\$expires\s*=\s*\[DateTime\]::UtcNow\.AddSeconds\(\$ApprovalTimeoutSeconds\)", invoke)))
    need("PROMPT_MINUTES_DERIVED_FROM_CENTRAL_TIMEOUT",
         bool(re.search(r"\$ApprovalTimeoutSeconds\s*/\s*60", responder))
         and "minutos" in responder
         and "30 segundos" not in responder)
    need("EXACT_PHRASE_AND_REQUEST_CODE_STILL_REQUIRED",
         '[string]$response.text -ceq ("APROVAR "+[string]$pending.challenge)' in responder)
    need("READER_REVALIDATES_ENTER_DEADLINE_AND_REQUEST",
         "[DateTime]::UtcNow -ge $expires -or -not $stillCurrent" in reader
         and "Test-LocalApprovalRequestCurrent $Pending" in reader)
    need("CONSUMER_REVALIDATES_RESPONSE_AND_ACCEPTANCE_DEADLINE",
         "$responded -ge $expires" in invoke and "[DateTime]::UtcNow -ge $expires" in invoke
         and 'throw "LOCAL_ACTION_APPROVAL_EXPIRED"' in invoke)
    need("REQUEST_BINDS_NONCE_OWNER_CONSUMER_AND_ARGUMENT_DIGEST", all(item in current for item in (
        "nonce", "arguments_sha256", "owner_started_at_utc", "consumer_started_at_utc",
        "Test-LocalApprovalConsumerAlive $Pending", "Get-OperatorSession")))
    need("EXISTING_PENDING_LIFETIME_USES_ITS_DEADLINE", "$priorExpires -le [DateTime]::UtcNow" in invoke
         and "if ($older) { $expiredPrior=$prior }" in invoke)
    need("ORPHAN_REPLY_AGE_COVERS_FULL_APPROVAL_WINDOW", "[Math]::Max(120,$ApprovalTimeoutSeconds)" in invoke)
    need("REPLY_BOOL_AND_REQUEST_IDENTITY_STILL_VALIDATED", all(item in invoke for item in (
        "$answer.approved -isnot [bool]", "$answer.nonce -cne $nonce",
        "$answer.request_id -cne", "$answer.arguments_sha256 -cne $digest",
        "$answer.owner_pid", "$answer.consumer_pid", "$answer.consumer_started_at_utc")))
    need("ASK_EVERY_ACTION_REQUIRES_REAL_LOCAL_APPROVAL", all(item in policy for item in (
        'if ($mode -eq "ASK_EVERY_ACTION")', "Invoke-LocalActionApproval $Call",
        'throw "LOCAL_OPERATOR_SESSION_REQUIRED"'))
         and not re.search(r'(?m)^\s*\$cfg\.approval_mode\s*=\s*"(?:SESSION_TRUSTED|PERSISTENT_TRUSTED)"', source, re.I))
    need("APPROVAL_CONSUMER_HEARTBEAT_INTERVAL_60", bool(re.search(r"(?m)^\$HeartbeatSeconds = 60$", source))
         and "Send-LocalApprovalConsumerHeartbeat $Cfg $ApprovalDeviceToken" in invoke
         and "Invoke-LocalActionApproval $Call $Cfg $script:DeviceToken" in policy)
    need("HEARTBEAT_NETWORK_TIMEOUT_BOUNDED_AND_FAILURE_FAILS_CLOSED",
         "/api/device/heartbeat" in heartbeat and "} 5 | Out-Null" in heartbeat
         and "catch {" in heartbeat and "return $false" in heartbeat)
    need("NATIVE_FIXTURE_HAS_BOUNDARY_AND_CONCURRENCY_CONTROLS", all(label in fixture for label in LABELS))
    need("CLOCK_SEAM_EXISTS_ONLY_INSIDE_SOURCE_PINNED_AST_FIXTURE", all(item in fixture for item in (
        "WINDOW49_FIXTURE_SOURCE_NOT_PINNED", "Parser]::ParseFile", "WINDOW49_FIXTURE_REQUIRES_PS51",
        "$definition.Replace('[DateTime]::UtcNow','(Get-FixtureUtcNow)')"))
         and "Get-FixtureUtcNow" not in source)
    need("NATIVE_FIXTURE_NEVER_RUNS_AGENT_MAIN_LOOP_OR_PRODUCTION_ACTION", all(item in fixture for item in (
        "source_main_loop_executed=$false", "real_task_touched=$false", "live_profile_touched=$false",
        "production_action_executed=$false", "real_human_approval_proven=$false",
        "consumer_liveness_fixture_adapter=$true",
        "heartbeat_transport_and_telemetry_mocked=$true",
        "fifteen_minute_wall_clock_wait_performed=$false")))
    source_sha = hashlib.sha256(raw).hexdigest()
    dynamic = False
    if args.execute:
        if sys.platform != "win32":
            raise RuntimeError("WINDOW49_DYNAMIC_WINDOWS_RUNTIME_REQUIRED")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(HARNESS),
             "-AgentSource", str(source_path), "-ExpectedSourceSha256", source_sha],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            raise AssertionError("WINDOW49_DYNAMIC_FIXTURE_FAILED:" + result.stderr[-600:])
        lines = [line for line in result.stdout.splitlines() if line.startswith('{"schema":')]
        if not lines:
            raise AssertionError("WINDOW49_DYNAMIC_RECEIPT_MISSING")
        receipt = json.loads(lines[-1])
        if (receipt.get("schema") != "hara.commander-windows-approval-window49-fixture.v1"
                or receipt.get("state") != "PASS" or receipt.get("source_sha256") != source_sha
                or receipt.get("approval_timeout_seconds") != 900
                or not set(LABELS).issubset(set(receipt.get("passed_checks", [])))
                or receipt.get("source_function_ast_real") is not True
                or receipt.get("clock_and_keyboard_fixture_only") is not True
                or receipt.get("consumer_liveness_fixture_adapter") is not True
                or receipt.get("heartbeat_transport_and_telemetry_mocked") is not True
                or any(receipt.get(field) is not False for field in (
                    "source_main_loop_executed", "real_task_touched", "live_profile_touched",
                    "production_action_executed", "real_human_approval_proven",
                    "fifteen_minute_wall_clock_wait_performed"))):
            raise AssertionError("WINDOW49_DYNAMIC_RECEIPT_INVALID")
        dynamic = True
    print(json.dumps({
        "schema": "hara.commander-windows-approval-window49-static.v1", "state": "PASS",
        "checks": len(checks), "passed_checks": checks, "source_sha256": source_sha,
        "dynamic_powershell51_fixture_tested": dynamic,
        "production_action_executed": False, "real_human_approval_proven": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
