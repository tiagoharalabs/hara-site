#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
INSTALLER = APP / "public/install/linux.sh"
MANIFEST = APP / "public/release/agent-manifest.json"
DEFAULT_ORIGIN = "https://commander.haralabs.com.br"

class PreflightError(RuntimeError):
    pass

def run_installer(action: str, origin: str) -> str:
    env = os.environ.copy()
    env["HARA_COMMANDER_URL"] = origin
    proc = subprocess.run(
        ["bash", str(INSTALLER), action],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise PreflightError(f"INSTALLER_{action.upper()}_FAILED")
    return proc.stdout

def parse_status(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip()
    return out

def parse_preflight(text: str) -> dict:
    candidates = [line.strip() for line in text.splitlines() if line.strip().startswith("{")]
    if not candidates:
        raise PreflightError("PREFLIGHT_JSON_MISSING")
    try:
        return json.loads(candidates[-1])
    except json.JSONDecodeError as exc:
        raise PreflightError("PREFLIGHT_JSON_INVALID") from exc

def _xdg_root(home: Path, value: str | None, fallback: str) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            raise PreflightError("XDG_PATH_NOT_ABSOLUTE")
    else:
        path = home / fallback
    return path.resolve()

def residue_state(
    home: Path,
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    env = os.environ if environ is None else environ
    config_root = _xdg_root(home, env.get("XDG_CONFIG_HOME"), ".config")
    data_root = _xdg_root(home, env.get("XDG_DATA_HOME"), ".local/share")
    paths = {
        "config_dir": config_root / "hara-commander",
        "data_dir": data_root / "hara-commander",
        "systemd_unit": config_root / "systemd/user/hara-commander-agent.service",
    }
    return {name: path.exists() for name, path in paths.items()}

def need(condition: bool, code: str) -> None:
    if not condition:
        raise PreflightError(code)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove a Linux host is clean and ready for the first Commander PROD pairing without mutating it."
    )
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    origin = args.origin.rstrip("/")
    need(origin == DEFAULT_ORIGIN, "ORIGIN_NOT_CANONICAL_PROD")
    need(sys.platform.startswith("linux"), "LINUX_REQUIRED")
    need(INSTALLER.is_file(), "INSTALLER_MISSING")
    need(MANIFEST.is_file(), "RELEASE_MANIFEST_MISSING")

    status = parse_status(run_installer("status", origin))
    need(status.get("HARA_COMMANDER_DEVICE_ENROLLED") == "FALSE", "DEVICE_ALREADY_ENROLLED")
    need(status.get("HARA_COMMANDER_AGENT_ACTIVE") == "FALSE", "AGENT_ALREADY_ACTIVE")
    need(status.get("HARA_COMMANDER_AGENT_ENABLED") == "FALSE", "AGENT_ALREADY_ENABLED")
    need(status.get("DEVICE_TOKEN_EXPOSED") == "FALSE", "TOKEN_EXPOSURE_MARKER_INVALID")

    residues = residue_state(Path.home())
    need(not any(residues.values()), "LOCAL_RESIDUE_PRESENT")

    preflight = parse_preflight(run_installer("preflight", origin))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release_version = str(manifest.get("agent_version") or "")

    need(preflight.get("schema") == "hara.commander-device-preflight.v1", "PREFLIGHT_SCHEMA_INVALID")
    need(preflight.get("platform") == "LINUX", "PREFLIGHT_PLATFORM_INVALID")
    need(preflight.get("commander_url") == DEFAULT_ORIGIN, "PREFLIGHT_ORIGIN_INVALID")
    need(preflight.get("commander_health") is True, "COMMANDER_HEALTH_FAILED")
    need(preflight.get("release_manifest") is True, "RELEASE_MANIFEST_UNREACHABLE")
    need(preflight.get("persistence") == "systemd-user", "PERSISTENCE_KIND_INVALID")
    need(preflight.get("persistence_ready") is True, "PERSISTENCE_NOT_READY")
    need(preflight.get("mutation_performed") is False, "PREFLIGHT_MUTATED_HOST")
    need(bool(release_version), "LOCAL_RELEASE_VERSION_MISSING")
    need(preflight.get("stable_agent_version") == release_version, "PUBLIC_LOCAL_RELEASE_VERSION_DRIFT")

    report = {
        "schema": "hara.commander-first-device-candidate.v1",
        "state": "READY",
        "platform": "LINUX",
        "architecture": str(preflight.get("architecture") or ""),
        "origin": DEFAULT_ORIGIN,
        "agent_version": release_version,
        "device_enrolled": False,
        "agent_active": False,
        "agent_enabled": False,
        "local_residue": False,
        "persistence_ready": True,
        "commander_health": True,
        "release_manifest": True,
        "mutation_performed": False,
        "device_token_exposed": False,
    }

    if args.json:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    print("COMMANDER_FIRST_DEVICE_CANDIDATE_STATUS=PASS")
    print("COMMANDER_FIRST_DEVICE_CANDIDATE_RESIDUE=ABSENT")
    print("COMMANDER_FIRST_DEVICE_CANDIDATE_PERSISTENCE=READY")
    print("COMMANDER_FIRST_DEVICE_CANDIDATE_MUTATION=FALSE")
    print("COMMANDER_FIRST_DEVICE_CANDIDATE_TOKEN_EXPOSED=FALSE")
    print("COMMANDER_FIRST_DEVICE_CANDIDATE=READY")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        print(f"COMMANDER_FIRST_DEVICE_CANDIDATE=FAIL:{exc}")
        raise SystemExit(1)
