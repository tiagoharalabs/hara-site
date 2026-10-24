#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "apps" / "commander" / "scripts" / "commander_linux_clean_lifecycle.py"

proc = subprocess.run(
    ["python3", str(SCRIPT), "--check"],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=30,
    check=False,
)
if proc.returncode != 0 or "COMMANDER_CLEAN_LINUX_LIFECYCLE_SOURCE=PASS" not in proc.stdout:
    raise SystemExit("COMMANDER_CLEAN_LINUX_LIFECYCLE_CONTRACT=FAIL")
print("COMMANDER_CLEAN_LINUX_LIFECYCLE_CONTRACT=PASS")
