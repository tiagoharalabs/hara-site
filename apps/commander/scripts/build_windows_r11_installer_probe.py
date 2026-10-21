#!/usr/bin/env python3
"""Extract candidate installer pre-enrollment function for no-install Windows QA."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1]
SOURCE = APP / "candidate/windows_install_043.ps1"
FIXTURE = APP / "scripts/test_windows_r11_installer_fixture.ps1"


def function(source: str, name: str) -> str:
    match = re.search(r"(?m)^function " + re.escape(name) + r"\b", source)
    if not match:
        raise ValueError("WINDOWS_R11_PROBE_FUNCTION_MISSING:" + name)
    start = match.start()
    end = source.index("\nfunction ", start + 1)
    return source[start:end].rstrip() + "\n\n"


def build() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    selected = function(source, "Assert-ReleaseManifestSignature") + function(source, "Get-VerifiedReleaseBeforeEnrollment")
    return ("$ErrorActionPreference='Stop'\n$BaseUrl='https://candidate.local'\n"
            "$ReleaseSigningKid='commander-release-v2'\n"
            + selected + FIXTURE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = build()
    args.output.write_text(data, encoding="utf-8")
    print("WINDOWS_R11_PROBE_SHA256=" + hashlib.sha256(data.encode()).hexdigest())
