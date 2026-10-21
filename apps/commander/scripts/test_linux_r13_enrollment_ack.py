#!/usr/bin/env python3
"""Signed QA release and synthetic localhost enrollment ACK failures only."""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import threading
from urllib.parse import urlparse

from test_linux_r11_pre_enroll import Handler as ReleaseHandler, run_pty, signed_release


class Handler(ReleaseHandler):
    scenario = ""
    enroll_count = 0
    legacy_enroll_count = 0
    client_tokens: list[str | None] = []

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/api/device/revoke-self":
            body = b'{"ok":true,"state":"REVOKED","device_id":"HARA-DEVICE-QA_SYNTHETIC"}'
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path == "/api/device/enroll":
            Handler.legacy_enroll_count += 1
            self.send_error(409)
            return
        if urlparse(self.path).path != "/api/device/enroll-intent":
            self.send_error(404)
            return
        if self.scenario == "legacy_server":
            self.send_error(404)
            return
        payload = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
        Handler.enroll_count += 1
        token = payload.get("client_device_token")
        Handler.client_tokens.append(token)
        if self.scenario == "lost_ack" and Handler.enroll_count == 1:
            self.close_connection = True
            self.connection.close()
            return
        if self.scenario == "lost_ack" and (not token or token != Handler.client_tokens[0]):
            self.send_error(409)
            return
        if self.scenario == "missing_token":
            body = b'{"device_id":"HARA-DEVICE-QA_SYNTHETIC"}'
        elif self.scenario == "missing_id":
            body = json.dumps({"device_token": token or "QA_OLD_TOKEN"}).encode()
        elif self.scenario == "malformed_json":
            body = b'{"device_id":'
        elif self.scenario == "invalid_id":
            body = json.dumps({"device_id": "QA_INVALID_ID", "device_token": token}).encode()
        else:
            body = json.dumps({"device_id": "HARA-DEVICE-QA_SYNTHETIC", "device_token": token}).encode()
        self.send_response(201)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_case(scenario: str) -> None:
    Handler.assets = signed_release()
    Handler.scenario = scenario
    Handler.enroll_count = 0
    Handler.legacy_enroll_count = 0
    Handler.client_tokens = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="commander-r13-ack-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            script = root / "installer.sh"
            script.write_bytes(Handler.assets["install/linux.sh"])
            env = os.environ.copy()
            env.update({
                "HOME": str(home), "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "HARA_COMMANDER_URL": f"http://127.0.0.1:{server.server_address[1]}",
                "HARA_COMMANDER_TRANSPORT_MODE": "INVALID_MODE",
                "HARA_COMMANDER_TUNNEL_AUTOSTART": "OFF",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            })
            exit_code, output = run_pty(["bash", str(script), "install"], env,
                                        "QA_PAIRING_TOKEN_NOT_REAL", timeout=50)
            assert exit_code != 0, scenario
            assert "ENROLLMENT_ACK_UNKNOWN" in output, scenario
            assert "unbound variable" not in output, scenario
            assert Handler.enroll_count == (0 if scenario == "legacy_server" else 1), scenario
            assert Handler.legacy_enroll_count == 0, scenario
            intent = root / "config/hara-commander/enrollment-intent.json"
            assert intent.is_file(), scenario
            assert stat.S_IMODE(intent.stat().st_mode) == 0o600, scenario
            if scenario != "legacy_server":
                assert Handler.client_tokens[0] and len(Handler.client_tokens[0]) == 64, scenario
            if scenario == "lost_ack":
                pending = subprocess.run(["bash", str(script), "uninstall"], env=env,
                                         capture_output=True, text=True, timeout=20)
                assert pending.returncode == 12, pending.stdout + pending.stderr
                assert "HARA_COMMANDER_AGENT_UNINSTALL=LOCAL_ONLY" in pending.stdout
                assert "SERVER_DEVICE_REVOKE_PENDING=TRUE" in pending.stdout
                assert intent.is_file(), "uninstall must preserve recovery credential"
                wrong_exit, wrong_output = run_pty(
                    ["bash", str(script), "install"], env,
                    "QA_DIFFERENT_PAIRING_TOKEN", timeout=50,
                )
                assert wrong_exit != 0 and "ENROLLMENT_INTENT_PAIRING_MISMATCH" in wrong_output, (
                    wrong_exit, re.sub(r"[A-Za-z0-9_-]{60,}", "[REDACTED]", wrong_output))
                assert Handler.enroll_count == 1, scenario
                retry_exit, retry_output = run_pty(
                    ["bash", str(script), "install"], env,
                    "QA_PAIRING_TOKEN_NOT_REAL", timeout=50,
                )
                assert retry_exit != 0, scenario  # invalid transport stops before systemd
                assert "DEVICE_TRANSPORT_MODE_INVALID" in retry_output, (
                    scenario, re.sub(r"[A-Za-z0-9_-]{60,}", "[REDACTED]", retry_output))
                assert Handler.enroll_count == 2, scenario
                assert Handler.client_tokens[1] == Handler.client_tokens[0], scenario
            print(f"COMMANDER_R13_LINUX_{scenario.upper()}=PASS")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    for scenario in ("missing_token", "missing_id", "malformed_json", "invalid_id",
                     "lost_ack", "legacy_server"):
        run_case(scenario)


if __name__ == "__main__":
    main()
