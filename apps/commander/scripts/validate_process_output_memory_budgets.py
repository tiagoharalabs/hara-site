#!/usr/bin/env python3
"""No-network stress regression of Agent managed-process RAM/session budgets.

Loads candidate source into an isolated namespace without running its main().
No real processes, user files or runtime systemd services are touched.
"""
from __future__ import annotations

from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "apps/commander/public/agent/linux.py"
ns = {"__name__": "hara_process_budget_test", "__file__": str(AGENT)}
exec(compile(AGENT.read_text(encoding="utf-8"), str(AGENT), "exec"), ns)


def session():
    return {"lines": [], "partial": "", "base_line": 0, "cursor": 0, "truncated": False}


def need(ok, code):
    if not ok:
        raise AssertionError("PROCESS_BUDGET_" + code + "_FAILED")
    print("PROCESS_BUDGET_" + code + "=PASS")


def main():
    append = ns["_append_process_output"]
    bound = ns["MAX_PROCESS_LINE_CHARS"]
    cap = ns["MAX_PROCESS_BUFFER_CHARS"]
    need(bound <= 16 * 1024 and cap <= 4 * 1024 * 1024, "CONSTANTS")

    s = session()
    append(s, "X" * (256 * 1024))
    need(len(s["partial"]) <= bound and s["truncated"], "NO_NEWLINE_256K_BOUND")

    s = session()
    append(s, "Y" * (256 * 1024) + "\n")
    need(len(s["lines"]) == 1 and len(s["lines"][0]) <= bound
         and s["truncated"], "SINGLE_HUGE_LINE_BOUND")

    s = session()
    for i in range(600):
        append(s, "Z" * 8192 + "\n")
    retained = sum(map(len, s["lines"]))
    need(retained <= cap and s["base_line"] > 0 and s["truncated"],
         "MULTILINE_BUFFER_BUDGET")
    need(s["cursor"] >= s["base_line"], "CURSOR_CONTINUATION_AFTER_TRUNCATION")

    store = ns["PROCESS_SESSIONS"]
    store.clear()
    now = time.monotonic()
    for i in range(100):
        store[f"old-{i}"] = {
            "pid": 123, "exit_code": 0, "fd": -1,
            "finished_monotonic": now - ns["PROCESS_FINISHED_RETENTION_SECONDS"] - 1,
        }
    ns["_prune_process_sessions"]()
    need(len(store) == 0, "EXPIRED_SESSION_PRUNE")

    for i in range(60):
        store[f"new-{i}"] = {
            "pid": 123, "exit_code": 0, "fd": -1,
            "finished_monotonic": now - 10 + (i / 10),
        }
    ns["_prune_process_sessions"]()
    need(len(store) < ns["MAX_PROCESS_RETAINED_SESSIONS"], "FINISHED_SESSION_CAP")

    store.clear()
    for i in range(ns["MAX_PROCESS_ACTIVE_SESSIONS"]):
        store[f"active-{i}"] = {"pid": 123, "fd": -1, "exit_code": None}
    # The fake active rows need no subprocess. Prevent _prune from reaping
    # artificial PIDs, then prove process_start rejects BEFORE pty.fork.
    ns["_process_update_state"] = lambda session: None
    try:
        ns["process_start"]("printf safety")
    except ValueError as exc:
        need(str(exc) == "PROCESS_SESSION_CAPACITY_EXCEEDED",
             "ACTIVE_SESSION_CAP_BEFORE_FORK")
    else:
        raise AssertionError("PROCESS_CAPACITY_UNBOUNDED")
    finally:
        store.clear()
    print("PROCESS_BUDGET_PRODUCTION_SIDE_EFFECTS=ABSENT")


if __name__ == "__main__":
    main()
