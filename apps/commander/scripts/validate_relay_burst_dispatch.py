#!/usr/bin/env python3
"""Offline relay-loop proof: drain a bounded burst without concurrent execution."""

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


DEFAULT_AGENT = Path(__file__).resolve().parents[1] / "public/agent/linux.py"


class StopSimulation(BaseException):
    pass


def simulate(source, count, pending_after_first=False, reject_after_first=False):
    with tempfile.TemporaryDirectory(prefix="hara-relay-burst-") as temporary:
        root = Path(temporary)
        prior = {key: os.environ.get(key) for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
        try:
            for key, name in (("HOME", "home"), ("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config")):
                path = root / name
                path.mkdir()
                os.environ[key] = str(path)
            spec = importlib.util.spec_from_file_location("hara_relay_burst_agent", source)
            agent = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = agent
            spec.loader.exec_module(agent)
            clock = [100.0]
            sleeps = []
            claims = []
            executed = []
            pending_checks = []
            rejected = [False]
            queue = [{"call_id": f"QA-{index}"} for index in range(count)]
            config = {"HARA_DEVICE_ID": "QA-DEVICE", "HARA_DEVICE_TOKEN": "QA-TOKEN",
                      "HARA_DEVICE_ARCH": "qa", "HARA_COMMANDER_URL": "https://qa.invalid"}

            def fake_sleep(seconds):
                sleeps.append((len(executed), float(seconds)))
                clock[0] += float(seconds)
                if (len(executed) >= count and not queue) or (pending_after_first and executed):
                    raise StopSimulation
                if reject_after_first and rejected[0] and len(sleeps) >= 2:
                    raise StopSimulation
                if len(sleeps) > 30:
                    raise AssertionError("RELAY_LOOP_DID_NOT_QUIESCE")

            def fake_post(url, _token, _payload):
                if url.endswith("/api/device/heartbeat"):
                    return {"ok": True}
                assert url.endswith("/api/device/calls/next"), url
                claims.append(clock[0])
                if reject_after_first and executed and not rejected[0]:
                    rejected[0] = True
                    raise RuntimeError("HTTP_429")
                return queue.pop(0) if queue else None

            agent.sys = SimpleNamespace(argv=["linux.py"])
            agent.time = SimpleNamespace(monotonic=lambda: clock[0], sleep=fake_sleep)
            agent.load_config = lambda: config
            agent.start_local_portal_server = lambda _config: None
            agent.try_write_runtime_status = lambda **_kwargs: True
            agent.transport_mode = lambda _config: "OUTBOUND_RELAY"
            agent.effective_approval_mode = lambda _config=None: "PERSISTENT_TRUSTED"
            agent.operator_session_active = lambda: False
            agent.append_console_event = lambda *_args, **_kwargs: None
            agent.local_activity_heartbeat_snapshot = lambda: {}
            agent.refresh_product_lease = lambda _config: None
            agent.flush_completion_outbox = lambda _config: None
            agent.completion_outbox_health = lambda: (
                pending_checks.append(len(executed)) or
                {"quarantined": 0, "pending": bool(pending_after_first and executed)}
            )
            agent.post_json = fake_post
            agent.execute_call = lambda _config, call: executed.append((call["call_id"], clock[0]))

            try:
                agent.main()
            except StopSimulation:
                pass
            return {"claims": claims, "executed": executed, "sleeps": sleeps,
                    "pending_checks": pending_checks}
        finally:
            for key, value in prior.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def main(source):
    four = simulate(source, 4)
    assert [call_id for call_id, _ in four["executed"]] == [f"QA-{index}" for index in range(4)], four
    assert [at for _, at in four["executed"]] == [100.0] * 4, four
    assert four["sleeps"] == [(4, 2.0)], four
    print("COMMANDER_RELAY_FOUR_CALLS_DRAIN_WITHOUT_INTERCALL_SLEEP=PASS")

    ten = simulate(source, 10)
    assert [call_id for call_id, _ in ten["executed"]] == [f"QA-{index}" for index in range(10)], ten
    assert [at for _, at in ten["executed"]] == [100.0] * 8 + [102.0] * 2, ten
    assert ten["sleeps"] == [(8, 2.0), (10, 2.0)], ten
    print("COMMANDER_RELAY_IMMEDIATE_DRAIN_BOUNDED_AT_EIGHT=PASS")

    pending = simulate(source, 3, pending_after_first=True)
    assert [call_id for call_id, _ in pending["executed"]] == ["QA-0"], pending
    assert len(pending["claims"]) == 1 and pending["pending_checks"][:2] == [0, 1], pending
    print("COMMANDER_RELAY_PENDING_OUTBOX_BLOCKS_NEXT_CLAIM=PASS")

    empty = simulate(source, 0)
    assert len(empty["claims"]) == 1 and empty["sleeps"] == [(0, 2.0)], empty
    print("COMMANDER_RELAY_EMPTY_POLL_STILL_SLEEPS=PASS")

    limited = simulate(source, 3, reject_after_first=True)
    assert [call_id for call_id, _ in limited["executed"]] == ["QA-0"], limited
    assert len(limited["claims"]) == 2 and limited["sleeps"] == [(1, 10.0), (1, 5.0)], limited
    print("COMMANDER_RELAY_RATE_LIMIT_STOPS_IMMEDIATE_DRAIN=PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_AGENT)
    args = parser.parse_args()
    main(args.source.resolve(strict=True))
