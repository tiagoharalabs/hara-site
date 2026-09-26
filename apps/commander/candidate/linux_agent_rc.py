#!/usr/bin/env python3
"""H.A.R.A. Commander Linux Agent release-candidate launcher.

Source-only candidate. The stable public Agent remains 0.3.7 / POLL_V1.

Transport selection:
- missing/empty HARA_DEVICE_TRANSPORT_MODE -> POLL_V1
- POLL_V1 -> proven stable 0.3.7 loop
- EVENT_V2 -> Commander Event V2 customer loop

This file is intentionally outside apps/commander/public and outside the stable
release manifest until #163 productization gates are terminal.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDER = HERE.parent
BASELINE_PATH = COMMANDER / "public" / "agent" / "linux.py"
EVENT_LOOP_PATH = COMMANDER / "experimental" / "event_v2_agent_loop.py"

TRANSPORT_ENV = "HARA_DEVICE_TRANSPORT_MODE"
POLL_V1 = "POLL_V1"
EVENT_V2 = "EVENT_V2"
ALLOWED = {POLL_V1, EVENT_V2}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("COMMANDER_RC_MODULE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def selected_transport(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    raw = str(env.get(TRANSPORT_ENV) or "").strip().upper()
    mode = raw or POLL_V1
    if mode not in ALLOWED:
        raise RuntimeError("COMMANDER_RC_TRANSPORT_INVALID")
    return mode


def run(mode: str | None = None) -> None:
    selected = mode or selected_transport()
    if selected == POLL_V1:
        baseline = load_module(BASELINE_PATH, "hara_commander_rc_baseline")
        baseline.main()
        return
    if selected == EVENT_V2:
        event_loop = load_module(EVENT_LOOP_PATH, "hara_commander_rc_event_v2")
        raise SystemExit(event_loop.main())
    raise RuntimeError("COMMANDER_RC_TRANSPORT_INVALID")


def self_test() -> None:
    assert selected_transport({}) == POLL_V1
    assert selected_transport({TRANSPORT_ENV: ""}) == POLL_V1
    assert selected_transport({TRANSPORT_ENV: "poll_v1"}) == POLL_V1
    assert selected_transport({TRANSPORT_ENV: "event_v2"}) == EVENT_V2

    try:
        selected_transport({TRANSPORT_ENV: "AUTO"})
    except RuntimeError as exc:
        assert str(exc) == "COMMANDER_RC_TRANSPORT_INVALID"
    else:
        raise AssertionError("COMMANDER_RC_UNKNOWN_TRANSPORT_NOT_DENIED")

    assert BASELINE_PATH.is_file()
    assert EVENT_LOOP_PATH.is_file()

    print("COMMANDER_AGENT_RC_SOURCE=PASS")
    print("COMMANDER_AGENT_RC_DEFAULT_TRANSPORT=POLL_V1")
    print("COMMANDER_AGENT_RC_EVENT_V2=OPT_IN_ONLY")
    print("COMMANDER_AGENT_RC_UNKNOWN_TRANSPORT=DENIED")
    print("COMMANDER_AGENT_RC_PUBLIC_RELEASE_MUTATION=FALSE")


def main() -> int:
    if "--self-test" in sys.argv:
        self_test()
        return 0
    if "--transport" in sys.argv:
        index = sys.argv.index("--transport")
        try:
            explicit = str(sys.argv[index + 1]).strip().upper()
        except IndexError as exc:
            raise RuntimeError("COMMANDER_RC_TRANSPORT_ARGUMENT_MISSING") from exc
        if explicit not in ALLOWED:
            raise RuntimeError("COMMANDER_RC_TRANSPORT_INVALID")
        run(explicit)
        return 0
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
