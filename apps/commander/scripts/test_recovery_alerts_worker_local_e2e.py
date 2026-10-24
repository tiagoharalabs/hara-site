#!/usr/bin/env python3
"""Commander #163: disposable loopback Worker + local D1 HTTP gate.

No production/hosted DEV/remote D1 access, real device token or external sink.
Uses only Wrangler --local, synthetic credentials and a temporary directory.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

APP = Path(__file__).resolve().parents[1]
NODE = "/home/sartorius/.nvm/versions/node/v24.15.0/bin/node"
WRANGLER = (Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site")
            / "commander-product-current/node_modules/wrangler/bin/wrangler.js")
DEPS = Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules")
SYNTH_TOKEN = "commander163-loopback-synthetic-not-real-token"
DATABASE = "hara-recovery-loopback"
PREFIX = "hara.commander.recovery"
TIME_LIMIT = 28


def checked(argv, *, timeout=35, cwd=None, env=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                            timeout=timeout, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f"RC={result.returncode} CMD={argv[:5]}"
                           f" OUT={result.stdout[-850:]} ERR={result.stderr[-1100:]}")
    return result


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def req(url, method="GET", data=None, token=None):
    headers = {"content-type": "application/json"}
    if token is not None:
        headers["authorization"] = "Bearer " + token
    raw = json.dumps(data, separators=(",", ":")).encode() if data is not None else None
    request = urllib.request.Request(url, data=raw, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=8) as r:
            data=r.read(16384).decode()
            try: return r.status,json.loads(data)
            except ValueError: return r.status,{"text":data[:320]}
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read(16384).decode())
        except ValueError:
            return error.code, {}


def main():
    if not (Path(NODE).is_file() and WRANGLER.is_file() and
            (DEPS / "@modelcontextprotocol/server").is_dir()):
        raise RuntimeError("LOCAL_TEST_DEPENDENCY_UNAVAILABLE")
    link = APP.parents[1] / "node_modules"
    if link.exists() or link.is_symlink():
        raise RuntimeError("LOCAL_TEST_DEPENDENCY_PATH_OCCUPIED")
    with tempfile.TemporaryDirectory(prefix="hara-cmd163-loopback-") as tmp:
        directory = Path(tmp)
        config = directory / "wrangler.local.jsonc"
        persist = directory / "state"
        fixture = directory / "fixture.sql"
        port = free_port()
        origin = f"http://127.0.0.1:{port}"
        conf = {
            "name": "hara-commander-163-loopback",
            "main": str(APP / "src/worker.js"),
            # The installed local workerd binary supports up to 2026-05-01;
            # this is a source HTTP smoke, NOT production parity attestation.
            "compatibility_date": "2026-05-01",
            "vars": {"ENVIRONMENT": "DEV",
                     "STORAGE_MODE": "D1_LOCAL",
                     "COMMANDER_RECOVERY_ALERTS_ENABLED": "true"},
            "d1_databases": [{"binding": "PRODUCT_DB",
                              "database_name": DATABASE,
                              "database_id": "b2ed3fc4-404a-4f5a-8efb-2528f6293617"}],
        }
        config.write_text(json.dumps(conf))
        created = "2026-10-20T00:00:00Z"
        seen = time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(time.time()-300))
        token_hash = base64.urlsafe_b64encode(hashlib.sha256(SYNTH_TOKEN.encode()).digest()).decode().rstrip("=")
        init = (
            "CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);"
            "CREATE TABLE commander_devices("
            "device_id TEXT PRIMARY KEY,tenant_id TEXT,credential_hash TEXT,"
            "enrolled_by_subject_id TEXT,device_name TEXT,platform TEXT,"
            "architecture TEXT,agent_version TEXT,tunnel_mode TEXT,state TEXT,"
            "created_at_utc TEXT,last_seen_at_utc TEXT,revoked_at_utc TEXT,"
            "approval_mode TEXT,local_authorized_until_utc TEXT,"
            "last_metering_sync_at_utc TEXT,last_local_mcp_started_at_utc TEXT,"
            "last_local_mcp_stopped_at_utc TEXT);"
            "INSERT INTO tenants VALUES('HARA-TEST-TENANT');"
            "INSERT INTO commander_devices("
            "device_id,tenant_id,credential_hash,enrolled_by_subject_id,"
            "device_name,platform,architecture,agent_version,tunnel_mode,state,"
            "created_at_utc,last_seen_at_utc,revoked_at_utc,approval_mode)"
            " VALUES('HARA-TEST-DEVICE','HARA-TEST-TENANT',"
            f"'{token_hash}','SYNTHETIC','Synthetic Linux','LINUX','x86_64',"
            f"'0.3.56','OUTBOUND_RELAY','ACTIVE','{created}','{seen}',NULL,"
            "'PERSISTENT_TRUSTED');\n"
        )
        fixture.write_text(init + (APP / "migrations/0037_device_recovery_alerts.sql").read_text())
        env = {**os.environ, "WRANGLER_SEND_METRICS": "false",
               "CI": "true", "NO_COLOR": "1", "BROWSER": "none"}
        link.symlink_to(DEPS, target_is_directory=True)
        process = None
        try:
            checked([NODE, str(WRANGLER), "d1", "execute", DATABASE, "--local",
                     "--config", str(config), "--persist-to", str(persist),
                     "--file", str(fixture), "--yes"], env=env, timeout=35)
            print("D1_LOCAL_MIGRATION_AND_FIXTURE_PASS", flush=True)
            with (directory / "worker.log").open("w") as output:
                process = subprocess.Popen(
                    [NODE, str(WRANGLER), "dev", "--local",
                     "--config", str(config), "--persist-to", str(persist),
                     "--ip", "127.0.0.1", "--port", str(port),
                     "--log-level", "error", "--test-scheduled",
                     "--show-interactive-dev-session=false"],
                    stdout=output, stderr=subprocess.STDOUT,
                    env=env, start_new_session=True)
                deadline = time.monotonic() + TIME_LIMIT
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("WORKER_EXITED " + (directory / "worker.log").read_text()[-2000:])
                    try:
                        status, response = req(origin + "/api/health")
                        if status == 200 and response.get("service") == "hara-commander":
                            break
                    except (urllib.error.URLError, TimeoutError, OSError):
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("WORKER_STARTUP_TIMEOUT " + (directory / "worker.log").read_text()[-1500:])
                    time.sleep(.25)
                print("WORKER_LOOPBACK_HEALTH_PASS", flush=True)
                event = {"schema": "hara.commander.recovery-alert.proposal.v1",
                         "event_id": "e" * 32, "client_incident_key": "a" * 32,
                         "transition_seq": 1, "worker": "executor",
                         "state": "STALLED",
                         "observed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "detector": "LINUX_PROCESS_GUARDIAN"}
                route = origin + "/api/device/recovery-events"
                status, body = req(route, "POST", event)
                assert status == 401, (status, body)
                print("WORKER_UNAUTHENTICATED_DENIED_PASS", flush=True)
                status, body = req(route, "POST", event, SYNTH_TOKEN)
                if status != 202:
                    readback = subprocess.run(
                        [NODE, str(WRANGLER), "d1", "execute", DATABASE,
                         "--local", "--config", str(config),
                         "--persist-to", str(persist),
                         "--command", "SELECT count(*) AS n FROM commander_devices;",
                         "--json"], capture_output=True,text=True,timeout=15,env=env)
                    print("D1_READBACK_RC",readback.returncode,"BODY",readback.stdout[-950:],
                          "LOG",(directory / "worker.log").read_text()[-700:],flush=True)
                assert status == 202 and body.get("ack") == "PERSISTED", (status, body)
                assert body.get("external_delivery_confirmed") is False, body
                print("WORKER_PERSISTED_NOT_EXTERNAL_DELIVERY_PASS", flush=True)
                status, duplicate = req(route, "POST", event, SYNTH_TOKEN)
                assert status == 202 and duplicate.get("duplicate") is True, (status, duplicate)
                assert duplicate.get("event_id") == body.get("event_id")
                print("WORKER_DEDUPLICATION_PASS", flush=True)
                status, conflict = req(route, "POST", {**event, "state": "RECOVERED"}, SYNTH_TOKEN)
                assert status == 409 and conflict.get("code") == "RECOVERY_EVENT_IDEMPOTENCY_CONFLICT", (status, conflict)
                print("WORKER_CONFLICT_DENIED_PASS", flush=True)
                gap = {**event, "event_id": "f" * 32, "transition_seq": 3, "state": "RECOVERED"}
                status, response = req(route, "POST", gap, SYNTH_TOKEN)
                assert status == 409 and response.get("code") == "RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER", (status, response)
                print("WORKER_SEQUENCE_GAP_DENIED_PASS", flush=True)
                status, response = req(route, "POST", {**gap, "transition_seq": 2, "state": "RECOVERING"}, SYNTH_TOKEN)
                assert status == 202 and response.get("ack") == "PERSISTED", (status, response)
                print("WORKER_ORDERED_TRANSITION_PASS", flush=True)
                status, response = req(origin + "/api/portal/recovery-events")
                assert status == 401, (status, response)
                print("WORKER_PORTAL_REQUIRES_AUTH_PASS", flush=True)
                # The server cron is the recovery detector when the device is offline.
                # Its event is an incident in the local D1 database, not a delivered message.
                scheduled = origin + "/__scheduled?cron=%2A%20%2A%20%2A%20%2A%20%2A"
                cron_status, cron_body = req(scheduled)
                assert cron_status == 200, (cron_status, cron_body)
                print("WORKER_SCHEDULED_1MIN_TRIGGER_ACCEPTED_PASS", flush=True)
                def count_server_events():
                    query = checked([NODE,str(WRANGLER),"d1","execute",DATABASE,
                        "--local","--config",str(config),"--persist-to",str(persist),
                        "--command","SELECT COUNT(*) AS n FROM commander_device_recovery_events "
                                    "WHERE origin='SERVER';","--json"],env=env,timeout=15)
                    return json.loads(query.stdout)[0]["results"][0]["n"]
                expected = time.monotonic() + 12
                while count_server_events() != 1:
                    if time.monotonic() > expected:
                        raise RuntimeError("NO_SERVER_OFFLINE_EVENT")
                    time.sleep(.3)
                print("WORKER_REMOTE_OFFLINE_DETECTOR_D1_PASS", flush=True)
                status, heartbeat = req(origin + "/api/device/heartbeat","POST",
                    {"device_id":"HARA-TEST-DEVICE","architecture":"x86_64",
                     "agent_version":"0.3.56","approval_mode":"PERSISTENT_TRUSTED"},
                    SYNTH_TOKEN)
                assert status == 200 and heartbeat.get("ok") is True,(status,heartbeat)
                expected = time.monotonic() + 12
                while count_server_events()!=2:
                    if time.monotonic()>expected:
                        raise RuntimeError("NO_SERVER_RECOVERY_EVENT")
                    time.sleep(.3)
                print("WORKER_REMOTE_RECOVERY_CORRELATED_PASS", flush=True)
                print("RECOVERY_ALERT_WORKER_LOOPBACK_E2E=11_OF_11_PASS", flush=True)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
            if link.is_symlink() and link.resolve() == DEPS.resolve():
                link.unlink()
            print("ISOLATED_RUN_CLEANUP=PASS", flush=True)


if __name__ == "__main__":
    main()
