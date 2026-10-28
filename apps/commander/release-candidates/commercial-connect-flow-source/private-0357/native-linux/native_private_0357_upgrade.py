#!/usr/bin/env python3
"""One pinned, direct .56 -> .57 Ubuntu QA update; never an enrollment flow.

Run as the existing commanderqa UID 2000. The owning root operator verifies the
QGA domain separately. This driver never changes system trust, config, service
definitions, or credentials itself. The verified installer owns update/rollback.
Only sanitized receipts leave its private working directory.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import ssl
import stat
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request

QA_UID = 2000
QA_ACCOUNT = "commanderqa"
QA_HOME = Path("/home/commanderqa")
HELPER = QA_HOME / ".local/share/hara-commander-connect-qa"
CONTROLLER = HELPER / "commander_connect.py"
CONTROLLER_SHA = "a696a233e81b1b89b536fd4097af7b571762c953e54266cba49349308db74c1d"
WORK = HELPER / "upgrade-0357"
CERT = HELPER / "qa-release-0357.crt"
CERT_SHA = "c15308e100ba014d463b20cc56568e2183c4c50e2b2b672af38a0926d1c879c1"
CERT_DER_SHA = "893aeec40a123d5fd74fd312fa1ed90e4c9881e10a562cdc126026c3d848f29e"
CONFIG = QA_HOME / ".config/hara-commander/device.env"
AGENT = QA_HOME / ".local/share/hara-commander/hara-commander-agent"
UNIT = QA_HOME / ".config/systemd/user/hara-commander-agent.service"
CLI = QA_HOME / ".local/bin/hara-commander"
HARA_CLI = QA_HOME / ".local/bin/hara"
RUNTIME = AGENT.parent / "runtime-status.json"
SERVICE = "hara-commander-agent.service"
DEVICE = "HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889"
ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
RELEASE = "https://192.168.10.23:18444/releases/0.3.57"
CLOSES = dt.datetime(2026, 10, 28, 18, 40, tzinfo=dt.timezone.utc)
OLD_AGENT_SHA = "ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d"
NEW_AGENT_SHA = "79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13"
NEW_AGENT_BYTES = 265620
INSTALLER_SHA = "2b11dd4cb5219d64692d9df764544752c04f4cb2518742d5c54a3f631178cbed"
INSTALLER_BYTES = 72524
MANIFEST_SHA = "d1a9361f5edec6c926d6febc7990e9b0c00df28f5131c6ffe1146ebe348554d0"
SIGNATURE_SHA = "5637d5861c49c170af55a8d86f8051df78785c39f4a17b06a41b5c8ed25ddef7"
SYSTEM_CA = Path("/etc/ssl/certs/ca-certificates.crt")
PREFLIGHT_WINDOW_SECONDS = 280
CHILD_LONG_RUNNING_SECONDS = 180
POST_UPDATE_OBSERVATION_SECONDS = 90
MAX_LOG_BYTES = 2 * 1024 * 1024


class Hold(Exception):
    pass


def need(ok, code):
    if not ok:
        raise Hold(code)


def now():
    return dt.datetime.now(dt.timezone.utc)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_uid, info.st_gid, info.st_mode, info.st_nlink)


def path_parents(path):
    for parent in reversed(path.parents):
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode), "PARENT_SYMLINK_OR_NOT_DIRECTORY")
        need(info.st_uid in (0, QA_UID) and not info.st_mode & 0o022, "PARENT_OWNERSHIP_OR_WRITE_MODE")


def read_owned(path, maximum, *, private=False, root_ok=False):
    path_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        owners = (0, QA_UID) if root_ok else (QA_UID,)
        need(stat.S_ISREG(before.st_mode) and before.st_uid in owners and before.st_nlink == 1,
             "EXPECTED_OWNED_REGULAR_FILE")
        need(not before.st_mode & 0o022 and (not private or not before.st_mode & 0o077), "FILE_MODE_REFUSED")
        need(0 < before.st_size <= maximum, "FILE_SIZE_REFUSED")
        raw = b""
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part:
                break
            raw += part
        need(len(raw) == before.st_size and identity(os.fstat(fd)) == identity(before)
             and identity(path.lstat()) == identity(before), "FILE_CHANGED_DURING_READ")
        return raw, {"sha256": digest(raw), "bytes": len(raw), "uid": before.st_uid,
                     "gid": before.st_gid, "mode": oct(stat.S_IMODE(before.st_mode))}
    finally:
        os.close(fd)


def file_fingerprint(path, *, optional=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        need(optional, "EXPECTED_FILE_MISSING")
        return {"present": False}
    path_parents(path)
    need(info.st_uid == QA_UID, "CLI_OWNER_MISMATCH")
    if stat.S_ISLNK(info.st_mode):
        return {"present": True, "kind": "symlink", "target": os.readlink(path),
                "uid": info.st_uid, "gid": info.st_gid}
    raw, meta = read_owned(path, 2 * 1024 * 1024)
    return {"present": True, "kind": "file", **meta}


def write_new(path, raw):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def write_report(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    pending = path.with_name(path.name + ".pending")
    write_new(pending, raw)
    os.replace(pending, path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Upgrade:
    def __init__(self):
        self.deadline = time.monotonic() + PREFLIGHT_WINDOW_SECONDS
        self.env = os.environ.copy()
        self.env.update({"XDG_RUNTIME_DIR": "/run/user/2000",
                         "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/2000/bus"})
        self.report = {"schema": "hara.commander.linux-private-0357-upgrade.v1",
                       "started_utc": now().isoformat(), "state": "HOLD", "stage": "IDENTITY",
                       "artifact_source": "EXPLICIT_PRIVATE_SIGNED_RELEASE", "release_url": RELEASE,
                       "credential_origin": ORIGIN, "device_id": DEVICE,
                       "pairing_permitted": False, "public_distribution_changed": False,
                       "automatic_controller_discovery_certified": False,
                       "system_trust_changed": False, "token_exposed": False,
                       "driver_performed_rollback": False}
        self.config_before = None
        self.unit_before = None
        self.agent_before = None
        self.before = None
        self.work_created = False
        self.child = None
        self.control = None
        self.context = None

    def remaining(self, maximum):
        remaining = self.deadline - time.monotonic()
        need(remaining > 0, "NATIVE_DRIVER_DEADLINE_EXCEEDED")
        return min(maximum, remaining)

    def checkpoint(self, stage):
        self.report.update(stage=stage, progress_utc=now().isoformat())
        if self.work_created:
            write_report(WORK / "progress.json", self.report)

    def command(self, args, *, maximum=10):
        try:
            result = subprocess.run(args, env=self.env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=self.remaining(maximum))
        except subprocess.TimeoutExpired as exc:
            raise Hold("NATIVE_OBSERVATION_TIMEOUT") from exc
        need(len(result.stdout) <= 65536 and len(result.stderr) <= 65536, "OBSERVATION_OUTPUT_TOO_LARGE")
        return result

    def service(self):
        names = ("LoadState", "ActiveState", "SubState", "UnitFileState", "FragmentPath", "DropInPaths", "Type", "ExecStart", "MainPID")
        command = ["/usr/bin/systemctl", "--user", "show", SERVICE]
        command += ["--property=" + name for name in names]
        result = self.command(command)
        need(result.returncode == 0, "SERVICE_OBSERVATION_FAILED")
        values = {}
        for row in result.stdout.decode("utf-8").splitlines():
            key, value = row.split("=", 1)
            need(key in names and key not in values, "SERVICE_OBSERVATION_INVALID")
            values[key] = value
        need(set(values) == set(names), "SERVICE_OBSERVATION_INCOMPLETE")
        need(values["LoadState"] == "loaded" and values["FragmentPath"] == str(UNIT)
             and not values["DropInPaths"] and values["Type"] == "simple", "EFFECTIVE_SERVICE_DEFINITION_MISMATCH")
        parts = [part.strip() for part in values["ExecStart"].split(";")]
        need(len(parts) >= 3 and parts[0] == "{ path=" + str(AGENT) and parts[1] == "argv[]=" + str(AGENT)
             and values["ExecStart"].count("{ path=") == 1, "EFFECTIVE_SERVICE_EXECUTABLE_MISMATCH")
        return values

    def config(self):
        raw, meta = read_owned(CONFIG, 16384, private=True)
        values = {}
        for line in raw.decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            need("=" in line, "CONFIG_FORMAT_INVALID")
            key, value = line.split("=", 1)
            need(key not in values, "CONFIG_DUPLICATE_KEY")
            values[key] = value
        need(values.get("HARA_COMMANDER_URL") == ORIGIN and values.get("HARA_DEVICE_ID") == DEVICE,
             "EXPECTED_DEV_DEVICE_BINDING_REQUIRED")
        need(values.get("HARA_DEVICE_TOKEN") and values.get("HARA_COMMANDER_APPROVAL_MODE") == "PERSISTENT_TRUSTED"
             and values.get("HARA_COMMANDER_TRANSPORT_MODE") == "OUTBOUND_RELAY", "EXPECTED_DEVICE_POLICY_REQUIRED")
        return raw, meta, values

    def heartbeat(self, config, agent_version):
        # This separate opener trusts only the ordinary OS roots. The private
        # artifact CA and its origin never receive the existing device token.
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(SYSTEM_CA))))
        payload = {"device_id": DEVICE, "architecture": config.get("HARA_DEVICE_ARCH", ""),
                   "agent_version": agent_version, "approval_mode": config["HARA_COMMANDER_APPROVAL_MODE"]}
        request = urllib.request.Request(ORIGIN + "/api/device/heartbeat", data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Accept": "application/json",
                                                  "User-Agent": "HARA-QA-Private-0357-Upgrade/1",
                                                  "Authorization": "Bearer " + config["HARA_DEVICE_TOKEN"]})
        try:
            with opener.open(request, timeout=self.remaining(15)) as response:
                raw = response.read(65537)
                need(response.status == 200 and len(raw) <= 65536, "AUTHENTICATED_HEARTBEAT_REJECTED")
                obj = json.loads(raw)
                need(obj.get("ok") is True and obj.get("device_id") == DEVICE, "AUTHENTICATED_HEARTBEAT_INVALID")
                return {"http_status": 200, "ok": True, "device_matches": True, "agent_version_reported": agent_version}
        except Hold:
            raise
        except Exception as exc:
            raise Hold("AUTHENTICATED_HEARTBEAT_UNCONFIRMED") from exc

    def runtime(self):
        raw, _ = read_owned(RUNTIME, 262144)
        obj = json.loads(raw)
        result = {name: obj.get(name) for name in ("agent_version", "started_at_utc", "last_successful_heartbeat_at_utc", "updated_at_utc")}
        if obj.get("device_id") is not None:
            need(obj["device_id"] == DEVICE, "RUNTIME_DEVICE_MISMATCH")
            result["device_id"] = DEVICE
        return result

    def fresh(self, runtime, expected, floor, old_start=None):
        try:
            heartbeat = dt.datetime.fromisoformat(runtime["last_successful_heartbeat_at_utc"].replace("Z", "+00:00"))
            started = dt.datetime.fromisoformat(runtime["started_at_utc"].replace("Z", "+00:00"))
            if runtime["agent_version"] != expected or not floor <= heartbeat <= now() + dt.timedelta(seconds=5):
                return False
            if old_start is not None:
                return runtime["started_at_utc"] != old_start and floor <= started <= now() + dt.timedelta(seconds=5)
            return started <= heartbeat
        except (TypeError, ValueError, KeyError):
            return False

    def download(self, suffix, expected, maximum):
        need(suffix in ("release/agent-manifest.json", "release/agent-manifest.sig.json", "agent/linux.py", "install/linux.sh"),
             "UNEXPECTED_ARTIFACT_PATH")
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
        request = urllib.request.Request(RELEASE + "/" + suffix, headers={"Accept": "application/octet-stream", "User-Agent": "HARA-QA-Private-0357-Upgrade/1"})
        try:
            with opener.open(request, timeout=self.remaining(20)) as response:
                need(response.status == 200 and response.url == RELEASE + "/" + suffix, "PRIVATE_ARTIFACT_HTTP_INVALID")
                raw = response.read(maximum + 1)
        except Hold:
            raise
        except Exception as exc:
            raise Hold("PRIVATE_ARTIFACT_DOWNLOAD_FAILED") from exc
        need(0 < len(raw) <= maximum and digest(raw) == expected, "PRIVATE_ARTIFACT_PIN_MISMATCH")
        return raw

    def prepare(self):
        need(os.getuid() == QA_UID and os.geteuid() == QA_UID, "COMMANDERQA_UID_REQUIRED")
        account = pwd.getpwuid(QA_UID)
        need(account.pw_name == QA_ACCOUNT and account.pw_dir == str(QA_HOME), "COMMANDERQA_ACCOUNT_REQUIRED")
        need(now() + dt.timedelta(seconds=PREFLIGHT_WINDOW_SECONDS) < CLOSES, "PRIVATE_RELEASE_WINDOW_TOO_SHORT")
        path_parents(WORK)
        folder = HELPER.lstat()
        need(stat.S_ISDIR(folder.st_mode) and folder.st_uid == QA_UID and not folder.st_mode & 0o022, "HELPER_DIRECTORY_INVALID")
        os.mkdir(WORK, 0o700)
        self.work_created = True
        controller, meta = read_owned(CONTROLLER, 200000)
        need(meta["sha256"] == CONTROLLER_SHA, "FROZEN_CONTROLLER_PIN_MISMATCH")
        self.control = types.ModuleType("hara_qa_verified_connect")
        self.control.__file__ = str(CONTROLLER)
        exec(compile(controller, str(CONTROLLER), "exec"), self.control.__dict__)
        self.report["frozen_controller_sha256"] = CONTROLLER_SHA
        self.checkpoint("PREIMAGE")
        trust, trust_meta = read_owned(SYSTEM_CA, 4 * 1024 * 1024, root_ok=True)
        need(SYSTEM_CA.stat().st_uid == 0 and b"-----BEGIN CERTIFICATE-----" in trust, "SYSTEM_CA_BUNDLE_INVALID")
        self.config_before, config_meta, config = self.config()
        self.agent_before, agent_meta = read_owned(AGENT, 2097152)
        self.unit_before, unit_meta = read_owned(UNIT, 65536, private=True)
        need(agent_meta["sha256"] == OLD_AGENT_SHA, "EXPECTED_0356_AGENT_REQUIRED")
        need(re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', self.agent_before, re.M) == [b"0.3.56"], "EXPECTED_0356_VERSION_REQUIRED")
        cli = file_fingerprint(CLI)
        need(cli.get("kind") == "symlink" and cli.get("target") == str(AGENT), "EXPECTED_AGENT_CLI_SYMLINK_REQUIRED")
        hara_cli = file_fingerprint(HARA_CLI, optional=True)
        service = self.service()
        need(service["ActiveState"] == "active" and service["SubState"] == "running" and int(service["MainPID"]) > 0,
             "EXISTING_AGENT_MUST_BE_RUNNING")
        runtime = self.runtime()
        need(self.fresh(runtime, "0.3.56", now() - dt.timedelta(seconds=90)), "EXISTING_RUNTIME_NOT_CURRENT")
        authenticated = self.heartbeat(config, "0.3.56")
        self.before = {"config": config_meta, "agent": agent_meta, "unit": unit_meta, "cli": cli,
                       "hara_cli": hara_cli, "service": service, "runtime": runtime,
                       "approval_mode": config["HARA_COMMANDER_APPROVAL_MODE"], "heartbeat": authenticated}
        self.report["before"] = self.before
        # Exact preimages remain user-private; config.before contains a secret
        # and must never be collected into Git, public evidence, or chat.
        write_new(WORK / "config.before.private", self.config_before)
        write_new(WORK / "agent.before.py", self.agent_before)
        write_new(WORK / "unit.before.service", self.unit_before)
        write_new(WORK / "preimage.json", (json.dumps(self.before, sort_keys=True) + "\n").encode())
        previous_rollback = AGENT.with_name(AGENT.name + ".rollback")
        if previous_rollback.exists() or previous_rollback.is_symlink():
            rollback_raw, rollback_meta = read_owned(previous_rollback, 2097152)
            write_new(WORK / "previous-agent-rollback.py", rollback_raw)
            self.report["previous_rollback_preimage"] = rollback_meta
        self.checkpoint("PRIVATE_TLS_AND_RELEASE")
        public, cert_meta = read_owned(CERT, 16384, root_ok=True)
        need(cert_meta["sha256"] == CERT_SHA and public.count(b"-----BEGIN CERTIFICATE-----") == 1
             and b"PRIVATE KEY" not in public, "PUBLIC_QA_CERT_PIN_MISMATCH")
        der = ssl.PEM_cert_to_DER_cert(public.decode("ascii"))
        need(digest(der) == CERT_DER_SHA, "PUBLIC_QA_DER_PIN_MISMATCH")
        self.context = ssl.create_default_context(cafile=str(SYSTEM_CA))
        self.context.load_verify_locations(cadata=public.decode("ascii"))
        need(self.context.verify_mode == ssl.CERT_REQUIRED and self.context.check_hostname, "NORMAL_TLS_VERIFICATION_REQUIRED")
        combined = trust.rstrip() + b"\n" + public.rstrip() + b"\n"
        write_new(WORK / "process-only-ca-bundle.pem", combined)
        self.report["tls"] = {"public_certificate_sha256": CERT_SHA, "public_der_sha256": CERT_DER_SHA,
                              "system_bundle_sha256": trust_meta["sha256"], "combined_bundle_sha256": digest(combined),
                              "trust_scope": "THIS_PROCESS_AND_SIGNED_INSTALLER_CHILD_ONLY"}
        manifest = self.download("release/agent-manifest.json", MANIFEST_SHA, 16384)
        signature = self.download("release/agent-manifest.sig.json", SIGNATURE_SHA, 16384)
        metadata = self.control.verify_manifest(manifest, signature)
        need(metadata["agent_version"] == "0.3.57", "EXPECTED_SIGNED_0357_VERSION_REQUIRED")
        entries = {row["path"]: row for row in metadata["files"]}
        need(entries["agent/linux.py"] == {"path": "agent/linux.py", "bytes": NEW_AGENT_BYTES, "sha256": NEW_AGENT_SHA}
             and entries["install/linux.sh"] == {"path": "install/linux.sh", "bytes": INSTALLER_BYTES, "sha256": INSTALLER_SHA},
             "EXPECTED_SIGNED_0357_PAYLOAD_REQUIRED")
        payload = self.download("agent/linux.py", NEW_AGENT_SHA, NEW_AGENT_BYTES)
        installer = self.download("install/linux.sh", INSTALLER_SHA, INSTALLER_BYTES)
        need(len(payload) == NEW_AGENT_BYTES and len(installer) == INSTALLER_BYTES, "PRIVATE_PAYLOAD_SIZE_MISMATCH")
        need(re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', payload, re.M) == [b"0.3.57"], "TARGET_AGENT_VERSION_MISMATCH")
        compile(payload, "verified-private-0357-agent.py", "exec")
        write_new(WORK / "agent-manifest.json", manifest)
        write_new(WORK / "agent-manifest.sig.json", signature)
        write_new(WORK / "verified-linux-agent.py", payload)
        write_new(WORK / "verified-install-linux.sh", installer)
        syntax = self.command(["/usr/bin/bash", "-n", str(WORK / "verified-install-linux.sh")])
        need(syntax.returncode == 0, "VERIFIED_INSTALLER_SYNTAX_FAILED")
        self.report["signed_release"] = {"manifest_sha256": MANIFEST_SHA, "signature_sha256": SIGNATURE_SHA,
                                         "signing_kid": "commander-release-v2", "version": "0.3.57",
                                         "agent_bytes": NEW_AGENT_BYTES, "agent_sha256": NEW_AGENT_SHA,
                                         "installer_bytes": INSTALLER_BYTES, "installer_sha256": INSTALLER_SHA,
                                         "signature_verified": True, "payloads_verified": True}

    def wait_for_child(self, stdout_path, stderr_path):
        """Observe a live signed transaction; never interrupt its swap/rollback."""
        if not self.child:
            return
        started = time.monotonic()
        next_report = started
        while self.child.poll() is None:
            current = time.monotonic()
            if current >= next_report:
                # Monitoring failures cannot abort an already-running updater.
                # A fresh independent observation window begins after it exits.
                self.report["child_elapsed_seconds"] = round(current - started, 3)
                self.report["child_long_running"] = current - started > CHILD_LONG_RUNNING_SECONDS
                self.report["child_terminated_by_driver"] = False
                try:
                    sizes = {"stdout_bytes": stdout_path.stat().st_size,
                             "stderr_bytes": stderr_path.stat().st_size}
                    self.report["private_logs"] = sizes
                    self.report["child_log_threshold_exceeded"] = any(size > MAX_LOG_BYTES for size in sizes.values())
                    self.checkpoint("SIGNED_INSTALLER_UPDATE_RUNNING")
                except Exception:
                    self.report["monitoring_warning"] = "PROGRESS_RECEIPT_UNAVAILABLE_WHILE_TRANSACTION_RUNNING"
                next_report = current + 15
            try:
                self.child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        self.report["child_exit_code"] = self.child.returncode
        self.report["child_elapsed_seconds"] = round(time.monotonic() - started, 3)
        self.report["child_long_running"] = time.monotonic() - started > CHILD_LONG_RUNNING_SECONDS
        self.report["child_finished_utc"] = now().isoformat()
        self.report["child_terminated_by_driver"] = False
        self.deadline = time.monotonic() + POST_UPDATE_OBSERVATION_SECONDS

    def update(self):
        self.checkpoint("SIGNED_INSTALLER_UPDATE")
        need(self.deadline - time.monotonic() > 65, "INSUFFICIENT_TIME_FOR_UPDATE_AND_ATTESTATION")
        # The owned preimage must still match after network/preflight work.
        need(read_owned(CONFIG, 16384, private=True)[0] == self.config_before
             and read_owned(AGENT, 2097152)[0] == self.agent_before
             and read_owned(UNIT, 65536, private=True)[0] == self.unit_before,
             "PREIMAGE_CHANGED_BEFORE_UPDATE")
        need(file_fingerprint(CLI) == self.before["cli"]
             and file_fingerprint(HARA_CLI, optional=True) == self.before["hara_cli"]
             and read_owned(CONTROLLER, 200000)[1]["sha256"] == CONTROLLER_SHA,
             "ENTRYPOINT_PREIMAGE_CHANGED_BEFORE_UPDATE")
        need(read_owned(CERT, 16384, root_ok=True)[1]["sha256"] == CERT_SHA,
             "PUBLIC_QA_CERT_CHANGED_BEFORE_UPDATE")
        need(read_owned(WORK / "verified-install-linux.sh", INSTALLER_BYTES, private=True)[1]["sha256"] == INSTALLER_SHA,
             "VERIFIED_INSTALLER_CHANGED_BEFORE_UPDATE")
        need(read_owned(SYSTEM_CA, 4 * 1024 * 1024, root_ok=True)[1]["sha256"] == self.report["tls"]["system_bundle_sha256"],
             "SYSTEM_CA_BUNDLE_CHANGED_BEFORE_UPDATE")
        child_env = self.env.copy()
        for name in ("BASH_ENV", "ENV", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH"):
            child_env.pop(name, None)
        child_env.update({"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                          "HARA_COMMANDER_URL": ORIGIN, "HARA_COMMANDER_RELEASE_URL": RELEASE,
                          "CURL_CA_BUNDLE": str(WORK / "process-only-ca-bundle.pem"),
                          "SSL_CERT_FILE": str(WORK / "process-only-ca-bundle.pem"),
                          "PYTHONDONTWRITEBYTECODE": "1"})
        self.report["child_long_running_threshold_seconds"] = CHILD_LONG_RUNNING_SECONDS
        self.report["child_timeout_policy"] = "MONITOR_ONLY_NEVER_INTERRUPT_SIGNED_TRANSACTION"
        stdout_path = WORK / "installer-stdout.private.txt"
        stderr_path = WORK / "installer-stderr.private.txt"
        out_fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            err_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except Exception:
            os.close(out_fd)
            raise
        try:
            # update() is called under the frozen controller's connection lock.
            # Re-read the effective running definition immediately before spawn;
            # bytes checked earlier cannot alone prove what systemd will run.
            dispatch_service = self.service()
            definition_fields = ("LoadState", "UnitFileState", "FragmentPath", "DropInPaths", "Type", "MainPID")
            need(all(dispatch_service[key] == self.before["service"][key] for key in definition_fields)
                 and dispatch_service["ActiveState"] == "active" and dispatch_service["SubState"] == "running"
                 and int(dispatch_service["MainPID"]) > 0, "EFFECTIVE_RUNNING_SERVICE_CHANGED_BEFORE_DISPATCH")
            need(self.fresh(self.runtime(), "0.3.56", now() - dt.timedelta(seconds=90)),
                 "EXISTING_RUNTIME_NOT_CURRENT_AT_DISPATCH")
            self.report["dispatch_service_rechecked_under_lock"] = True
            self.report["updater_started_utc"] = now().isoformat()
            self.child = subprocess.Popen(["/usr/bin/bash", str(WORK / "verified-install-linux.sh"), "update"],
                                          stdin=subprocess.DEVNULL, stdout=out_fd, stderr=err_fd,
                                          env=child_env, cwd=str(WORK), start_new_session=True)
            self.report["child_pid"] = self.child.pid
            self.wait_for_child(stdout_path, stderr_path)
        finally:
            # Even an unexpected monitor error must not kill the transaction or
            # release its connection lock while the installer is still live.
            if self.child and self.child.poll() is None:
                self.report["monitoring_warning"] = "WAITING_FOR_LIVE_TRANSACTION_AFTER_OBSERVER_ERROR"
                self.wait_for_child(stdout_path, stderr_path)
            os.close(out_fd)
            os.close(err_fd)
        # Raw child output stays private. Expose only fixed marker booleans.
        stdout_size = stdout_path.stat().st_size
        stderr_size = stderr_path.stat().st_size
        self.report["private_logs"] = {"stdout_bytes": stdout_size, "stderr_bytes": stderr_size}
        need(stdout_size <= MAX_LOG_BYTES and stderr_size <= MAX_LOG_BYTES,
             "SIGNED_UPDATER_LOG_LIMIT_AFTER_TRANSACTION_EXIT")
        stdout = read_owned(stdout_path, MAX_LOG_BYTES, private=True)[0] if stdout_size else b""
        self.report["installer_markers"] = {
            "update_pass": b"HARA_COMMANDER_AGENT_UPDATE=PASS" in stdout.splitlines(),
            "integrity_pass": b"HARA_COMMANDER_AGENT_INTEGRITY=PASS" in stdout.splitlines(),
            "startup_attestation_pass": b"HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS" in stdout.splitlines(),
            "rollback_ready": b"HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE" in stdout.splitlines(),
            "pairing_prompt_seen": b"Pairing token:" in stdout,
        }
        self.report["private_logs"] = {"stdout_bytes": len(stdout), "stderr_bytes": stderr_path.stat().st_size}
        need(self.child.returncode == 0, "SIGNED_INSTALLER_UPDATE_FAILED")
        need(not self.report["installer_markers"]["pairing_prompt_seen"]
             and all(self.report["installer_markers"][key] for key in ("update_pass", "integrity_pass", "startup_attestation_pass", "rollback_ready")),
             "SIGNED_INSTALLER_SUCCESS_MARKERS_UNCONFIRMED")

    def observe(self):
        observed = {"observed_utc": now().isoformat(), "state": "UNCONFIRMED", "mutation_performed_by_observer": False}
        try:
            raw, config_meta, config = self.config()
            agent, agent_meta = read_owned(AGENT, 2097152)
            unit, unit_meta = read_owned(UNIT, 65536, private=True)
            versions = re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', agent, re.M)
            need(len(versions) == 1, "OBSERVED_AGENT_VERSION_INVALID")
            current = versions[0].decode("ascii")
            service = self.service()
            runtime = self.runtime()
            observed.update(config_bytes_preserved=raw == self.config_before,
                            config_metadata_preserved=config_meta == self.before["config"],
                            unit_bytes_preserved=unit == self.unit_before,
                            unit_metadata_preserved=unit_meta == self.before["unit"],
                            cli_preserved=file_fingerprint(CLI) == self.before["cli"],
                            hara_cli_preserved=file_fingerprint(HARA_CLI, optional=True) == self.before["hara_cli"],
                            approval_mode_preserved=config["HARA_COMMANDER_APPROVAL_MODE"] == self.before["approval_mode"],
                            agent_version=current, agent_sha256=agent_meta["sha256"], agent_bytes=len(agent),
                            runtime=runtime, service=service,
                            heartbeat=self.heartbeat(config, current))
            definition_fields = ("LoadState", "UnitFileState", "FragmentPath", "DropInPaths", "Type")
            observed["effective_unit_preserved"] = all(service[key] == self.before["service"][key] for key in definition_fields)
            # ExecStart is revalidated against the exact Agent path above; its
            # systemd diagnostic timestamps/PIDs legitimately change on restart.
            observed["service_running"] = service["ActiveState"] == "active" and service["SubState"] == "running" and int(service["MainPID"]) > 0
            observed["frozen_controller_unchanged"] = read_owned(CONTROLLER, 200000)[1]["sha256"] == CONTROLLER_SHA
            observed["system_ca_bundle_unchanged"] = read_owned(SYSTEM_CA, 4 * 1024 * 1024, root_ok=True)[1]["sha256"] == self.report["tls"]["system_bundle_sha256"]
            required = ("config_bytes_preserved", "config_metadata_preserved", "unit_bytes_preserved", "unit_metadata_preserved",
                        "cli_preserved", "hara_cli_preserved", "approval_mode_preserved", "effective_unit_preserved",
                        "service_running", "frozen_controller_unchanged", "system_ca_bundle_unchanged")
            if all(observed[key] for key in required):
                if current == "0.3.57" and agent_meta["sha256"] == NEW_AGENT_SHA and len(agent) == NEW_AGENT_BYTES:
                    floor = dt.datetime.fromisoformat(self.report["updater_started_utc"]) - dt.timedelta(seconds=5)
                    observed["fresh_target_runtime"] = self.fresh(runtime, current, floor, self.before["runtime"]["started_at_utc"])
                    if observed["fresh_target_runtime"]:
                        rollback = read_owned(AGENT.with_name(AGENT.name + ".rollback"), 2097152)[0]
                        observed["rollback_agent_preimage_exact"] = rollback == self.agent_before
                        if observed["rollback_agent_preimage_exact"]:
                            observed["state"] = "TARGET_INSTALLED_AND_CONNECTED"
                elif current == "0.3.56" and agent_meta["sha256"] == OLD_AGENT_SHA:
                    observed["fresh_original_runtime"] = self.fresh(runtime, current, now() - dt.timedelta(seconds=90))
                    if observed["fresh_original_runtime"]:
                        observed["state"] = "ORIGINAL_INSTALLED_AND_CONNECTED"
        except Exception as exc:
            observed["error_code"] = str(exc) if isinstance(exc, Hold) else "INDEPENDENT_STATE_ATTESTATION_FAILED"
        return observed

    def run(self):
        try:
            self.prepare()
            with self.control.connection_lock():
                self.update()
                self.checkpoint("INDEPENDENT_NATIVE_ATTESTATION")
                until = min(self.deadline - 15, time.monotonic() + 35)
                while True:
                    observed = self.observe()
                    self.report["after"] = observed
                    if observed["state"] == "TARGET_INSTALLED_AND_CONNECTED" or time.monotonic() >= until:
                        break
                    time.sleep(1)
                need(observed["state"] == "TARGET_INSTALLED_AND_CONNECTED", "TARGET_RUNTIME_NOT_CONFIRMED")
                self.report["state"] = "PASS_DIRECT_SIGNED_0357_UPDATE"
        except Exception as exc:
            self.report["error_code"] = str(exc) if isinstance(exc, Hold) else "NATIVE_PRIVATE_UPGRADE_FAILED"
            self.report["error_type"] = type(exc).__name__
            if self.before and self.deadline - time.monotonic() > 20:
                self.report["independent_failure_attestation"] = self.observe()
        finally:
            self.report["finished_utc"] = now().isoformat()
            if self.work_created:
                write_report(WORK / "result.json", self.report)
        print(json.dumps(self.report, sort_keys=True))
        return 0 if self.report["state"] == "PASS_DIRECT_SIGNED_0357_UPDATE" else 2


if __name__ == "__main__":
    raise SystemExit(Upgrade().run())
