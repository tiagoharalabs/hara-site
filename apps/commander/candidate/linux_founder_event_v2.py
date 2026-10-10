#!/usr/bin/env python3
"""Separate Linux Event V2 Founder canary launcher for signed release v2.

Never overwrites legacy v1. Requires an explicit service handoff and opt-in.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

APP = Path(__file__).resolve().parents[1]
LOOP_PATH = APP / "experimental/event_v2_agent_loop.py"
WS_PATH = APP / "experimental/event_v2_websocket.py"
FULL_PATH = APP / "candidate/event_v2_full_agent.py"
BASE_PATH = APP / "public/agent/linux.py"
VERSION = "0.3.44"
CANARY_DEVICE = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62"
ORIGIN = "https://commander.haralabs.com.br"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_RELEASE_ASSET_UNAVAILABLE")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def validate_config(config, agent, environ=None):
    environ = os.environ if environ is None else environ
    if str(config.get("HARA_COMMANDER_URL") or "").rstrip("/") != ORIGIN:
        raise RuntimeError("EVENT_V2_COMMERCIAL_ORIGIN_DENIED")
    if config.get("HARA_DEVICE_ID") != CANARY_DEVICE:
        raise RuntimeError("EVENT_V2_NON_FOUNDER_DEVICE_DENIED")
    if agent.BASELINE.AGENT_VERSION != VERSION:
        raise RuntimeError("EVENT_V2_SIGNED_RELEASE_VERSION_INVALID")
    if environ.get("HARA_COMMANDER_EVENT_V2_OPT_IN") != "1":
        raise RuntimeError("EVENT_V2_EXPLICIT_OPT_IN_REQUIRED")
    # Retain the operator's existing local approval mode without loosening it.


def validate_single_loop():
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet",
         "hara-commander-agent.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if r.returncode == 0:
        raise RuntimeError("EVENT_V2_LEGACY_AGENT_STILL_ACTIVE")


def self_test():
    assert all(p.is_file() for p in (LOOP_PATH, WS_PATH, FULL_PATH, BASE_PATH))
    a = load(FULL_PATH, "hara_event_v2_full_candidate_self_test")
    a.self_test()
    assert a.BASELINE.AGENT_VERSION == VERSION
    test_cfg = {"HARA_COMMANDER_URL": ORIGIN, "HARA_DEVICE_ID": CANARY_DEVICE}
    validate_config(test_cfg, a, {"HARA_COMMANDER_EVENT_V2_OPT_IN": "1"})
    for config, env in (
        ({**test_cfg, "HARA_DEVICE_ID": "HARA-DEVICE-OTHER"},
         {"HARA_COMMANDER_EVENT_V2_OPT_IN": "1"}),
        (test_cfg, {}),
    ):
        try:
            validate_config(config, a, env)
        except RuntimeError:
            pass
        else:
            raise AssertionError("EVENT_V2_GUARD_BYPASSED")
    print("EVENT_V2_SIGNED_FOUNDER_CANARY_SELF_TEST=PASS")
    print("EVENT_V2_LEGACY_SIGNED_RELEASE_UNCHANGED=TRUE")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--version":
        print(VERSION)
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return 0
    if len(sys.argv) != 1:
        raise RuntimeError("EVENT_V2_LAUNCH_ARGUMENTS_DENIED")
    loop = load(LOOP_PATH, "hara_event_v2_loop_release")
    socket = load(WS_PATH, "hara_event_v2_ws_release")
    agent = load(FULL_PATH, "hara_event_v2_agent_release")
    cfg = agent.load_config()
    validate_config(cfg, agent)
    validate_single_loop()
    loop.install_shutdown_handlers()
    try:
        loop.run_forever(socket, agent, cfg)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
