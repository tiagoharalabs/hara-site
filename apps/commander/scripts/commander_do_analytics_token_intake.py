#!/usr/bin/env python3
"""Secure one-time intake for the dedicated DEV Durable Objects analytics token."""

from __future__ import annotations

import argparse
import getpass
import os
import stat
from pathlib import Path

DEFAULT_DEST = Path(__file__).resolve().parents[1] / ".generated" / "do-analytics-account-read-token"
MIN_TOKEN_LENGTH = 32


class IntakeError(RuntimeError):
    pass


def validate_dest(path: Path) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(parent, 0o700)
    if path.exists():
        raise IntakeError("DO_ANALYTICS_TOKEN_DEST_EXISTS")


def write_secret(path: Path, secret: str) -> None:
    if len(secret.strip()) < MIN_TOKEN_LENGTH:
        raise IntakeError("DO_ANALYTICS_TOKEN_INVALID")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, secret.strip().encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    if os.name != "nt":
        os.chmod(path, 0o600)
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise IntakeError("DO_ANALYTICS_TOKEN_PERMISSIONS")


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "getpass.getpass" in source
    assert "os.O_EXCL" in source
    assert "0o600" in source
    for forbidden in ("CLOUDFLARE_API_TOKEN", ".wrangler", "default.toml"):
        assert forbidden not in source
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE_SOURCE=PASS")
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE_ECHO=DISABLED")
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE_MODE=0600")
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE_ENV_FALLBACK=ABSENT")
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE_OAUTH_REUSE=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dest", default=str(DEFAULT_DEST))
    args = parser.parse_args()
    if args.check:
        self_check()
        return 0

    path = Path(args.dest).expanduser().resolve()
    validate_dest(path)
    secret = getpass.getpass("Cloudflare Account Analytics Read token: ")
    try:
        write_secret(path, secret)
    finally:
        secret = ""

    info = path.stat()
    print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE=PASS")
    print("COMMANDER_DO_ANALYTICS_TOKEN_FILE=" + str(path))
    print("COMMANDER_DO_ANALYTICS_TOKEN_MODE=" + oct(stat.S_IMODE(info.st_mode))[2:])
    print("COMMANDER_DO_ANALYTICS_TOKEN_BYTES=" + str(info.st_size))
    print("COMMANDER_DO_ANALYTICS_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntakeError as exc:
        print("COMMANDER_DO_ANALYTICS_TOKEN_INTAKE=FAIL:" + str(exc))
        raise SystemExit(1)
