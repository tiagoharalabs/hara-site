#!/usr/bin/env python3
"""Pin the unsigned Windows installer source and its no-install QA fixture."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_windows_r11_installer_probe import build

APP = Path(__file__).resolve().parents[1]
SOURCE = APP / "candidate/windows_install_043.ps1"
EXPECTED_SOURCE = "69a6bf0c2a3c7c373d524dd63d2272511eae5b81665d5ecf0d625bcb31c5cdad"
EXPECTED_PROBE = "64f0f2ca7ba59f57191515271ad0da9a26046ac7a739cec047144c472a04365e"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    raw = SOURCE.read_bytes()
    source = raw.decode("utf-8")
    assert sha(raw) == EXPECTED_SOURCE, "WINDOWS_R11_INSTALLER_SOURCE_DRIFT"
    assert source.index("$PreparedRelease = Get-VerifiedReleaseBeforeEnrollment") < source.index(
        '$Enroll = Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll-intent"'), "WINDOWS_R11_ENROLL_BEFORE_VERIFY"
    assert "Copy-Item -LiteralPath $PreparedRelease.Agent -Destination $InstallTmp" in source
    assert sha(build().encode()) == EXPECTED_PROBE, "WINDOWS_R11_VM_PROBE_DRIFT"
    print(json.dumps({
        "schema": "hara.commander-windows-r11-installer-candidate.v1",
        "state": "PASS", "candidate_sha256": EXPECTED_SOURCE,
        "vm_probe_sha256": EXPECTED_PROBE,
        "signature_present": False, "candidate_installed": False,
        "production_mutation": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
