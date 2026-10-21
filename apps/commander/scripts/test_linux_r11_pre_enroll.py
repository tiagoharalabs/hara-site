#!/usr/bin/env python3
"""Exercise release validation before Linux enrollment on a local mock only."""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from commander_linux_clean_lifecycle import run_pty

APP = Path(__file__).resolve().parents[1]
CANDIDATE = APP / "candidate/linux_install_043.sh"
OLD = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect/install/linux.sh"
BUNDLE = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect"
FILES = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")


def b64int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def signed_release(*, wrong_kid: bool = False, corrupt: str | None = None,
                   wrong_agent_version: bool = False) -> dict[str, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    script = CANDIDATE.read_text(encoding="utf-8")
    script, count = re.subn(r'RELEASE_SIGNING_N="[^"]+"',
                            'RELEASE_SIGNING_N="' + b64int(pub.n) + '"', script)
    assert count == 1
    script, count = re.subn(r'RELEASE_SIGNING_E="[^"]+"',
                            'RELEASE_SIGNING_E="' + b64int(pub.e) + '"', script)
    assert count == 1
    assets = {name: (BUNDLE / name).read_bytes() for name in FILES}
    assets["agent/linux.py"] = (APP / "public/agent/linux.py").read_bytes()
    if wrong_agent_version:
        needle = b'AGENT_VERSION = "0.3.43"'
        assert assets["agent/linux.py"].count(needle) == 1
        assets["agent/linux.py"] = assets["agent/linux.py"].replace(needle, b'AGENT_VERSION = "0.3.44"')
    assets["install/linux.sh"] = script.encode()
    manifest = json.loads((BUNDLE / "release/agent-manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = [
        {"path": name, "bytes": len(assets[name]),
         "sha256": hashlib.sha256(assets[name]).hexdigest()}
        for name in FILES
    ]
    raw = (json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n").encode()
    signature = key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
    signed = {
        "schema": "hara.commander-release-signature.v1", "alg": "RS256",
        "kid": "commander-release-v1" if wrong_kid else "commander-release-v2",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }
    assets["release/agent-manifest.json"] = raw
    assets["release/agent-manifest.sig.json"] = (json.dumps(signed) + "\n").encode()
    if corrupt:
        assets[corrupt] += b"\n# changed after signing\n"
    return assets


class Handler(http.server.BaseHTTPRequestHandler):
    assets: dict[str, bytes]
    enroll_count = 0

    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        name = urlparse(self.path).path.lstrip("/")
        raw = self.assets.get(name)
        if raw is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        if urlparse(self.path).path in ("/api/device/enroll", "/api/device/enroll-intent"):
            Handler.enroll_count += 1
            self.send_error(503)
            return
        self.send_error(404)


def run_case(name: str, assets: dict[str, bytes], expected: str,
             *, reach_enroll: bool = False, historical: bool = False) -> None:
    Handler.assets = assets
    Handler.enroll_count = 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="commander-r11-pre-enroll-") as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            installer = root / "installer.sh"
            installer.write_bytes(OLD.read_bytes() if historical else assets["install/linux.sh"])
            env = os.environ.copy()
            env.update({
                "HOME": str(home), "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "HARA_COMMANDER_URL": f"http://127.0.0.1:{server.server_address[1]}",
                "HARA_COMMANDER_TRANSPORT_MODE": "OUTBOUND_RELAY",
                "HARA_COMMANDER_TUNNEL_AUTOSTART": "OFF", "PATH": "/usr/local/bin:/usr/bin:/bin",
            })
            exit_code, output = run_pty(["bash", str(installer), "install"], env, "PAIR-LOCAL", timeout=50)
            assert exit_code != 0, (name, output)
            assert expected in output, (name, output)
            assert Handler.enroll_count == int(reach_enroll), (name, Handler.enroll_count, output)
            assert not (root / "config/hara-commander/device.env").exists(), name
            print(f"COMMANDER_R11_{name}=PASS enroll_posts={Handler.enroll_count} exit={exit_code}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    run_case("OLD_ORDER_CONTROL", signed_release(wrong_kid=True),
             "Pairing token:", reach_enroll=True, historical=True)
    run_case("KID_MISMATCH_BEFORE_ENROLL", signed_release(wrong_kid=True),
             "RELEASE_SIGNATURE_KID_MISMATCH")
    run_case("LINUX_DIGEST_BEFORE_ENROLL", signed_release(corrupt="agent/linux.py"),
             "RELEASE_ASSET_DIGEST_MISMATCH")
    run_case("WINDOWS_DIGEST_BEFORE_ENROLL", signed_release(corrupt="agent/windows.ps1"),
             "RELEASE_ASSET_DIGEST_MISMATCH")
    run_case("VERSION_BEFORE_ENROLL", signed_release(wrong_agent_version=True),
             "AGENT_VERSION_MANIFEST_MISMATCH")
    run_case("VALID_RELEASE_REACHES_MOCK_ENROLL", signed_release(),
             "curl: (22)", reach_enroll=True)
    print("COMMANDER_R11_PRE_ENROLL_CASES=6")


if __name__ == "__main__":
    main()
