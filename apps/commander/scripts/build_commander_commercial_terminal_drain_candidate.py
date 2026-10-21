#!/usr/bin/env python3
"""Prepare a source candidate for official signing without reading a private key.

Linux gets the reviewed continuous and terminal-drain fixes. Both candidate
installers authenticate the complete release before enrollment; the Windows
Agent remains the signed commercial 0.3.43 source. The separate Windows 0.3.55
source is not silently promoted. The output has no signature and cannot be
published.
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
REVIEWED_LINUX_SHA256 = "4c81d45a6532a53387db40ac06d95a382a7ffdb3a6da35861d4f9b350f1ab6aa"
LINUX_INSTALLER_SOURCE = APP / "candidate/linux_install_043.sh"
REVIEWED_LINUX_INSTALLER_SHA256 = "4ba6749ca3d3554918de93eb266c2e409fe2e88254c493e79fe7171e5633b9b1"
WINDOWS_INSTALLER_SOURCE = APP / "candidate/windows_install_043.ps1"
REVIEWED_WINDOWS_INSTALLER_SHA256 = "69a6bf0c2a3c7c373d524dd63d2272511eae5b81665d5ecf0d625bcb31c5cdad"
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
    installer = LINUX_INSTALLER_SOURCE.read_bytes()
    if digest(installer) != REVIEWED_LINUX_INSTALLER_SHA256 or b'RELEASE_SIGNING_KID="commander-release-v2"' not in installer:
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_LINUX_INSTALLER_DRIFT")
    windows_installer = WINDOWS_INSTALLER_SOURCE.read_bytes()
    if digest(windows_installer) != REVIEWED_WINDOWS_INSTALLER_SHA256 or b'$ReleaseSigningKid = "commander-release-v2"' not in windows_installer:
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_WINDOWS_INSTALLER_DRIFT")
    for script in ("validate_process_terminal_drain.py", "validate_process_continuous_drain.py",
                   "validate_process_oneshot_pagination.py", "validate_process_session_policy.py",
                   "validate_result_delivery_outbox.py", "validate_result_envelope_budget.py",
                   "validate_file_cas_atomicity.py", "validate_relay_burst_dispatch.py",
                   "validate_mount_aware_resources.py"):
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
    (public / "install/linux.sh").write_bytes(installer)
    (public / "install/windows.ps1").write_bytes(windows_installer)
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
        if relative not in ("agent/linux.py", "install/linux.sh", "install/windows.ps1") and (public / relative).read_bytes() != (BUNDLES[ROLLBACK_RELEASE] / relative).read_bytes():
            raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_COMMERCIAL_ASSET_DRIFT")
    if (public / "release/agent-manifest.sig.json").exists():
        raise RuntimeError("COMMERCIAL_DRAIN_CANDIDATE_MUST_REMAIN_UNSIGNED")
    report = {
        "schema": "hara.commander-commercial-drain-source-candidate.v1",
        "state": "AWAITING_OFFICIAL_SIGNATURE",
        "linux_agent_version": "0.3.43",
        "windows_agent_version": "0.3.43",
        "linux_agent_sha256": digest(linux),
        "linux_installer_sha256": digest(installer),
        "windows_installer_sha256": digest(windows_installer),
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
