#!/usr/bin/env python3
"""The Agent self-test must own its workspace root under a marked temp parent."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

AGENT = Path(__file__).resolve().parents[1] / "public/agent/linux.py"

with tempfile.TemporaryDirectory(prefix="commander-parent-marker-") as temporary:
    parent = Path(temporary)
    (parent / ".git").mkdir()
    result = subprocess.run(
        [sys.executable, "-B", str(AGENT), "--self-test"],
        env={**os.environ, "TMPDIR": str(parent),
             "XDG_DATA_HOME": str(parent / "isolated-data"),
             "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]

print("COMMANDER_AGENT_SELFTEST_MARKED_TEMP_PARENT=PASS")
