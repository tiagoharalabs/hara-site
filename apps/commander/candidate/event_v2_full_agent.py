#!/usr/bin/env python3
"""Full-tool Event V2 durable execution adapter for the Founder-only candidate.

This is SOURCE-ONLY. It is not part of the published signed Agent bundle.
All durable tool invocations use the existing Commander Agent's exact
authorization, local operator approval, budget and execution controls.
Only the Event V2 transport/receipt provenance is adapted.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading


COMMANDER = Path(__file__).resolve().parents[1]
RESTRICTED_PATH = COMMANDER / "experimental/event_v2_customer_agent.py"


def _load_restricted():
    spec = importlib.util.spec_from_file_location(
        "hara_event_v2_full_embedded_restricted", RESTRICTED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_FULL_ADAPTER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RESTRICTED = _load_restricted()
BASELINE = RESTRICTED.BASELINE
OPERATIONAL_AUTHORITY = "HARA_COMMANDER"
TRANSPORT_MODE = "EVENT_V2"
_EXECUTION_LOCK = threading.RLock()
_ORIGINAL_EXECUTE_TOOL = BASELINE.execute_tool
_ORIGINAL_EXECUTE_CALL = BASELINE.execute_call
_ORIGINAL_DEVICE_INFO = BASELINE.device_info
_ORIGINAL_WRITE_RECEIPT = BASELINE.write_receipt


def utcnow():
    return RESTRICTED.utcnow()


def safe_error_code(error):
    return BASELINE.safe_error_code(error)


def load_config():
    return BASELINE.load_config()


def post_json(url, token, payload):
    return BASELINE.post_json(url, token, payload)


def try_write_runtime_status(**kwargs):
    return BASELINE.try_write_runtime_status(**kwargs)


def try_write_event_v2_status(**kwargs):
    return RESTRICTED.try_write_event_v2_status(**kwargs)


def write_event_v2_status(**kwargs):
    return RESTRICTED.write_event_v2_status(**kwargs)


def _event_device_info(config):
    return {
        **_ORIGINAL_DEVICE_INFO(config),
        "tunnel_mode": TRANSPORT_MODE,
    }


def _write_event_receipt(config, call, state, result):
    """Same receipt schema as the full Agent; immutable EVENT_V2 provenance."""
    receipt_dir = BASELINE.RECEIPT_DIR
    receipt_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool_id = str(call.get("tool_id") or "")
    stdout_binding = (
        tool_id == "hara.functions.invoke"
        or tool_id in BASELINE.DIRECT_TOOL_FUNCTIONS
        or BASELINE._is_mutation_tool(tool_id)
        or BASELINE._is_process_tool(tool_id)
    )
    stdout = str((result or {}).get("stdout") or "") if isinstance(result, dict) else ""
    approval = call.get("_local_approval") or {}
    mutation = BASELINE._is_mutation_tool(tool_id)
    function_id = (
        (call.get("payload") or {}).get("function_id")
        or BASELINE.DIRECT_TOOL_FUNCTIONS.get(tool_id)
        or (result.get("function_id") if isinstance(result, dict) else None)
    )
    receipt = {
        "schema": "hara.commander-device-receipt.v1",
        "request_id": str(call.get("request_id") or ""),
        "device_id": config["HARA_DEVICE_ID"],
        "tool_id": tool_id,
        "function_id_if_any": function_id,
        "transport_mode": TRANSPORT_MODE,
        "operational_authority": OPERATIONAL_AUTHORITY,
        "execution_authority": "HARA_COMMANDER_AGENT",
        "mutation_class": BASELINE._mutation_class(tool_id),
        "human_approval_required": bool(
            mutation and approval.get("mode") == "ASK_EVERY_ACTION"
        ),
        "human_approval_state": approval.get("state") if mutation else None,
        "local_authorization_mode": approval.get("mode"),
        "authorization_source": approval.get("source") if mutation else None,
        "preimage_sha256": (result or {}).get("preimage_sha256"),
        "preimage_id": (result or {}).get("preimage_id"),
        "rollback_preimage_id": (result or {}).get("rollback_preimage_id"),
        "state": state,
        "payload_values_persisted": False,
        "result_binding": "STDOUT_SHA256_V1" if stdout_binding else "NONE",
        "result_stdout_sha256": (
            hashlib.sha256(stdout.encode("utf-8")).hexdigest()
            if stdout_binding else None
        ),
        "completed_at_utc": utcnow(),
    }
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = receipt_dir / (digest + ".json")
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError("EVENT_V2_RECEIPT_HASH_COLLISION")
        return digest
    tmp = receipt_dir / (digest + "." + str(os.getpid()) + ".tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return digest


def _event_execute_tool(config, call):
    prepared = {**call, "_transport": TRANSPORT_MODE}
    payload = _ORIGINAL_EXECUTE_TOOL(config, prepared)
    if not isinstance(payload, dict):
        raise RuntimeError("EVENT_V2_AGENT_RESULT_INVALID")
    output = {**payload, "operational_authority": OPERATIONAL_AUTHORITY}
    if str(call.get("tool_id") or "") == "hara.health":
        inner = dict(output.get("result") or {})
        inner.pop("hara_services_state", None)
        inner.pop("services_bridge_state", None)
        inner.update({
            "authority": OPERATIONAL_AUTHORITY,
            "commander_edge_state": "PASS",
            "device_channel_state": "PASS",
        })
        output["result"] = inner
    return output


@contextmanager
def _event_baseline_overlay():
    # Dedicated Event V2 process executes one durable call at a time.
    # A lock guards module-global overlays for unit tests/reentrant callers.
    with _EXECUTION_LOCK:
        original = (
            BASELINE.execute_tool, BASELINE.write_receipt,
            BASELINE.device_info,
        )
        BASELINE.execute_tool = _event_execute_tool
        BASELINE.write_receipt = _write_event_receipt
        BASELINE.device_info = _event_device_info
        try:
            yield
        finally:
            (BASELINE.execute_tool,
             BASELINE.write_receipt,
             BASELINE.device_info) = original


def execute_tool(config, call):
    with _event_baseline_overlay():
        return _event_execute_tool(config, call)


def execute_call(config, call):
    # Preserve the mature Agent's operator-session check, local human approval,
    # bounded command execution, local budget and success/failure transitions.
    with _event_baseline_overlay():
        return _ORIGINAL_EXECUTE_CALL(config, call)


def execute_transient_call(config, event, *, monotonic=None):
    # PROD transient RPC is disabled. The experimental path stays restricted
    # until its idempotency and quota parity is requalified for the full set.
    if monotonic is None:
        return RESTRICTED.execute_transient_call(config, event)
    return RESTRICTED.execute_transient_call(config, event, monotonic=monotonic)


def supported_durable_tools():
    return frozenset({
        "hara.health",
        "hara.functions.list",
        "hara.functions.describe",
        "hara.functions.invoke",
        "hara.receipts.get",
        "hara.files.preimages.list",
    } | set(BASELINE.DIRECT_TOOL_FUNCTIONS)
      | set(BASELINE.FILESYSTEM_MUTATION_TOOLS)
      | set(BASELINE.PROCESS_TOOLS))


def self_test():
    import tempfile
    original = (BASELINE.RECEIPT_DIR, BASELINE.DATA_DIR)
    try:
        with tempfile.TemporaryDirectory(prefix="hara-event-v2-full-") as temp:
            BASELINE.RECEIPT_DIR = Path(temp) / "receipts"
            BASELINE.DATA_DIR = Path(temp) / "data"
            cfg = {"HARA_DEVICE_ID": "HARA-DEVICE-SELFTEST",
                   "HARA_DEVICE_ARCH": "x86_64"}
            calls = (
                ("hara.health", {}),
                ("hara.ping", {}),
                ("hara.device.info", {}),
                ("hara.system.uptime", {}),
                ("hara.functions.list", {}),
                ("hara.files.info", {"path": temp}),
            )
            for tool_id, arguments in calls:
                result = execute_tool(cfg, {
                    "request_id": "SELFTEST-" + tool_id,
                    "tool_id": tool_id, "payload": arguments,
                })
                assert result["state"] == "PASS", tool_id
                assert result["operational_authority"] == OPERATIONAL_AUTHORITY
                digest = result["bridge_receipt_sha256"]
                p = BASELINE.RECEIPT_DIR / (digest + ".json")
                assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
                info = json.loads(p.read_text())
                assert info["transport_mode"] == "EVENT_V2"
                assert info["operational_authority"] == OPERATIONAL_AUTHORITY
                assert not info["payload_values_persisted"]
            health = execute_tool(cfg, {
                "request_id": "SELFTEST-HEALTH",
                "tool_id": "hara.health", "payload": {},
            })
            assert health["result"]["device"]["tunnel_mode"] == "EVENT_V2"
            assert "hara_services_state" not in health["result"]
            assert len(supported_durable_tools()) >= 29
            try:
                execute_tool(cfg, {
                    "request_id": "SELFTEST-DENY",
                    "tool_id": "hara.nonexistent", "payload": {},
                })
            except ValueError as exc:
                assert str(exc) == "TOOL_ID_INVALID"
            else:
                raise AssertionError("EVENT_V2_UNKNOWN_TOOL_NOT_DENIED")
            assert BASELINE.execute_tool is _ORIGINAL_EXECUTE_TOOL
            assert BASELINE.write_receipt is _ORIGINAL_WRITE_RECEIPT
            assert BASELINE.device_info is _ORIGINAL_DEVICE_INFO
    finally:
        BASELINE.RECEIPT_DIR, BASELINE.DATA_DIR = original
    print("COMMANDER_EVENT_V2_FULL_TOOLS="+str(len(supported_durable_tools())))
    print("COMMANDER_EVENT_V2_FULL_AGENT_EXECUTION=PASS")
    print("COMMANDER_EVENT_V2_FULL_RECEIPT_SHA256=PASS")
    print("COMMANDER_EVENT_V2_FULL_PROVENANCE=HARA_COMMANDER")
    print("COMMANDER_EVENT_V2_FULL_AGENT_SIGNED_PUBLIC_RELEASE=FALSE")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        self_test()
    else:
        raise SystemExit("SOURCE_ONLY_USE_EVENT_V2_AGENT_LOOP")
