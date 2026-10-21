#!/usr/bin/env python3
"""Fail-closed review gate: latest platform installers AND fleet release parity.

Offline: reads reviewed source, a signed release and an explicit evidence file.
No network, no enrollment, no signing, no Agent restart, no promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from verify_signed_distribution import verify_bundle, ReleaseValidationError

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs/evidence/commander-version-parity-r20-20261021/fleet_release_inventory.json"
SEMVER = re.compile(r"^[0-9]+[.][0-9]+[.][0-9]+$")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def source_version(raw: bytes, platform: str) -> str | None:
    pattern = (rb'^AGENT_VERSION\s*=\s*"([0-9]+[.][0-9]+[.][0-9]+)"'
               if platform == "linux"
               else rb'^\$AgentVersion\s*=\s*"([0-9]+[.][0-9]+[.][0-9]+)"')
    matches = re.findall(pattern, raw, re.M)
    return matches[0].decode("ascii") if len(matches) == 1 else None

def evaluate(inventory: dict, *, root: Path = ROOT, target: str = "0.3.55") -> dict:
    if inventory.get("schema") != "hara.commander.release.parity.inventory.r20.v1":
        raise ValueError("R20_INVENTORY_SCHEMA_INVALID")
    if not SEMVER.fullmatch(target):
        raise ValueError("R20_TARGET_RELEASE_VERSION_INVALID")
    blockers = []
    checks = {}
    def gate(code: str, ok: bool):
        checks[code] = bool(ok)
        if not ok:
            blockers.append(code)
    li = inventory["linux"]
    win = inventory["windows"]
    commercial = inventory["commercial_current"]
    public = inventory["public_live_last_checked"]
    configured = inventory.get("provisional_target_release")
    gate("RELEASE_TARGET_EXPLICITLY_SELECTED", target == configured)
    observed = {
        "linux_runtime": li["installed_version"],
        "windows_registry": win["registered_agent_version"],
        "windows_candidate": win["latest_candidate_version"],
        "commercial_signed": commercial["signed_package_version"],
        "public_download": public["served_manifest_version"],
    }
    gate("SEVEN_LINUX_REAL_RUNTIME_PASS",
         li["active_ping_pass"] == li["read_file_pass"] == li["short_process_pass"] ==
         li["rs256_manifest_verified"] == li["unit_v2_active_enabled"] == 7
         and li["signed_asset_hash_mismatches"] == 0 and li["capabilities_each"] == 31)
    gate("LINUX_FOUNDER_RUNNING_TARGET_RELEASE", li["installed_version"] == target)
    loops = li["runtime_loop_variants"]
    gate("RUNNING_LINUX_LOOP_BUILD_EQUIVALENCE_APPROVED",
         len(loops) == 1 or li.get("loop_variants_approved_as_equivalent") is True)
    gate("WINDOWS_VM_ONLINE_AND_TARGET_INSTALLED",
         win["runtime_state"] == "RUNNING"
         and win["registered_agent_version"] == target
         and win.get("live_clean_install_055_pass") is True)

    # Verify signed commercial bytes; inventory cannot declare a signed release.
    bundle_name = commercial["bundle_name"]
    bundle = root / "apps/commander/release-bundles" / bundle_name
    try:
        signed = verify_bundle(bundle)
        signed_version = signed["agent_version"]
        trusted_signature = signed["signature"] == "RS256_RSA3072_VALID"
    except (ReleaseValidationError, OSError, ValueError, KeyError) as exc:
        signed_version = None
        trusted_signature = False
    gate("COMMERCIAL_BUNDLE_CRYPTOGRAPHICALLY_VALID", trusted_signature)
    gate("SIGNED_RELEASE_INVENTORY_MATCHES_BYTES",
         signed_version == commercial["signed_package_version"]
         and signed_version == commercial["linux_agent_version"]
         and signed_version == commercial["windows_agent_version"])
    gate("LATEST_LINUX_AND_WINDOWS_INSTALLERS_SIGNED_TO_SAME_TARGET",
         trusted_signature and signed_version == target
         and commercial["channel"] == "COMMERCIAL_STABLE")

    # An available Windows candidate cannot be used to authorize a release.
    cand = root / "apps/commander/candidate/windows_agent_055.ps1"
    win_raw = cand.read_bytes() if cand.is_file() and not cand.is_symlink() else b""
    gate("WINDOWS_CANDIDATE_SOURCE_HASH_INTACT",
         bool(win_raw) and sha(win_raw) == win["candidate_source_sha256"]
         and source_version(win_raw, "windows") == win["latest_candidate_version"])
    gate("WINDOWS_LATEST_SOURCE_MATCHES_TARGET", win["latest_candidate_version"] == target)
    gate("WINDOWS_LATEST_SIGNED_AND_RUNTIME_ACCEPTED",
         win["candidate_signed"] is True and win["candidate_installed"] is True
         and win["runtime_state"] == "RUNNING"
         and win["live_clean_install_055_pass"] is True)

    # Filename/version alone never attests a Linux successor. Explicit source
    # hash and independent runtime evidence must be supplied in the inventory.
    patch = int(target.split(".")[-1])
    linux_target = root / f"apps/commander/candidate/linux_agent_{patch:03d}.py"
    source_raw = linux_target.read_bytes() if linux_target.is_file() and not linux_target.is_symlink() else b""
    linux_pin = li.get("proposed_commercial_source_sha256")
    gate("LINUX_TARGET_COMMERCIAL_SOURCE_PROVEN",
         bool(source_raw) and bool(linux_pin) and sha(source_raw) == linux_pin
         and source_version(source_raw, "linux") == target
         and li.get("commercial_target_runtime_regressions_pass") is True)

    # Platform-specific capabilities can differ, but exceptions MUST be agreed
    # and publicly documented; claiming full parity from version equality is wrong.
    gate("CROSS_PLATFORM_CAPABILITY_PARITY_QUALIFIED",
         not win["capabilities_missing_relative_to_linux"]
         or win.get("platform_differences_documented_and_approved") is True)

    gate("PUBLIC_DOWNLOADS_PASS_SIGNED_TARGET_READBACK",
         public["state"] == "PASS" and public["served_manifest_version"] == target
         and public["served_signature_kid"] == "commander-release-v2"
         and public["asset_hash_matches"] == public["total_assets"] == 4)

    gate("ALL_HOSTS_UNIFIED_RELEASE_AND_BUILD_QUALIFIED",
         li["installed_version"] == win["registered_agent_version"] == target
         and (len(loops) == 1 or li.get("loop_variants_approved_as_equivalent") is True))
    return {
        "schema": "hara.commander.release-train-parity-gate.r20.v1",
        "state": "READY_FOR_PLATFORM_ACCEPTANCE" if not blockers else "HOLD",
        "target_release_proposed_not_approved": target,
        "versions_observed": observed,
        "linux_declared_capabilities": li["capabilities_each"],
        "windows_candidate_declared_capabilities": win["capabilities_candidate_worker_contract"],
        "fleet_semver_uniform_linux": True,
        "fleet_build_uniform_linux": len(loops) == 1,
        "checks": checks,
        "blockers": blockers,
        "mutation_performed": False,
        "network_access": False,
        "public_distribution_updated": False,
    }

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory", type=Path, default=INVENTORY)
    p.add_argument("--target", default="0.3.55")
    args = p.parse_args()
    report=evaluate(json.loads(args.inventory.read_text()),target=args.target)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["state"] == "READY_FOR_PLATFORM_ACCEPTANCE" else 2

if __name__ == "__main__":
    raise SystemExit(main())
