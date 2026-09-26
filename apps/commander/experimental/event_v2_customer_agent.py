#!/usr/bin/env python3
"""Customer-plane execution adapter for Commander Event V2.

This module deliberately reuses the proven 0.3.7 five-tool implementation for
bounded device behavior while replacing historical internal-HARA authority and
transport labels that are not true for the customer Event V2 data path.

It is experimental/source-only and is not part of the stable release manifest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDER = HERE.parent
BASELINE_PATH = COMMANDER / "public" / "agent" / "linux.py"
OPERATIONAL_AUTHORITY = "HARA_COMMANDER"
EXECUTION_AUTHORITY = "HARA_COMMANDER_AGENT"
TRANSPORT_MODE = "EVENT_V2"


def _load_baseline():
    spec = importlib.util.spec_from_file_location(
        "hara_agent_v1_execution_baseline",
        BASELINE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_BASELINE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASELINE = _load_baseline()


def utcnow():
    return BASELINE.utcnow()


def safe_error_code(exc):
    return BASELINE.safe_error_code(exc)


def try_write_runtime_status(**kwargs):
    return BASELINE.try_write_runtime_status(**kwargs)


def _event_status_file():
    return BASELINE.DATA_DIR / "event-v2-status.json"


def write_event_v2_status(
    *,
    connected: bool,
    connected_at_utc=None,
    disconnected_at_utc=None,
    error_code=None,
):
    BASELINE.DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _event_status_file()
    current = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    payload = {
        "schema": "hara.commander-event-v2-runtime-status.v1",
        "transport_mode": TRANSPORT_MODE,
        "connected": bool(connected),
        "connected_at_utc": (
            connected_at_utc
            if connected_at_utc is not None
            else current.get("connected_at_utc")
        ),
        "disconnected_at_utc": (
            disconnected_at_utc
            if disconnected_at_utc is not None
            else current.get("disconnected_at_utc")
        ),
        "last_error_code": error_code,
        "updated_at_utc": utcnow(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return payload


def try_write_event_v2_status(**kwargs):
    try:
        write_event_v2_status(**kwargs)
        return True
    except Exception:
        return False


def load_config():
    return BASELINE.load_config()


def post_json(url, token, payload):
    return BASELINE.post_json(url, token, payload)


def _receipt_dir():
    return BASELINE.RECEIPT_DIR


def write_receipt(config, call, state, result=None):
    receipt_dir = _receipt_dir()
    receipt_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool_id = str(call.get("tool_id") or "")
    result_binding = "NONE"
    result_stdout_sha256 = None
    if tool_id == "hara.functions.invoke":
        stdout = str((result or {}).get("stdout") or "")
        result_binding = "STDOUT_SHA256_V1"
        result_stdout_sha256 = hashlib.sha256(stdout.encode("utf-8")).hexdigest()

    receipt = {
        "schema": "hara.commander-device-receipt.v1",
        "request_id": str(call.get("request_id") or ""),
        "device_id": config["HARA_DEVICE_ID"],
        "tool_id": tool_id,
        "function_id_if_any": (call.get("payload") or {}).get("function_id"),
        "transport_mode": TRANSPORT_MODE,
        "operational_authority": OPERATIONAL_AUTHORITY,
        "execution_authority": EXECUTION_AUTHORITY,
        "mutation_class": "READ_ONLY_OR_NONE_V1",
        "state": state,
        "payload_values_persisted": False,
        "result_binding": result_binding,
        "result_stdout_sha256": result_stdout_sha256,
        "completed_at_utc": utcnow(),
    }
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = receipt_dir / (sha + ".json")
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    return sha


def read_receipt(identifier):
    return BASELINE.read_receipt(identifier)


def device_info(config):
    return {
        **BASELINE.device_info(config),
        "tunnel_mode": TRANSPORT_MODE,
    }


def invoke(config, function_id, arguments):
    if function_id != BASELINE.FUNCTION_ID:
        raise ValueError("UNKNOWN_FUNCTION_ID")
    argv = arguments.get("argv") if isinstance(arguments, dict) else None
    if argv != []:
        raise ValueError("FUNCTION_ARGUMENTS_DENIED")
    result = device_info(config)
    return {
        "function_id": BASELINE.FUNCTION_ID,
        "risk_class": "READ_ONLY",
        "process_exit_code": 0,
        "stdout": json.dumps(result, sort_keys=True, separators=(",", ":")),
        "domain_success_inferred": False,
    }


def _response(result, blocker=None, receipt_sha=None):
    payload = {
        "state": "PASS" if blocker is None else "DENIED",
        "operational_authority": OPERATIONAL_AUTHORITY,
        "runtime_authority_from_chatgpt": False,
        "mutation_performed": False,
        "result": result,
        "blocker": blocker,
    }
    if receipt_sha is not None:
        payload["bridge_receipt_sha256"] = receipt_sha
    return payload


def execute_tool(config, call):
    tool = str(call.get("tool_id") or "")
    payload = call.get("payload") or {}

    if tool == "hara.health":
        result = {
            "commander_edge_state": "PASS",
            "device_channel_state": "PASS",
            "registered_function_count": 1,
            "executable_function_count": 1,
            "authority": OPERATIONAL_AUTHORITY,
            "device": device_info(config),
        }
    elif tool == "hara.functions.list":
        if payload:
            raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
        result = BASELINE.catalog()
    elif tool == "hara.functions.describe":
        result = BASELINE.describe(str(payload.get("function_id") or ""))
    elif tool == "hara.functions.invoke":
        result = invoke(
            config,
            str(payload.get("function_id") or ""),
            payload.get("arguments") or {},
        )
    elif tool == "hara.receipts.get":
        return _response(
            BASELINE.read_receipt(payload.get("receipt_id_or_sha256"))
        )
    else:
        raise ValueError("TOOL_ID_INVALID")

    receipt_sha = write_receipt(config, call, "PASS", result)
    return _response(result, receipt_sha=receipt_sha)


def complete(config, call, state, result, error_code=None):
    body = {
        "call_id": call["call_id"],
        "state": state,
        "result": result,
    }
    if error_code:
        body["error_code"] = error_code
    post_json(
        config["HARA_COMMANDER_URL"] + "/api/device/calls/complete",
        config["HARA_DEVICE_TOKEN"],
        body,
    )


def execute_call(config, call):
    try:
        complete(config, call, "COMPLETED", execute_tool(config, call))
    except Exception as exc:
        code = safe_error_code(exc)
        complete(
            config,
            call,
            "FAILED",
            _response({}, blocker={"code": code}),
            code,
        )


def self_test():
    global BASELINE
    import tempfile

    original_receipt_dir = BASELINE.RECEIPT_DIR
    original_data_dir = BASELINE.DATA_DIR
    try:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            BASELINE.RECEIPT_DIR = temp_path / "receipts"
            BASELINE.DATA_DIR = temp_path / "data"
            cfg = {
                "HARA_DEVICE_ID": "event-v2-selftest",
                "HARA_DEVICE_ARCH": "test",
            }
            base = {
                "call_id": "c",
                "request_id": "event-v2-selftest",
                "payload": {},
            }
            health = execute_tool(cfg, {**base, "tool_id": "hara.health"})
            assert health["operational_authority"] == OPERATIONAL_AUTHORITY
            assert "services_bridge_state" not in health["result"]
            assert health["result"]["device"]["tunnel_mode"] == TRANSPORT_MODE

            invoke_result = execute_tool(
                cfg,
                {
                    **base,
                    "request_id": "event-v2-invoke",
                    "tool_id": "hara.functions.invoke",
                    "payload": {
                        "function_id": BASELINE.FUNCTION_ID,
                        "arguments": {"argv": []},
                    },
                },
            )
            stdout_obj = json.loads(invoke_result["result"]["stdout"])
            assert stdout_obj["tunnel_mode"] == TRANSPORT_MODE
            receipt = BASELINE.read_receipt(
                invoke_result["bridge_receipt_sha256"]
            )
            assert receipt["operational_authority"] == OPERATIONAL_AUTHORITY
            assert receipt["transport_mode"] == TRANSPORT_MODE
            assert receipt["execution_authority"] == EXECUTION_AUTHORITY
            assert receipt["payload_values_persisted"] is False

            connected = write_event_v2_status(
                connected=True,
                connected_at_utc="2026-09-26T00:00:00+00:00",
                disconnected_at_utc=None,
                error_code=None,
            )
            assert connected["connected"] is True
            assert connected["transport_mode"] == "EVENT_V2"
            status_path = _event_status_file()
            assert status_path.is_file()
            assert (status_path.stat().st_mode & 0o777) == 0o600

            disconnected = write_event_v2_status(
                connected=False,
                disconnected_at_utc="2026-09-26T00:01:00+00:00",
                error_code="NETWORK_ERROR",
            )
            assert disconnected["connected"] is False
            assert disconnected["last_error_code"] == "NETWORK_ERROR"

            try:
                execute_tool(
                    cfg,
                    {
                        **base,
                        "tool_id": "hara.functions.invoke",
                        "payload": {
                            "function_id": "shell.run",
                            "arguments": {"argv": []},
                        },
                    },
                )
            except ValueError as exc:
                assert str(exc) == "UNKNOWN_FUNCTION_ID"
            else:
                raise AssertionError("EVENT_V2_ARBITRARY_FUNCTION_NOT_DENIED")
    finally:
        BASELINE.RECEIPT_DIR = original_receipt_dir
        BASELINE.DATA_DIR = original_data_dir

    print("COMMANDER_EVENT_V2_CUSTOMER_AGENT_AUTHORITY=PASS")
    print("COMMANDER_EVENT_V2_CUSTOMER_AUTHORITY=HARA_COMMANDER")
    print("COMMANDER_EVENT_V2_TRANSPORT_MODE=EVENT_V2")
    print("COMMANDER_EVENT_V2_HARA_SERVICES_DATA_PATH=ABSENT")
    print("COMMANDER_EVENT_V2_ARBITRARY_FUNCTION=DENIED")
    print("COMMANDER_EVENT_V2_RUNTIME_STATUS=PASS")
    print("COMMANDER_EVENT_V2_RUNTIME_STATUS_MODE=0600")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        raise SystemExit("SOURCE_ONLY_USE_EVENT_V2_AGENT_LOOP")
