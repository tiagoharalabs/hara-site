#!/usr/bin/env python3
"""Native function tests; private PTYs only, no enrollment or product authority."""
import hashlib
import importlib.util
import json
import os
import shlex
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "linux-053-baseline.py"
CANDIDATE = HERE / "linux-managed-cap-candidate.py"
SOURCE_SHA256 = "db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e"
CANDIDATE_SHA256 = "bbac34bc7e48d68a31f478e2c062905f30d4a7c486aada20e6f0e452e62ae71b"
SCOPE = "UNIT_ORIGINAL_FUNCTIONS_NATIVE_PTY_PRIVATE_FIXTURES_NO_BACKEND"

CHILD = r'''import os, sys, termios
n = int(sys.argv[1])
attrs = termios.tcgetattr(0)
attrs[1] &= ~termios.OPOST
attrs[3] &= ~termios.ECHO
termios.tcsetattr(0, termios.TCSANOW, attrs)
burst = "".join("L%03d\n" % i for i in range(n)) + "READY\n"
assert len(burst.encode("utf-8")) < 4096
assert os.write(1, burst.encode("utf-8")) == len(burst.encode("utf-8"))
value = sys.stdin.readline().rstrip("\n")
os.write(1, ("UTF8:" + value + "\n").encode("utf-8"))
'''

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(label, path, private):
    os.environ["XDG_CONFIG_HOME"] = str(private / label / "config")
    os.environ["XDG_DATA_HOME"] = str(private / label / "data")
    spec = importlib.util.spec_from_file_location("hara_unit_" + label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PROCESS_SESSIONS == {}
    assert private in module.RECEIPT_DIR.parents
    return module

class NativeHarness:
    def __init__(self, module, label, private, child):
        self.module = module
        self.label = label
        self.private = private
        self.child = child
        self.config = {"HARA_DEVICE_ID": "QA-UNIT-NATIVE-PTY-" + label}
        self.receipts = set()
        self.calls = 0

    def command(self, count):
        return shlex.join([sys.executable, "-I", "-B", str(self.child), str(count)])

    def dispatch(self, tool, payload):
        call = {
            "call_id": "unit-" + uuid.uuid4().hex,
            "request_id": "unit-" + uuid.uuid4().hex,
            "tool_id": tool,
            "payload": payload,
            "_transport": "LOCAL_MCP",
        }
        # No approved ASK response or simulated operator session is supplied.
        # execute_tool is tested as a native unit function, not an authority route.
        result = self.module.execute_tool(self.config, call)
        assert result["state"] == "PASS", result
        receipt_sha = result["bridge_receipt_sha256"]
        assert receipt_sha not in self.receipts
        self.receipts.add(receipt_sha)
        receipt_path = self.module.RECEIPT_DIR / (receipt_sha + ".json")
        receipt = json.loads(receipt_path.read_text())
        assert receipt_path.stat().st_mode & 0o777 == 0o600
        assert receipt["human_approval_state"] is None
        assert receipt["result_stdout_sha256"] == hashlib.sha256(result["result"]["stdout"].encode()).hexdigest()
        self.calls += 1
        return json.loads(result["result"]["stdout"])

    def simple(self, name, args):
        tool, payload = self.module._local_simple_map(self.config, name, args)
        return self.dispatch(tool, payload)

    def cleanup(self):
        self.module.cleanup_process_sessions()
        for session in self.module.PROCESS_SESSIONS.values():
            if int(session.get("fd", -1)) >= 0:
                try:
                    os.close(session["fd"])
                except OSError:
                    pass
        self.module.PROCESS_SESSIONS.clear()

    def collect(self, sid, first):
        batches = [first]
        observed = first.get("text", "").splitlines()
        deadline = time.monotonic() + 5
        while "READY" not in observed and time.monotonic() < deadline:
            output = self.simple("read_process_output", {"session_id": sid, "length": 500, "timeout_ms": 500})
            batches.append(output)
            observed += output.get("text", "").splitlines()
        assert observed.count("READY") == 1, observed
        return batches, observed

    def finish(self, sid, batches, observed, input_value):
        output = self.simple("interact_with_process", {"session_id": sid, "input": input_value, "timeout_ms": 1000})
        batches.append(output)
        observed += output.get("text", "").splitlines()
        deadline = time.monotonic() + 5
        while output["state"] != "EXITED" and time.monotonic() < deadline:
            output = self.simple("read_process_output", {"session_id": sid, "length": 500, "timeout_ms": 500})
            batches.append(output)
            observed += output.get("text", "").splitlines()
        assert output["state"] == "EXITED" and output["exit_code"] == 0, output
        tail = self.simple("read_process_output", {"session_id": sid, "length": 500, "timeout_ms": 0})
        batches.append(tail)
        assert tail["text"] == "", tail
        assert all(not x.get("buffer_truncated") and not x.get("truncated_before") for x in batches)
        assert observed.count("UTF8:" + input_value) == 1, observed
        expected_offset = 0
        for batch in batches:
            assert batch["offset"] == expected_offset, batches
            expected_offset = batch["next_offset"]
        self.module.PROCESS_SESSIONS.pop(sid)
        return observed

    def cap_case(self, label, count, expected_cap, supplied_cap=None, timeout=1000, direct=False, expected_failure=False):
        args = {"command": self.command(count), "cwd": str(self.private), "timeout_ms": timeout}
        if supplied_cap is not None:
            args["max_lines"] = supplied_cap
        if direct:
            first = self.dispatch("hara.process.start", args)
        else:
            args["interactive"] = timeout <= 10000
            first = self.simple("start_process", args)
        sid = first["session_id"]
        try:
            initial = first.get("text", "").splitlines()
            cap_ok = len(initial) == expected_cap
            batches, observed = self.collect(sid, first)
            deferred_markers = sum(x.startswith("L") for x in observed[len(initial):])
            value = "ação_日本_🚗"
            observed = self.finish(sid, batches, observed, value)
            markers = [x for x in observed if x.startswith("L")]
            assert markers == ["L%03d" % i for i in range(count)], markers
            assert observed.count("READY") == 1
            assert len(set(markers)) == count
            if expected_failure:
                assert not cap_ok and len(initial) > expected_cap, initial
            else:
                assert cap_ok, {"initial_lines": len(initial), "expected_cap": expected_cap}
            return {
                "name": label,
                "state": "FAIL_EXPECTED_REPRODUCTION" if expected_failure else "PASS",
                "first_lines": len(initial),
                "requested_effective_cap": expected_cap,
                "deferred_numbered_lines": deferred_markers,
                "numbered_lines_exactly_once": count,
                "utf8_input_exactly_once": True,
                "exit_code": 0,
                "contiguous_cursor": True,
                "no_buffer_loss": True,
            }
        finally:
            self.cleanup()

def assert_raises_without_fork(harness, label, callback, exception, code=None):
    before = set(harness.module.PROCESS_SESSIONS)
    try:
        callback()
    except exception as exc:
        if code is not None:
            assert str(exc) == code, (label, str(exc))
    else:
        raise AssertionError(label + ": exception missing")
    assert set(harness.module.PROCESS_SESSIONS) == before
    return {"name": label, "state": "PASS", "process_created": False}

def main():
    assert sha(SOURCE) == SOURCE_SHA256
    assert sha(CANDIDATE) == CANDIDATE_SHA256
    report = {
        "scope": SCOPE,
        "baseline_sha256": sha(SOURCE),
        "candidate_sha256": sha(CANDIDATE),
        "vm_actions": 0,
        "installations": 0,
        "backend_calls": 0,
        "operator_approval_simulated": False,
        "candidate_tests": [],
    }
    with tempfile.TemporaryDirectory(prefix="hara-managed-cap-unit-", dir="/tmp") as tmp:
        private = Path(tmp)
        os.chmod(private, 0o700)
        child = private / "controlled_child.py"
        child.write_text(CHILD)
        os.chmod(child, 0o600)
        baseline = load("baseline", SOURCE, private)
        candidate = load("candidate", CANDIDATE, private)
        old = NativeHarness(baseline, "baseline", private, child)
        new = NativeHarness(candidate, "candidate", private, child)
        try:
            report["baseline_contract"] = old.cap_case("managed_cap_20_baseline", 120, 20, 20, expected_failure=True)
            mapped_tool, mapped_payload = baseline._local_simple_map(old.config, "start_process", {
                "command": old.command(120), "interactive": True, "max_lines": 20
            })
            assert mapped_tool == "hara.process.start" and "max_lines" not in mapped_payload
            report["baseline_map_drops_max_lines"] = True
            report["baseline_dispatch_rejects_max_lines"] = assert_raises_without_fork(
                old, "baseline_dispatch_rejects_max_lines",
                lambda: old.dispatch("hara.process.start", {"command": old.command(120), "max_lines": 20}),
                ValueError, "FUNCTION_ARGUMENTS_DENIED",
            )
            for label, count, cap, supplied, timeout, direct in [
                ("managed_cap_20", 120, 20, 20, 1000, False),
                ("managed_default_200", 240, 200, None, 1000, False),
                ("managed_lower_boundary_1", 120, 1, 1, 1000, False),
                ("managed_upper_boundary_500", 560, 500, 500, 1000, False),
                ("native_lower_clamp_0_to_1", 120, 1, 0, 1000, True),
                ("native_upper_clamp_900_to_500", 560, 500, 900, 1000, True),
                ("automatic_managed_timeout_cap_20", 120, 20, 20, 15000, False),
                ("dispatch_direct_cap_20", 120, 20, 20, 1000, True),
                ("dispatch_direct_default_200", 240, 200, None, 1000, True),
            ]:
                report["candidate_tests"].append(new.cap_case(label, count, cap, supplied, timeout, direct))
            # Internal conversions/clamps match the existing one-shot pattern.
            report["candidate_tests"] += [
                assert_raises_without_fork(new, "invalid_max_lines_map", lambda: candidate._local_simple_map(new.config, "start_process", {"command": "printf unit", "interactive": True, "max_lines": "twenty"}), ValueError),
                assert_raises_without_fork(new, "invalid_max_lines_dispatch", lambda: new.dispatch("hara.process.start", {"command": "printf unit", "max_lines": "twenty"}), ValueError),
                assert_raises_without_fork(new, "invalid_max_lines_native_none", lambda: candidate.process_start("printf unit", str(private), 100, None), TypeError),
                assert_raises_without_fork(new, "invalid_command_empty", lambda: candidate.process_start("", str(private), 100, 20), ValueError, "PROCESS_COMMAND_INVALID"),
                assert_raises_without_fork(new, "invalid_command_nul", lambda: candidate.process_start("printf" + chr(0), str(private), 100, 20), ValueError, "PROCESS_COMMAND_INVALID"),
                assert_raises_without_fork(new, "invalid_command_length", lambda: candidate.process_start("x" * 4097, str(private), 100, 20), ValueError, "PROCESS_COMMAND_INVALID"),
                assert_raises_without_fork(new, "unknown_dispatch_argument", lambda: new.dispatch("hara.process.start", {"command": "printf unit", "unexpected": 1}), ValueError, "FUNCTION_ARGUMENTS_DENIED"),
                assert_raises_without_fork(new, "missing_dispatch_command", lambda: new.dispatch("hara.process.start", {"max_lines": 20}), ValueError, "FUNCTION_ARGUMENTS_DENIED"),
                assert_raises_without_fork(new, "invalid_timeout_dispatch", lambda: new.dispatch("hara.process.start", {"command": "printf unit", "timeout_ms": "late", "max_lines": 20}), ValueError),
            ]
            mapped_tool, mapped = candidate._local_simple_map(new.config, "start_process", {"command": "printf unit", "max_lines": 20})
            assert mapped_tool == "hara.process.run" and mapped["max_lines"] == 20
            oneshot = new.simple("start_process", {"command": shlex.join([sys.executable, "-I", "-B", "-c", "print(chr(10).join(str(i) for i in range(120)))"]), "cwd": str(private), "timeout_ms": 3000, "max_lines": 20})
            assert oneshot["state"] == "EXITED" and oneshot["exit_code"] == 0
            assert oneshot["text"].splitlines() == [str(i) for i in range(20)]
            assert oneshot["output_truncated"] is True and oneshot["session_retained"] is False
            assert oneshot["run_id"] not in candidate.PROCESS_SESSIONS
            report["candidate_tests"].append({"name": "oneshot_cap_20_regression", "state": "PASS", "first_lines": 20, "session_retained": False})
            old_specs = baseline.local_simple_mcp_tools()
            new_specs = candidate.local_simple_mcp_tools()
            assert old_specs == new_specs
            spec = next(x for x in new_specs if x["name"] == "start_process")
            assert spec["inputSchema"]["properties"]["max_lines"] == {"type": "integer", "minimum": 1, "maximum": 500}
            assert baseline.SESSION_MAX_SECONDS == candidate.SESSION_MAX_SECONDS
            assert baseline.PROCESS_FINISHED_RETENTION_SECONDS == candidate.PROCESS_FINISHED_RETENTION_SECONDS
            assert baseline.MAX_PROCESS_LINES == candidate.MAX_PROCESS_LINES
            report["candidate_tests"].append({"name": "schema_global_limits_and_ttl_unchanged", "state": "PASS"})
            report["native_receipt_count"] = {"baseline": len(old.receipts), "candidate": len(new.receipts)}
            report["candidate_pass_count"] = len(report["candidate_tests"])
            report["candidate_state"] = "PASS"
            assert all(x["state"] == "PASS" for x in report["candidate_tests"])
        finally:
            old.cleanup()
            new.cleanup()
    (HERE / "managed-cap-native-result.json").write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))

if __name__ == "__main__":
    main()
