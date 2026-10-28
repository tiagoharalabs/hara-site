#!/usr/bin/env python3
"""Source candidate: explicit connection, enrollment, and signed auto-update.

This controller is not a signed release asset. Native deployment and public
distribution require separate admission. No password or token is logged.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

KID = "commander-release-v2"
MODULUS = "p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43"
EXPONENT = "AQAB"
PATHS = ["agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1"]
PAIR_MARKER = b"# HARA_COMMANDER_PAIR_EXISTING=1"
SERVICE = "hara-commander-agent.service"


class Hold(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Hold(code)


def version(value: str) -> tuple[int, int, int]:
    need(bool(re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)), "INVALID_AGENT_VERSION")
    return tuple(int(x) for x in value.split("."))


def origin(value: str) -> str:
    p = urllib.parse.urlsplit(value)
    need(p.scheme == "https" and bool(p.hostname) and p.username is None and p.password is None
         and p.path in ("", "/") and not p.query and not p.fragment, "COMMANDER_ORIGIN_INVALID")
    return value.rstrip("/")


def unique_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise Hold("JSON_INVALID") from exc


def b64ud(value: str) -> bytes:
    need(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", value)), "RELEASE_SIGNATURE_ENCODING_INVALID")
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def verify_manifest(raw: bytes, signature: bytes) -> dict:
    sig = unique_json(signature)
    need(isinstance(sig, dict) and sig.get("schema") == "hara.commander-release-signature.v1"
         and sig.get("alg") == "RS256" and sig.get("kid") == KID, "RELEASE_SIGNATURE_INVALID")
    need(sig.get("manifest_sha256") == hashlib.sha256(raw).hexdigest(), "RELEASE_MANIFEST_HASH_MISMATCH")
    n = int.from_bytes(b64ud(MODULUS), "big")
    e = int.from_bytes(b64ud(EXPONENT), "big")
    signed = b64ud(sig.get("signature", ""))
    size = (n.bit_length() + 7) // 8
    need(len(signed) == size and int.from_bytes(signed, "big") < n, "RELEASE_SIGNATURE_INVALID")
    actual = pow(int.from_bytes(signed, "big"), e, n).to_bytes(size, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(raw).digest()
    padding = size - len(digest_info) - 3
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
    need(padding >= 8 and hmac.compare_digest(actual, expected), "RELEASE_SIGNATURE_INVALID")
    obj = unique_json(raw)
    need(isinstance(obj, dict) and set(obj) == {"schema", "product", "channel", "agent_version", "files"}
         and obj.get("schema") == "hara.commander-agent-release.v1"
         and obj.get("product") == "H.A.R.A. Commander" and obj.get("channel") == "stable", "RELEASE_MANIFEST_INVALID")
    need(isinstance(obj.get("agent_version"), str), "RELEASE_MANIFEST_INVALID")
    need(version(obj["agent_version"]) >= (0, 3, 54), "RELEASE_BELOW_LINUX_FLOOR")
    rows = obj.get("files")
    need(isinstance(rows, list) and len(rows) == 4 and all(isinstance(r, dict) for r in rows)
         and [r.get("path") for r in rows] == PATHS, "RELEASE_FILESET_INVALID")
    for row in rows:
        need(set(row) == {"path", "bytes", "sha256"} and type(row["bytes"]) is int
             and 0 < row["bytes"] <= 2 * 1024 * 1024 and isinstance(row["sha256"], str)
             and bool(re.fullmatch(r"[0-9a-f]{64}", row["sha256"])), "RELEASE_MANIFEST_INVALID")
    return obj


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Http:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self, url: str, *, payload=None, token=None, limit=2 * 1024 * 1024):
        headers = {"Accept": "application/json", "User-Agent": "HARA-Commander-Connect/1"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode()
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise Hold("CONNECTION_UNAVAILABLE") from exc
        with response:
            raw = response.read(limit + 1)
            need(len(raw) <= limit, "HTTP_RESPONSE_TOO_LARGE")
            return response.code, raw

    def get(self, url: str, limit=2 * 1024 * 1024) -> bytes:
        status, raw = self.request(url, limit=limit)
        need(status == 200, "RELEASE_DOWNLOAD_HTTP_" + str(status))
        return raw


def owned_regular(path: Path, *, private=False) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), "LOCAL_FILE_OWNERSHIP_INVALID")
    need(not info.st_mode & 0o022, "LOCAL_FILE_WRITABLE_BY_OTHERS")
    if private:
        need(not info.st_mode & 0o077, "DEVICE_CONFIG_NOT_PRIVATE")
    return True


def read_config(path: Path) -> dict | None:
    if not owned_regular(path, private=True):
        return None
    raw = path.read_bytes()
    need(len(raw) <= 16384, "DEVICE_CONFIG_TOO_LARGE")
    values = {}
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            need("=" in line, "DEVICE_CONFIG_INVALID")
            key, value = line.split("=", 1)
            need(key not in values, "DEVICE_CONFIG_DUPLICATE_KEY")
            values[key] = value
    except UnicodeError as exc:
        raise Hold("DEVICE_CONFIG_INVALID") from exc
    need(all(values.get(k) for k in ("HARA_COMMANDER_URL", "HARA_DEVICE_ID", "HARA_DEVICE_TOKEN")), "DEVICE_CONFIG_INCOMPLETE")
    origin(values["HARA_COMMANDER_URL"])
    return values


def installed_version(path: Path) -> str | None:
    if not owned_regular(path):
        return None
    raw = path.read_bytes()
    need(len(raw) <= 2 * 1024 * 1024, "INSTALLED_AGENT_TOO_LARGE")
    matches = re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', raw, re.M)
    need(len(matches) == 1, "INSTALLED_AGENT_VERSION_INVALID")
    value = matches[0].decode("ascii")
    version(value)
    return value


def enrollment_state(http: Http, config: dict | None, current: str | None) -> str:
    if config is None:
        return "UNPAIRED"
    need(current is not None, "PAIRED_AGENT_MISSING")
    status, raw = http.request(origin(config["HARA_COMMANDER_URL"]) + "/api/device/heartbeat", payload={
        "device_id": config["HARA_DEVICE_ID"], "architecture": config.get("HARA_DEVICE_ARCH", ""),
        "agent_version": current, "approval_mode": config.get("HARA_COMMANDER_APPROVAL_MODE", "ASK_EVERY_ACTION"),
    }, token=config["HARA_DEVICE_TOKEN"], limit=65536)
    obj = unique_json(raw)
    need(isinstance(obj, dict), "ENROLLMENT_VALIDATION_AMBIGUOUS")
    if status == 200 and obj.get("ok") is True and obj.get("device_id") == config["HARA_DEVICE_ID"]:
        return "PAIRED"
    if status == 401 and obj.get("code") == "DEVICE_AUTH_INVALID":
        return "REJECTED"
    raise Hold("ENROLLMENT_VALIDATION_AMBIGUOUS")


def decide(state: str, current: str | None, offered: str, pair_existing_supported: bool) -> tuple[str | None, bool]:
    newer = current is None or version(offered) > version(current)
    if current is not None:
        need(version(offered) >= version(current), "AUTO_DOWNGRADE_REFUSED")
    if state == "PAIRED":
        return ("update" if newer else None), False
    if state == "REJECTED":
        return "re-enroll", newer
    need(state == "UNPAIRED", "ENROLLMENT_STATE_INVALID")
    if current is not None:
        need(pair_existing_supported, "SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED")
        return "pair-existing", newer
    return "install", False


class Release:
    def __init__(self, http: Http, base: str, selected_url: str | None = None, current: str | None = None):
        self.http = http
        self.base = base
        # An explicit QA release selection is not an update channel. It remains
        # same-origin, versioned, signed, and never opts out of TLS validation.
        if selected_url:
            parsed = urllib.parse.urlsplit(selected_url)
            need(parsed.scheme == "https" and origin(parsed.scheme + "://" + parsed.netloc) == base
                 and re.fullmatch(r"/releases/\d+\.\d+\.\d+", parsed.path)
                 and not parsed.query and not parsed.fragment, "QA_RELEASE_SELECTION_INVALID")
            latest_base = selected_url.rstrip("/")
        else:
            latest_base = base
        latest = http.get(latest_base + "/release/agent-manifest.json", 16384)
        latest_sig = http.get(latest_base + "/release/agent-manifest.sig.json", 16384)
        self.manifest = verify_manifest(latest, latest_sig)
        self.version = self.manifest["agent_version"]
        if current is not None:
            need(version(self.version) >= version(current), "AUTO_DOWNGRADE_REFUSED")
        self.url = base + "/releases/" + self.version
        immutable = http.get(self.url + "/release/agent-manifest.json", 16384)
        immutable_sig = http.get(self.url + "/release/agent-manifest.sig.json", 16384)
        verify_manifest(immutable, immutable_sig)
        need(immutable == latest, "LATEST_IMMUTABLE_MANIFEST_MISMATCH")
        self.agent = self.payload("agent/linux.py")
        self.installer = self.payload("install/linux.sh")
        matches = re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', self.agent, re.M)
        need(matches == [self.version.encode()], "AGENT_RELEASE_VERSION_MISMATCH")
        self.pair_existing_supported = PAIR_MARKER in self.installer.splitlines()

    def payload(self, name: str) -> bytes:
        row = next(row for row in self.manifest["files"] if row["path"] == name)
        raw = self.http.get(self.url + "/" + name, row["bytes"])
        need(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "RELEASE_PAYLOAD_MISMATCH")
        return raw

    def verify_old_agent(self, path: Path, current: str) -> None:
        old_base = self.base + "/releases/" + current
        raw = self.http.get(old_base + "/release/agent-manifest.json", 16384)
        signature = self.http.get(old_base + "/release/agent-manifest.sig.json", 16384)
        metadata = verify_manifest(raw, signature)
        need(metadata["agent_version"] == current, "INSTALLED_AGENT_RELEASE_MISMATCH")
        expected = metadata["files"][0]
        actual = path.read_bytes()
        need(len(actual) == expected["bytes"] and hashlib.sha256(actual).hexdigest() == expected["sha256"], "INSTALLED_AGENT_INTEGRITY_FAILED")


class Connect:
    def __init__(self, http=None):
        self.http = http or Http()
        self.home = Path.home()
        self.config_root = Path(os.environ.get("XDG_CONFIG_HOME", self.home / ".config"))
        self.data_root = Path(os.environ.get("XDG_DATA_HOME", self.home / ".local/share"))
        self.config_file = self.config_root / "hara-commander/device.env"
        self.agent = self.data_root / "hara-commander/hara-commander-agent"
        self.status = self.data_root / "hara-commander/runtime-status.json"
        self.unit = self.config_root / "systemd/user" / SERVICE
        self.report = {"state": "PENDING", "pairing_validated": False, "phase": "VALIDATE_PAIRING", "token_exposed": False}

    def invoke_installer(self, path: Path, action: str, base: str, release: Release) -> None:
        environment = os.environ.copy()
        environment["HARA_COMMANDER_URL"] = base
        environment["HARA_COMMANDER_RELEASE_URL"] = release.url
        # Inherit the controlling terminal for the signed installer's hidden
        # token prompt. The controller never places the token in argv or logs.
        result = subprocess.run(["bash", str(path), action], env=environment)
        need(result.returncode == 0, "SIGNED_INSTALLER_ACTION_FAILED")

    def require_terminal(self) -> None:
        try:
            terminal = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
            os.close(terminal)
        except OSError as exc:
            raise Hold("PAIRING_REQUIRES_LOCAL_TERMINAL") from exc

    def invoke_and_recheck_failure(self, path: Path, action: str, base: str, release: Release) -> None:
        validated_before = self.report.get("pairing_validated", False)
        prior_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if validated_before else None
        self.report["pairing_validated"] = False
        try:
            self.invoke_installer(path, action, base, release)
        except Hold:
            # A failed update may have rolled back successfully. Revalidate the
            # same credential before reporting that its pairing still works.
            if validated_before:
                try:
                    config = read_config(self.config_file)
                    unchanged = hashlib.sha256(self.config_file.read_bytes()).hexdigest() == prior_sha
                    current = installed_version(self.agent)
                    if unchanged and enrollment_state(self.http, config, current) == "PAIRED":
                        self.report.update(pairing_validated=True, agent_version=current)
                except (Hold, OSError, ValueError):
                    pass
            raise

    def start_and_verify(self, expected: str, device_id: str) -> None:
        need(owned_regular(self.unit), "AGENT_SERVICE_MISSING")
        was_active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE]).returncode == 0
        started_after = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
        completed = subprocess.run(["systemctl", "--user", "start", SERVICE], capture_output=True)
        need(completed.returncode == 0, "AGENT_SERVICE_START_FAILED")
        # A connection command deliberately starts the service; it never enables
        # login/boot autostart. Current local approval mode is preserved.
        floor = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=90) if was_active else started_after
        for _ in range(45):
            try:
                if owned_regular(self.status):
                    obj = unique_json(self.status.read_bytes())
                    last = dt.datetime.fromisoformat(str(obj.get("last_successful_heartbeat_at_utc", "")).replace("Z", "+00:00"))
                    started = dt.datetime.fromisoformat(str(obj.get("started_at_utc", "")).replace("Z", "+00:00"))
                    device_matches = obj.get("device_id", device_id) == device_id
                    if obj.get("agent_version") == expected and last >= floor and device_matches and (was_active or started >= started_after):
                        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE])
                        if active.returncode == 0:
                            return
            except (ValueError, Hold):
                pass
            time.sleep(1)
        raise Hold("FRESH_AGENT_HEARTBEAT_NOT_CONFIRMED")

    def run(self, selected_url=None) -> dict:
        need(os.geteuid() != 0, "RUN_AS_DESKTOP_USER")
        # Explicit desktop connect may be invoked through SSH with an existing
        # user bus; no new login session or global system service is created.
        runtime = Path("/run/user") / str(os.getuid())
        if runtime.is_dir():
            os.environ.setdefault("XDG_RUNTIME_DIR", str(runtime))
            if (runtime / "bus").exists():
                os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=" + str(runtime / "bus"))
        config = read_config(self.config_file)
        config_before = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if config else None
        current = installed_version(self.agent)
        state = enrollment_state(self.http, config, current)
        base = origin(config["HARA_COMMANDER_URL"] if config else os.environ.get("HARA_COMMANDER_URL", "https://commander.haralabs.com.br"))
        self.report.update(initial_state=state, initial_pairing_validated=state == "PAIRED", pairing_validated=state == "PAIRED", agent_version=current,
                           commander_url=base, phase="CHECK_UPDATE")
        print("Validando a conexao e a versao assinada do Commander...", flush=True)
        release = Release(self.http, base, selected_url, current)
        action, update_after_pair = decide(state, current, release.version, release.pair_existing_supported)
        if current is not None:
            release.verify_old_agent(self.agent, current)
        if action in ("install", "pair-existing", "re-enroll"):
            self.require_terminal()
            print("Abra " + base + "/auth/login, entre na sua conta e gere um codigo de pareamento.", flush=True)
            print("Digite somente esse codigo quando o instalador solicitar. A senha fica no site.", flush=True)
        else:
            print("Maquina ja pareada; o vinculo existente sera preservado.", flush=True)
        with tempfile.TemporaryDirectory(prefix="hara-connect-") as directory:
            installer = Path(directory) / "linux.sh"
            installer.write_bytes(release.installer)
            os.chmod(installer, 0o700)
            if action:
                self.report["phase"] = "PAIRING" if action != "update" else "UPDATE"
                self.invoke_and_recheck_failure(installer, action, base, release)
            after = read_config(self.config_file)
            actual = installed_version(self.agent)
            if state == "PAIRED":
                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_before, "EXISTING_ENROLLMENT_CHANGED")
            need(enrollment_state(self.http, after, actual) == "PAIRED", "PAIRING_NOT_CONFIRMED")
            self.report.update(pairing_validated=True, agent_version=actual, device_id=after["HARA_DEVICE_ID"])
            if update_after_pair:
                self.report["phase"] = "UPDATE"
                post_pair_config_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest()
                self.invoke_and_recheck_failure(installer, "update", base, release)
                after = read_config(self.config_file)
                actual = installed_version(self.agent)
                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == post_pair_config_sha, "POST_PAIR_ENROLLMENT_CHANGED")
                need(enrollment_state(self.http, after, actual) == "PAIRED", "POST_UPDATE_PAIRING_NOT_CONFIRMED")
                self.report.update(pairing_validated=True, agent_version=actual)
            need(actual == release.version, "AGENT_UPDATE_NOT_CONFIRMED")
            release.verify_old_agent(self.agent, actual)
            self.report["phase"] = "START_AND_VERIFY_RUNTIME"
            config_after_actions = hashlib.sha256(self.config_file.read_bytes()).hexdigest()
            self.start_and_verify(actual, after["HARA_DEVICE_ID"])
            final = read_config(self.config_file)
            need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_after_actions,
                 "ENROLLMENT_CHANGED_DURING_START")
            need(enrollment_state(self.http, final, actual) == "PAIRED", "FINAL_CONNECTION_NOT_CONFIRMED")
        return {"state": "CONNECTED", "agent_version": actual, "initial_state": state,
                "action": action or "already-current", "updated_after_pair": update_after_pair,
                "commander_url": base, "device_id": after["HARA_DEVICE_ID"], "token_exposed": False}


@contextlib.contextmanager
def connection_lock():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid())))
    info = runtime.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
         "PRIVATE_USER_RUNTIME_REQUIRED")
    path = runtime / "hara-commander-connect.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
             "CONNECT_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold("CONNECTION_ALREADY_IN_PROGRESS") from exc
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description="Conectar, parear quando necessario e atualizar o HARA Commander.")
    parser.add_argument("action", nargs="?", default="connect", choices=("connect", "conectar"))
    parser.add_argument("--qa-release-url", help="Selecao QA assinada, versionada e na mesma origem; nao substitui o canal publico.")
    args = parser.parse_args()
    flow = Connect()
    try:
        with connection_lock():
            report = flow.run(args.qa_release_url)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Hold as exc:
        report = dict(flow.report)
        report.update(state="HOLD", error_code=exc.code)
        if report.get("pairing_validated") and report.get("phase") in ("CHECK_UPDATE", "UPDATE"):
            report["state"] = "PAIRING_VALID_UPDATE_HOLD"
            print("Pareamento validado; atualizacao pendente: " + exc.code, file=sys.stderr)
        else:
            print("Commander nao concluiu a conexao: " + exc.code, file=sys.stderr)
        print(json.dumps(report, sort_keys=True))
        return 2
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        # Do not copy arbitrary exception text containing request/auth data.
        print("Commander nao concluiu a conexao: CONNECT_OPERATION_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
