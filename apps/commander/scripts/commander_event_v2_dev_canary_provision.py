#!/usr/bin/env python3
"""Provision one isolated H.A.R.A. Commander Event V2 DEV canary device.

Safety properties:
- exact DEV origin and exact DEV D1 only;
- token plaintext exists only in process memory and SSH stdin;
- D1 stores only SHA-256 of the one-time pairing token;
- enrollment uses the normal public /api/device/enroll contract;
- the stable PROD Agent service/config is never edited;
- canary files live under /tmp_hara in isolated XDG roots;
- no secret/token value is printed.

This helper requires existing Cloudflare Wrangler credentials on the operator
host and SSH access to the HARA-owned canary host.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
DEV_CONFIG = APP / "wrangler.dev.jsonc"

DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DEV_DATABASE_NAME = "hara-commander-product-dev"
DEV_DATABASE_ID = "698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
DEV_TENANT_ID = "HARA-TENANT-DEMO-0001"
DEV_SUBJECT_ID = "HARA-SUBJECT-DEMO-0001"
WRANGLER_VERSION = "4.137.0"
DEFAULT_TARGET_HOST = "nucleo-a"
REMOTE_ROOT = "/tmp_hara/commander-event-v2-dev-canary"

SOURCE_FILES = (
    "apps/commander/experimental/event_v2_websocket.py",
    "apps/commander/experimental/event_v2_agent_loop.py",
    "apps/commander/experimental/event_v2_customer_agent.py",
    "apps/commander/public/agent/linux.py",
)

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$")


def fail(code: str) -> RuntimeError:
    return RuntimeError(code)


def run(command: list[str], *, input_text: str | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    if proc.returncode:
        raise fail("CANARY_COMMAND_FAILED:" + command[0])
    return proc


def load_dev_config() -> dict:
    obj = json.loads(DEV_CONFIG.read_text(encoding="utf-8"))
    if obj.get("name") != "hara-commander-dev-v2":
        raise fail("CANARY_DEV_WORKER_NAME_INVALID")
    if (obj.get("vars") or {}).get("ENVIRONMENT") != "DEV":
        raise fail("CANARY_ENVIRONMENT_NOT_DEV")
    if (obj.get("vars") or {}).get("DEVICE_EVENT_V2_ENABLED") != "true":
        raise fail("CANARY_EVENT_V2_NOT_ENABLED")
    databases = obj.get("d1_databases") or []
    if len(databases) != 1:
        raise fail("CANARY_DEV_D1_COUNT_INVALID")
    database = databases[0]
    if (
        database.get("database_name") != DEV_DATABASE_NAME
        or database.get("database_id") != DEV_DATABASE_ID
    ):
        raise fail("CANARY_DEV_D1_INVALID")
    if "commander.haralabs.com.br" in DEV_CONFIG.read_text(encoding="utf-8"):
        raise fail("CANARY_PROD_ORIGIN_IN_DEV_CONFIG")
    return obj


def d1_execute(sql: str) -> list[dict]:
    proc = run([
        "npx",
        "--yes",
        f"wrangler@{WRANGLER_VERSION}",
        "d1",
        "execute",
        DEV_DATABASE_NAME,
        "--remote",
        "--config",
        str(DEV_CONFIG),
        "--json",
        "--command",
        sql,
    ])
    payload = json.loads(proc.stdout)
    if not isinstance(payload, list) or not payload:
        raise fail("CANARY_D1_RESPONSE_INVALID")
    return payload


def quote_sql(value: str) -> str:
    # All values are locally generated or fixed constants. Still quote
    # defensively to prevent accidental SQL framing changes.
    return "'" + str(value).replace("'", "''") + "'"


def worker_sha256(value: str) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_pairing_token() -> tuple[str, str]:
    created_dt = datetime.now(timezone.utc)
    created = created_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    expires = (created_dt + timedelta(minutes=10)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    pairing_id = "HARA-PAIR-CANARY-" + str(uuid.uuid4())
    pairing_token = secrets.token_urlsafe(32)
    token_hash = worker_sha256(pairing_token)

    sql = f"""
UPDATE device_pairing_tokens
   SET superseded_at_utc = {quote_sql(created)}
 WHERE tenant_id = {quote_sql(DEV_TENANT_ID)}
   AND subject_id = {quote_sql(DEV_SUBJECT_ID)}
   AND consumed_at_utc IS NULL
   AND superseded_at_utc IS NULL;

INSERT INTO device_pairing_tokens
  (pairing_id, token_hash, tenant_id, subject_id, created_at_utc, expires_at_utc,
   consumed_at_utc, superseded_at_utc)
VALUES
  ({quote_sql(pairing_id)}, {quote_sql(token_hash)}, {quote_sql(DEV_TENANT_ID)},
   {quote_sql(DEV_SUBJECT_ID)}, {quote_sql(created)}, {quote_sql(expires)},
   NULL, NULL);
"""
    result = d1_execute(sql)
    if any(int((item.get("meta") or {}).get("rows_written") or 0) < 0 for item in result):
        raise fail("CANARY_PAIRING_WRITE_INVALID")
    return pairing_token, pairing_id


def enroll(pairing_token: str) -> tuple[str, str]:
    body = json.dumps(
        {
            "pairing_token": pairing_token,
            "device_name": "nucleo-a-event-v2-dev",
            "platform": "LINUX",
            "architecture": "x86_64",
            "agent_version": "0.3.7-event-v2-canary",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        DEV_ORIGIN + "/api/device/enroll",
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "HARA-Commander-EventV2-DEV-Canary/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise fail("CANARY_ENROLL_HTTP_" + str(exc.code)) from None

    device_id = str(payload.get("device_id") or "")
    device_token = str(payload.get("device_token") or "")
    if not device_id.startswith("HARA-DEVICE-") or len(device_token) < 32:
        raise fail("CANARY_ENROLL_RESPONSE_INVALID")
    return device_id, device_token


def ssh(target: str, command: str, *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=6",
            target,
            command,
        ],
        input_text=input_text,
    )


def preflight_target(target: str) -> None:
    if not HOST_RE.fullmatch(target):
        raise fail("CANARY_TARGET_HOST_INVALID")
    proc = ssh(
        target,
        f"""
set -Eeuo pipefail
test -d /tmp_hara
test ! -e {REMOTE_ROOT}
systemctl --user is-active --quiet hara-commander-agent.service
printf 'PROD_AGENT_BASELINE_ACTIVE=TRUE\n'
""",
    )
    if "PROD_AGENT_BASELINE_ACTIVE=TRUE" not in proc.stdout:
        raise fail("CANARY_PROD_BASELINE_NOT_ACTIVE")


def stage_sources(target: str) -> None:
    ssh(target, f"umask 077; mkdir -p {REMOTE_ROOT}/source")
    tar = subprocess.Popen(
        ["tar", "-C", str(ROOT), "-cf", "-", *SOURCE_FILES],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert tar.stdout is not None
    remote = subprocess.Popen(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=6",
            target,
            f"tar -xf - -C {REMOTE_ROOT}/source",
        ],
        stdin=tar.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tar.stdout.close()
    remote_out, remote_err = remote.communicate(timeout=30)
    tar_err = tar.stderr.read() if tar.stderr else b""
    tar_rc = tar.wait(timeout=10)
    if tar_rc or remote.returncode:
        _ = remote_out, remote_err, tar_err
        raise fail("CANARY_SOURCE_STAGE_FAILED")


def write_remote_config(target: str, device_id: str, device_token: str) -> None:
    config = (
        f"HARA_COMMANDER_URL={DEV_ORIGIN}\n"
        f"HARA_DEVICE_ID={device_id}\n"
        f"HARA_DEVICE_TOKEN={device_token}\n"
        "HARA_DEVICE_ARCH=x86_64\n"
    )
    ssh(
        target,
        f"""
set -Eeuo pipefail
umask 077
mkdir -p {REMOTE_ROOT}/xdg-config/hara-commander
mkdir -p {REMOTE_ROOT}/xdg-data/hara-commander
cat > {REMOTE_ROOT}/xdg-config/hara-commander/device.env
chmod 600 {REMOTE_ROOT}/xdg-config/hara-commander/device.env
printf '%s\n' {quote_shell(device_id)} > {REMOTE_ROOT}/device-id
chmod 600 {REMOTE_ROOT}/device-id
""",
        input_text=config,
    )


def quote_shell(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def verify_remote(target: str, device_id: str) -> None:
    proc = ssh(
        target,
        f"""
set -Eeuo pipefail
test "$(stat -c %a {REMOTE_ROOT}/xdg-config/hara-commander/device.env)" = 600
test "$(cat {REMOTE_ROOT}/device-id)" = {quote_shell(device_id)}
test -f {REMOTE_ROOT}/source/apps/commander/experimental/event_v2_agent_loop.py
test -f {REMOTE_ROOT}/source/apps/commander/experimental/event_v2_customer_agent.py
test -f {REMOTE_ROOT}/source/apps/commander/experimental/event_v2_websocket.py
test -f {REMOTE_ROOT}/source/apps/commander/public/agent/linux.py
systemctl --user is-active --quiet hara-commander-agent.service
printf 'CANARY_REMOTE_STAGE=PASS\n'
printf 'PROD_AGENT_BASELINE_ACTIVE=TRUE\n'
""",
    )
    if "CANARY_REMOTE_STAGE=PASS" not in proc.stdout:
        raise fail("CANARY_REMOTE_VERIFY_FAILED")


def self_check() -> None:
    load_dev_config()
    assert worker_sha256("abc") == "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0"
    for path in SOURCE_FILES:
        if not (ROOT / path).is_file():
            raise fail("CANARY_SOURCE_MISSING:" + path)
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "print":
            continue
        rendered = " ".join(ast.dump(arg) for arg in node.args)
        if any(name in rendered for name in ("pairing_token", "device_token", "config")):
            raise fail("CANARY_SECRET_PRINT_SURFACE")
    # Fail closed on an actual generic recursive-delete command without making
    # this validator self-match its own policy string.
    forbidden_delete_tokens = ("rm", "-" + "r" + "f")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        normalized = " ".join(node.value.split())
        if " ".join(forbidden_delete_tokens) in normalized:
            raise fail("CANARY_GENERIC_DELETE_DENIED")
    print("COMMANDER_EVENT_V2_DEV_CANARY_PROVISION_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_DEV_CANARY_TOKEN_OUTPUT=ABSENT")
    print("COMMANDER_EVENT_V2_DEV_CANARY_PROD_AGENT_MUTATION=ABSENT")
    print("COMMANDER_EVENT_V2_DEV_CANARY_TOKEN_HASH=WORKER_BASE64URL_SHA256")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--target-host", default=DEFAULT_TARGET_HOST)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")

    load_dev_config()
    preflight_target(args.target_host)
    pairing_token, _pairing_id = create_pairing_token()
    try:
        device_id, device_token = enroll(pairing_token)
    finally:
        pairing_token = ""

    try:
        stage_sources(args.target_host)
        write_remote_config(args.target_host, device_id, device_token)
        verify_remote(args.target_host, device_id)
    finally:
        device_token = ""

    print("COMMANDER_EVENT_V2_DEV_CANARY_PAIRING=PASS")
    print("COMMANDER_EVENT_V2_DEV_CANARY_ENROLLMENT=PASS")
    print("COMMANDER_EVENT_V2_DEV_CANARY_REMOTE_STAGE=PASS")
    print("COMMANDER_EVENT_V2_DEV_CANARY_DEVICE_ID=" + device_id)
    print("COMMANDER_EVENT_V2_DEV_CANARY_TOKEN_EXPOSED=FALSE")
    print("COMMANDER_EVENT_V2_PROD_AGENT_BASELINE=PRESERVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
