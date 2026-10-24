#!/usr/bin/env python3
"""Offline systemd failover regressions: no machine or network mutations."""
from __future__ import annotations

import importlib.util
from pathlib import Path

GUARD = Path(__file__).with_name("commander_event_v2_persistent_guard.py")
spec = importlib.util.spec_from_file_location("hara_eventv2_guard_test", GUARD)
assert spec is not None and spec.loader is not None
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def healthy():
    return {
        "old_active": False,
        "old_enabled": False,
        "new_active": True,
        "new_enabled": True,
        "pid": 42,
        "age_seconds": 300,
        "valid_status": True,
        "connected": True,
        "connected_this_service": True,
        "socket": True,
    }


def test_2_strikes():
    state = {"checks_failed": 0}
    events = []
    original = g.snapshot, g.secure_read_json, g.write_state, g.fallback
    try:
        g.snapshot = lambda: {**healthy(), "socket": False}
        g.secure_read_json = lambda path: state
        g.write_state = lambda obj: state.update(obj)
        g.fallback = lambda reason, *, commit: events.append((reason, commit))
        assert g.check_once(commit=True) == 0
        assert state["checks_failed"] == 1 and not events
        assert g.check_once(commit=True) == 0
        assert state["checks_failed"] == 2
        assert events == [("EVENT_V2_TCP_CONNECTION_MISSING", True)]
        g.snapshot = healthy
        assert g.check_once(commit=True) == 0
        assert state["checks_failed"] == 0
        print("EVENT_V2_WATCHDOG_CONSECUTIVE_FAILURE_GATE=PASS")
    finally:
        g.snapshot, g.secure_read_json, g.write_state, g.fallback = original


def test_rollback_order():
    events = []
    active = {g.NEW: "active", g.OLD: "inactive"}
    original = g.call, g.unit, g.write_state
    try:
        def fake_call(*argv, **kwargs):
            assert argv[0:2] == ("systemctl", "--user")
            events.append(argv[2:])
            if argv[2] == "stop":
                active[argv[3]] = "inactive"
            elif argv[2] == "start":
                active[argv[3]] = "active"
            return None
        g.call = fake_call
        g.unit = lambda name: {"ActiveState": active[name]}
        g.write_state = lambda obj: events.append(("write", obj["state"]))
        g.fallback("SIMULATED", commit=True)
        assert events[:4] == [
            ("disable", g.NEW),
            ("stop", g.NEW),
            ("enable", g.OLD),
            ("start", g.OLD),
        ], events
        assert events[-1] == ("disable", "--now", g.TIMER)
        assert active[g.NEW] == "inactive" and active[g.OLD] == "active"
        print("EVENT_V2_ROLLBACK_STOPS_NEW_BEFORE_START_OLD=PASS")
        print("EVENT_V2_ROLLBACK_DISARMS_WATCHDOG_TIMER=PASS")

        # Prevent starting the legacy service if new cannot actually stop.
        events.clear()
        active[g.NEW] = "active"
        active[g.OLD] = "inactive"
        def refuse_stop(*argv, **kwargs):
            events.append(argv[2:])
            return None
        g.call = refuse_stop
        try:
            g.fallback("SIMULATED_NOT_STOPPED", commit=True)
        except RuntimeError as exc:
            assert str(exc) == "EVENT_V2_FALLBACK_DUAL_AGENT_DENIED"
        else:
            raise AssertionError("DUAL_AGENT_UNSAFE_FALLBACK_PERMITTED")
        assert ("start", g.OLD) not in events
        print("EVENT_V2_ROLLBACK_OLD_START_ON_FAILED_STOP=DENIED")
    finally:
        g.call, g.unit, g.write_state = original


if __name__ == "__main__":
    unit = (GUARD.parents[1] / "candidate/hara-commander-v2-guard.service").read_text()
    assert "NoNewPrivileges=yes" in unit
    # In a PrivateTmp mount namespace ss -tnp cannot attribute the Agent PID,
    # producing a false TCP_CONNECTION_MISSING and an unsafe timer rollback.
    assert "\nPrivateTmp=yes" not in unit
    print("EVENT_V2_WATCHDOG_PID_VISIBILITY_HARDENING=PASS")
    g.self_test()
    test_2_strikes()
    test_rollback_order()
    print("EVENT_V2_WATCHDOG_SANDBOX=PASS")
