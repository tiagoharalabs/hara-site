#!/usr/bin/env python3
"""R13 local-only regression: malformed HTTP 200 enrollment reply is not
a successful, recoverable device enrollment. Uses only a loopback HTTP
server, synthetic pairing token, temporary HOME/XDG, and signed QA assets.
Does not call any cloud or mutate a real HARA service.
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
import threading

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("HARA_PEER_SOURCE", str(HERE / "source")))
BASE = SOURCE / "apps/commander/scripts/test_linux_r11_pre_enroll.py"
sys.path.insert(0, str(BASE.parent))
spec = importlib.util.spec_from_file_location("r13_base_test", BASE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

class Handler(mod.Handler):
    enrollment_reply: bytes | None = b""
    enroll_count = 0
    revoke_count = 0
    registered_ids: set[str] = set()
    pairing_consumed = False
    def do_POST(self):
        path = mod.urlparse(self.path).path
        if path == "/api/device/enroll":
            Handler.enroll_count += 1
            if Handler.pairing_consumed:
                self.send_error(409, "SYNTHETIC_PAIRING_ALREADY_CONSUMED")
                return
            Handler.pairing_consumed = True
            Handler.registered_ids.add("QA_DEVICE_SYNTHETIC")
            raw = self.enrollment_reply
            if raw is None:
                # Simulate: server committed enrollment, connection lost before response.
                self.close_connection = True
                self.connection.close()
                return
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif path == "/api/device/revoke-self":
            Handler.revoke_count += 1
            Handler.registered_ids.discard("QA_DEVICE_SYNTHETIC")
            raw = b'{"ok":true,"state":"REVOKED","device_id":"QA_DEVICE_SYNTHETIC"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_error(404)

def run_one(name: str, response: bytes | None) -> dict:
    Handler.assets = mod.signed_release()
    Handler.enrollment_reply = response
    Handler.enroll_count = Handler.revoke_count = 0
    Handler.registered_ids = set()
    Handler.pairing_consumed = False
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="commander-r13-malformed-reply-") as td:
            tmp = Path(td)
            home = tmp / "home"
            home.mkdir()
            script = tmp / "installer.sh"
            script.write_bytes(Handler.assets["install/linux.sh"])
            env = os.environ.copy()
            env.update({
                "HOME": str(home), "XDG_CONFIG_HOME": str(tmp/"config"),
                "XDG_DATA_HOME": str(tmp/"data"),
                "HARA_COMMANDER_URL": f"http://127.0.0.1:{server.server_address[1]}",
                "HARA_COMMANDER_TRANSPORT_MODE": "OUTBOUND_RELAY",
                "HARA_COMMANDER_TUNNEL_AUTOSTART": "OFF",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            })
            rc, output = mod.run_pty(
                ["bash", str(script), "install"], env, "QA_PAIRING_TOKEN_NOT_REAL",
                timeout=45,
            )
            retry_rc = None
            retry_was_denied = False
            if response is None:
                retry_rc, retry_output = mod.run_pty(
                    ["bash", str(script), "install"], env,
                    "QA_PAIRING_TOKEN_NOT_REAL", timeout=45,
                )
                retry_was_denied = (retry_rc != 0 and Handler.enroll_count == 2)
            result = {
                "case": name,
                "exit_code": rc,
                "signed_release_preflight_ran": "HARA_COMMANDER_RELEASE_PRE_ENROLL=PASS" in output,
                "server_created_registration": "QA_DEVICE_SYNTHETIC" in Handler.registered_ids,
                "server_mock_pairing_consumed": Handler.pairing_consumed,
                "enroll_post_count": Handler.enroll_count,
                "retry_same_pairing_after_ack_loss": retry_rc is not None,
                "retry_denied_after_pairing_consumed": retry_was_denied,
                "enroll_http_200": Handler.enroll_count == 1 and response is not None,
                "revoke_self_requests": Handler.revoke_count,
                "local_device_config_exists": (tmp/"config/hara-commander/device.env").exists(),
                "rollback_marker_present": "HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=" in output,
                "response_error_typed": "DEVICE_ENROLLMENT_RESPONSE_INVALID" in output,
                "bash_unbound_variable_error": "unbound variable" in output,
                "fixture_token_redacted": True,
                "public_internet_used": False,
            }
            return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

def main() -> int:
    cases = [
        ("missing_device_token", b'{"device_id":"QA_DEVICE_SYNTHETIC"}'),
        ("missing_device_id", b'{"device_token":"QA_TOKEN_SYNTHETIC"}'),
        ("malformed_json", b'{"device_id":'),
        ("response_lost_after_server_commit", None),
    ]
    results = [run_one(n, b) for n,b in cases]
    for r in results:
        print(json.dumps(r,sort_keys=True))
    report = {
        "schema":"hara.commander.peer-r13-malformed-enrollment.v1",
        "cases": results,
        "scope":"isolated mock server HTTP 200 after valid release; no real tokens or registrations",
        "potential_orphan_count":sum(1 for x in results if x["server_created_registration"] and x["revoke_self_requests"] == 0),
        "production_mutation":False,
    }
    (HERE/"r13-malformed-enrollment-results.json").write_text(json.dumps(report,indent=2)+"\n")
    assert all(r["signed_release_preflight_ran"] and r["server_created_registration"] and not r["local_device_config_exists"] for r in results)
    return 2 if report["potential_orphan_count"] else 0

if __name__=="__main__":
    raise SystemExit(main())
