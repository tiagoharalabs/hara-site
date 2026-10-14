#!/usr/bin/env python3
"""Offline negative test: an unsigned modification must fail the commercial release verifier.

No credentials, production network calls, or changes to the signed original.
"""
from __future__ import annotations
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "apps/commander/scripts/build_commander_commercial_autoreconnect_signed.py"
FILES = (
    "agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1",
    "release/agent-manifest.json", "release/agent-manifest.sig.json",
    "release/release-signing-public.jwk", "release/SHA256SUMS", "index.html",
)

def digest(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()

def verify(stage: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(VERIFIER), "verify", "--stage", str(stage)],
        capture_output=True, text=True, timeout=25, check=False,
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    original = args.stage.resolve()
    public = original / "apps/commander/public"
    assert all((public / f).is_file() for f in FILES), "SIGNED_FILES_MISSING"
    originals = {f: digest(public / f) for f in FILES}
    untouched = verify(original)
    assert untouched.returncode == 0, "UNMODIFIED_STAGE_REJECTED"
    with tempfile.TemporaryDirectory(prefix="commander-sig-negative-", dir="/tmp_hara") as td:
        stage = Path(td)
        target = stage / "apps/commander/public"
        for relative in FILES:
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(public / relative, dest)
        assert verify(stage).returncode == 0, "ISOLATED_STAGE_REJECTED"
        with (target / "install/linux.sh").open("ab") as output:
            output.write(b"\n# unsigned-test-marker\n")
        rejected = verify(stage)
        assert rejected.returncode != 0, "UNSIGNED_PACKAGE_ACCEPTED"
        assert "COMMERCIAL_SIGNED_V2_FILE_HASH_MISMATCH" in rejected.stderr, (
            "WRONG_TAMPER_FAILURE:" + rejected.stderr[-250:]
        )
    assert all(digest(public / f) == expected for f, expected in originals.items()), (
        "ORIGINAL_SIGNED_ASSETS_CHANGED"
    )
    print("COMMANDER_COMMERCIAL_SIGNED_ORIGINAL=PASS")
    print("COMMANDER_COMMERCIAL_TAMPER_DENIED=PASS")
    print("COMMANDER_COMMERCIAL_PRIVATE_KEY_NOT_USED=TRUE")
    print("COMMANDER_COMMERCIAL_ORIGINAL_UNCHANGED=TRUE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
