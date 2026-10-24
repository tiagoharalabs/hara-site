#!/usr/bin/env python3
"""Offline test of reversible file custody, bounded preimage disk usage.

Uses a temporary directory; never reads or edits the real user's preimage store.
"""
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "apps/commander/public/agent/linux.py"
ns = {"__name__": "hara_preimage_storage_budget_test", "__file__": str(AGENT)}
exec(compile(AGENT.read_text(encoding="utf-8"), str(AGENT), "exec"), ns)


def denied(method, code):
    try:
        method()
    except ValueError as exc:
        assert str(exc) == code, (code, exc)
        return
    raise AssertionError("PREIMAGE_EXPECTED_DENIAL_MISSING:" + code)


with tempfile.TemporaryDirectory(prefix="hara-commander-preimage-budget-") as folder:
    root = Path(folder)
    ns["PREIMAGE_DIR"] = root / "preimages"
    ns["MAX_PREIMAGE_ENTRIES"] = 2
    ns["MAX_PREIMAGE_STORE_BYTES"] = 12
    file = root / "file.txt"
    file.write_text("12345")
    store = ns["_store_preimage"]
    first = store(file, "PREIMAGE-TEST-1", "hara.files.write")
    second = store(file, "PREIMAGE-TEST-2", "hara.files.write")
    assert first["preimage_id"] != second["preimage_id"]
    assert ns["_load_preimage"](first["preimage_id"])[1] == b"12345"
    denied(lambda: store(file,"PREIMAGE-TEST-3"), "PREIMAGE_CAPACITY_EXCEEDED")
    assert file.read_text() == "12345"
    print("PREIMAGE_STORAGE_ENTRY_CAP=PASS")

    ns["MAX_PREIMAGE_ENTRIES"] = 10
    denied(lambda: store(file,"PREIMAGE-TEST-4"), "PREIMAGE_CAPACITY_EXCEEDED")
    assert file.read_text() == "12345"
    print("PREIMAGE_STORAGE_BYTE_CAP=PASS")

    ns["MAX_PREIMAGE_STORE_BYTES"] = 20
    third = store(file, "PREIMAGE-TEST-5")
    assert third and ns["_load_preimage"](third["preimage_id"])[1] == b"12345"
    assert len(list(ns["PREIMAGE_DIR"].glob("*.bin"))) == 3
    print("PREIMAGE_STORAGE_EXISTING_HISTORY_PRESERVED=PASS")

    target = ns["PREIMAGE_DIR"] / ("HARA-PREIMAGE-"+"a"*32+".bin")
    target.symlink_to(file)
    denied(lambda: store(file,"PREIMAGE-TEST-6"), "PREIMAGE_STORAGE_UNSAFE")
    assert file.read_text() == "12345"
    print("PREIMAGE_STORAGE_SYMLINK=DENIED")

assert ns["MAX_PROCESS_BUFFER_CHARS"] <= 4 * 1024 * 1024
print("PREIMAGE_STORAGE_TEST_REAL_CUSTOMER_FILES_TOUCHED=FALSE")
