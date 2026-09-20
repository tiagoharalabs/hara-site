#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "public" / ".well-known" / "openai-apps-challenge"


def read_token(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    if not raw:
        raise SystemExit("TOKEN_EMPTY")
    if len(raw) > 4096:
        raise SystemExit("TOKEN_TOO_LARGE")
    if b"\n" in raw or b"\r" in raw or b"\x00" in raw:
        raise SystemExit("TOKEN_NOT_SINGLE_LINE")
    return raw


def status() -> int:
    if not TARGET.is_file():
        print("OPENAI_APPS_CHALLENGE_STATE=ABSENT")
        return 0
    raw = TARGET.read_bytes()
    print("OPENAI_APPS_CHALLENGE_STATE=PRESENT")
    print(f"OPENAI_APPS_CHALLENGE_BYTES={len(raw)}")
    print(f"OPENAI_APPS_CHALLENGE_SHA256={hashlib.sha256(raw).hexdigest()}")
    return 0


def set_token(source: Path) -> int:
    token = read_token(source)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    tmp = TARGET.with_name(TARGET.name + ".tmp")
    tmp.write_bytes(token)
    os.replace(tmp, TARGET)
    print("OPENAI_APPS_CHALLENGE_WRITE=PASS")
    print(f"OPENAI_APPS_CHALLENGE_BYTES={len(token)}")
    print(f"OPENAI_APPS_CHALLENGE_SHA256={hashlib.sha256(token).hexdigest()}")
    print("TOKEN_VALUE_PRINTED=FALSE")
    return 0


def verify(source: Path) -> int:
    expected = read_token(source)
    if not TARGET.is_file():
        raise SystemExit("CHALLENGE_FILE_MISSING")
    actual = TARGET.read_bytes()
    if actual != expected:
        raise SystemExit("CHALLENGE_TOKEN_MISMATCH")
    print("OPENAI_APPS_CHALLENGE_VERIFY=PASS")
    print(f"OPENAI_APPS_CHALLENGE_SHA256={hashlib.sha256(actual).hexdigest()}")
    print("TOKEN_VALUE_PRINTED=FALSE")
    return 0


def clear() -> int:
    TARGET.unlink(missing_ok=True)
    print("OPENAI_APPS_CHALLENGE_CLEAR=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p_set = sub.add_parser("set")
    p_set.add_argument("--token-file", required=True)
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--token-file", required=True)
    sub.add_parser("clear")
    args = parser.parse_args()

    if args.command == "status":
        return status()
    if args.command == "set":
        return set_token(Path(args.token_file))
    if args.command == "verify":
        return verify(Path(args.token_file))
    if args.command == "clear":
        return clear()
    raise SystemExit("UNKNOWN_COMMAND")


if __name__ == "__main__":
    raise SystemExit(main())
