#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps/commander/scripts/commander_first_device_preflight.py"
SOURCE = TARGET.read_text(encoding="utf-8")
ast.parse(SOURCE)

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_FIRST_DEVICE_PREFLIGHT_{code}=FAIL")
    print(f"COMMANDER_FIRST_DEVICE_PREFLIGHT_{code}=PASS")

need('run_installer("status", origin)' in SOURCE, "STATUS_ONLY_READ")
need('run_installer("preflight", origin)' in SOURCE, "PREFLIGHT_ONLY_READ")
need('"mutation_performed") is False' in SOURCE, "MUTATION_FALSE_GUARD")
need('"LOCAL_RESIDUE_PRESENT"' in SOURCE, "RESIDUE_GUARD")
need('"DEVICE_ALREADY_ENROLLED"' in SOURCE, "ENROLLMENT_GUARD")
need('"PERSISTENCE_NOT_READY"' in SOURCE, "PERSISTENCE_GUARD")
need('"PUBLIC_LOCAL_RELEASE_VERSION_DRIFT"' in SOURCE, "RELEASE_VERSION_GUARD")
need('"DEVICE_TOKEN_EXPOSED") == "FALSE"' in SOURCE, "TOKEN_EXPOSURE_GUARD")
need("COMMANDER_FIRST_DEVICE_CANDIDATE=READY" in SOURCE, "READY_MARKER")

for forbidden in (
    'run_installer("install"',
    'run_installer("update"',
    'run_installer("uninstall"',
    'subprocess.run(["rm"',
    'shutil.rmtree',
):
    need(forbidden not in SOURCE, "NO_MUTATION_" + forbidden.replace('"', '').replace("(", "_").replace(")", "_").replace("[", "_").replace("]", "_").replace(".", "_").replace(" ", "_").upper()[:36])

print("COMMANDER_FIRST_DEVICE_PREFLIGHT_CONTRACT=PASS")
