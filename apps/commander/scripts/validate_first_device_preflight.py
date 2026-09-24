#!/usr/bin/env python3
from __future__ import annotations

import ast
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps/commander/scripts/commander_first_device_preflight.py"
SOURCE = TARGET.read_text(encoding="utf-8")
ast.parse(SOURCE)

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_FIRST_DEVICE_PREFLIGHT_{code}=FAIL")
    print(f"COMMANDER_FIRST_DEVICE_PREFLIGHT_{code}=PASS")

need('run_installer("status", origin)' in SOURCE, "STATUS_ONLY_READ")
need('run_installer("preflight", origin)' in SOURCE, "PREFLIGHT_ONLY_READ")
need('"mutation_performed") is False' in SOURCE, "MUTATION_FALSE_GUARD")
need('"LOCAL_RESIDUE_PRESENT"' in SOURCE, "RESIDUE_GUARD")
need('"DEVICE_ALREADY_ENROLLED"' in SOURCE, "ENROLLMENT_GUARD")
need('"PERSISTENCE_NOT_READY"' in SOURCE, "PERSISTENCE_GUARD")
need('"PUBLIC_LOCAL_RELEASE_VERSION_DRIFT"' in SOURCE, "RELEASE_VERSION_GUARD")
need('"DEVICE_TOKEN_EXPOSED") == "FALSE"' in SOURCE, "TOKEN_EXPOSURE_GUARD")
need("COMMANDER_FIRST_DEVICE_CANDIDATE=READY" in SOURCE, "READY_MARKER")

for forbidden in (
    'run_installer("install"',
    'run_installer("update"',
    'run_installer("uninstall"',
    'subprocess.run(["rm"',
    'shutil.rmtree',
):
    need(forbidden not in SOURCE, "NO_MUTATION_" + forbidden.replace('"', '').replace("(", "_").replace(")", "_").replace("[", "_").replace("]", "_").replace(".", "_").replace(" ", "_").upper()[:36])


need('"XDG_CONFIG_HOME"' in SOURCE, "XDG_CONFIG_HOME_GUARD")
need('"XDG_DATA_HOME"' in SOURCE, "XDG_DATA_HOME_GUARD")

namespace = {
    "__name__": "commander_first_device_preflight_test",
    "__file__": str(TARGET),
}
exec(compile(SOURCE, str(TARGET), "exec"), namespace)
residue_state = namespace["residue_state"]

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    home = root / "home"
    config = root / "xdg-config"
    data = root / "xdg-data"
    home.mkdir()
    config.mkdir()
    data.mkdir()

    env = {
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
    }
    clean = residue_state(home, env)
    need(not any(clean.values()), "XDG_CLEAN_STATE")

    (data / "hara-commander").mkdir()
    with_data = residue_state(home, env)
    need(with_data["data_dir"] is True, "XDG_DATA_RESIDUE_DETECTED")

    (config / "systemd/user").mkdir(parents=True)
    (config / "systemd/user/hara-commander-agent.service").write_text(
        "[Unit]\nDescription=test\n",
        encoding="utf-8",
    )
    with_unit = residue_state(home, env)
    need(with_unit["systemd_unit"] is True, "XDG_SYSTEMD_RESIDUE_DETECTED")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    home = root / "home"
    home.mkdir()
    (home / ".config/hara-commander").mkdir(parents=True)
    default_state = residue_state(home, {})
    need(default_state["config_dir"] is True, "DEFAULT_CONFIG_RESIDUE_DETECTED")


for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
    try:
        residue_state(home, {key: "relative/path"})
    except namespace["PreflightError"] as exc:
        need(str(exc) == "XDG_PATH_NOT_ABSOLUTE", f"{key}_RELATIVE_DENIED")
    else:
        raise SystemExit(f"COMMANDER_FIRST_DEVICE_PREFLIGHT_{key}_RELATIVE_DENIED=FAIL")

print("COMMANDER_FIRST_DEVICE_PREFLIGHT_CONTRACT=PASS")
