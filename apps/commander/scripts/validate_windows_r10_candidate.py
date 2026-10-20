#!/usr/bin/env python3
"""Offline provenance and packaging guard for the unsigned Windows 0.3.55 source.

The Windows runtime behavior is exercised separately by the R10 PowerShell
probe on the QA VM. This guard does not sign, stage or install an Agent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import build_windows_r10_runtime_probe as probe
from verify_signed_distribution import FILES, METADATA, verify_bundle

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
BASE_COMMIT = "0e0c2ac"
BASE_PATH = "apps/commander/release-bundles/commercial-0.3.54-v14-rc-r2"
BASE_AGENT_SHA256 = "fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62"
FROZEN_PUBLIC_052_SHA256 = "817325667ea552136efa10d807148fa4dc6d035aca24046c884f444a4fb61ebc"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def git_blob(relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{BASE_PATH}/{relative}"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="commander-win055-base-") as temp:
        bundle = Path(temp)
        for relative in (*FILES, *METADATA):
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git_blob(relative))
        verified = verify_bundle(bundle)
        if verified["agent_version"] != "0.3.54":
            raise AssertionError("WINDOWS_R10_SIGNED_BASE_VERSION_INVALID")
        if sha((bundle / "agent/windows.ps1").read_bytes()) != BASE_AGENT_SHA256:
            raise AssertionError("WINDOWS_R10_SIGNED_BASE_SHA_INVALID")
    public = APP / "public/agent/windows.ps1"
    if sha(public.read_bytes()) != FROZEN_PUBLIC_052_SHA256:
        raise AssertionError("WINDOWS_R10_HISTORICAL_052_SOURCE_DRIFT")
    candidate = APP / "candidate/windows_agent_055.ps1"
    source = candidate.read_text(encoding="utf-8")
    if source.count('$AgentVersion = "0.3.55"') != 1:
        raise AssertionError("WINDOWS_R10_CANDIDATE_VERSION_INVALID")
    required = (
        'function Get-WindowsDirectory(', 'function Read-WindowsManyTextFiles(',
        'function Search-WindowsFiles(', 'function Edit-WindowsTextFile(',
        'function Get-WindowsRelayPollSleep(', 'function Read-WindowsManagedSession(',
        'function Invoke-WindowsOneShotProcess(',
        'HaraWindowsProcessSession(string id, string cwd, string command, bool oneShot)',
    )
    if any(marker not in source for marker in required):
        raise AssertionError("WINDOWS_R10_CANDIDATE_FUNCTION_MISSING")
    if "ReadToEndAsync" in source:
        raise AssertionError("WINDOWS_R10_UNBOUNDED_ONESHOT_READER_REINTRODUCED")
    generated = probe.build()
    if "WINDOWS_R10_CANDIDATE_ONESHOT=PASS" not in generated:
        raise AssertionError("WINDOWS_R10_RUNTIME_PROBE_INCOMPLETE")
    print(json.dumps({
        "schema": "hara.commander-windows-r10-candidate-offline.v1",
        "state": "PASS", "signed_base_version": "0.3.54",
        "signed_base_verified": True, "signed_base_agent_sha256": BASE_AGENT_SHA256,
        "candidate_version": "0.3.55", "candidate_sha256": sha(candidate.read_bytes()),
        "runtime_probe_sha256": sha(generated.encode()),
        "candidate_signature_present": False,
        "candidate_installed": False, "production_action": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
