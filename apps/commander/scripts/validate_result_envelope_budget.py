#!/usr/bin/env python3
"""Measure the actual Agent completion envelope, including JSON escaping."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path,
                    default=Path(__file__).resolve().parents[1] / "public/agent/linux.py")
SOURCE = parser.parse_args().source
WORKER_RESULT_MAX_BYTES = 256 * 1024


def encoded_bytes(value):
    return len(json.dumps(value,separators=(",",":"),ensure_ascii=False).encode("utf-8"))


def check_public_projection(tool_id, result):
    probe = subprocess.run(
        ["node", str(Path(__file__).with_name("test_public_result_projection.mjs")), "--stdin"],
        input=json.dumps({"tool_id":tool_id,"result":result},ensure_ascii=False),
        text=True,capture_output=True,timeout=10,check=True,
    )
    observed=json.loads(probe.stdout)
    expected=hashlib.sha256(result["result"]["stdout"].encode("utf-8")).hexdigest()
    assert observed["sha256"]==expected==observed["original_sha256"]
    return observed


with tempfile.TemporaryDirectory(prefix="hara-result-envelope-") as temporary:
    prior = {key: os.environ.get(key) for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
    for key, leaf in (("HOME", "home"), ("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
        path = Path(temporary) / leaf
        path.mkdir()
        os.environ[key] = str(path)
    try:
        spec = importlib.util.spec_from_file_location("hara_result_envelope_agent", SOURCE)
        assert spec and spec.loader
        agent = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = agent
        spec.loader.exec_module(agent)
        config = {"HARA_DEVICE_ID": "fixture-device", "HARA_DEVICE_ARCH": "x86_64"}
        paths = []
        for index in range(10):
            path = Path(temporary) / f"bulk-{index}.txt"
            path.write_text("".join(f"ROW-{line:03d}-" + "x" * 590 + "\n" for line in range(100)))
            paths.append(str(path))

        for count in (1, 4, 10):
            result = agent.execute_tool(config, {
                "call_id": f"BULK-{count}", "request_id": f"BULK-{count}",
                "tool_id": "hara.files.read_many",
                "payload": {"paths": paths[:count], "offset": 0, "length": 100},
            })
            actual = encoded_bytes(result)
            assert actual <= WORKER_RESULT_MAX_BYTES, (count, actual)
            data = json.loads(result["result"]["stdout"])
            assert data["count"] == count and len(data["files"]) == count
            for item in data["files"]:
                assert item["state"] == "PASS" and item["line_count"] > 0
                assert item["text"].startswith("ROW-000-")
                if item["has_more"]:
                    assert item["next_offset"] == item["offset"] + item["line_count"]
            public=check_public_projection("hara.files.read_many",result)
            assert public["count"]==count and len(public["files"])==count
            assert [item["next_offset"] for item in public["files"]]==[item["next_offset"] for item in data["files"]]
            print(f"COMMANDER_READ_MANY_{count}_FILES_SERIALIZED_BUDGET=PASS")

        control = Path(temporary) / "control.txt"
        control.write_bytes(b"\x01" * 60000 + b"\n")
        result = agent.execute_tool(config, {
            "call_id": "CONTROL", "request_id": "CONTROL", "tool_id": "hara.files.read",
            "payload": {"path": str(control), "offset": 0, "length": 1},
        })
        assert encoded_bytes(result) <= WORKER_RESULT_MAX_BYTES
        data = json.loads(result["result"]["stdout"])
        assert data["content_truncated"] is True and data["continuation_safe"] is False
        check_public_projection("hara.files.read",result)
        print("COMMANDER_CONTROL_CHAR_ESCAPING_STAYS_WITHIN_WORKER_LIMIT=PASS")

        base = {"state": "PASS", "operational_authority": "HARA_SERVICES",
                "runtime_authority_from_chatgpt": False, "mutation_performed": False,
                "result": {"stdout": ""}, "blocker": None}
        low, high = 0, agent.COMPLETION_RESULT_MAX_BYTES + 1
        while low + 1 < high:
            middle = (low + high) // 2
            base["result"]["stdout"] = "X" * middle
            if encoded_bytes(base) <= agent.COMPLETION_RESULT_MAX_BYTES:
                low = middle
            else:
                high = middle
        base["result"]["stdout"] = "X" * low
        assert agent._completion_bounded_body("COMPLETED", base)["state"] == "COMPLETED"
        base["result"]["stdout"] += "X"
        over = agent._completion_bounded_body("COMPLETED", base)
        assert over["state"] == "FAILED" and over["error_code"] == "DEVICE_RESULT_TOO_LARGE"
        print("COMMANDER_RESULT_ENVELOPE_BYTE_BOUNDARY=PASS")
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
