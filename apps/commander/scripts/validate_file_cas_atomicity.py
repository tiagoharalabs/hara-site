#!/usr/bin/env python3
"""Exercise real Linux Agent file mutations from competing OS processes."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path

DEFAULT_AGENT = Path(__file__).resolve().parents[1] / "public/agent/linux.py"
AGENT = Path(os.environ.get("HARA_FILE_CAS_SOURCE") or DEFAULT_AGENT)


def load_agent(name, root, data_name):
    os.environ["HOME"] = str(root / "home")
    os.environ["XDG_CONFIG_HOME"] = str(root / "config")
    os.environ["XDG_DATA_HOME"] = str(root / data_name)
    spec = importlib.util.spec_from_file_location(name, AGENT)
    agent = importlib.util.module_from_spec(spec)
    sys.modules[name] = agent
    spec.loader.exec_module(agent)
    return agent


def writer(root, path, expected, desired, mode, data_name, start, reports):
    agent = load_agent("cas_" + desired, root, data_name)
    original = agent._assert_path_matches_preimage

    def pause_after_real_validation(target, preimage):
        result = original(target, preimage)
        time.sleep(0.15)
        return result

    agent._assert_path_matches_preimage = pause_after_real_validation
    reports.put(("ready", desired))
    if not start.wait(12):
        reports.put(("result", desired, "START_TIMEOUT", None, 0))
        return
    try:
        call = {"call_id": "CAS-" + desired}
        if mode == "edit":
            result = agent.filesystem_edit(call, str(path), "BASE", desired, False, expected)
        elif mode == "delete":
            result = agent.filesystem_delete(call, str(path), expected)
        else:
            result = agent.filesystem_write(call, str(path), desired, mode, expected)
        outcome = "ACCEPTED"
        previous = result.get("previous_sha256", result.get("deleted_sha256"))
        preimage, saved = agent._load_preimage(result["preimage_id"])
        preimage_correct = preimage["sha256"] == expected and saved == b"BASE"
    except Exception as exc:
        outcome = str(exc)
        previous = None
        preimage_correct = None
    preimages = len(list(agent.PREIMAGE_DIR.glob("HARA-PREIMAGE-*.json")))
    reports.put(("result", desired, outcome, previous, preimages, preimage_correct))


def mcp_writer(root, path, expected, desired, start, reports):
    agent = load_agent("mcp_" + desired, root, "data-mcp-" + desired)
    config = {"HARA_DEVICE_ID": "QA-MCP-DEVICE"}
    # Isolate the file path after a synthetically approved local MCP call.
    # The product's authority and approval functions are not changed.
    agent.require_local_product_authority = lambda _config: {"plan_code": "FOUNDER_INTERNAL"}
    agent.effective_approval_mode = lambda _config=None: "PERSISTENT_TRUSTED"
    agent.local_tunnel_usage = lambda *_args: None
    agent.local_budget_reserve = lambda *_args: None
    agent.request_local_approval = lambda _call: {
        "state": "APPROVED", "mode": "PERSISTENT_TRUSTED", "source": "QA_FIXTURE",
    }
    agent.append_console_event = lambda *_args, **_kwargs: None
    original = agent._assert_path_matches_preimage

    def pause_after_real_validation(target, preimage):
        result = original(target, preimage)
        time.sleep(0.15)
        return result

    agent._assert_path_matches_preimage = pause_after_real_validation
    reports.put(("ready", desired))
    if not start.wait(12):
        reports.put(("result", desired, "START_TIMEOUT", None, 0, False))
        return
    try:
        result = agent.local_simple_mcp_call(config, "edit_block", {
            "path": str(path), "old_string": "BASE", "new_string": desired,
            "expected_sha256": expected,
        })
        data = json.loads(result["result"]["stdout"])
        outcome = "ACCEPTED" if (result["state"] == "PASS"
            and result["result"]["function_id"] == "filesystem.edit") else "MCP_RESULT_INVALID"
        previous = data["previous_sha256"]
        receipt_present = bool(result.get("bridge_receipt_sha256"))
    except Exception as exc:
        outcome = str(exc)
        previous = None
        receipt_present = False
    preimages = len(list(agent.PREIMAGE_DIR.glob("HARA-PREIMAGE-*.json")))
    reports.put(("result", desired, outcome, previous, preimages, receipt_present))


def run_local_mcp_race(root):
    files = root / "files-local-mcp"
    files.mkdir()
    target = files / "shared.txt"
    target.write_text("BASE", encoding="utf-8")
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    ctx = mp.get_context("spawn")
    start = ctx.Event()
    reports = ctx.Queue()
    names = ("MCP_A", "MCP_B")
    children = [ctx.Process(target=mcp_writer, args=(root, target, expected, name, start, reports))
                for name in names]
    for child in children:
        child.start()
    try:
        assert [reports.get(timeout=12)[0] for _ in children] == ["ready", "ready"]
        start.set()
        outcomes = [reports.get(timeout=12) for _ in children]
        for child in children:
            child.join(timeout=3)
        assert all(child.exitcode == 0 for child in children), outcomes
        accepted = [item for item in outcomes if item[2] == "ACCEPTED"]
        denied = [item for item in outcomes if item[2] != "ACCEPTED"]
        assert len(accepted) == 1 and len(denied) == 1, outcomes
        assert accepted[0][3] == expected and accepted[0][4:] == (1, True), outcomes
        assert denied[0][2] == "FILE_PRECONDITION_FAILED" and denied[0][4:] == (0, False), outcomes
        assert target.read_text(encoding="utf-8") == accepted[0][1], outcomes
    finally:
        start.set()
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(timeout=2)
        reports.close()


def run_race(root, mode, count, alias=False):
    files = root / ("files-" + mode + str(count) + ("-alias" if alias else ""))
    files.mkdir()
    target = files / "shared.txt"
    target.write_text("BASE", encoding="utf-8")
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    alias_path = root / ("alias-" + mode + str(count))
    if alias:
        alias_path.symlink_to(files, target_is_directory=True)
    ctx = mp.get_context("spawn")
    start = ctx.Event()
    reports = ctx.Queue()
    names = ["WRITER_%02d" % index for index in range(count)]
    children = [ctx.Process(target=writer, args=(root,
                (alias_path if alias and index % 2 else files) / target.name,
                expected, name, mode, "data-" + files.name + "-" + name, start, reports))
                for index, name in enumerate(names)]
    for child in children:
        child.start()
    try:
        for _ in children:
            status, _ = reports.get(timeout=12)
            assert status == "ready", status
        start.set()
        outcomes = []
        for _ in children:
            item = reports.get(timeout=12)
            assert item[0] == "result", item
            outcomes.append(item)
        for child in children:
            child.join(timeout=3)
            assert child.exitcode == 0, child.exitcode
        accepted = [item for item in outcomes if item[2] == "ACCEPTED"]
        denied = [item for item in outcomes if item[2] != "ACCEPTED"]
        assert len(accepted) == 1, outcomes
        assert all(item[2] == "FILE_PRECONDITION_FAILED" for item in denied), outcomes
        assert accepted[0][3] == expected and accepted[0][4] == 1 and accepted[0][5], outcomes
        assert all(item[4] == 0 for item in denied), outcomes
        if mode == "delete":
            assert not target.exists(), target
        else:
            final = target.read_text(encoding="utf-8")
            assert final == ("BASE" if mode == "append" else "") + accepted[0][1], final
    finally:
        start.set()
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(timeout=2)
        reports.close()


def hold_directory_lock(path, ready):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    ready.set()
    time.sleep(10)


def move_worker(root, source, destination, start, reports):
    agent = load_agent("move_" + source.name, root, "data-move-" + source.name)
    reports.put("ready")
    start.wait(5)
    try:
        agent.filesystem_move(str(source), str(destination))
        reports.put("MOVED")
    except Exception as exc:
        reports.put(str(exc))


def need(ok, label):
    if not ok:
        raise SystemExit("COMMANDER_FILE_CAS_" + label + "=FAIL")
    print("COMMANDER_FILE_CAS_" + label + "=PASS")


def check_local_mcp_race(root):
    try:
        run_local_mcp_race(root)
    except (AssertionError, queue.Empty) as exc:
        raise SystemExit("COMMANDER_FILE_CAS_LOCAL_MCP_TWO_PROCESSES=FAIL " + str(exc))
    need(True, "LOCAL_MCP_TWO_PROCESSES_ONE_ACCEPTED")


def main(mcp_route_only=False):
    with tempfile.TemporaryDirectory(prefix="hara-file-cas-atomicity-") as temp:
        root = Path(temp)
        (root / "home").mkdir()
        (root / "config").mkdir()
        agent = load_agent("cas_parent", root, "data-parent")
        if mcp_route_only:
            check_local_mcp_race(root)
            return
        sequential = root / "sequential.txt"
        sequential.write_text("BASE", encoding="utf-8")
        expected = hashlib.sha256(sequential.read_bytes()).hexdigest()
        agent.filesystem_edit({"call_id": "SEQUENTIAL-1"}, str(sequential), "BASE", "FIRST", False, expected)
        try:
            agent.filesystem_edit({"call_id": "SEQUENTIAL-2"}, str(sequential), "BASE", "SECOND", False, expected)
            sequential_error = None
        except ValueError as exc:
            sequential_error = str(exc)
        need(sequential_error == "FILE_PRECONDITION_FAILED" and sequential.read_text() == "FIRST",
             "SEQUENTIAL_STALE_HASH_DENIED")

        for mode, count, alias, label in (
            ("edit", 2, False, "TWO_EDITORS_ONE_ACCEPTED"),
            ("rewrite", 2, False, "TWO_REWRITES_ONE_ACCEPTED"),
            ("append", 2, False, "TWO_APPENDS_ONE_ACCEPTED"),
            ("delete", 2, False, "TWO_DELETES_ONE_ACCEPTED"),
            ("edit", 20, False, "TWENTY_EDITORS_ONE_ACCEPTED"),
            ("edit", 2, True, "SYMLINK_PARENT_ALIAS_SERIALIZED"),
        ):
            try:
                run_race(root, mode, count, alias)
            except (AssertionError, queue.Empty) as exc:
                raise SystemExit("COMMANDER_FILE_CAS_" + label + "=FAIL " + str(exc))
            need(True, label)

        check_local_mcp_race(root)

        threaded = root / "threaded.txt"
        threaded.write_text("BASE", encoding="utf-8")
        threaded_hash = hashlib.sha256(threaded.read_bytes()).hexdigest()
        gate = threading.Barrier(2)
        thread_outcomes = []

        def edit_in_thread(value):
            gate.wait(timeout=3)
            try:
                agent.filesystem_edit({"call_id": "THREAD-" + value}, str(threaded), "BASE", value,
                                      False, threaded_hash)
                thread_outcomes.append("ACCEPTED")
            except ValueError as exc:
                thread_outcomes.append(str(exc))

        threads = [threading.Thread(target=edit_in_thread, args=(name,)) for name in ("A", "B")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        need(not any(thread.is_alive() for thread in threads)
             and sorted(thread_outcomes) == ["ACCEPTED", "FILE_PRECONDITION_FAILED"],
             "TWO_THREADS_ONE_ACCEPTED")

        left = root / "move-left"
        right = root / "move-right"
        left.mkdir()
        right.mkdir()
        (left / "a.txt").write_text("A")
        (right / "b.txt").write_text("B")
        ctx = mp.get_context("spawn")
        move_start = ctx.Event()
        move_reports = ctx.Queue()
        movers = [
            ctx.Process(target=move_worker, args=(root, left / "a.txt", right / "a.txt", move_start, move_reports)),
            ctx.Process(target=move_worker, args=(root, right / "b.txt", left / "b.txt", move_start, move_reports)),
        ]
        for mover in movers:
            mover.start()
        try:
            need([move_reports.get(timeout=5) for _ in movers] == ["ready", "ready"], "TWO_PARENT_MOVERS_READY")
            move_start.set()
            outcomes = [move_reports.get(timeout=5) for _ in movers]
            for mover in movers:
                mover.join(timeout=3)
            need(outcomes == ["MOVED", "MOVED"] and all(mover.exitcode == 0 for mover in movers)
                 and (right / "a.txt").read_text() == "A" and (left / "b.txt").read_text() == "B",
                 "TWO_PARENT_MOVE_NO_DEADLOCK")
        finally:
            move_start.set()
            for mover in movers:
                if mover.is_alive():
                    mover.terminate()
                mover.join(timeout=2)
            move_reports.close()

        target = root / "busy.txt"
        target.write_text("BASE", encoding="utf-8")
        expected = hashlib.sha256(target.read_bytes()).hexdigest()
        ctx = mp.get_context("spawn")
        ready = ctx.Event()
        holder = ctx.Process(target=hold_directory_lock, args=(root, ready))
        holder.start()
        try:
            need(ready.wait(3), "LOCK_HOLDER_READY")
            agent.FILE_MUTATION_LOCK_WAIT_SECONDS = 0.15
            try:
                agent.filesystem_edit({"call_id": "BUSY"}, str(target), "BASE", "AFTER", False, expected)
                busy_error = None
            except ValueError as exc:
                busy_error = str(exc)
            need(busy_error == "FILE_MUTATION_BUSY" and target.read_text() == "BASE",
                 "LOCK_TIMEOUT_NO_MUTATION")
            busy_state = agent._known_nonmutating_file_conflict("hara.files.edit", busy_error)
            local_state = agent.local_mcp_operational_error(busy_error, "edit_block", {})
            need(busy_state["state"] == "BUSY" and busy_state["retryable"] is False
                 and local_state["blocker"]["retryable"] is False
                 and local_state["mutation_performed"] is False,
                 "LOCK_TIMEOUT_RESULT_IS_SAFE")
        finally:
            holder.terminate()
            holder.join(timeout=3)
        completed = agent.filesystem_edit({"call_id": "AFTER-HOLDER"}, str(target), "BASE", "AFTER", False, expected)
        need(completed["sha256"] == hashlib.sha256(b"AFTER").hexdigest(),
             "KILLED_LOCK_HOLDER_RELEASES_LOCK")

        failure = root / "rename-failure.txt"
        failure.write_text("BASE", encoding="utf-8")
        failure_sha = hashlib.sha256(failure.read_bytes()).hexdigest()
        original_replace = agent.os.replace

        def fail_final_replace(source, destination):
            if str(destination) == str(failure):
                raise OSError("QA_RENAME_FAILURE")
            return original_replace(source, destination)

        agent.os.replace = fail_final_replace
        try:
            try:
                agent.filesystem_edit({"call_id": "FAIL-RENAME"}, str(failure), "BASE", "LOST", False, failure_sha)
                failed = False
            except OSError as exc:
                failed = str(exc) == "QA_RENAME_FAILURE"
        finally:
            agent.os.replace = original_replace
        need(failed and failure.read_text() == "BASE", "FAILED_RENAME_KEEPS_ORIGINAL")
        stored = []
        for metadata in agent.PREIMAGE_DIR.glob("HARA-PREIMAGE-*.json"):
            value = json.loads(metadata.read_text(encoding="utf-8"))
            if value.get("source_call_id") == "FAIL-RENAME":
                stored.append(value)
        need(len(stored) == 1 and stored[0]["sha256"] == failure_sha,
             "FAILED_RENAME_PREIMAGE_CORRECT")
        retried = agent.filesystem_edit({"call_id": "AFTER-RENAME-FAIL"}, str(failure), "BASE", "DONE", False, failure_sha)
        need(retried["precondition_checked"] and failure.read_text() == "DONE",
             "FAILED_RENAME_RELEASES_LOCK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--mcp-route-only", action="store_true")
    args = parser.parse_args()
    AGENT = (args.source or DEFAULT_AGENT).resolve(strict=True)
    os.environ["HARA_FILE_CAS_SOURCE"] = str(AGENT)
    main(args.mcp_route_only)
