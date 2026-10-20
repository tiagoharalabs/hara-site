#!/usr/bin/env python3
"""Real local mutation with synthetic lost result acknowledgments; no network."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path,
                    default=Path(__file__).resolve().parents[1] / "public/agent/linux.py")
SOURCE = parser.parse_args().source


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.effective_approval_mode = lambda config=None: "PERSISTENT_TRUSTED"
    module.request_local_approval = lambda call: {"state": "APPROVED", "mode": "PERSISTENT_TRUSTED", "source": "OFFLINE_FIXTURE"}
    module.append_console_event = lambda *args, **kwargs: None
    return module


with tempfile.TemporaryDirectory(prefix="hara-result-outbox-") as temporary:
    prior = {key: os.environ.get(key) for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
    for key, leaf in (("HOME", "home"), ("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
        path = Path(temporary) / leaf
        path.mkdir()
        os.environ[key] = str(path)
    try:
        agent = load("hara_result_outbox_first")
        config = {
            "HARA_DEVICE_ID": "fixture-device", "HARA_DEVICE_ARCH": "x86_64",
            "HARA_COMMANDER_URL": "https://fixture.invalid", "HARA_DEVICE_TOKEN": "fixture-token",
            "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED",
        }
        target = Path(temporary) / "written.txt"
        call = {"call_id": "CALL-LOST-ACK", "request_id": "REQUEST-LOST-ACK",
                "tool_id": "hara.files.write",
                "payload": {"path": str(target), "content": "ONE_LOCAL_MUTATION", "mode": "rewrite"}}
        sent = []
        def lost_ack(_config, _call, state, result, error_code=None):
            sent.append((state, result, error_code))
            if len(sent) == 1:
                raise ConnectionResetError("SYNTHETIC_ACK_LOST")
            return {"ok": True, "existing": True}
        agent.complete = lost_ack
        agent.execute_call(config, dict(call))
        assert target.read_text() == "ONE_LOCAL_MUTATION"
        assert len(sent) == 1, "DELIVERY_ERROR_RECLASSIFIED_EXECUTED_MUTATION"
        assert sent[0][0] == "COMPLETED" and sent[0][1]["mutation_performed"] is True
        receipt = sent[0][1]["bridge_receipt_sha256"]
        assert agent.completion_outbox_pending() == 1
        print("COMMANDER_COMPLETION_LOST_ACK_NEVER_DENIES_MUTATION=PASS")

        agent = load("hara_result_outbox_restarted")
        executed = []
        original_execute = agent.execute_tool
        def observed_execute(*args):
            executed.append(1)
            return original_execute(*args)
        agent.execute_tool = observed_execute
        agent.complete = lost_ack
        assert agent.flush_completion_outbox(config) == 0 and len(sent) == 1
        with agent._ops_connect() as conn:
            conn.execute("UPDATE completion_outbox SET retry_after_epoch=0 WHERE call_id=?",(call["call_id"],))
        assert agent.flush_completion_outbox(config) == 1
        assert executed == [], "REDELIVERY_REEXECUTED_MUTATION"
        assert len(sent) == 2 and sent[1] == sent[0]
        assert sent[1][1]["bridge_receipt_sha256"] == receipt
        assert agent.completion_outbox_pending() == 0
        print("COMMANDER_COMPLETION_RESTART_REPLAYS_IDENTICAL_RECEIPT=PASS")

        # Replaying after the server's accepted response is still local-only.
        agent.execute_call(config, dict(call))
        assert executed == [] and len(sent) == 2
        print("COMMANDER_COMPLETION_ACKED_DUPLICATE_HAS_ONE_EFFECT=PASS")

        unknown = {**call, "call_id": "CALL-INTENT-CRASH", "request_id": "REQUEST-INTENT-CRASH"}
        _, inserted = agent._completion_outbox_intent(unknown)
        assert inserted
        agent = load("hara_result_outbox_intent_recovered")
        agent.execute_tool = lambda *_: (_ for _ in ()).throw(AssertionError("INTENT_REEXECUTED"))
        recovered = []
        agent.complete = lambda _cfg, _call, state, result, error_code=None: recovered.append((state, result, error_code)) or {"ok": True}
        agent.execute_call(config, dict(unknown))
        assert len(recovered) == 1 and recovered[0][0] == "FAILED"
        assert recovered[0][1]["state"] == "UNKNOWN"
        assert recovered[0][1]["mutation_performed"] is None
        assert recovered[0][2] == "LOCAL_EXECUTION_OUTCOME_UNKNOWN"
        print("COMMANDER_COMPLETION_CRASHED_INTENT_STAYS_UNKNOWN_NO_REEXECUTION=PASS")

        repeated = {**call, "call_id": "CALL-REPEATED-LOSS", "request_id": "REQUEST-REPEATED-LOSS",
                    "payload": {**call["payload"], "content": "REPEATED_LOSS_ONE_WRITE"}}
        sends = []
        def repeated_loss(_cfg, _call, state, result, error_code=None):
            sends.append((state, result, error_code))
            raise ConnectionResetError("SYNTHETIC_REPEATED_LOSS")
        agent = load("hara_result_outbox_repeated_loss")
        agent.complete = repeated_loss
        agent.execute_call(config, dict(repeated))
        assert agent.completion_outbox_pending() == 1
        assert agent.flush_completion_outbox(config) == 0
        assert len(sends) == 1
        with agent._ops_connect() as conn:
            conn.execute("UPDATE completion_outbox SET retry_after_epoch=0 WHERE call_id=?",(repeated["call_id"],))
        assert agent.flush_completion_outbox(config) == 0
        assert len(sends) == 2 and sends[0] == sends[1]
        agent.complete = lambda _cfg, _call, state, result, error_code=None: sends.append((state, result, error_code)) or {"ok": True}
        with agent._ops_connect() as conn:
            conn.execute("UPDATE completion_outbox SET retry_after_epoch=0 WHERE call_id=?",(repeated["call_id"],))
        assert agent.flush_completion_outbox(config) == 1
        assert len(sends) == 3 and sends[0] == sends[2]
        assert target.read_text() == "REPEATED_LOSS_ONE_WRITE"
        print("COMMANDER_COMPLETION_REPEATED_FAILURE_RETRIES_SAME_BODY=PASS")

        disk_target = Path(temporary) / "disk-fault-write.txt"
        disk_call = {**call, "call_id": "CALL-DISK-FAULT", "request_id": "REQUEST-DISK-FAULT",
                     "payload": {**call["payload"], "path": str(disk_target)}}
        agent = load("hara_result_outbox_disk_fault")
        agent._completion_outbox_ready = lambda *_: (_ for _ in ()).throw(OSError("SYNTHETIC_DISK_FULL"))
        agent.complete = lambda *_: (_ for _ in ()).throw(AssertionError("UNPERSISTED_RESULT_SENT"))
        try:
            agent.execute_call(config, dict(disk_call))
        except OSError as exc:
            assert str(exc) == "SYNTHETIC_DISK_FULL"
        else:
            raise AssertionError("DISK_FAULT_WAS_NOT_REPORTED")
        assert disk_target.read_text() == "ONE_LOCAL_MUTATION"
        agent = load("hara_result_outbox_disk_fault_recovery")
        recovered = []
        agent.execute_tool = lambda *_: (_ for _ in ()).throw(AssertionError("DISK_FAULT_REEXECUTED"))
        agent.complete = lambda _cfg, _call, state, result, error_code=None: recovered.append((state,result,error_code)) or {"ok": True}
        agent.execute_call(config, dict(disk_call))
        assert len(recovered) == 1 and recovered[0][1]["state"] == "UNKNOWN"
        assert recovered[0][1]["mutation_performed"] is None
        print("COMMANDER_COMPLETION_DISK_FAULT_FAILS_UNCERTAIN_NO_REPLAY=PASS")

        terminal_target = Path(temporary) / "terminal-conflict.txt"
        terminal_call = {**call,"call_id":"CALL-TERMINAL-CONFLICT","request_id":"REQUEST-TERMINAL-CONFLICT",
                         "payload":{**call["payload"],"path":str(terminal_target)}}
        agent = load("hara_result_outbox_terminal")
        terminal_sends = []
        def terminal_conflict(*args):
            terminal_sends.append(args)
            raise urllib.error.HTTPError("https://fixture.invalid",409,"Conflict",None,None)
        agent.complete = terminal_conflict
        agent.execute_call(config,dict(terminal_call))
        assert terminal_target.read_text() == "ONE_LOCAL_MUTATION"
        assert agent.completion_outbox_pending() == 1
        assert agent.completion_outbox_health()["quarantined"] == 1
        assert agent.flush_completion_outbox(config) == 0
        assert len(terminal_sends) == 1, "terminal conflict retried automatically"
        preserved=agent._completion_outbox_fetch(terminal_call["call_id"])["body_json"]
        status_output=io.StringIO()
        with contextlib.redirect_stdout(status_output):
            agent.completion_outbox_cli_status()
        status=json.loads(status_output.getvalue())
        assert status["quarantined"] == 1
        assert status["entries"][0]["last_error_code"] == "HTTP_409"
        assert "body_json" not in status_output.getvalue()
        assert "ONE_LOCAL_MUTATION" not in status_output.getvalue()

        class HealthyResponse:
            status=200
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self): return b'{"ok":true,"service":"hara-commander"}'
        agent.load_config=lambda: config
        agent.transport_mode=lambda _config=None: "OUTBOUND_RELAY"
        agent.operator_session_active=lambda: True
        agent.NO_REDIRECT_OPENER=type("OfflineOpener",(),{"open":lambda *_args,**_kwargs:HealthyResponse()})()
        doctor_output=io.StringIO()
        with contextlib.redirect_stdout(doctor_output):
            assert agent.commander_doctor() == 2
        assert "HARA_COMMANDER_OUTBOX_QUARANTINED=1" in doctor_output.getvalue()
        assert "HARA_COMMANDER_DOCTOR=DEGRADED" in doctor_output.getvalue()
        assert agent.completion_outbox_retry(terminal_call["call_id"]) is True
        assert agent._completion_outbox_fetch(terminal_call["call_id"])["body_json"] == preserved
        agent.complete = lambda *_: {"ok":True,"existing":True}
        assert agent.flush_completion_outbox(config) == 1
        assert agent.completion_outbox_pending() == 0
        assert terminal_target.read_text() == "ONE_LOCAL_MUTATION"
        doctor_output=io.StringIO()
        with contextlib.redirect_stdout(doctor_output):
            assert agent.commander_doctor() == 0
        assert "HARA_COMMANDER_OUTBOX_QUARANTINED=0" in doctor_output.getvalue()
        print("COMMANDER_COMPLETION_TERMINAL_CONFLICT_QUARANTINE_AND_EXPLICIT_RETRY=PASS")

        transient_target = Path(temporary) / "transient-loss.txt"
        transient_call = {**call,"call_id":"CALL-TRANSIENT-LOSS","request_id":"REQUEST-TRANSIENT-LOSS",
                          "payload":{**call["payload"],"path":str(transient_target)}}
        agent = load("hara_result_outbox_transient")
        transient_sends = []
        def transient_failure(*args):
            transient_sends.append(args)
            raise ConnectionResetError("TRANSIENT_SEND_LOSS")
        agent.complete = transient_failure
        agent.execute_call(config,dict(transient_call))
        row=agent._completion_outbox_fetch(transient_call["call_id"])
        assert row["retry_after_epoch"] > int(agent.time.time())
        assert agent.flush_completion_outbox(config) == 0 and len(transient_sends) == 1
        with agent._ops_connect() as conn:
            conn.execute("UPDATE completion_outbox SET retry_after_epoch=0 WHERE call_id=?",(transient_call["call_id"],))
        agent.complete=lambda *_: {"ok":True,"existing":True}
        assert agent.flush_completion_outbox(config) == 1
        assert transient_target.read_text() == "ONE_LOCAL_MUTATION"
        print("COMMANDER_COMPLETION_TRANSIENT_FAILURE_BACKOFF_SAME_BODY=PASS")
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
