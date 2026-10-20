#!/usr/bin/env python3
"""Prepare a source candidate for official signing without reading a private key.

Linux gets the reviewed continuous and terminal-drain fixes. Windows and both installers remain
the last signed commercial versions; the separate Windows 0.3.52 RC is not
silently promoted. The output has no signature and cannot be published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from stage_signed_commercial_assets import APP, BUNDLES, ROLLBACK_RELEASE, stage

LINUX_SOURCE = APP / "public/agent/linux.py"
REVIEWED_LINUX_SHA256 = "0c8e5793af6636e2215752b448a8e4ad15ab35c9f0c1902f388c80bb73b204a8"
FILESET = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
CURRENT_STATIC = ("index.html", "app.js")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(output: Path) -> dict:
    if output.exists() or output.is_symlink() or not output.is_absolute():
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_REQUIRES_NEW_ABSOLUTE_OUTPUT")
    if Path("/tmp") not in output.parents or output.parent.resolve() != output.parent.absolute():
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_REQUIRES_PRIVATE_TMP")
    linux = LINUX_SOURCE.read_bytes()
    if digest(linux) != REVIEWED_LINUX_SHA256 or b'AGENT_VERSION = "0.3.43"' not in linux:
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_LINUX_SOURCE_DRIFT")
    for script in ("validate_process_terminal_drain.py", "validate_process_continuous_drain.py",
                   "validate_process_oneshot_pagination.py",
                   "validate_result_delivery_outbox.py", "validate_result_envelope_budget.py"):
        regression = subprocess.run(
            [sys.executable, "-B", str(APP / "scripts" / script)],
            capture_output=True, text=True, check=False, timeout=20,
        )
        if regression.returncode:
            raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_PTY_REGRESSION:" + script)
    public = output / "apps/commander/public"
    public.parent.mkdir(mode=0o700, parents=True)
    stage(public, BUNDLES[ROLLBACK_RELEASE], rollback_only=True)
    (public / "agent/linux.py").write_bytes(linux)
    for relative in CURRENT_STATIC:
        (public / relative).write_bytes((APP / "public" / relative).read_bytes())
    manifest_path = public / "release/agent-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("agent_version") != "0.3.43":
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_VERSION_DRIFT")
    manifest["files"] = [
        {"bytes": len((public / relative).read_bytes()),
         "path": relative,
         "sha256": digest((public / relative).read_bytes())}
        for relative in FILESET
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (public / "release/SHA256SUMS").write_text("".join(
        f"{row['sha256']}  {row['path']}\n" for row in manifest["files"]
    ))
    (public / "release/agent-manifest.sig.json").unlink()
    for relative in FILESET:
        if relative != "agent/linux.py" and (public / relative).read_bytes() != (BUNDLES[ROLLBACK_RELEASE] / relative).read_bytes():
            raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_COMMERCIAL_ASSET_DRIFT")
    if (public / "release/agent-manifest.sig.json").exists():
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_MUST_REMAIN_UNSIGNED")
    report = {
        "schema": "hara.commander-commercial-drain-source-candidate.v1",
        "state": "AWAITING_OFFICIAL_SIGNATURE",
        "linux_agent_version": "0.3.43",
        "windows_agent_version": "0.3.43",
        "linux_agent_sha256": digest(linux),
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "frozen_commercial_base": ROLLBACK_RELEASE,
        "current_static_sha256": {
            relative: digest((public / relative).read_bytes())
            for relative in CURRENT_STATIC
        },
        "signature_present": False,
        "private_key_read": False,
        "production_mutation": False,
    }
    (output / "CANDIDATE_STATUS.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.check == bool(args.output):
        raise SystemExit("COMMERCIAL_DRAIN_CANDIDATE_CHOOSE_CHECK_OR_OUTPUT")
    if args.check:
        with tempfile.TemporaryDirectory(prefix="commander-drain-candidate-") as temporary:
            report = prepare(Path(temporary) / "candidate")
        print("COMMERCIAL_DRAIN_SOURCE_CANDIDATE=PASS_UNSIGNED_ONLY")
    else:
        report = prepare(args.output)
        report["candidate_path"] = str(args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
