#!/usr/bin/env python3
"""Sandbox transition proof for Linux Event V2 RC installer."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "apps/commander/candidate/install_linux_rc.sh"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(installer_env: dict[str, str], action: str, *, expect: int = 0, fail_rc=False):
    env = installer_env.copy()
    if fail_rc:
        env["HARA_TEST_FAIL_RC_START"] = "1"
    else:
        env.pop("HARA_TEST_FAIL_RC_START", None)
    proc = subprocess.run(
        ["bash", str(INSTALLER), action],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if proc.returncode != expect:
        raise AssertionError(
            f"{action}: expected {expect}, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc


def state(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            out[key] = value
    return out


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hara-event-v2-rc-") as tmp:
        root = Path(tmp)
        home = root / "home"
        config = root / "config"
        data = root / "data"
        fakebin = root / "bin"
        fakebin.mkdir(parents=True)
        home.mkdir()

        commander_config = config / "hara-commander"
        commander_config.mkdir(parents=True)
        device_env = commander_config / "device.env"
        device_env.write_text(
            "\n".join(
                (
                    "HARA_COMMANDER_URL=https://dev.invalid",
                    "HARA_DEVICE_ID=HARA-DEVICE-RC-TEST",
                    "HARA_DEVICE_TOKEN=TEST_TOKEN_" + "x" * 64,
                    "HARA_DEVICE_ARCH=x86_64",
                    "",
                )
            ),
            encoding="utf-8",
        )
        device_env.chmod(0o600)
        before_hash = sha256(device_env)

        state_file = root / "systemctl.state"
        state_file.write_text(
            "hara-commander-agent.service=active\n"
            "hara-commander-agent-rc.service=inactive\n",
            encoding="utf-8",
        )

        systemctl = fakebin / "systemctl"
        systemctl.write_text(
            r'''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

args=[a for a in sys.argv[1:] if a != "--user"]
state_path=Path(os.environ["HARA_TEST_SYSTEMCTL_STATE"])
pairs={}
for raw in state_path.read_text().splitlines():
    if "=" in raw:
        key,value=raw.split("=",1)
        pairs[key]=value

def save():
    state_path.write_text("".join(f"{k}={v}\n" for k,v in sorted(pairs.items())))

if not args:
    raise SystemExit(2)
cmd=args[0]
service=args[1] if len(args)>1 else ""

if cmd in {"daemon-reload","enable","disable"}:
    raise SystemExit(0)
if cmd == "is-active":
    raise SystemExit(0 if pairs.get(service)=="active" else 3)
if cmd == "stop":
    pairs[service]="inactive"
    save()
    raise SystemExit(0)
if cmd == "start":
    if service=="hara-commander-agent-rc.service" and os.environ.get("HARA_TEST_FAIL_RC_START")=="1":
        raise SystemExit(1)
    pairs[service]="active"
    if service=="hara-commander-agent-rc.service":
        pairs["hara-commander-agent.service"]="inactive"
    elif service=="hara-commander-agent.service":
        pairs["hara-commander-agent-rc.service"]="inactive"
    save()
    raise SystemExit(0)
raise SystemExit(0)
''',
            encoding="utf-8",
        )
        systemctl.chmod(0o700)

        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(config),
                "XDG_DATA_HOME": str(data),
                "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
                "HARA_TEST_SYSTEMCTL_STATE": str(state_file),
            }
        )

        installed = run(env, "install")
        assert "COMMANDER_AGENT_RC_INSTALL=PASS" in installed.stdout
        assert "COMMANDER_AGENT_RC_AUTO_START=FALSE" in installed.stdout
        assert sha256(device_env) == before_hash
        assert stat.S_IMODE(device_env.stat().st_mode) == 0o600
        s = state(state_file)
        assert s["hara-commander-agent.service"] == "active"
        assert s["hara-commander-agent-rc.service"] == "inactive"

        activated = run(env, "activate-event-v2")
        assert "COMMANDER_AGENT_RC_EVENT_V2_ACTIVATION=PASS" in activated.stdout
        assert sha256(device_env) == before_hash
        rc_env = commander_config / "rc.env"
        assert rc_env.read_text(encoding="utf-8").strip() == "HARA_DEVICE_TRANSPORT_MODE=EVENT_V2"
        assert stat.S_IMODE(rc_env.stat().st_mode) == 0o600
        s = state(state_file)
        assert s["hara-commander-agent.service"] == "inactive"
        assert s["hara-commander-agent-rc.service"] == "active"

        rolled = run(env, "rollback")
        assert "COMMANDER_AGENT_RC_ROLLBACK=PASS" in rolled.stdout
        assert sha256(device_env) == before_hash
        assert rc_env.read_text(encoding="utf-8").strip() == "HARA_DEVICE_TRANSPORT_MODE=POLL_V1"
        s = state(state_file)
        assert s["hara-commander-agent.service"] == "active"
        assert s["hara-commander-agent-rc.service"] == "inactive"

        # Reset and force RC start failure: stable must be restored.
        state_file.write_text(
            "hara-commander-agent.service=active\n"
            "hara-commander-agent-rc.service=inactive\n",
            encoding="utf-8",
        )
        failed = run(env, "activate-event-v2", expect=2, fail_rc=True)
        assert "RC_EVENT_V2_START_FAILED_ROLLED_BACK" in failed.stderr
        assert "COMMANDER_AGENT_RC_ROLLBACK=PASS" in failed.stdout
        assert sha256(device_env) == before_hash
        assert rc_env.read_text(encoding="utf-8").strip() == "HARA_DEVICE_TRANSPORT_MODE=POLL_V1"
        s = state(state_file)
        assert s["hara-commander-agent.service"] == "active"
        assert s["hara-commander-agent-rc.service"] == "inactive"

    print("COMMANDER_EVENT_V2_LINUX_RC_SANDBOX=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_DEVICE_ENV_PRESERVED=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_ACTIVATE=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_ROLLBACK=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_FAILED_START_ROLLBACK=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_DUAL_AGENT=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
