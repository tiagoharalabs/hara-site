#!/usr/bin/env python3
"""Offline, no-secret, no-network acceptance of customer-side MCP tunnel bootstrap."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("hara_commander_local_tunnel_bootstrap.py")


def check(value: bool, name: str) -> None:
    if not value:
        raise AssertionError("BRIDGE_TEST_" + name)
    print("COMMANDER_OPENAI_LOCAL_BRIDGE_" + name + "=PASS")


with tempfile.TemporaryDirectory(prefix="hara-openai-local-bridge-test-") as dirname:
    home = Path(dirname)
    fakebin = home / "fakebin"
    fakebin.mkdir()
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/share/hara-commander").mkdir(parents=True)

    for path in [
        home / ".local/bin/hara-commander",
        home / ".local/share/hara-commander/tunnel-client",
    ]:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)

    service_log = home / "systemctl.log"
    mock_systemctl = fakebin / "systemctl"
    mock_systemctl.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
        "case \"$*\" in *is-active*|*is-enabled*) exit 1;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    mock_systemctl.chmod(0o700)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["SYSTEMCTL_LOG"] = str(service_log)
    env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env, capture_output=True, text=True, timeout=15,
        )

    first = run("prepare")
    check(first.returncode == 0 and "OPENAI_TUNNEL_TRAFFIC_STARTED=FALSE" in first.stdout, "PREPARE_INERT")
    unit = home / ".config/systemd/user/hara-commander-openai-tunnel.service"
    check(unit.is_file() and stat.S_IMODE(unit.stat().st_mode) == 0o600, "PRIVATE_USER_UNIT")
    data = unit.read_text(encoding="utf-8")
    check(
        "ExecStart=" + str(home / ".local/share/hara-commander/tunnel-client") + " run --profile hara-commander" in data
        and "EnvironmentFile=%h/.config/hara-commander/openai-tunnel.env" in data
        and "ExecStartPre=/usr/bin/test -r %h/.config/tunnel-client/hara-commander.yaml" in data,
        "BRIDGE_POINTS_LOCAL_CLIENT",
    )
    check("hara-remote-mcp" not in data and "services" not in data.lower(), "NO_HARA_SERVICES_RELAY")
    commands = service_log.read_text(encoding="utf-8").splitlines()
    check(commands == ["--user daemon-reload"], "PREPARE_NO_START")

    repeat = run("prepare")
    check(repeat.returncode == 0, "PREPARE_IDEMPOTENT")
    status = run("status")
    check(status.returncode == 0 and "OPENAI_TUNNEL_ID_CONFIGURED=FALSE" in status.stdout
          and "OPENAI_RUNTIME_KEY_CONFIGURED=FALSE" in status.stdout
          and "OPENAI_TUNNEL_ACTIVE=FALSE" in status.stdout, "STATUS_NO_CREDS")

    start = run("start")
    check(start.returncode != 0 and "OPENAI_TUNNEL_ID_NOT_CONFIGURED" in start.stderr, "START_WITHOUT_TUNNEL_DENIED")
    config = run("configure")
    check(config.returncode != 0 and "RUN_CONFIGURE_IN_LOCAL_INTERACTIVE_TERMINAL" in config.stderr,
          "CREDENTIALS_INTERACTIVE_ONLY")
    check(not (home / ".config/hara-commander/openai-tunnel.env").exists()
          and not (home / ".config/tunnel-client/hara-commander.yaml").exists(), "NO_FAKE_TUNNEL_OR_SECRET")

print("COMMANDER_OPENAI_LOCAL_BRIDGE_BOOTSTRAP=PASS")
