#!/usr/bin/env python3
"""Fail-closed validation for Commander Agent Event V2 productization."""

from pathlib import Path
import json
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[3]
RC = ROOT / "apps/commander/candidate/linux_agent_rc.py"
PUBLIC_AGENT = ROOT / "apps/commander/public/agent/linux.py"
MANIFEST = ROOT / "apps/commander/public/release/agent-manifest.json"
DOC = ROOT / "docs/architecture/HARA_COMMANDER_EVENT_V2_PRODUCTIZATION.md"


def load_rc():
    spec = importlib.util.spec_from_file_location("hara_commander_rc_validation", RC)
    if spec is None or spec.loader is None:
        raise AssertionError("RC_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    rc = load_rc()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")
    public = PUBLIC_AGENT.read_text(encoding="utf-8")

    assert rc.selected_transport({}) == "POLL_V1"
    assert rc.selected_transport({"HARA_DEVICE_TRANSPORT_MODE": "EVENT_V2"}) == "EVENT_V2"
    try:
        rc.selected_transport({"HARA_DEVICE_TRANSPORT_MODE": "AUTO"})
    except RuntimeError as exc:
        assert str(exc) == "COMMANDER_RC_TRANSPORT_INVALID"
    else:
        raise AssertionError("UNKNOWN_TRANSPORT_ALLOWED")

    assert manifest["agent_version"] == "0.3.7"
    assert all("candidate/" not in str(item.get("path") or "") for item in manifest.get("files", []))
    assert 'AGENT_VERSION = "0.3.7"' in public
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public

    for marker in (
        "RC_DEFAULT_TRANSPORT=POLL_V1",
        "EVENT_V2=EXPLICIT_OPT_IN_ONLY",
        "PROD_CUTOVER=DENY",
        "CUSTOMER_SERVICES_PROXY=FALSE",
        "CUSTOMER_CONTENT_COLLECTION=FALSE",
        "ARBITRARY_SHELL=DENY",
    ):
        assert marker in doc

    print("COMMANDER_EVENT_V2_PRODUCTIZATION=PASS")
    print("COMMANDER_AGENT_RC_DEFAULT_TRANSPORT=POLL_V1")
    print("COMMANDER_AGENT_RC_EVENT_V2=OPT_IN_ONLY")
    print("COMMANDER_STABLE_AGENT_VERSION=0.3.7")
    print("COMMANDER_STABLE_RELEASE_MANIFEST_EVENT_V2=ABSENT")
    print("COMMANDER_PROD_CUTOVER=DENY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
