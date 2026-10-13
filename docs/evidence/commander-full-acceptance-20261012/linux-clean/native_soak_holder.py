#!/usr/bin/env python3
"""QA-only transport holder; real CLI sessions rotate before the unchanged 12h TTL."""
import argparse
import fcntl
import hashlib
import json
import os
import pty
import re
import secrets
import select
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEV = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
QA_ROOT = Path("/home/commanderqa")
QA_HOST = "commander-linux-clean"
ROTATE_SECONDS = 11 * 60 * 60


class GuardError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise GuardError(code)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(path):
    require(stat.S_ISREG(path.lstat().st_mode), "QA_REGULAR_FILE_REQUIRED")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_config(path):
    require(stat.S_ISREG(path.lstat().st_mode), "QA_CONFIG_REGULAR_FILE_REQUIRED")
    raw = path.read_bytes()
    values = {}
    for line in raw.decode("utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            require(key not in values, "QA_CONFIG_DUPLICATE_KEY")
            values[key] = value
    return raw, values


def atomic_status(path, state):
    """Keep the previous complete report until the new report is durable."""
    temp = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write((json.dumps(state, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def terminate_group(process):
    """This group is created by bounded_run, never discovered by name."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # A reaped parent can leave a descendant that ignores SIGTERM, including
    # commands whose output goes to DEVNULL. Always escalate the owned group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("QA_OWNED_PROCESS_GROUP_DID_NOT_EXIT") from error


def bounded_run(command, timeout, env, capture=False):
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env, start_new_session=True, text=True)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException:
        terminate_group(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout or "", None)


def fork_console(command, env):
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(command[0], command, env)
        except BaseException:
            # A failed child must never unwind into parent stop/uninstall/report code.
            os._exit(127)
    return pid, fd


def process_start_marker(pid):
    try:
        raw = Path("/proc/{}/stat".format(pid)).read_text(encoding="utf-8")
        tail = raw[raw.rfind(")") + 2:].split()
        return tail[19] if len(tail) > 19 else None
    except OSError:
        return None


class SoakHolder:
    def __init__(self, args, root=QA_ROOT, hostname_path=Path("/etc/hostname"), expected_uid=2000):
        self.args, self.root = args, Path(root)
        self.hostname_path, self.expected_uid = Path(hostname_path), expected_uid
        self.fixture = self.root / "commander-qa"
        self.data = self.root / ".local/share/hara-commander"
        self.agent = self.data / "hara-commander-agent"
        self.installer = self.fixture / "linux.sh"
        self.config = self.root / ".config/hara-commander/device.env"
        self.session = self.data / "operator-session.json"
        self.status = self.fixture / "soak-holder-status.json"
        self.pid = self.fd = None
        self.console_identity = None
        self.child_done, self.stopped = True, False
        self.began = time.monotonic()
        self.guard_environment()
        require(300 <= args.seconds <= 86400, "QA_SOAK_BUDGET_INVALID")
        require(all(re.fullmatch("[0-9a-f]{64}", value) for value in
            (args.expected_agent_sha256, args.expected_installer_sha256)), "QA_SHA256_INVALID")
        raw, cfg = read_config(self.config)
        require(cfg.get("HARA_COMMANDER_URL") == DEV, "QA_DEV_ORIGIN_REQUIRED")
        require(cfg.get("HARA_COMMANDER_APPROVAL_MODE") == "ASK_EVERY_ACTION", "QA_ASK_MODE_REQUIRED")
        require(bool(cfg.get("HARA_DEVICE_ID")), "QA_DEVICE_ID_REQUIRED")
        self.config_sha256 = hashlib.sha256(raw).hexdigest()
        self.device_id = cfg["HARA_DEVICE_ID"]
        self.verify_invocation()
        require(not os.path.lexists(self.session), "QA_OPERATOR_SESSION_STILL_ACTIVE")
        self.state = {"schema": "hara.commander-linux-native-soak-holder.v3", "state": "STARTING",
            "device_id": self.device_id, "started_at_utc": utc(), "budget_seconds": args.seconds,
            "operator_mode": "ASK_EVERY_ACTION", "automatic_action_approvals": 0,
            "stdout_content_retained": False, "qa_only": True,
            "transport_scope": "24h_transport_with_rotated_real_CLI_sessions",
            "product_session_ttl_changed": False, "rotation_interval_seconds": ROTATE_SECONDS,
            "sessions_started": 0, "rotation_count": 0, "rotation_gaps_seconds": [],
            "samples": 0, "bound_samples": 0, "pin_valid_samples": 0,
            "terminal_bytes_drained": 0, "config_sha256": self.config_sha256,
            "expected_agent_sha256": args.expected_agent_sha256,
            "expected_installer_sha256": args.expected_installer_sha256,
            "cleanup_errors": [], "cleanup_blocked": False, "status_write_errors": 0}

    def guard_environment(self):
        require(os.getuid() == self.expected_uid, "QA_UID_REQUIRED")
        require(self.hostname_path.read_text().strip() == QA_HOST, "QA_HOST_REQUIRED")
        require(os.environ.get("HOME") == str(self.root), "QA_HOME_REQUIRED")
        for key, expected in (("XDG_CONFIG_HOME", self.root / ".config"),
                              ("XDG_DATA_HOME", self.root / ".local/share")):
            require(not os.environ.get(key) or os.environ[key] == str(expected), "QA_XDG_PROFILE_REQUIRED")

    def environment(self):
        env = os.environ.copy()
        env.update(HOME=str(self.root), HARA_COMMANDER_URL=DEV,
                   HARA_COMMANDER_APPROVAL_MODE="ASK_EVERY_ACTION")
        return env

    def verify_invocation(self):
        try:
            self.guard_environment()
            raw, cfg = read_config(self.config)
            require(cfg.get("HARA_COMMANDER_URL") == DEV, "QA_DEV_ORIGIN_DRIFT")
            require(cfg.get("HARA_COMMANDER_APPROVAL_MODE") == "ASK_EVERY_ACTION", "QA_APPROVAL_MODE_DRIFT")
            require(cfg.get("HARA_DEVICE_ID") == self.device_id, "QA_DEVICE_ID_DRIFT")
            require(hashlib.sha256(raw).hexdigest() == self.config_sha256, "QA_CONFIG_SHA256_DRIFT")
            require(digest(self.agent) == self.args.expected_agent_sha256, "QA_AGENT_SHA256_DRIFT")
            require(digest(self.installer) == self.args.expected_installer_sha256, "QA_INSTALLER_SHA256_DRIFT")
            self.guard_session_ownership()
        except (GuardError, OSError, ValueError):
            if hasattr(self, "state"):
                self.state["cleanup_blocked"] = True
            raise

    def guard_session_ownership(self):
        if os.path.lexists(self.session):
            require(stat.S_ISREG(self.session.lstat().st_mode), "QA_SESSION_REGULAR_FILE_REQUIRED")
            session = json.loads(self.session.read_text())
            require(self.console_identity is not None and
                session.get("owner_pid") == self.console_identity[0] and
                session.get("owner_start_marker") == self.console_identity[1],
                "QA_FOREIGN_OPERATOR_SESSION")

    def save(self):
        atomic_status(self.status, self.state)

    def error(self, stage, error):
        item = {"stage": stage, "error_type": type(error).__name__}
        if isinstance(error, GuardError):
            item["error_code"] = str(error)
        self.state["cleanup_errors"].append(item)

    def product_command(self, command, timeout, capture=False):
        require(not self.state["cleanup_blocked"], "QA_CLEANUP_BLOCKED_AFTER_DRIFT")
        self.verify_invocation()
        return bounded_run(command, timeout, self.environment(), capture)

    def cli_stop(self):
        return self.product_command([sys.executable, str(self.agent), "stop"], 30).returncode

    def close_console(self):
        try:
            if self.pid is not None and not self.child_done:
                for sig, grace in ((signal.SIGINT, 5), (signal.SIGKILL, 2)):
                    try:
                        os.kill(self.pid, sig)
                    except ProcessLookupError:
                        pass
                    until = time.monotonic() + grace
                    while time.monotonic() < until:
                        try:
                            done, _ = os.waitpid(self.pid, os.WNOHANG)
                        except ChildProcessError:
                            done = self.pid
                        if done:
                            self.child_done = True
                            break
                        time.sleep(.05)
                    if self.child_done:
                        break
                require(self.child_done, "QA_OWNED_CONSOLE_DID_NOT_EXIT")
        finally:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None
            if self.child_done:
                self.pid = None

    def launch_console(self):
        require(not self.state["cleanup_blocked"], "QA_CLEANUP_BLOCKED_AFTER_DRIFT")
        self.verify_invocation()
        require(not os.path.lexists(self.session), "QA_OPERATOR_SESSION_STILL_ACTIVE")
        self.pid, self.fd = fork_console([sys.executable, str(self.agent), "start"], self.environment())
        self.child_done = False
        marker = process_start_marker(self.pid)
        require(marker is not None, "QA_CONSOLE_PROCESS_IDENTITY_UNAVAILABLE")
        self.console_identity = (self.pid, marker)
        self.state["sessions_started"] += 1

    def bound_session(self):
        try:
            session = json.loads(self.session.read_text())
        except (OSError, ValueError):
            return False
        marker = process_start_marker(self.pid) if self.pid else None
        return bool(marker and self.console_identity == (self.pid, marker) and
            session.get("owner_pid") == self.pid and
            session.get("owner_start_marker") == marker and
            session.get("device_id") == self.device_id and
            session.get("authorization") == "LOCAL_OPERATOR_TERMINAL" and
            session.get("approval_mode") == "ASK_EVERY_ACTION")

    def cleanup(self):
        outcome = self.state["state"]
        stop_code = uninstall_code = None
        revoke_pass = False
        for stage, operation in (("cli_stop", self.cli_stop), ("close_console", self.close_console)):
            try:
                result = operation()
                if stage == "cli_stop":
                    stop_code = result
            except BaseException as error:
                self.error(stage, error)
                if isinstance(error, (GuardError, OSError)) and stage == "cli_stop":
                    self.state["cleanup_blocked"] = True
        try:
            uninstall = self.product_command(["/bin/bash", str(self.installer), "uninstall"], 120, True)
            uninstall_code = uninstall.returncode
            revoke_pass = "SERVER_DEVICE_REVOKE=PASS" in uninstall.stdout.splitlines()
        except BaseException as error:
            self.error("uninstall", error)
            if isinstance(error, (GuardError, OSError)):
                self.state["cleanup_blocked"] = True
        complete = (stop_code == 0 and uninstall_code == 0 and revoke_pass and
                    not os.path.lexists(self.config) and not os.path.lexists(self.agent) and
                    not os.path.lexists(self.session) and not os.path.lexists(self.root / ".local/bin/hara"))
        self.state.update(state=outcome, finished_at_utc=utc(), elapsed_seconds=int(time.monotonic() - self.began),
            qa_cli_stop_exit_code=stop_code, qa_uninstall_exit_code=uninstall_code,
            qa_config_removed=not os.path.lexists(self.config), qa_agent_removed=not os.path.lexists(self.agent),
            qa_operator_session_removed=not os.path.lexists(self.session),
            qa_wrapper_removed=not os.path.lexists(self.root / ".local/bin/hara"),
            server_self_revoke_pass=revoke_pass, cleanup_complete=complete, automatic_action_approvals=0)
        try:
            self.save()
        except BaseException as error:
            self.state["status_write_errors"] += 1
            self.error("final_status", error)
            # A transient primary-path error must not discard terminal aggregate evidence.
            try:
                atomic_status(self.status.with_name("soak-holder-final-status.json"), self.state)
            except BaseException as fallback:
                self.error("fallback_status", fallback)

    def run(self):
        lock = os.open(self.fixture / "soak-holder.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            require(stat.S_ISREG(os.fstat(lock).st_mode) and os.fstat(lock).st_uid == os.getuid()
                    and os.fstat(lock).st_nlink == 1, "QA_LOCK_OWNER_REQUIRED")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fchmod(lock, 0o600)
            self._run_locked()
        finally:
            os.close(lock)
        return self.state

    def _run_locked(self):
        deadline = self.began + self.args.seconds
        next_sample, rotation_at = self.began, self.began + ROTATE_SECONDS
        try:
            self.save()
            self.launch_console()
            while time.monotonic() < deadline and not self.stopped:
                readable, _, _ = select.select([self.fd], [], [], 1)
                if readable:
                    try:
                        raw = os.read(self.fd, 65536)
                    except OSError:
                        raw = b""
                    self.state["terminal_bytes_drained"] += len(raw)
                child, _ = os.waitpid(self.pid, os.WNOHANG)
                if child:
                    self.child_done = True
                    self.state["state"] = "FAILED_OPERATOR_CONSOLE_EXITED"
                    break
                now = time.monotonic()
                if now >= rotation_at:
                    gap_start = now
                    try:
                        require(self.cli_stop() == 0, "QA_CLI_STOP_FAILED")
                    finally:
                        self.close_console()
                    if self.stopped:
                        break
                    self.launch_console()
                    until = time.monotonic() + 15
                    while time.monotonic() < until and not self.bound_session():
                        time.sleep(.1)
                    require(self.bound_session(), "QA_SESSION_ROTATION_FAILED")
                    self.state["rotation_count"] += 1
                    self.state["rotation_gaps_seconds"].append(round(time.monotonic() - gap_start, 3))
                    rotation_at = time.monotonic() + ROTATE_SECONDS
                if now >= next_sample:
                    self.verify_invocation()
                    bound = self.bound_session()
                    self.state["samples"] += 1
                    self.state["pin_valid_samples"] += 1
                    self.state["bound_samples"] += int(bound)
                    self.state.update(state="RUNNING", observed_at_utc=utc(), elapsed_seconds=int(now - self.began),
                                      session_bound=bound, source_pin_ok=True, config_pin_ok=True)
                    self.save()
                    next_sample = time.monotonic() + 60
                    require(now - self.began <= 15 or bound, "QA_SESSION_BINDING_LOST")
            else:
                self.state["state"] = "CANCELLED" if self.stopped else "ELAPSED_PENDING_PROBE_REVIEW"
            if self.stopped and self.state["state"] == "RUNNING":
                self.state["state"] = "CANCELLED"
        except BaseException as error:
            self.state.update(state="FAILED_OBSERVER", error_type=type(error).__name__)
            if isinstance(error, GuardError):
                self.state["error_code"] = str(error)
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-agent-sha256", required=True)
    parser.add_argument("--expected-installer-sha256", required=True)
    parser.add_argument("--seconds", type=int, default=86400)
    args = parser.parse_args()
    try:
        holder = SoakHolder(args)
        def stop(signum, frame):
            holder.stopped = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        report = holder.run()
        print(json.dumps(report, sort_keys=True))
        return 0 if report["state"] == "ELAPSED_PENDING_PROBE_REVIEW" and report["cleanup_complete"] else 1
    except BaseException as error:
        report = {"schema": "hara.commander-linux-native-soak-holder.v3", "state": "FAILED_TO_START",
                  "error_type": type(error).__name__, "automatic_action_approvals": 0, "qa_only": True}
        if isinstance(error, GuardError):
            report["error_code"] = str(error)
        print(json.dumps(report, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
