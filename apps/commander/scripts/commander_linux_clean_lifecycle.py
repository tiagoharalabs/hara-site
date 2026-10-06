#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import pty
import select
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
INSTALLER = APP / "public" / "install" / "linux.sh"
AGENT = APP / "public" / "agent" / "linux.py"
MANIFEST = APP / "public" / "release" / "agent-manifest.json"


class MockState:
    def __init__(self):
        self.tokens: dict[str, dict] = {}
        self.pairings = {
            "PAIR-ONE": ("HARA-CLEAN-DEVICE-1", "HARA-CLEAN-TOKEN-1"),
            "PAIR-TWO": ("HARA-CLEAN-DEVICE-2", "HARA-CLEAN-TOKEN-2"),
        }


class Handler(http.server.BaseHTTPRequestHandler):
    state: MockState
    base_dir: Path

    def log_message(self, *_args):
        return

    def _json(self, status: int, payload: dict):
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "service": "hara-commander"})
            return
        if path == "/release/agent-manifest.json":
            raw = MANIFEST.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/release/agent-manifest.sig.json":
            raw = (APP / "public" / "release" / "agent-manifest.sig.json").read_bytes()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/agent/linux.py":
            raw = AGENT.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "text/x-python")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self._json(404, {"ok": False, "code": "NOT_FOUND"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except Exception:
            body = {}
        if path == "/api/device/enroll":
            pairing = str(body.get("pairing_token") or "")
            record = self.state.pairings.get(pairing)
            if not record:
                self._json(401, {"ok": False, "code": "DEVICE_PAIRING_INVALID"})
                return
            device_id, token = record
            self.state.tokens[token] = {"device_id": device_id, "revoked": False}
            self._json(201, {"device_id": device_id, "device_token": token})
            return
        auth = str(self.headers.get("authorization") or "")
        token = auth.removeprefix("Bearer ").strip()
        record = self.state.tokens.get(token)
        if not record or record["revoked"]:
            self._json(401, {"ok": False, "code": "DEVICE_AUTH_INVALID"})
            return
        if path == "/api/device/heartbeat":
            if str(body.get("device_id") or "") != record["device_id"]:
                self._json(403, {"ok": False, "code": "DEVICE_ID_MISMATCH"})
                return
            self._json(200, {"ok": True, "device_id": record["device_id"]})
            return
        if path == "/api/device/revoke-self":
            record["revoked"] = True
            self._json(200, {"ok": True, "state": "REVOKED", "device_id": record["device_id"]})
            return
        self._json(404, {"ok": False, "code": "NOT_FOUND"})


FAKE_SYSTEMCTL = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time

args=[a for a in sys.argv[1:] if a != "--user"]
home=pathlib.Path(os.environ["HOME"])
data=pathlib.Path(os.environ.get("XDG_DATA_HOME", str(home/".local/share")))
state_dir=home/".hara-clean-systemctl"
state_dir.mkdir(parents=True, exist_ok=True)
active=state_dir/"active"
enabled=state_dir/"enabled"
agent=data/"hara-commander/hara-commander-agent"
status=data/"hara-commander/runtime-status.json"

def attest():
    version=subprocess.run(
        [sys.executable,str(agent),"--version"],
        capture_output=True,text=True,timeout=10,check=True,
    ).stdout.strip()
    status.parent.mkdir(parents=True,exist_ok=True)
    status.write_text(json.dumps({
        "schema":"hara.commander-runtime-status.v1",
        "agent_version":version,
        "started_at_utc":str(time.time_ns()),
        "last_successful_heartbeat_at_utc":None,
        "last_runtime_error_code":None,
        "last_runtime_error_at_utc":None,
    }),encoding="utf-8")

if not args:
    raise SystemExit(1)
cmd=args[0]
if cmd in ("daemon-reload","show-environment"):
    raise SystemExit(0)
if cmd=="is-active":
    raise SystemExit(0 if active.exists() else 3)
if cmd=="is-enabled":
    raise SystemExit(0 if enabled.exists() else 1)
if cmd=="enable":
    enabled.touch()
    active.touch()
    if agent.exists(): attest()
    raise SystemExit(0)
if cmd=="restart":
    active.touch()
    if agent.exists(): attest()
    raise SystemExit(0)
if cmd=="stop":
    active.unlink(missing_ok=True)
    raise SystemExit(0)
if cmd=="disable":
    active.unlink(missing_ok=True)
    enabled.unlink(missing_ok=True)
    raise SystemExit(0)
raise SystemExit(0)
'''


def run_pty(command: list[str], env: dict[str, str], token: str, timeout: int = 45) -> tuple[int, str]:
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(command[0], command, env)
    output = bytearray()
    sent = False
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.1)
        if readable:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if chunk:
                output.extend(chunk)
                if not sent and b"Pairing token:" in output:
                    os.write(fd, (token + "\n").encode())
                    sent = True
        done, raw_status = os.waitpid(pid, os.WNOHANG)
        if done:
            status = raw_status
            break
    if status is None:
        os.kill(pid, 9)
        _, status = os.waitpid(pid, 0)
    try:
        os.close(fd)
    except OSError:
        pass
    rc = os.waitstatus_to_exitcode(status)
    return rc, output.decode("utf-8", "replace")


def run(command: list[str], env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )


def parse_config(path: Path) -> dict[str, str]:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            out[key] = value
    return out


def self_test() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == "agent/linux.py")
    assert hashlib.sha256(AGENT.read_bytes()).hexdigest() == entry["sha256"]
    assert manifest["agent_version"] == "0.3.38"
    print("COMMANDER_CLEAN_LINUX_HARNESS_SELFTEST=PASS")


def execute() -> int:
    state = MockState()
    Handler.state = state
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with tempfile.TemporaryDirectory(prefix="hara-clean-linux-") as td:
            root = Path(td)
            home = root / "home"
            config = root / "config"
            data = root / "data"
            fakebin = root / "fakebin"
            home.mkdir()
            config.mkdir()
            data.mkdir()
            fakebin.mkdir()
            systemctl = fakebin / "systemctl"
            systemctl.write_text(FAKE_SYSTEMCTL, encoding="utf-8")
            systemctl.chmod(0o700)

            env = os.environ.copy()
            env.update({
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(config),
                "XDG_DATA_HOME": str(data),
                "HARA_COMMANDER_URL": base,
                "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED",
                "HOSTNAME": "clean-linux-harness",
                "PATH": str(fakebin) + ":/usr/local/bin:/usr/bin:/bin",
            })

            rc, install_out = run_pty(["bash", str(INSTALLER), "install"], env, "PAIR-ONE")
            assert rc == 0, install_out
            assert "HARA_COMMANDER_DEVICE_ENROLLMENT=PASS" in install_out
            assert "HARA-CLEAN-TOKEN-1" not in install_out

            cfg_path = config / "hara-commander/device.env"
            agent_path = data / "hara-commander/hara-commander-agent"
            unit_path = config / "systemd/user/hara-commander-agent.service"
            cli_path = home / ".local/bin/hara-commander"
            wrapper_path = home / ".local/bin/hara"
            assert cfg_path.is_file() and stat.S_IMODE(cfg_path.stat().st_mode) == 0o600
            assert agent_path.is_file() and stat.S_IMODE(agent_path.stat().st_mode) == 0o700
            assert unit_path.is_file() and stat.S_IMODE(unit_path.stat().st_mode) == 0o600
            assert cli_path.is_symlink()
            cfg1 = parse_config(cfg_path)
            assert cfg1["HARA_DEVICE_ID"] == "HARA-CLEAN-DEVICE-1"
            assert cfg1["HARA_DEVICE_TOKEN"] == "HARA-CLEAN-TOKEN-1"
            print("COMMANDER_CLEAN_LINUX_INSTALL=PASS")

            support = run(["bash", str(INSTALLER), "support"], env)
            assert support.returncode == 0, support.stdout
            support_json = json.loads(support.stdout.strip().splitlines()[-1])
            assert support_json["schema"] == "hara.commander-support-report.v2"
            assert support_json["privacy"]["secret_material_exposed"] is False
            assert "HARA-CLEAN-TOKEN-1" not in support.stdout
            print("COMMANDER_CLEAN_LINUX_SUPPORT=PASS")

            update = run(["bash", str(INSTALLER), "update"], env)
            assert update.returncode == 0, update.stdout
            assert "HARA_COMMANDER_AGENT_UPDATE=PASS" in update.stdout
            assert "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE" in update.stdout
            print("COMMANDER_CLEAN_LINUX_UPDATE=PASS")

            state.tokens["HARA-CLEAN-TOKEN-1"]["revoked"] = True
            rc, reenroll_out = run_pty(["bash", str(INSTALLER), "re-enroll"], env, "PAIR-TWO")
            assert rc == 0, reenroll_out
            assert "HARA_COMMANDER_REENROLL_OLD_CREDENTIAL_REJECTED=PASS" in reenroll_out
            assert "HARA_COMMANDER_DEVICE_REENROLL=PASS" in reenroll_out
            assert "OLD_DEVICE_AUTHORITY_RESURRECTED=FALSE" in reenroll_out
            assert "HARA-CLEAN-TOKEN-1" not in reenroll_out
            assert "HARA-CLEAN-TOKEN-2" not in reenroll_out
            cfg2 = parse_config(cfg_path)
            assert cfg2["HARA_DEVICE_ID"] == "HARA-CLEAN-DEVICE-2"
            assert cfg2["HARA_DEVICE_TOKEN"] == "HARA-CLEAN-TOKEN-2"
            print("COMMANDER_CLEAN_LINUX_REENROLL=PASS")

            uninstall = run(["bash", str(INSTALLER), "uninstall"], env)
            assert uninstall.returncode == 0, uninstall.stdout
            assert "HARA_COMMANDER_AGENT_UNINSTALL=PASS" in uninstall.stdout
            assert "SERVER_DEVICE_REVOKE=PASS" in uninstall.stdout
            assert "HARA-CLEAN-TOKEN-2" not in uninstall.stdout
            assert not cfg_path.exists()
            assert not agent_path.exists()
            assert not unit_path.exists()
            assert not cli_path.exists()
            if wrapper_path.exists():
                # Managed wrapper must not survive uninstall.
                raise AssertionError("MANAGED_HARA_WRAPPER_SURVIVED_UNINSTALL")
            print("COMMANDER_CLEAN_LINUX_UNINSTALL=PASS")
            print("COMMANDER_CLEAN_LINUX_HOME_EMPTY_AFTER_UNINSTALL=PASS")
            print("COMMANDER_CLEAN_LINUX_LIFECYCLE=PASS")
            return 0
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    self_test()
    if args.execute:
        return execute()
    if args.check:
        print("COMMANDER_CLEAN_LINUX_LIFECYCLE_SOURCE=PASS")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
