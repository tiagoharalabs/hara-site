#!/usr/bin/env python3
"""Isolated H.A.R.A. Event V2 full-tool customer Agent release candidate.

DEV only until a trusted public release is signed. This file does not change,
wrap or install over the signed Agent 0.3.41 service.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOOP_PATH = ROOT / "experimental/event_v2_agent_loop.py"
TRANSPORT_PATH = ROOT / "experimental/event_v2_websocket.py"
FULL_AGENT_PATH = ROOT / "candidate/event_v2_full_agent.py"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DEVICE_ENV = "HARA_EVENT_V2_RC_DEVICE_ID"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_FULL_RC_IMPORT_INVALID")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require_dev(config, env=None):
    env = os.environ if env is None else env
    allowlist = str(env.get(DEVICE_ENV) or "").strip()
    if not allowlist or allowlist != config.get("HARA_DEVICE_ID"):
        raise RuntimeError("EVENT_V2_FULL_RC_DEVICE_NOT_ALLOWLISTED")
    if str(config.get("HARA_COMMANDER_URL") or "").rstrip("/") != DEV_ORIGIN:
        raise RuntimeError("EVENT_V2_FULL_RC_PROD_UNTRUSTED_DENIED")
    if str(env.get("HARA_DEVICE_TRANSPORT_MODE") or "") != "EVENT_V2":
        raise RuntimeError("EVENT_V2_FULL_RC_EXPLICIT_OPT_IN_REQUIRED")
    if str(config.get("HARA_COMMANDER_APPROVAL_MODE") or "") != "PERSISTENT_TRUSTED":
        raise RuntimeError("EVENT_V2_FULL_RC_DEV_LOCAL_APPROVAL_MODE_REQUIRED")


def self_test():
    fake = {
        "HARA_DEVICE_ID": "HARA-DEVICE-DEV-TEST",
        "HARA_COMMANDER_URL": DEV_ORIGIN,
        "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED",
    }
    enabled = {DEVICE_ENV: "HARA-DEVICE-DEV-TEST",
               "HARA_DEVICE_TRANSPORT_MODE": "EVENT_V2"}
    require_dev(fake, enabled)
    for key, bad in (
        (DEVICE_ENV, "HARA-DEVICE-OTHER"),
        ("HARA_DEVICE_TRANSPORT_MODE", "OUTBOUND_RELAY"),
    ):
        b = dict(enabled, **{key: bad})
        try:
            require_dev(fake, b)
        except RuntimeError:
            pass
        else:
            raise AssertionError("EVENT_V2_FULL_RC_GATE_NOT_DENIED")
    try:
        require_dev({**fake, "HARA_COMMANDER_URL": "https://commander.haralabs.com.br"},
                    enabled)
    except RuntimeError as error:
        assert str(error) == "EVENT_V2_FULL_RC_PROD_UNTRUSTED_DENIED"
    else:
        raise AssertionError("EVENT_V2_FULL_RC_PROD_ALLOWED")
    assert LOOP_PATH.is_file() and TRANSPORT_PATH.is_file() and FULL_AGENT_PATH.is_file()
    print("COMMANDER_EVENT_V2_FULL_RC_DEV_EXPLICIT_OPT_IN=PASS")
    print("COMMANDER_EVENT_V2_FULL_RC_PROD_UNSIGNED=DENIED")
    print("COMMANDER_EVENT_V2_FULL_RC_UNAUTHORIZED_DEVICE=DENIED")


def main():
    if "--self-test" in sys.argv:
        self_test()
        return 0
    loop = load(LOOP_PATH, "hara_event_v2_full_rc_loop")
    transport = load(TRANSPORT_PATH, "hara_event_v2_full_rc_socket")
    agent = load(FULL_AGENT_PATH, "hara_event_v2_full_rc_agent")
    config = agent.load_config()
    require_dev(config)
    loop.install_shutdown_handlers()
    try:
        loop.run_forever(transport, agent, config)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
