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
from unittest.mock import patch

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
            assert (data["successful_count"],data["failed_count"],data["deferred_count"],data["overall_status"]) == (count,0,0,"PASS")
            for item in data["files"]:
                assert item["state"] == "PASS" and item["line_count"] > 0
                assert item["text"].startswith("ROW-000-")
                assert len(item["file_revision_hint"]) == 64
                assert item["file_changed_during_read"] is False
                if item["has_more"]:
                    assert item["next_offset"] == item["offset"] + item["line_count"]
            public=check_public_projection("hara.files.read_many",result)
            assert public["count"]==count and len(public["files"])==count
            assert (public["successful_count"],public["failed_count"],public["deferred_count"],public["overall_status"]) == (count,0,0,"PASS")
            assert [item["next_offset"] for item in public["files"]]==[item["next_offset"] for item in data["files"]]
            assert [item["file_revision_hint"] for item in public["files"]]==[item["file_revision_hint"] for item in data["files"]]
            print(f"COMMANDER_READ_MANY_{count}_FILES_SERIALIZED_BUDGET=PASS")

        short=Path(temporary)/"short-cas.txt"
        short_bytes="ação 🍵\r\nsegunda linha\r\n".encode("utf-8")
        short.write_bytes(short_bytes)
        expected_sha=hashlib.sha256(short_bytes).hexdigest()
        for tool_id,payload in (
            ("hara.files.read",{"path":str(short),"offset":0,"length":400}),
            ("hara.files.read_many",{"paths":[str(short)],"offset":0,"length":100}),
        ):
            result=agent.execute_tool(config,{"call_id":"CAS-"+tool_id,
                                              "request_id":"CAS-"+tool_id,
                                              "tool_id":tool_id,"payload":payload})
            data=json.loads(result["result"]["stdout"])
            public=check_public_projection(tool_id,result)
            actual=data["files"][0]["full_file_sha256"] if tool_id.endswith("read_many") else data["full_file_sha256"]
            exposed=public["files"][0]["full_file_sha256"] if tool_id.endswith("read_many") else public["full_file_sha256"]
            assert actual==exposed==expected_sha
        print("COMMANDER_COMPLETE_SHORT_READ_CAS_HASH_SURVIVES_PUBLIC_MCP=PASS")

        mixed=agent.execute_tool(config,{
            "call_id":"MIXED","request_id":"MIXED","tool_id":"hara.files.read_many",
            "payload":{"paths":[paths[0],str(Path(temporary)/"missing.txt")],"offset":0,"length":1},
        })
        mixed_data=json.loads(mixed["result"]["stdout"])
        assert [item["state"] for item in mixed_data["files"]]==["PASS","FAILED"]
        assert (mixed_data["successful_count"],mixed_data["failed_count"],mixed_data["deferred_count"],mixed_data["overall_status"])==(1,1,0,"PARTIAL")
        mixed_public=check_public_projection("hara.files.read_many",mixed)
        assert (mixed_public["successful_count"],mixed_public["failed_count"],mixed_public["deferred_count"],mixed_public["overall_status"])==(1,1,0,"PARTIAL")
        missing_only=agent.filesystem_read_many([str(Path(temporary)/"missing.txt")],0,1)
        assert (missing_only["successful_count"],missing_only["failed_count"],missing_only["deferred_count"],missing_only["overall_status"])==(0,1,0,"FAILED")
        print("COMMANDER_READ_MANY_PARTIAL_AND_FAILED_SUMMARY=PASS")

        revision_file=Path(temporary)/"revision.txt"
        revision_file.write_text("one\ntwo\nthree\n",encoding="utf-8")
        first=agent.filesystem_read(str(revision_file),0,1)
        assert len(first["file_revision_hint"])==64 and first["next_offset"]==1
        initial_stat=revision_file.stat()
        revision_file.write_text("uno\ndos\ntres\n",encoding="utf-8")
        os.utime(revision_file,ns=(initial_stat.st_atime_ns,initial_stat.st_mtime_ns+1000000000))
        second=agent.filesystem_read(str(revision_file),1,1)
        assert second["file_revision_hint"]!=first["file_revision_hint"]
        assert second["file_changed_during_read"] is False
        print("COMMANDER_READ_PAGE_FILE_REVISION_HINT_CHANGES=PASS")

        original_open=Path.open
        mutated=[False]
        def mutate_on_text_open(path,*args,**kwargs):
            mode=args[0] if args else kwargs.get("mode","r")
            if path==revision_file and mode=="r" and not mutated[0]:
                prior_stat=revision_file.stat()
                with original_open(revision_file,"w",encoding="utf-8") as handle:
                    handle.write("new\nrows\nnow\n")
                os.utime(revision_file,ns=(prior_stat.st_atime_ns,prior_stat.st_mtime_ns+1000000000))
                mutated[0]=True
            return original_open(path,*args,**kwargs)
        with patch.object(Path,"open",mutate_on_text_open):
            raced=agent.filesystem_read(str(revision_file),0,1)
        assert mutated[0] and raced["file_changed_during_read"] is True
        assert raced["continuation_safe"] is False and raced["next_offset"] is None
        assert raced["restart_offset"]==0
        print("COMMANDER_READ_MUTATION_DURING_PAGE_REQUIRES_RESTART=PASS")

        read_attempts=[]
        def changed_then_retry(path,offset,length,budget):
            read_attempts.append(budget)
            first=len(read_attempts)==1
            return {"path":path,"offset":offset,"line_count":1,
                    "text":"X"*100000 if first else "safe",
                    "has_more":first,"eof":not first,"next_offset":None if first else offset+1,
                    "content_truncated":False,"continuation_safe":not first,
                    "file_revision_hint":"a"*64 if first else "b"*64,
                    "file_changed_during_read":first,"restart_offset":0 if first else None,
                    **({} if first else {"full_file_sha256":"b"*64})}
        with patch.object(agent,"filesystem_read",side_effect=changed_then_retry):
            retried=agent.filesystem_read_many([str(revision_file)],0,1)
        assert len(read_attempts)>=2
        entry=retried["files"][0]
        assert entry["file_changed_during_read"] is True
        assert entry["continuation_safe"] is False and entry["next_offset"] is None
        assert entry["restart_offset"]==0
        assert "full_file_sha256" not in entry
        assert retried["overall_status"]=="PARTIAL"
        print("COMMANDER_READ_MANY_BUDGET_RETRY_PRESERVES_CHANGE_SIGNAL=PASS")

        oversize={"path":str(revision_file),"offset":0,"line_count":1,"text":"X"*100000,
                  "has_more":True,"eof":False,"next_offset":1,"content_truncated":False,
                  "continuation_safe":True,"file_revision_hint":"a"*64,
                  "file_changed_during_read":False,"restart_offset":None}
        with patch.object(agent,"filesystem_read",return_value=oversize):
            deferred=agent.filesystem_read_many([str(revision_file)],0,1)
        assert deferred["files"][0]["state"]=="DEFERRED"
        assert (deferred["successful_count"],deferred["failed_count"],deferred["deferred_count"],deferred["overall_status"])==(0,0,1,"PARTIAL")
        print("COMMANDER_READ_MANY_DEFERRED_SUMMARY=PASS")

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
