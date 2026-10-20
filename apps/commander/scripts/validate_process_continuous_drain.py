#!/usr/bin/env python3
"""Real PTY regression: children must progress without client output reads."""
from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path,
                    default=Path(__file__).resolve().parents[1] / "public/agent/linux.py")
SOURCE = parser.parse_args().source


def wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def command(py):
    return "python3 -u -c " + shlex.quote(py)


with tempfile.TemporaryDirectory(prefix="hara-pty-continuous-") as temporary:
    prior = {key: os.environ.get(key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME")}
    os.environ["XDG_CONFIG_HOME"] = str(Path(temporary) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(temporary) / "data")
    spec = importlib.util.spec_from_file_location("hara_agent_pty_continuous", SOURCE)
    assert spec and spec.loader
    agent = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = agent
    spec.loader.exec_module(agent)
    try:
        marker = Path(temporary) / "large-complete"
        py = ("import sys;from pathlib import Path;"
              "sys.stdout.write('X'*262144+'\\nTAIL-END\\n');sys.stdout.flush();"
              f"Path({str(marker)!r}).write_text('done')")
        started = agent.process_start(command(py), temporary, 0)
        session = agent.PROCESS_SESSIONS[started["session_id"]]
        assert wait_until(marker.exists, 3.0), "PTY_CHILD_BLOCKED_WITHOUT_CLIENT_READ"
        assert wait_until(lambda: session.get("exit_code") is not None)
        result = agent._process_output_payload(session, 0, 200, 0)
        assert result["exit_code"] == 0 and "TAIL-END" in result["text"]
        assert result["buffer_truncated"] is True
        print("COMMANDER_PROCESS_256K_COMPLETES_WITHOUT_CLIENT_READ=PASS")

        marker = Path(temporary) / "unicode-complete"
        py = ("import os,time;from pathlib import Path;"
              "data='linha-🍵-fim\\n'.encode('utf-8');"
              "os.write(1,data[:8]);time.sleep(.05);os.write(1,data[8:]);"
              f"Path({str(marker)!r}).write_text('done')")
        started = agent.process_start(command(py), temporary, 0)
        session = agent.PROCESS_SESSIONS[started["session_id"]]
        assert wait_until(marker.exists, 3.0)
        assert wait_until(lambda: session.get("exit_code") is not None)
        result = agent._process_output_payload(session, 0, 20, 0)
        assert "linha-🍵-fim" in result["text"] and "�" not in result["text"]
        print("COMMANDER_PROCESS_SPLIT_UTF8_PRESERVED=PASS")

        marker = Path(temporary) / "multi-complete"
        py = ("import sys;from pathlib import Path;"
              "[sys.stdout.write('ROW-%05d '%i+'Z'*350+'\\n') for i in range(11000)];"
              "sys.stdout.flush();"
              f"Path({str(marker)!r}).write_text('done')")
        started = agent.process_start(command(py), temporary, 0)
        session = agent.PROCESS_SESSIONS[started["session_id"]]
        assert wait_until(marker.exists, 8.0), "PTY_MULTI_MIB_BLOCKED_WITHOUT_CLIENT_READ"
        assert wait_until(lambda: session.get("exit_code") is not None)
        result = agent._process_output_payload(session, 0, 500, 0)
        assert result["buffer_truncated"] and result["base_line"] > 0
        assert session.get("_buffer_chars", 0) <= agent.MAX_PROCESS_BUFFER_CHARS
        assert len(session["lines"]) <= agent.MAX_PROCESS_LINES
        assert "ROW-10999" in "\n".join(session["lines"][-10:])
        print("COMMANDER_PROCESS_MULTI_MIB_BOUNDED_AND_TRUNCATED=PASS")

        started = agent.process_start(command("import time;print('READY',flush=True);time.sleep(60)"), temporary, 0)
        session = agent.PROCESS_SESSIONS[started["session_id"]]
        assert wait_until(lambda: bool(session["lines"]), 2.0)
        stopped = agent.process_kill(started["session_id"], True)
        assert stopped["state"] == "EXITED"
        assert wait_until(lambda: not session["_collector_thread"].is_alive())
        assert session["fd"] == -1
        print("COMMANDER_PROCESS_KILL_STOPS_COLLECTOR=PASS")

        child_pid_file = Path(temporary) / "descendant.pid"
        py = ("import subprocess,time;from pathlib import Path;"
              "child=subprocess.Popen(['sleep','60']);"
              f"Path({str(child_pid_file)!r}).write_text(str(child.pid));"
              "time.sleep(60)")
        started = agent.process_start(command(py), temporary, 0)
        assert wait_until(child_pid_file.exists, 3.0)
        child_pid = int(child_pid_file.read_text())
        agent.cleanup_process_sessions()
        def descendant_stopped():
            proc_stat = Path(f"/proc/{child_pid}/stat")
            return not proc_stat.exists() or proc_stat.read_text().split()[2] == "Z"
        assert wait_until(descendant_stopped, 3.0), "PROCESS_DESCENDANT_SURVIVED_REVOKE"
        print("COMMANDER_PROCESS_REVOKE_STOPS_DESCENDANT=PASS")
    finally:
        agent.cleanup_process_sessions()
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
