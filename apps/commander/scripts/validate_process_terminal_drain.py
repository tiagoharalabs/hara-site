#!/usr/bin/env python3
"""Real-PTY regression for preserving bounded output after process termination.

No Cloudflare calls, customer data, service restarts or permanent files.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import shlex
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path,
                    default=Path(__file__).resolve().parents[1] / "public/agent/linux.py")
SOURCE = parser.parse_args().source
spec = importlib.util.spec_from_file_location("hara_agent_pty_regression", SOURCE)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
checks = []

def require(name: str, condition: bool):
    assert condition, name
    checks.append(name)

def command(py: str) -> str:
    return "python3 -u -c " + shlex.quote(py)

def await_exit(session, seconds=5.0, *, drain=False):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if drain:
            agent._drain_process(session, 20)
        else:
            agent._process_update_state(session)
        if session.get("exit_code") is not None:
            return
        time.sleep(0.015)
    raise AssertionError("PROCESS_EXIT_TIMEOUT")

with tempfile.TemporaryDirectory(prefix="hara-pty-output-") as temporary:
    # No output read after start until the process has already terminated.
    start = agent.process_start(command("import time;time.sleep(.15);[print('TAIL-%03d'%i) for i in range(120)]"), temporary, 0)
    session = agent.PROCESS_SESSIONS[start["session_id"]]
    await_exit(session, drain=False)
    output = agent._process_output_payload(session, 0, 200, 0)
    lines = [line.strip() for line in output["text"].splitlines() if line.strip()]
    require("terminal_state", output["state"] == "EXITED" and output["exit_code"] == 0)
    require("120_lines_available", len(lines) == 120)
    require("first_line_retained", lines[0] == "TAIL-000")
    require("last_line_retained", lines[-1] == "TAIL-119")
    require("not_falsely_truncated", output["buffer_truncated"] is False)
    identical = agent._process_output_payload(session, 0, 200, 0)
    require("repeated_read_idempotent", identical["text"] == output["text"])
    cursor = agent._process_output_payload(session, None, 200, 0)
    require("cursor_read_complete", cursor["next_offset"] == 120)
    require("cursor_followup_empty", agent._process_output_payload(session, None, 200, 0)["text"] == "")

    # UTF-8 text must not disappear on exit; lines and EOF stay visible.
    start = agent.process_start(command("import time;time.sleep(.15);[print('linha-%03d-áé🚀'%i) for i in range(40)]"), temporary, 0)
    session = agent.PROCESS_SESSIONS[start["session_id"]]
    await_exit(session, drain=False)
    output = agent._process_output_payload(session, 0, 200, 0)
    require("unicode_complete", "linha-039-áé🚀" in output["text"])
    require("unicode_count", len(output["text"].splitlines()) == 40)
    require("unicode_exit_zero", output["exit_code"] == 0)

    # Reads performed during execution still include the final burst.
    start = agent.process_start(command("import time;print('FIRST');time.sleep(.20);[print('FINAL-%03d'%i) for i in range(80)]"), temporary, 60)
    session = agent.PROCESS_SESSIONS[start["session_id"]]
    await_exit(session, drain=True)
    output = agent._process_output_payload(session, 0, 200, 0)
    require("during_run_and_final_lines", "FIRST" in output["text"] and "FINAL-079" in output["text"])
    require("during_run_exit_zero", output["exit_code"] == 0)

    # Keep collection bounded even when the process produces many lines.
    start = agent.process_start(command("for i in range(7000): print('L%04d'%i+'x'*380)"), temporary, 0)
    session = agent.PROCESS_SESSIONS[start["session_id"]]
    await_exit(session, seconds=10.0, drain=True)
    output = agent._process_output_payload(session, 0, 500, 0)
    require("large_stdout_buffer_bounded", len(session["lines"]) <= agent.MAX_PROCESS_LINES and session.get("_buffer_chars", 0) <= agent.MAX_PROCESS_BUFFER_CHARS)
    require("large_stdout_truncation_flag", output["buffer_truncated"] and output["base_line"] > 0)
    require("large_stdout_last_line_preserved", "L6999" in "\n".join(session["lines"][-10:]))
    require("large_stdout_exit_zero", output["exit_code"] == 0)

    # One-shot process captures the last line after exit.
    result = agent.process_run(command("print('RUN-LAST-LINE')"), temporary, 3000, 50)
    require("one_shot_exit_zero", result["exit_code"] == 0)
    require("one_shot_stdout_retained", "RUN-LAST-LINE" in result["text"])

agent.cleanup_process_sessions()
print(json.dumps({
    "schema": "hara.commander-pty-terminal-drain-regression.v1",
    "checked": len(checks), "passed": len(checks), "failed": 0,
    "scope": "REAL_LOCAL_PTY_ONLY_NO_NETWORK",
    "source": str(SOURCE.name),
}, sort_keys=True))
