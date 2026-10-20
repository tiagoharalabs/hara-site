#!/usr/bin/env python3
"""Real one-shot process output must remain pageable without rerunning it."""
from __future__ import annotations

import argparse
import importlib.util
import json
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


def command(source):
    return "python3 -u -c " + shlex.quote(source)


with tempfile.TemporaryDirectory(prefix="hara-oneshot-pagination-") as temporary:
    prior = {name: os.environ.get(name) for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME")}
    os.environ["XDG_CONFIG_HOME"] = str(Path(temporary) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(temporary) / "data")
    spec = importlib.util.spec_from_file_location("hara_agent_oneshot_pagination", SOURCE)
    assert spec and spec.loader
    agent = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = agent
    spec.loader.exec_module(agent)
    try:
        counter = Path(temporary) / "effect-count"
        py = ("from pathlib import Path;"
              f"p=Path({str(counter)!r});"
              "p.write_text(str(int(p.read_text())+1) if p.exists() else '1');"
              "[print(f'R5-LINE-{i:02d}') for i in range(8)]")
        result = agent.process_run(command(py), temporary, 3000, 3)
        assert result["exit_code"] == 0 and result["output_truncated"] is True
        assert result["session_retained"] is True
        assert result["next_offset"] == 3
        assert result["run_id"] == result["session_id"]
        run_id = result["run_id"]
        pages = [result["text"]]
        offset = result["next_offset"]
        while offset < result["total_lines"]:
            page = agent._process_output_payload(agent._process_get(run_id), offset, 3, 0)
            pages.append(page["text"])
            assert page["next_offset"] > offset
            offset = page["next_offset"]
        assert "\n".join(pages).splitlines() == [f"R5-LINE-{i:02d}" for i in range(8)]
        assert counter.read_text() == "1", "paging repeated the process mutation"
        assert agent.PROCESS_SESSIONS[run_id]["exit_code"] == 0
        print("COMMANDER_ONESHOT_EIGHT_LINES_PAGED_EFFECT_ONCE=PASS")

        small = agent.process_run(command("print('SHORT')"), temporary, 3000, 3)
        assert small["session_retained"] is False
        assert small["run_id"] not in agent.PROCESS_SESSIONS
        print("COMMANDER_ONESHOT_SMALL_RESULT_NOT_RETAINED=PASS")

        big = agent.process_run(command("[print(f'PAGE-{i:02d}-'+'X'*5000) for i in range(20)]"),
                                temporary, 3000, 20)
        assert big["session_retained"] is True
        assert big["next_offset"] < big["total_lines"]
        assert len(json.dumps(big,ensure_ascii=False).encode("utf-8")) < 128 * 1024
        seen = big["text"].splitlines()
        offset = big["next_offset"]
        while offset < big["total_lines"]:
            page = agent._process_output_payload(agent._process_get(big["run_id"]), offset, 20, 0)
            seen.extend(page["text"].splitlines())
            offset = page["next_offset"]
        assert len(seen) == 20 and seen[0].startswith("PAGE-00-") and seen[-1].startswith("PAGE-19-")
        print("COMMANDER_ONESHOT_LONG_OUTPUT_BYTE_PAGES=PASS")

        agent.PROCESS_SESSIONS[run_id]["finished_monotonic"] = (
            time.monotonic() - agent.PROCESS_FINISHED_RETENTION_SECONDS - 1
        )
        agent._prune_process_sessions()
        try:
            agent._process_get(run_id)
        except ValueError as exc:
            assert str(exc) == "PROCESS_RESULT_EXPIRED"
        else:
            raise AssertionError("expired one-shot output remained readable")
        print("COMMANDER_ONESHOT_EXPIRED_RESULT_DISTINCT_FROM_UNKNOWN=PASS")

        now = time.monotonic()
        for i in range(agent.MAX_PROCESS_ONESHOT_RESULTS + 1):
            sid = f"HARA-PROC-QA-{i:02d}"
            agent.PROCESS_SESSIONS[sid] = {
                "session_id": sid, "exit_code": 0, "finished_monotonic": now + i * 0.001,
                "one_shot_result": True, "lines": [f"QA-{i}"], "partial": "",
                "base_line": 0, "cursor": 0, "fd": -1, "pid": 0,
            }
        agent._prune_process_sessions()
        retained = [s for s in agent.PROCESS_SESSIONS.values() if s.get("one_shot_result")]
        assert len(retained) <= agent.MAX_PROCESS_ONESHOT_RESULTS
        assert len(agent.PROCESS_RESULT_TOMBSTONES) <= agent.MAX_PROCESS_RESULT_TOMBSTONES
        print("COMMANDER_ONESHOT_RESULT_COUNT_AND_TOMBSTONES_BOUNDED=PASS")
    finally:
        agent.cleanup_process_sessions()
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
