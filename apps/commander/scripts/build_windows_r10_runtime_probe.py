#!/usr/bin/env python3
"""Build a no-install PowerShell fixture from exact Windows candidate functions.

The generated script runs only in the existing Windows QA directory. It never
loads an installed Agent, device token, release key or scheduled task.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1]
SOURCE = APP / "candidate/windows_agent_055.ps1"
FIXTURE = APP / "scripts/test_windows_r10_candidate_fixture.ps1"
NAMES = (
    "Get-SafeErrorCode", "Get-Utf8Sha256", "Get-WindowsDirectory",
    "Read-WindowsManyTextFiles", "Search-WindowsFiles", "Edit-WindowsTextFile",
    "Initialize-WindowsManagedProcessType", "Cleanup-WindowsCompletedRuns",
    "Get-WindowsManagedSession", "Read-WindowsManagedSession",
    "Invoke-WindowsOneShotProcess", "Get-WindowsRelayPollSleep",
)


def extract(source: str, name: str) -> str:
    match = re.search(r"(?ms)^function " + re.escape(name) + r"\b.*?(?=^function |^if \(\$args|\Z)", source)
    if not match:
        raise ValueError("WINDOWS_R10_FUNCTION_MISSING:" + name)
    return match.group(0).rstrip() + "\n\n"


def build() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    if '$AgentVersion = "0.3.55"' not in source:
        raise ValueError("WINDOWS_R10_CANDIDATE_VERSION_INVALID")
    functions = "".join(extract(source, name) for name in NAMES)
    digest = hashlib.sha256(functions.encode()).hexdigest()
    return (
        "$ErrorActionPreference='Stop'\n"
        f"$CandidateFunctionsSha256='{digest}'\n"
        + functions
        + FIXTURE.read_text(encoding="utf-8")
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = build()
    args.output.write_text(output, encoding="utf-8")
    print(f"WINDOWS_R10_PROBE_BYTES={len(output.encode())}")
    print(f"WINDOWS_R10_PROBE_SHA256={hashlib.sha256(output.encode()).hexdigest()}")
