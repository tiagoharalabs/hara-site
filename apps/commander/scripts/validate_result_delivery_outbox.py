#!/usr/bin/env python3
"""Real local mutation with synthetic lost result acknowledgments; no network."""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
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
        assert len(sends) == 2 and sends[0] == sends[1]
        agent.complete = lambda _cfg, _call, state, result, error_code=None: sends.append((state, result, error_code)) or {"ok": True}
        assert agent.flush_completion_outbox(config) == 1
        assert len(sends) == 3 and sends[0] == sends[2]
        assert target.read_text() == "REPEATED_LOSS_ONE_WRITE"
        print("COMMANDER_COMPLETION_REPEATED_FAILURE_RETRIES_SAME_BODY=PASS")
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
