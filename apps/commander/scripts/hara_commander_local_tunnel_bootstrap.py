#!/usr/bin/env python3
"""Prepare a customer-owned OpenAI Secure MCP Tunnel to the signed local Agent.

The product's H.A.R.A. Cloud control plane is NOT an MCP tool relay in this mode.
No OpenAI credential is transported to HARA and no device token is read.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILE = "hara-commander"
UNIT_NAME = "hara-commander-openai-tunnel.service"
TUNNEL_RE = re.compile(r"tunnel_[A-Za-z0-9_-]{16,180}\Z")
RUNTIME_KEY_RE = re.compile(r"[A-Za-z0-9_.-]{20,512}\Z")


class BridgeError(RuntimeError):
    pass


def paths() -> dict[str, Path]:
    home = Path.home()
    return {
        "cli": home / ".local/bin/hara-commander",
        "client": home / ".local/share/hara-commander/tunnel-client",
        "unit": home / ".config/systemd/user" / UNIT_NAME,
        "env": home / ".config/hara-commander/openai-tunnel.env",
        "profile": home / ".config/tunnel-client" / (PROFILE + ".yaml"),
    }


def check_binary(path: Path, code: str) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise BridgeError(code)
    if path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise BridgeError(code + "_UNSAFE_PERMISSIONS")


def systemd_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime = Path("/run/user") / str(os.getuid())
    if "XDG_RUNTIME_DIR" not in env and runtime.is_dir():
        env["XDG_RUNTIME_DIR"] = str(runtime)
    if "DBUS_SESSION_BUS_ADDRESS" not in env and (runtime / "bus").is_socket():
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(runtime / "bus")
    return env


def systemctl(*arguments: str, required: bool = True) -> bool:
    result = subprocess.run(
        ["systemctl", "--user", *arguments],
        env=systemd_env(), text=True, capture_output=True, timeout=25,
    )
    if required and result.returncode:
        raise BridgeError("USER_SYSTEMD_" + arguments[0].replace("-", "_").upper() + "_FAILED")
    return result.returncode == 0


def prepare() -> None:
    p = paths()
    check_binary(p["cli"], "SIGNED_COMMANDER_CLI_MISSING")
    check_binary(p["client"], "OPENAI_TUNNEL_CLIENT_MISSING")
    text = (
        "[Unit]\nDescription=H.A.R.A. Commander — OpenAI Secure MCP Tunnel (local)\n"
        "After=network-online.target\nWants=network-online.target\n\n"
        "[Service]\nType=simple\nUMask=0077\nNoNewPrivileges=true\n"
        "EnvironmentFile=%h/.config/hara-commander/openai-tunnel.env\n"
        "ExecStartPre=/usr/bin/test -r %h/.config/tunnel-client/hara-commander.yaml\n"
        "ExecStartPre=/usr/bin/test -r %h/.config/hara-commander/openai-tunnel.env\n"
        f"ExecStart={p['client']} run --profile {PROFILE}\n"
        "Restart=on-failure\nRestartSec=15\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    p["unit"].parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(p["unit"].parent, 0o700)
    if p["unit"].exists():
        if p["unit"].read_text(encoding="utf-8") != text:
            raise BridgeError("EXISTING_TUNNEL_UNIT_DIFFERS_DO_NOT_OVERWRITE")
    else:
        p["unit"].write_text(text, encoding="utf-8")
        os.chmod(p["unit"], 0o600)
    systemctl("daemon-reload")
    # Installation does NOT start the bridge, and keeps the existing Agent untouched.
    print("LOCAL_MCP_BINARY=PASS")
    print("OPENAI_TUNNEL_CLIENT_BINARY=PASS")
    print("OPENAI_TUNNEL_UNIT=PREPARED_DISABLED")
    print("OPENAI_TUNNEL_TRAFFIC_STARTED=FALSE")


def read_runtime_env() -> dict[str, str]:
    p = paths()
    if not p["env"].is_file():
        raise BridgeError("OPENAI_RUNTIME_KEY_MISSING")
    if stat.S_IMODE(p["env"].stat().st_mode) & 0o077:
        raise BridgeError("OPENAI_RUNTIME_KEY_PERMISSIONS_INVALID")
    values = p["env"].read_text(encoding="utf-8").splitlines()
    matches = [v.split("=", 1)[1] for v in values if v.startswith("CONTROL_PLANE_API_KEY=")]
    if len(matches) != 1 or not RUNTIME_KEY_RE.fullmatch(matches[0]):
        raise BridgeError("OPENAI_RUNTIME_KEY_INVALID")
    env = os.environ.copy()
    env["CONTROL_PLANE_API_KEY"] = matches[0]
    return env


def doctor() -> bool:
    p = paths()
    if not p["profile"].is_file():
        raise BridgeError("OPENAI_TUNNEL_ID_NOT_CONFIGURED")
    env = read_runtime_env()
    result = subprocess.run(
        [str(p["client"]), "doctor", "--profile", PROFILE, "--explain"],
        env=env, text=True, capture_output=True, timeout=35,
    )
    # Never display the API key, or arbitrary error output that could echo it.
    print("OPENAI_TUNNEL_DOCTOR=" + ("PASS" if result.returncode == 0 else "FAIL"))
    return result.returncode == 0


def atomic_private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def configure(auto: bool = False) -> None:
    p = paths()
    if not sys.stdin.isatty():
        raise BridgeError("RUN_CONFIGURE_IN_LOCAL_INTERACTIVE_TERMINAL")
    if not p["unit"].is_file():
        prepare()
    if p["profile"].exists() or p["env"].exists():
        raise BridgeError("TUNNEL_ALREADY_CONFIGURED_REKEY_NEEDS_SEPARATE_REVIEW")
    tunnel_id = input("OpenAI tunnel_id (from OpenAI Platform): ").strip()
    runtime_key = getpass.getpass("OpenAI tunnel runtime API key (hidden): ").strip()
    if not TUNNEL_RE.fullmatch(tunnel_id):
        raise BridgeError("OPENAI_TUNNEL_ID_INVALID")
    if not RUNTIME_KEY_RE.fullmatch(runtime_key):
        raise BridgeError("OPENAI_RUNTIME_KEY_INVALID")

    env = os.environ.copy()
    env["CONTROL_PLANE_API_KEY"] = runtime_key
    command = shlex.quote(str(p["cli"])) + " mcp"
    result = subprocess.run(
        [
            str(p["client"]), "init", "--sample", "sample_mcp_stdio_local",
            "--profile", PROFILE, "--tunnel-id", tunnel_id,
            "--health-listen-addr", "127.0.0.1:0",
            "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY",
            "--mcp-command", command,
        ],
        env=env, text=True, capture_output=True, timeout=25,
    )
    if result.returncode:
        raise BridgeError("OPENAI_TUNNEL_PROFILE_INIT_FAILED")
    if not p["profile"].is_file():
        raise BridgeError("OPENAI_TUNNEL_PROFILE_NOT_CREATED")
    if stat.S_IMODE(p["profile"].stat().st_mode) & 0o077:
        raise BridgeError("OPENAI_TUNNEL_PROFILE_PERMISSIONS_INVALID")

    atomic_private_write(p["env"], "CONTROL_PLANE_API_KEY=" + runtime_key + "\n")
    runtime_key = ""
    print("OPENAI_TUNNEL_PROFILE=CREATED")
    print("OPENAI_RUNTIME_KEY_STORED_LOCALLY=TRUE")
    print("DEVICE_TOKEN_SENT_TO_HARA=FALSE")
    if not doctor():
        print("OPENAI_TUNNEL_SERVICE=NOT_STARTED")
        raise BridgeError("OPENAI_TUNNEL_DOCTOR_FAILED_CHECK_ORG_WORKSPACE_AND_KEY")
    if auto:
        systemctl("enable", "--now", UNIT_NAME)
        print("OPENAI_TUNNEL_AUTOSTART=ON")
    else:
        systemctl("disable", UNIT_NAME, required=False)
        print("OPENAI_TUNNEL_AUTOSTART=OFF")
        print("NEXT_COMMAND=hara-commander-openai-bridge start")
    print("CHATGPT_CONNECTION_TYPE=Tunnel")
    print("CHATGPT_TUNNEL_ID_CONFIGURED=TRUE")


def start() -> None:
    p = paths()
    if not p["unit"].is_file():
        raise BridgeError("RUN_PREPARE_FIRST")
    if not doctor():
        raise BridgeError("OPENAI_TUNNEL_DOCTOR_FAILED")
    systemctl("start", UNIT_NAME)
    if not systemctl("is-active", "--quiet", UNIT_NAME, required=False):
        raise BridgeError("OPENAI_TUNNEL_SERVICE_NOT_ACTIVE")
    print("OPENAI_TUNNEL_SERVICE=ACTIVE")


def stop() -> None:
    systemctl("stop", UNIT_NAME)
    print("OPENAI_TUNNEL_SERVICE=STOPPED")


def autostart(value: str) -> None:
    if value == "on":
        if not doctor():
            raise BridgeError("OPENAI_TUNNEL_DOCTOR_FAILED")
        systemctl("enable", "--now", UNIT_NAME)
    else:
        systemctl("disable", UNIT_NAME)
    print("OPENAI_TUNNEL_AUTOSTART=" + value.upper())


def status() -> None:
    p = paths()
    print("LOCAL_MCP_CLI=" + ("PRESENT" if p["cli"].is_file() else "MISSING"))
    print("OPENAI_TUNNEL_CLIENT=" + ("PRESENT" if p["client"].is_file() else "MISSING"))
    print("OPENAI_TUNNEL_UNIT=" + ("PREPARED" if p["unit"].is_file() else "MISSING"))
    print("OPENAI_TUNNEL_ID_CONFIGURED=" + str(p["profile"].is_file()).upper())
    print("OPENAI_RUNTIME_KEY_CONFIGURED=" + str(p["env"].is_file()).upper())
    if p["unit"].is_file():
        print("OPENAI_TUNNEL_ACTIVE=" + str(systemctl("is-active", "--quiet", UNIT_NAME, required=False)).upper())
        print("OPENAI_TUNNEL_AUTOSTART=" + str(systemctl("is-enabled", "--quiet", UNIT_NAME, required=False)).upper())
    print("HARA_SERVICES_RELAY_USED=FALSE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure customer-owned OpenAI tunnel to local HARA Commander MCP")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "status", "start", "stop", "doctor"):
        sub.add_parser(name)
    config = sub.add_parser("configure")
    config.add_argument("--autostart", action="store_true")
    auto = sub.add_parser("autostart")
    auto.add_argument("value", choices=("on", "off"))
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare()
        elif args.command == "status":
            status()
        elif args.command == "configure":
            configure(args.autostart)
        elif args.command == "start":
            start()
        elif args.command == "stop":
            stop()
        elif args.command == "doctor":
            if not doctor():
                return 2
        elif args.command == "autostart":
            autostart(args.value)
        return 0
    except (BridgeError, subprocess.TimeoutExpired) as exc:
        code = str(exc) if isinstance(exc, BridgeError) else "PROCESS_TIMEOUT"
        print("LOCAL_OPENAI_BRIDGE=" + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
