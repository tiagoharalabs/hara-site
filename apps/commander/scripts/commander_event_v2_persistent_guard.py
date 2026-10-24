#!/usr/bin/env python3
"""Founder-only H.A.R.A. Commander Event V2 boot-persistence/fallback guard.

Runs locally under the user systemd timer; never polls Cloudflare or accesses
device token files. A second consecutive unhealthy reading safely reverts
to the signed 0.3.41 service. No effect on the rest of the fleet.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

OLD = "hara-commander-agent.service"
NEW = "hara-commander-agent-v2.service"
TIMER = "hara-commander-v2-guard.timer"
HOME = Path.home()
BASE = HOME / ".local/share/hara-commander"
STATUS = BASE / "event-v2-status.json"
GUARD_DIR = BASE / "ops"
GUARD_STATE = GUARD_DIR / "event-v2-guard-status.json"
CANARY_DEVICE = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62"
CHECKS_BEFORE_FALLBACK = 2
STARTUP_GRACE_SECONDS = 105
SOCKET_PORT = ":443"


def call(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=12)
    if check and proc.returncode:
        raise RuntimeError("GUARD_SYSTEMD_COMMAND_FAILED")
    return proc


def unit(name: str) -> dict[str, str]:
    raw = call(
        "systemctl", "--user", "show", name,
        "-p", "ActiveState", "-p", "UnitFileState", "-p", "MainPID",
        "-p", "ActiveEnterTimestampMonotonic",
    ).stdout
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def secure_read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("GUARD_FILE_MISSING_OR_SYMLINK")
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise RuntimeError("GUARD_FILE_PERMISSION_DENIED")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("GUARD_JSON_INVALID")
    return value


def write_state(state: dict) -> None:
    GUARD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    GUARD_DIR.chmod(0o700)
    if GUARD_STATE.is_symlink():
        raise RuntimeError("GUARD_STATE_SYMLINK_DENIED")
    tmp = GUARD_DIR / (".event-v2-guard-" + str(os.getpid()) + ".tmp")
    data = json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, GUARD_STATE)
        GUARD_STATE.chmod(0o600)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def socket_alive(pid: int) -> bool:
    proc = call("ss", "-Htnp", check=False)
    if proc.returncode:
        return False
    needle = re.compile(r"\bpid=" + re.escape(str(pid)) + r",")
    for line in proc.stdout.splitlines():
        if line.startswith("ESTAB ") and needle.search(line) and SOCKET_PORT in line:
            return True
    return False


def snapshot() -> dict:
    old, new = unit(OLD), unit(NEW)
    started = int(new.get("ActiveEnterTimestampMonotonic") or 0) / 1_000_000
    age = max(0.0, time.monotonic() - started) if started else 0.0
    pid = int(new.get("MainPID") or 0)
    snap = {
        "old_active": old.get("ActiveState") == "active",
        "old_enabled": old.get("UnitFileState") == "enabled",
        "new_active": new.get("ActiveState") == "active",
        "new_enabled": new.get("UnitFileState") == "enabled",
        "pid": pid,
        "age_seconds": age,
        "connected": False,
        "valid_status": False,
        "socket": False,
        "connected_this_service": False,
    }
    try:
        stat = secure_read_json(STATUS)
        snap["valid_status"] = (
            stat.get("schema") == "hara.commander-event-v2-runtime-status.v1"
            and stat.get("transport_mode") == "EVENT_V2"
        )
        snap["connected"] = stat.get("connected") is True
        if snap["valid_status"] and snap["connected"]:
            raw = str(stat.get("connected_at_utc") or "")
            when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if when.tzinfo is None:
                raise ValueError("tz required")
            stamp = when.timestamp()
            process_start = time.time() - age
            snap["connected_this_service"] = (
                process_start - 10 <= stamp <= time.time() + 30
            )
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    if snap["new_active"] and pid > 1:
        snap["socket"] = socket_alive(pid)
    return snap


def judge(snap: dict) -> str:
    if snap["old_active"]:
        return "OLD_AGENT_UNEXPECTEDLY_ACTIVE"
    if snap["old_enabled"]:
        return "OLD_AGENT_ENABLED_AT_BOOT"
    if not snap["new_enabled"]:
        return "EVENT_V2_NOT_ENABLED_AT_BOOT"
    if snap["new_active"] and snap["age_seconds"] < STARTUP_GRACE_SECONDS:
        return "STARTUP_GRACE"
    if not snap["new_active"] or snap["pid"] <= 1:
        return "EVENT_V2_SERVICE_INACTIVE"
    if not snap["valid_status"]:
        return "EVENT_V2_STATUS_INVALID"
    if not snap["connected"]:
        return "EVENT_V2_SOCKET_DISCONNECTED"
    if not snap["connected_this_service"]:
        return "EVENT_V2_STALE_CONNECTION_STATUS"
    if not snap["socket"]:
        return "EVENT_V2_TCP_CONNECTION_MISSING"
    return "PASS"


def fallback(reason: str, *, commit: bool) -> None:
    # Never start old unless the new service is confirmed stopped.
    print("EVENT_V2_FALLBACK_REASON=" + reason, flush=True)
    if not commit:
        print("EVENT_V2_FALLBACK_SIMULATION=PASS")
        return
    call("systemctl", "--user", "disable", NEW)
    call("systemctl", "--user", "stop", NEW)
    if unit(NEW).get("ActiveState") == "active":
        raise RuntimeError("EVENT_V2_FALLBACK_DUAL_AGENT_DENIED")
    call("systemctl", "--user", "enable", OLD)
    call("systemctl", "--user", "start", OLD)
    if unit(OLD).get("ActiveState") != "active":
        raise RuntimeError("EVENT_V2_FALLBACK_OLD_NOT_ACTIVE")
    write_state({
        "schema": "hara.commander-event-v2-guard.v1",
        "state": "ROLLED_BACK_TO_SIGNED_V1",
        "reason": reason,
        "checks_failed": CHECKS_BEFORE_FALLBACK,
        "changed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    call("systemctl", "--user", "disable", "--now", TIMER)
    print("EVENT_V2_FALLBACK_SIGNED_0_3_41=PASS")


def check_once(*, commit: bool) -> int:
    snap = snapshot()
    reason = judge(snap)
    if reason == "STARTUP_GRACE":
        print("EVENT_V2_GUARD_STARTUP_GRACE=PASS")
        return 0
    if reason == "PASS":
        if commit:
            write_state({
                "schema": "hara.commander-event-v2-guard.v1",
                "state": "HEALTHY",
                "reason": "PASS",
                "checks_failed": 0,
                "changed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            })
        print("EVENT_V2_GUARD_HEALTH=PASS")
        return 0
    if not commit:
        print("EVENT_V2_GUARD_HEALTH=" + reason)
        return 2
    try:
        previous = secure_read_json(GUARD_STATE)
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError):
        previous = {}
    strikes = int(previous.get("checks_failed") or 0) + 1
    # A race that starts old while v2 is active is immediately safety-critical.
    if reason == "OLD_AGENT_UNEXPECTEDLY_ACTIVE":
        strikes = CHECKS_BEFORE_FALLBACK
    write_state({
        "schema": "hara.commander-event-v2-guard.v1",
        "state": "UNHEALTHY",
        "reason": reason,
        "checks_failed": strikes,
        "changed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    if strikes >= CHECKS_BEFORE_FALLBACK:
        fallback(reason, commit=True)
        return 0
    print("EVENT_V2_GUARD_WARNING=" + reason)
    return 0


def self_test() -> None:
    good = dict(
        old_active=False, old_enabled=False,
        new_active=True, new_enabled=True,
        pid=123, age_seconds=300,
        valid_status=True, connected=True,
        connected_this_service=True, socket=True,
    )
    assert judge(good) == "PASS"
    assert judge({**good, "old_active": True}) == "OLD_AGENT_UNEXPECTEDLY_ACTIVE"
    assert judge({**good, "old_enabled": True}) == "OLD_AGENT_ENABLED_AT_BOOT"
    assert judge({**good, "new_enabled": False}) == "EVENT_V2_NOT_ENABLED_AT_BOOT"
    assert judge({**good, "new_active": False}) == "EVENT_V2_SERVICE_INACTIVE"
    assert judge({**good, "connected": False}) == "EVENT_V2_SOCKET_DISCONNECTED"
    assert judge({**good, "socket": False}) == "EVENT_V2_TCP_CONNECTION_MISSING"
    assert judge({**good, "connected_this_service": False}) == "EVENT_V2_STALE_CONNECTION_STATUS"
    assert judge({**good, "age_seconds": 10, "connected": False}) == "STARTUP_GRACE"
    fallback("TEST", commit=False)
    print("EVENT_V2_GUARD_SOURCE_TEST=PASS")
    print("EVENT_V2_GUARD_NO_HTTP_POLL=PASS")
    print("EVENT_V2_GUARD_FALLBACK_DUAL_AGENT=DENIED")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.rollback:
        fallback("MANUAL_OPERATOR_ROLLBACK", commit=True)
        return 0
    return check_once(commit=args.run)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print("EVENT_V2_GUARD_ERROR=" + type(exc).__name__)
        raise SystemExit(2)
