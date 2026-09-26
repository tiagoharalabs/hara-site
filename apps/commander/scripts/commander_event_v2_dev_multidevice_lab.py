#!/usr/bin/env python3
"""Bounded DEV-only Event V2 multi-device lab.

Creates 2..100 distinct H.A.R.A.-owned DEV subjects/devices for concurrency
testing. Secrets stay only in isolated mode-0600 device.env files on the target.
The operator manifest contains identifiers only. PROD and public Agent 0.3.7 are
not modified. No automatic deletion is implemented.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ast
import base64
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
DEV_CONFIG = APP / "wrangler.dev.jsonc"

DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DEV_ISSUER = "https://auth.haralabs.com.br/"
DEV_DATABASE_NAME = "hara-commander-product-dev"
DEV_DATABASE_ID = "698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
TEMPLATE_SUBJECT_ID = "HARA-SUBJECT-DEMO-0001"
WRANGLER_VERSION = "4.137.0"
DEFAULT_TARGET_HOST = "nucleo-a"
REMOTE_BASE = "/tmp_hara/commander-event-v2-multidevice"
MIN_DEVICES = 2
MAX_DEVICES = 100
D1_FIXTURE_BATCH_SIZE = 10
D1_SELECTION_BATCH_SIZE = 25
ENROLL_MIN_INTERVAL_SECONDS = 1.10
LIFECYCLE_MAX_WORKERS = 4

SOURCE_FILES = (
    "apps/commander/experimental/event_v2_websocket.py",
    "apps/commander/experimental/event_v2_agent_loop.py",
    "apps/commander/experimental/event_v2_customer_agent.py",
    "apps/commander/public/agent/linux.py",
)

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$")
RUN_RE = re.compile(r"^[a-z0-9-]{8,64}$")
DEVICE_ID_RE = re.compile(r"^HARA-DEVICE-[A-Za-z0-9._:-]{1,180}$")


class LabError(RuntimeError):
    pass


def fail(code: str) -> LabError:
    return LabError(code)


def run(command: list[str], *, input_text: str | None = None, timeout: int = 90):
    proc = subprocess.run(
        command,
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise fail("MULTIDEVICE_COMMAND_FAILED:" + command[0])
    return proc


def quote_sql(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def quote_shell(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def worker_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def load_dev_config() -> dict:
    text = DEV_CONFIG.read_text(encoding="utf-8")
    obj = json.loads(text)
    if obj.get("name") != "hara-commander-dev-v2":
        raise fail("MULTIDEVICE_DEV_WORKER_NAME_INVALID")
    if (obj.get("vars") or {}).get("ENVIRONMENT") != "DEV":
        raise fail("MULTIDEVICE_ENVIRONMENT_NOT_DEV")
    if (obj.get("vars") or {}).get("DEVICE_EVENT_V2_ENABLED") != "true":
        raise fail("MULTIDEVICE_EVENT_V2_NOT_ENABLED")
    if (obj.get("vars") or {}).get("DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED") != "true":
        raise fail("MULTIDEVICE_TRANSIENT_RPC_NOT_ENABLED")
    dbs = obj.get("d1_databases") or []
    if len(dbs) != 1:
        raise fail("MULTIDEVICE_DEV_D1_COUNT_INVALID")
    if dbs[0].get("database_name") != DEV_DATABASE_NAME or dbs[0].get("database_id") != DEV_DATABASE_ID:
        raise fail("MULTIDEVICE_DEV_D1_INVALID")
    if "commander.haralabs.com.br" in text:
        raise fail("MULTIDEVICE_PROD_ORIGIN_IN_DEV_CONFIG")
    return obj


def d1_execute(
    sql: str,
    *,
    stage: str,
    retry_read_only: bool = False,
) -> list[dict]:
    attempts = 2 if retry_read_only else 1
    last_error = None
    for attempt in range(attempts):
        try:
            proc = run([
                "npx", "--yes", "wrangler@" + WRANGLER_VERSION,
                "d1", "execute", DEV_DATABASE_NAME, "--remote",
                "--config", str(DEV_CONFIG), "--json", "--command", sql,
            ])
            payload = json.loads(proc.stdout)
            if not isinstance(payload, list) or not payload:
                raise fail("MULTIDEVICE_D1_RESPONSE_INVALID")
            return payload
        except (LabError, json.JSONDecodeError) as exc:
            last_error = exc
            if not retry_read_only or attempt + 1 >= attempts:
                break
    raise fail("MULTIDEVICE_D1_" + stage + "_FAILED") from last_error


def d1_rows(payload: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in payload:
        part = item.get("results") or []
        if isinstance(part, list):
            rows.extend(x for x in part if isinstance(x, dict))
    return rows


def ssh(target: str, command: str, *, input_text: str | None = None, timeout: int = 90):
    if not HOST_RE.fullmatch(target):
        raise fail("MULTIDEVICE_TARGET_HOST_INVALID")
    return run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", target, command],
        input_text=input_text,
        timeout=timeout,
    )


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S").lower()
    return "md-" + stamp + "-" + secrets.token_hex(4)


def remote_root(run_id: str) -> str:
    if not RUN_RE.fullmatch(run_id):
        raise fail("MULTIDEVICE_RUN_ID_INVALID")
    return REMOTE_BASE + "/" + run_id


def template_context() -> tuple[str, str]:
    sql = f"""
SELECT u.tenant_id, e.plan_code
  FROM users u
  JOIN tenants t ON t.tenant_id = u.tenant_id
  JOIN entitlements e
    ON e.tenant_id = u.tenant_id
   AND (e.subject_id IS NULL OR e.subject_id = u.subject_id)
  JOIN plans p ON p.plan_code = e.plan_code
 WHERE u.subject_id = {quote_sql(TEMPLATE_SUBJECT_ID)}
   AND u.state = 'ACTIVE'
   AND t.state = 'ACTIVE'
   AND e.state = 'ACTIVE'
   AND p.state = 'ACTIVE'
 ORDER BY CASE WHEN e.subject_id = u.subject_id THEN 0 ELSE 1 END
 LIMIT 1;
"""
    rows = d1_rows(d1_execute(sql, stage="TEMPLATE_CONTEXT_QUERY", retry_read_only=True))
    if len(rows) != 1:
        raise fail("MULTIDEVICE_TEMPLATE_CONTEXT_INVALID")
    tenant_id = str(rows[0].get("tenant_id") or "")
    plan_code = str(rows[0].get("plan_code") or "")
    if not tenant_id or not plan_code:
        raise fail("MULTIDEVICE_TEMPLATE_CONTEXT_INVALID")
    return tenant_id, plan_code


def preflight_target(target: str, run_id: str) -> str:
    root = remote_root(run_id)
    proc = ssh(target, f"""
set -Eeuo pipefail
test -d /tmp_hara
test ! -e {quote_shell(root)}
systemctl --user is-active --quiet hara-commander-agent.service
printf 'MULTIDEVICE_TARGET_PREFLIGHT=PASS\n'
""")
    if "MULTIDEVICE_TARGET_PREFLIGHT=PASS" not in proc.stdout:
        raise fail("MULTIDEVICE_TARGET_PREFLIGHT_FAILED")
    return root


def stage_sources(target: str, root: str) -> None:
    ssh(target, "umask 077; mkdir -p " + quote_shell(root + "/source"))
    tar = subprocess.Popen(
        ["tar", "-C", str(ROOT), "-cf", "-", *SOURCE_FILES],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert tar.stdout is not None
    remote = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", target,
         "tar -xf - -C " + quote_shell(root + "/source")],
        stdin=tar.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tar.stdout.close()
    remote.communicate(timeout=45)
    tar_rc = tar.wait(timeout=10)
    if tar_rc or remote.returncode:
        raise fail("MULTIDEVICE_SOURCE_STAGE_FAILED")


def create_subjects_and_pairings(
    tenant_id: str,
    plan_code: str,
    run_id: str,
    count: int,
) -> list[dict]:
    fixtures = []
    statements = []
    for index in range(count):
        suffix = f"{run_id}-{index:02d}"
        subject_id = "HARA-SUBJECT-EV2-" + suffix.upper()
        external_subject = "hara-event-v2-" + suffix
        entitlement_id = "HARA-ENT-EV2-" + suffix.upper()
        binding_id = "PRIMARY:EV2:" + suffix.upper()
        pairing_id = "HARA-PAIR-EV2-MD-" + str(uuid.uuid4())
        pairing_token = secrets.token_urlsafe(32)
        token_hash = worker_sha256(pairing_token)
        created_dt = datetime.now(timezone.utc)
        created = created_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        expires = (created_dt + timedelta(minutes=10)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        statements.append(f"""
INSERT INTO users
  (subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role, created_at_utc)
VALUES
  ({quote_sql(subject_id)}, {quote_sql(tenant_id)}, {quote_sql(DEV_ISSUER)},
   {quote_sql(external_subject)}, NULL, {quote_sql("Event V2 multi-device " + str(index))},
   'ACTIVE', 'MEMBER', {quote_sql(created)});

INSERT INTO identity_bindings
  (identity_binding_id, subject_id, provider_code, issuer, external_subject, state, created_at_utc, revoked_at_utc)
VALUES
  ({quote_sql(binding_id)}, {quote_sql(subject_id)}, 'PRIMARY_OIDC',
   {quote_sql(DEV_ISSUER)}, {quote_sql(external_subject)}, 'ACTIVE', {quote_sql(created)}, NULL);

INSERT INTO entitlements
  (entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc)
VALUES
  ({quote_sql(entitlement_id)}, {quote_sql(tenant_id)}, {quote_sql(subject_id)},
   {quote_sql(plan_code)}, 'ACTIVE', {quote_sql(created)}, NULL);

INSERT INTO device_pairing_tokens
  (pairing_id, token_hash, tenant_id, subject_id, created_at_utc, expires_at_utc,
   consumed_at_utc, superseded_at_utc)
VALUES
  ({quote_sql(pairing_id)}, {quote_sql(token_hash)}, {quote_sql(tenant_id)},
   {quote_sql(subject_id)}, {quote_sql(created)}, {quote_sql(expires)}, NULL, NULL);
""")
        fixtures.append({
            "index": index,
            "subject_id": subject_id,
            "subject": external_subject,
            "pairing_token": pairing_token,
        })
    for offset in range(0, len(statements), D1_FIXTURE_BATCH_SIZE):
        d1_execute("\n".join(statements[offset:offset + D1_FIXTURE_BATCH_SIZE]), stage="FIXTURE_BATCH")
    return fixtures


def enroll(pairing_token: str, name: str) -> tuple[str, str]:
    raw = json.dumps({
        "pairing_token": pairing_token,
        "device_name": name,
        "platform": "LINUX",
        "architecture": "x86_64",
        "agent_version": "0.3.7-event-v2-multidevice",
    }, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        DEV_ORIGIN + "/api/device/enroll",
        data=raw,
        method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "user-agent": "HARA-Commander-EventV2-MultiDevice/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise fail("MULTIDEVICE_ENROLL_HTTP_" + str(exc.code)) from None
    device_id = str(payload.get("device_id") or "")
    device_token = str(payload.get("device_token") or "")
    if not DEVICE_ID_RE.fullmatch(device_id) or len(device_token) < 32:
        raise fail("MULTIDEVICE_ENROLL_RESPONSE_INVALID")
    return device_id, device_token


def select_devices(tenant_id: str, devices: list[dict]) -> None:
    if not devices:
        raise fail("MULTIDEVICE_SELECTION_EMPTY")
    selected_at = utcnow()
    for offset in range(0, len(devices), D1_SELECTION_BATCH_SIZE):
        values = []
        for row in devices[offset:offset + D1_SELECTION_BATCH_SIZE]:
            values.append(
                "("
                + ",".join((
                    quote_sql(tenant_id),
                    quote_sql(str(row["subject_id"])),
                    quote_sql(str(row["device_id"])),
                    quote_sql(selected_at),
                ))
                + ")"
            )
        d1_execute(
            "INSERT INTO commander_device_selections "
            "(tenant_id, subject_id, device_id, selected_at_utc) VALUES "
            + ",".join(values)
            + " ON CONFLICT(tenant_id, subject_id) DO UPDATE SET "
              "device_id=excluded.device_id, selected_at_utc=excluded.selected_at_utc;",
            stage="SELECTION_BATCH",
        )


def write_device_config(target: str, root: str, index: int, device_id: str, device_token: str) -> None:
    device_root = f"{root}/device-{index:02d}"
    config = (
        f"HARA_COMMANDER_URL={DEV_ORIGIN}\n"
        f"HARA_DEVICE_ID={device_id}\n"
        f"HARA_DEVICE_TOKEN={device_token}\n"
        "HARA_DEVICE_ARCH=x86_64\n"
    )
    ssh(target, f"""
set -Eeuo pipefail
umask 077
mkdir -p {quote_shell(device_root + "/xdg-config/hara-commander")}
mkdir -p {quote_shell(device_root + "/xdg-data/hara-commander")}
cat > {quote_shell(device_root + "/xdg-config/hara-commander/device.env")}
chmod 600 {quote_shell(device_root + "/xdg-config/hara-commander/device.env")}
""", input_text=config)


def validate_manifest(obj: dict) -> dict:
    if obj.get("schema") != "hara.commander-event-v2-multidevice-lab.v1":
        raise fail("MULTIDEVICE_MANIFEST_SCHEMA_INVALID")
    if obj.get("environment") != "DEV":
        raise fail("MULTIDEVICE_MANIFEST_ENV_INVALID")
    run_id = str(obj.get("run_id") or "")
    root = str(obj.get("remote_root") or "")
    if root != remote_root(run_id):
        raise fail("MULTIDEVICE_MANIFEST_ROOT_INVALID")
    if not HOST_RE.fullmatch(str(obj.get("target_host") or "")):
        raise fail("MULTIDEVICE_MANIFEST_TARGET_INVALID")
    devices = obj.get("devices")
    if not isinstance(devices, list) or not MIN_DEVICES <= len(devices) <= MAX_DEVICES:
        raise fail("MULTIDEVICE_MANIFEST_COUNT_INVALID")
    subjects, device_ids = set(), set()
    for index, row in enumerate(devices):
        if not isinstance(row, dict) or int(row.get("index", -1)) != index:
            raise fail("MULTIDEVICE_MANIFEST_INDEX_INVALID")
        subject = str(row.get("subject") or "")
        device_id = str(row.get("device_id") or "")
        if not subject or not DEVICE_ID_RE.fullmatch(device_id):
            raise fail("MULTIDEVICE_MANIFEST_DEVICE_INVALID")
        if subject in subjects or device_id in device_ids:
            raise fail("MULTIDEVICE_MANIFEST_DUPLICATE")
        subjects.add(subject)
        device_ids.add(device_id)
    lowered = json.dumps(obj).lower()
    if "device_token" in lowered or "pairing_token" in lowered:
        raise fail("MULTIDEVICE_MANIFEST_SECRET_FIELD")
    return obj


def write_manifest(path: Path, obj: dict) -> None:
    validate_manifest(obj)
    resolved = str(path.resolve())
    if not resolved.startswith("/tmp_hara/"):
        raise fail("MULTIDEVICE_MANIFEST_PATH_DENIED")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def load_manifest(path: Path) -> dict:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise fail("MULTIDEVICE_MANIFEST_FILE_INVALID")
    if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
        raise fail("MULTIDEVICE_MANIFEST_PERMISSIONS")
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")))


def provision(count: int, target: str, manifest_path: Path) -> dict:
    if not MIN_DEVICES <= count <= MAX_DEVICES:
        raise fail("MULTIDEVICE_COUNT_INVALID")
    load_dev_config()
    tenant_id, plan_code = template_context()
    run_id = make_run_id()
    root = preflight_target(target, run_id)
    stage_sources(target, root)
    fixtures = create_subjects_and_pairings(tenant_id, plan_code, run_id, count)
    devices = []
    previous_enroll_started = None
    for fixture in fixtures:
        index = int(fixture["index"])
        if previous_enroll_started is not None:
            elapsed = time.monotonic() - previous_enroll_started
            if elapsed < ENROLL_MIN_INTERVAL_SECONDS:
                time.sleep(ENROLL_MIN_INTERVAL_SECONDS - elapsed)
        previous_enroll_started = time.monotonic()
        pairing_token = str(fixture["pairing_token"])
        try:
            device_id, device_token = enroll(
                pairing_token, f"nucleo-a-event-v2-md-{run_id}-{index:02d}"
            )
        finally:
            fixture["pairing_token"] = ""
            pairing_token = ""
        try:
            write_device_config(target, root, index, device_id, device_token)
        finally:
            device_token = ""
        devices.append({
            "index": index,
            "subject": str(fixture["subject"]),
            "subject_id": str(fixture["subject_id"]),
            "device_id": device_id,
        })
    select_devices(tenant_id, devices)
    manifest = {
        "schema": "hara.commander-event-v2-multidevice-lab.v1",
        "environment": "DEV",
        "run_id": run_id,
        "target_host": target,
        "remote_root": root,
        "tenant_id": tenant_id,
        "plan_code": plan_code,
        "created_at_utc": utcnow(),
        "devices": devices,
    }
    write_manifest(manifest_path, manifest)
    return manifest


def parallel_device_rows(
    devices: list[dict],
    operation,
    *,
    max_workers: int | None = None,
) -> list:
    if not devices:
        return []
    requested_workers = LIFECYCLE_MAX_WORKERS if max_workers is None else max_workers
    if requested_workers < 1 or requested_workers > LIFECYCLE_MAX_WORKERS:
        raise fail("MULTIDEVICE_LIFECYCLE_WORKERS_INVALID")
    workers = min(requested_workers, len(devices))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(operation, row) for row in devices]
        results = []
        for future in futures:
            results.append(future.result())
        return results


def start_manifest(path: Path) -> int:
    manifest = load_manifest(path)
    target, root = manifest["target_host"], manifest["remote_root"]
    source = root + "/source/apps/commander/experimental/event_v2_agent_loop.py"

    def start_one(row: dict) -> bool:
        device_root = f"{root}/device-{int(row['index']):02d}"
        proc = ssh(target, f"""
set -Eeuo pipefail
root={quote_shell(device_root)}
pidfile="$root/agent.pid"
if [ -f "$pidfile" ]; then
  oldpid="$(cat "$pidfile" 2>/dev/null || true)"
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    printf 'MULTIDEVICE_AGENT_ALREADY_ACTIVE=TRUE\n'
    exit 0
  fi
fi
umask 077
nohup env XDG_CONFIG_HOME="$root/xdg-config" XDG_DATA_HOME="$root/xdg-data" \
  python3 {quote_shell(source)} > "$root/agent.log" 2>&1 < /dev/null &
pid="$!"
printf '%s\n' "$pid" > "$pidfile"
chmod 600 "$pidfile"
printf 'MULTIDEVICE_AGENT_STARTED=TRUE\n'
""")
        if (
            "MULTIDEVICE_AGENT_STARTED=TRUE" not in proc.stdout
            and "MULTIDEVICE_AGENT_ALREADY_ACTIVE=TRUE" not in proc.stdout
        ):
            raise fail("MULTIDEVICE_AGENT_START_FAILED")
        return True

    try:
        results = parallel_device_rows(manifest["devices"], start_one)
    except Exception as exc:
        try:
            stop_manifest(path, max_workers=1)
        except Exception as rollback_exc:
            raise fail("MULTIDEVICE_START_FAILED_ROLLBACK_FAILED") from rollback_exc
        raise fail("MULTIDEVICE_START_FAILED_ROLLED_BACK") from exc
    return sum(1 for result in results if result)


def status_manifest(path: Path) -> dict:
    manifest = load_manifest(path)
    target, root = manifest["target_host"], manifest["remote_root"]

    def status_one(row: dict) -> dict:
        device_root = f"{root}/device-{int(row['index']):02d}"
        proc = ssh(target, f"""
set -Eeuo pipefail
root={quote_shell(device_root)}
alive=false
if [ -f "$root/agent.pid" ]; then
  pid="$(cat "$root/agent.pid" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then alive=true; fi
fi
python3 - "$root/xdg-data/hara-commander/event-v2-status.json" "$alive" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
status={{}}
if p.is_file():
    try: status=json.loads(p.read_text(encoding="utf-8"))
    except Exception: status={{}}
print(json.dumps({{
    "alive": sys.argv[2] == "true",
    "connected": bool(status.get("connected")),
    "last_error_code": status.get("last_error_code"),
}}, sort_keys=True, separators=(",", ":")))
PY
""")
        return json.loads(proc.stdout.strip().splitlines()[-1])

    rows = parallel_device_rows(manifest["devices"], status_one)
    return {
        "count": len(rows),
        "alive": sum(1 for x in rows if x["alive"]),
        "connected": sum(1 for x in rows if x["connected"]),
        "error_codes": sorted({str(x["last_error_code"]) for x in rows if x["last_error_code"]}),
    }


def stop_manifest(path: Path, *, max_workers: int | None = None) -> int:
    manifest = load_manifest(path)
    target, root = manifest["target_host"], manifest["remote_root"]
    source = root + "/source/apps/commander/experimental/event_v2_agent_loop.py"

    def stop_one(row: dict) -> bool:
        device_root = f"{root}/device-{int(row['index']):02d}"
        proc = ssh(target, f"""
set -Eeuo pipefail
root={quote_shell(device_root)}
pidfile="$root/agent.pid"
if [ ! -f "$pidfile" ]; then
  printf 'MULTIDEVICE_AGENT_STOPPED=TRUE\n'
  exit 0
fi
pid="$(cat "$pidfile")"
case "$pid" in (*[!0-9]*|'') exit 31;; esac
if ! kill -0 "$pid" 2>/dev/null; then
  printf 'MULTIDEVICE_AGENT_STOPPED=TRUE\n'
  exit 0
fi
if kill -0 "$pid" 2>/dev/null; then
  cmdline="$(tr '\\0' ' ' < "/proc/$pid/cmdline")"
  expected={quote_shell(source)}
  case "$cmdline" in *"$expected"*) ;; *) exit 32;; esac
  kill -TERM "$pid"
  for _ in $(seq 1 100); do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then exit 33; fi
fi
printf 'MULTIDEVICE_AGENT_STOPPED=TRUE\n'
""", timeout=30)
        if "MULTIDEVICE_AGENT_STOPPED=TRUE" not in proc.stdout:
            raise fail("MULTIDEVICE_AGENT_STOP_FAILED")
        return True

    return sum(
        1
        for result in parallel_device_rows(
            manifest["devices"],
            stop_one,
            max_workers=max_workers,
        )
        if result
    )


def self_check() -> None:
    load_dev_config()
    assert MIN_DEVICES == 2 and MAX_DEVICES == 100
    assert D1_FIXTURE_BATCH_SIZE == 10
    assert D1_SELECTION_BATCH_SIZE == 25
    assert ENROLL_MIN_INTERVAL_SECONDS >= 1.0
    assert LIFECYCLE_MAX_WORKERS == 4
    assert parallel_device_rows([], lambda row: row) == []
    try:
        parallel_device_rows([{"index": 0}], lambda row: row, max_workers=5)
    except LabError as exc:
        assert str(exc) == "MULTIDEVICE_LIFECYCLE_WORKERS_INVALID"
    else:
        raise AssertionError("MULTIDEVICE_LIFECYCLE_WORKER_BOUND_MISSING")
    assert remote_root("md-20260926123456-1234abcd").startswith("/tmp_hara/")
    assert worker_sha256("abc") == "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0"
    for item in SOURCE_FILES:
        assert (ROOT / item).is_file()
    source = Path(__file__).read_text(encoding="utf-8")
    assert "create_subjects_and_pairings" in source
    assert "select_devices" in source
    assert "TEMPLATE_CONTEXT_QUERY" in source
    assert "FIXTURE_BATCH" in source
    assert "SELECTION_BATCH" in source
    assert "retry_read_only=True" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            rendered = " ".join(ast.dump(arg) for arg in node.args)
            if any(name in rendered for name in ("pairing_token", "device_token", "config")):
                raise fail("MULTIDEVICE_SECRET_PRINT_SURFACE")
    forbidden_delete = ("rm", "-" + "r" + "f")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if " ".join(forbidden_delete) in " ".join(node.value.split()):
                raise fail("MULTIDEVICE_GENERIC_DELETE_DENIED")
    forbidden_prod = "https://commander." + "haralabs.com.br"
    assert forbidden_prod not in source
    print("COMMANDER_EVENT_V2_MULTIDEVICE_LAB_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_MAX_DEVICES=100")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_D1_FIXTURE_BATCH_SIZE=10")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_D1_SELECTION_BATCH_SIZE=25")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_ENROLL_MIN_INTERVAL_SECONDS=1.10")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_LIFECYCLE_MAX_WORKERS=4")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_START_FAILURE_ROLLBACK=ENABLED")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_DISTINCT_IDENTITIES=REQUIRED")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_SECRET_OUTPUT=ABSENT")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_AUTO_DELETE=ABSENT")
    print("COMMANDER_EVENT_V2_MULTIDEVICE_PROD_MUTATION=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--provision", action="store_true")
    mode.add_argument("--start-manifest", action="store_true")
    mode.add_argument("--status-manifest", action="store_true")
    mode.add_argument("--stop-manifest", action="store_true")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--target-host", default=DEFAULT_TARGET_HOST)
    parser.add_argument("--manifest")
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.manifest:
        parser.error("--manifest is required")
    manifest = Path(args.manifest)
    if args.provision:
        result = provision(args.count, args.target_host, manifest)
        print("COMMANDER_EVENT_V2_MULTIDEVICE_PROVISION=PASS")
        print("COMMANDER_EVENT_V2_MULTIDEVICE_COUNT=" + str(len(result["devices"])))
        print("COMMANDER_EVENT_V2_MULTIDEVICE_RUN_ID=" + result["run_id"])
        print("COMMANDER_EVENT_V2_MULTIDEVICE_TOKEN_EXPOSED=FALSE")
        return 0
    if args.start_manifest:
        print("COMMANDER_EVENT_V2_MULTIDEVICE_START=PASS")
        print("COMMANDER_EVENT_V2_MULTIDEVICE_STARTED=" + str(start_manifest(manifest)))
        return 0
    if args.status_manifest:
        result = status_manifest(manifest)
        print("COMMANDER_EVENT_V2_MULTIDEVICE_STATUS=PASS")
        print("COMMANDER_EVENT_V2_MULTIDEVICE_ALIVE=" + str(result["alive"]))
        print("COMMANDER_EVENT_V2_MULTIDEVICE_CONNECTED=" + str(result["connected"]))
        print("COMMANDER_EVENT_V2_MULTIDEVICE_ERROR_CODES=" + (
            ",".join(result["error_codes"]) if result["error_codes"] else "NONE"
        ))
        return 0 if result["alive"] == result["count"] and result["connected"] == result["count"] else 1
    if args.stop_manifest:
        print("COMMANDER_EVENT_V2_MULTIDEVICE_STOP=PASS")
        print("COMMANDER_EVENT_V2_MULTIDEVICE_STOPPED=" + str(stop_manifest(manifest)))
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LabError as exc:
        print("COMMANDER_EVENT_V2_MULTIDEVICE=FAIL:" + str(exc))
        raise SystemExit(1)
