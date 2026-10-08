#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT_PATH = APP / "public/agent/linux.py"
WORKER = (APP / "src/worker.js").read_text(encoding="utf-8")
HTML = (APP / "public/index.html").read_text(encoding="utf-8")
JS = (APP / "public/app.js").read_text(encoding="utf-8")
MIGRATION = APP / "migrations/0029_local_tunnel_authorization.sql"
AGENT_SOURCE = AGENT_PATH.read_text(encoding="utf-8")
INSTALLER = (APP / "public/install/linux.sh").read_text(encoding="utf-8")

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_LOCAL_TUNNEL_{code}=FAIL")
    print(f"COMMANDER_LOCAL_TUNNEL_{code}=PASS")

# Control-plane contract.
need("const PRODUCT_LEASE_TTL_SECONDS = 6 * 60 * 60;" in WORKER, "LEASE_6H")
need("DEVICE_AUTHORIZATION_CODE_TTL_SECONDS = 10 * 60" in WORKER, "AUTH_CODE_10M")
need("commander_device_authorization_codes" in MIGRATION.read_text(encoding="utf-8"), "AUTH_CODE_TABLE")
need("local_authorized_until_utc" in MIGRATION.read_text(encoding="utf-8"), "DEVICE_AUTH_UNTIL")
need("/api/portal/devices/authorization-code" in WORKER, "PORTAL_AUTH_CODE_ROUTE")
need("DEVICE_AUTHORIZATION_CODE_INVALID" in WORKER, "ONE_TIME_CODE_FAIL_CLOSED")
need("tunnel_mode='LOCAL_TUNNEL'" in WORKER, "DEVICE_LOCAL_TUNNEL_STATE")
need("manual_reauthorization_required = localTunnel" in WORKER, "MANUAL_REAUTH_LEASE")
need("DEVICE_LOCAL_TUNNEL_DIRECT_PATH_REQUIRED" in WORKER, "REMOTE_RELAY_DENIED")
need("DEVICE_AUTHORIZATION_FORBIDDEN: 403" in WORKER, "HTTP_AUTH_FORBIDDEN")
need("DEVICE_AUTHORIZATION_CODE_INVALID: 403" in WORKER, "HTTP_AUTH_CODE_INVALID")
need("DEVICE_AUTHORIZATION_CODE_ALREADY_USED: 409" in WORKER, "HTTP_AUTH_CODE_REPLAY")
need("LOCAL_TUNNEL_PLATFORM_PENDING: 409" in WORKER, "HTTP_PLATFORM_PENDING")
need("DEVICE_TRANSPORT_MODE_INVALID: 400" in WORKER, "HTTP_TRANSPORT_INVALID")
need("DIRECT_PATH_REQUIRED" in (APP / "src/customer-mcp.mjs").read_text(encoding="utf-8"), "REMOTE_MCP_DIRECT_PATH_STATE")

# Portal UX.
need("Autorização local por 6 horas" in HTML, "PORTAL_6H_COPY")
need("hara-commander authorize" in HTML, "PORTAL_AUTHORIZE_COMMAND")
need("OpenAI Secure MCP Tunnel" in HTML, "PORTAL_OPENAI_TUNNEL")
need("data-authorize-device" in JS, "PORTAL_AUTHORIZE_ACTION")
need("/api/portal/devices/authorization-code" in JS, "PORTAL_AUTH_CODE_CALL")
need("authorization_active" in JS, "PORTAL_AUTH_STATUS")

# Agent transport boundary.
need('TRANSPORT_MODES = {"OUTBOUND_RELAY","LOCAL_TUNNEL"}' in AGENT_SOURCE, "AGENT_TRANSPORT_MODES")
need('if transport_mode(config)=="LOCAL_TUNNEL":' in AGENT_SOURCE, "LOCAL_TUNNEL_BRANCH")
local_branch = AGENT_SOURCE.split('if transport_mode(config)=="LOCAL_TUNNEL":',1)[1].split("last_heartbeat=0.0",1)[0]
need("/api/device/calls/next" not in local_branch, "LOCAL_TUNNEL_ZERO_CALL_POLL")
need("/api/device/heartbeat" not in local_branch, "LOCAL_TUNNEL_ZERO_HEARTBEAT")
need("require_local_product_authority" in AGENT_SOURCE, "LOCAL_MCP_LEASE_GATE")
need("PRODUCT_LEASE_TRANSPORT_MISMATCH" in AGENT_SOURCE, "LOCAL_MCP_LEASE_BINDING")
need("LOCAL_TUNNEL_USAGE_MODE_UNSUPPORTED" in AGENT_SOURCE, "LOCAL_TUNNEL_QUOTA_FAIL_CLOSED")
need("configure_openai_tunnel" in AGENT_SOURCE and "tunnel-client" in AGENT_SOURCE, "OPENAI_TUNNEL_CLI")
need('CONTROL_PLANE_API_KEY=' in AGENT_SOURCE, "OPENAI_TUNNEL_KEY_ENVFILE")
need("--mcp-command" in AGENT_SOURCE and " mcp" in AGENT_SOURCE, "OPENAI_TUNNEL_STDIO")
need("hara-commander-openai-tunnel.service" in AGENT_SOURCE, "OPENAI_TUNNEL_SERVICE")
need('"--health-listen-addr","127.0.0.1:0"' in AGENT_SOURCE, "OPENAI_TUNNEL_EPHEMERAL_HEALTH")
need('Restart=on-failure' in AGENT_SOURCE and 'RestartSec=15' in AGENT_SOURCE, "OPENAI_TUNNEL_SYSTEMD_BACKOFF")
need('OPENAI_TUNNEL_ID_INVALID' in AGENT_SOURCE and 'OPENAI_TUNNEL_API_KEY_INVALID' in AGENT_SOURCE, "OPENAI_TUNNEL_CREDENTIAL_FORMAT_GUARD")
need('TUNNEL_CLIENT_VERSION="0.0.15"' in INSTALLER, "INSTALLER_TUNNEL_PIN")
need('https://persistent.oaistatic.com/tunnel-client/v0.0.15' in INSTALLER, "INSTALLER_TUNNEL_OFFICIAL_ORIGIN")
need('8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1' in INSTALLER, "INSTALLER_TUNNEL_AMD64_SHA")
need('c51bfd883fc22e3445494a03c0179875176564bde470661b308fd83af5d01abb' in INSTALLER, "INSTALLER_TUNNEL_ARM64_SHA")
need('OPENAI_TUNNEL_CLIENT_SHA256_MISMATCH' in INSTALLER, "INSTALLER_TUNNEL_HASH_FAIL_CLOSED")
need('OPENAI_TUNNEL_CLIENT_INTEGRITY=PASS' in INSTALLER, "INSTALLER_TUNNEL_INTEGRITY_MARKER")
need('TUNNEL_CLIENT="$BIN_DIR/tunnel-client"' in INSTALLER, "INSTALLER_TUNNEL_PRIVATE_PATH")
need('install_tunnel_client' in INSTALLER[INSTALLER.index('  update)'):INSTALLER.index('  uninstall)')], "UPDATE_PREPARES_TUNNEL_CLIENT")
need('hara-commander-openai-tunnel.service' in INSTALLER[INSTALLER.index('  uninstall)'):], "UNINSTALL_TUNNEL_SERVICE")
need('tunnel-client/hara-commander.yaml' in INSTALLER[INSTALLER.index('  uninstall)'):], "UNINSTALL_TUNNEL_PROFILE")
need('HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT' in AGENT_SOURCE, "DOCTOR_LOCAL_DATA_PLANE")
need('HARA_COMMANDER_CONTROL_PLANE_HEALTH=' in AGENT_SOURCE and 'DEGRADED_OPTIONAL' in AGENT_SOURCE, "DOCTOR_CONTROL_PLANE_OPTIONAL")
need('product_transport_mode' in AGENT_SOURCE, "SUPPORT_TRANSPORT_MODE")
need("authorize_local_tunnel" in AGENT_SOURCE, "LOCAL_AUTH_CLI")
need("def local_usage_report(config):" in AGENT_SOURCE, "LOCAL_USAGE_REPORT")
need("transport_mode='LOCAL_MCP'" in AGENT_SOURCE, "LOCAL_USAGE_ONLY_LOCAL_MCP")
need("local_usage_baseline_event_id" in AGENT_SOURCE and "local_usage_device_id" in AGENT_SOURCE, "LOCAL_USAGE_DEVICE_BASELINE")
need("commander_device_usage_totals" in WORKER and "commander_device_usage_daily" in WORKER, "CLOUD_AGGREGATE_USAGE_TABLES")
need("MAX(commander_device_usage_totals.lifetime_units,excluded.lifetime_units)" in WORKER, "USAGE_SYNC_IDEMPOTENT_TOTAL")
need("MAX(commander_device_usage_daily.units,excluded.units)" in WORKER, "USAGE_SYNC_IDEMPOTENT_DAILY")
need("reconcileLocalUsageReport(env, device, body?.usage_report || null)" in WORKER and ".catch(() => ({ accepted:false }))" in WORKER, "USAGE_SYNC_NONBLOCKING_AUTH")
need("Number(local7d?.units || 0)" in WORKER and "Number(localTotal?.units || 0)" in WORKER, "PORTAL_USAGE_INCLUDES_LOCAL")
need("LOCAL_METERING_MIN_INTERVAL_SECONDS = 60 * 60" in WORKER, "METERING_SERVER_MIN_INTERVAL_1H")
need("LOCAL_METERING_MIN_INTERVAL_SECONDS = 60 * 60" in AGENT_SOURCE, "METERING_AGENT_MIN_INTERVAL_1H")
need("/api/device/metering-sync" in WORKER and "/api/device/metering-sync" in AGENT_SOURCE, "METERING_SYNC_ROUTE")
need("commander_device_metering_events" in WORKER and "commander_device_metering_events" in MIGRATION.read_text(encoding="utf-8"), "METERING_EVENT_TABLE")
need("MCP_START" in WORKER and "MCP_STOP" in WORKER, "METERING_START_STOP_ONLY")
need("LOCAL_METERING_SESSION_TOO_SHORT" in WORKER, "METERING_SERVER_SHORT_SESSION_GUARD")
need("SESSION_UNDER_MIN_INTERVAL" in AGENT_SOURCE, "METERING_AGENT_SHORT_SESSION_GUARD")
need("LOCAL_MCP_SESSION_START" in AGENT_SOURCE and "LOCAL_MCP_SESSION_STOP" in AGENT_SOURCE, "MCP_SESSION_LIFECYCLE_EVENTS")
need("local_metering_sync_due" in AGENT_SOURCE, "METERING_LOCAL_THROTTLE")
need("METERING_SYNC_DEGRADED" in AGENT_SOURCE, "METERING_BEST_EFFORT")
need('"customer_content_included":False' in AGENT_SOURCE, "METERING_NO_CUSTOMER_CONTENT")
need("local_lifetime_units" in WORKER and "customer_content_persisted:false" in WORKER, "METERING_MINIMAL_CLOUD_TELEMETRY")
need("allocation_cap_units: localTunnel ? context.unit_limit : LOCAL_BUDGET_BLOCK_UNITS" in WORKER, "LOCAL_TUNNEL_FULL_REMAINING_BUDGET")
lease_block = WORKER.split("async function deviceProductLease",1)[1].split("async function ensureSecondaryMcpBinding",1)[0]
need("validateDeviceAuthorizationCode" in lease_block, "AUTH_CODE_READONLY_VALIDATE")
need("consumeValidatedDeviceAuthorizationCode" in lease_block, "AUTH_CODE_ATOMIC_CONSUME")
need(
    lease_block.index("validateDeviceAuthorizationCode")
    < lease_block.index("consumeValidatedDeviceAuthorizationCode")
    < lease_block.index("issueDeviceBudgetBlock"),
    "AUTH_BEFORE_BUDGET_ORDER",
)
need(
    lease_block.index("await signProductLease(env, productLease, origin)")
    < lease_block.index("consumeValidatedDeviceAuthorizationCode"),
    "SIGNER_PREFLIGHT_BEFORE_CONSUME",
)
need('HARA_COMMANDER_TRANSPORT_MODE=$TRANSPORT_MODE' in INSTALLER, "INSTALLER_TRANSPORT_CONFIG")
need('TRANSPORT_MODE="LOCAL_TUNNEL"' in INSTALLER, "INSTALLER_LOCAL_TUNNEL_DEFAULT")
need('NEXT_COMMAND=hara-commander tunnel configure' in INSTALLER, "INSTALLER_TUNNEL_NEXT")
need('AUTHORIZATION_COMMAND=hara-commander authorize' in INSTALLER, "INSTALLER_AUTHORIZE_NEXT")
need('transport_mode(config)!="LOCAL_TUNNEL"' in AGENT_SOURCE, "SESSION_CLOSE_ZERO_CLOUD")

# Migration is valid against the relevant existing table shape.
with sqlite3.connect(":memory:") as db:
    db.executescript("""
      CREATE TABLE commander_devices(
        device_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL
      );
    """)
    db.executescript(MIGRATION.read_text(encoding="utf-8"))
    cols = {row[1] for row in db.execute("PRAGMA table_info(commander_devices)")}
    need("local_authorized_until_utc" in cols, "MIGRATION_DEVICE_COLUMN")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    need("commander_device_authorization_codes" in tables, "MIGRATION_AUTH_TABLE")
    need("commander_device_usage_totals" in tables, "MIGRATION_USAGE_TOTALS")
    need("commander_device_usage_daily" in tables, "MIGRATION_USAGE_DAILY")
    need("commander_device_metering_events" in tables, "MIGRATION_METERING_EVENTS")
    device_cols={row[1] for row in db.execute("PRAGMA table_info(commander_devices)")}
    need("last_metering_sync_at_utc" in device_cols, "MIGRATION_LAST_METERING_SYNC")
    need("last_local_mcp_started_at_utc" in device_cols, "MIGRATION_LAST_MCP_START")
    need("last_local_mcp_stopped_at_utc" in device_cols, "MIGRATION_LAST_MCP_STOP")

# Load Agent without executing main.
ns = {"__name__": "hara_agent_local_tunnel_test", "__file__": str(AGENT_PATH)}
exec(compile(AGENT_SOURCE, str(AGENT_PATH), "exec"), ns)

with tempfile.TemporaryDirectory(prefix="hara-local-tunnel-test-") as td:
    root = Path(td)
    config_dir = root / "config"
    data_dir = root / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    cfg = config_dir / "device.env"
    cfg.write_text(
        "HARA_COMMANDER_URL=https://example.invalid\n"
        "HARA_DEVICE_ID=HARA-DEVICE-TEST\n"
        "HARA_DEVICE_TOKEN=TEST_DEVICE_TOKEN\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n"
        "HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL\n",
        encoding="utf-8",
    )
    os.chmod(cfg, 0o600)

    # Rebind file globals into temp.
    ns["CONFIG_FILE"] = cfg
    ns["DATA_DIR"] = data_dir
    ns["RECEIPT_DIR"] = data_dir / "receipts"
    ns["STATUS_FILE"] = data_dir / "runtime-status.json"
    ns["SESSION_FILE"] = data_dir / "operator-session.json"
    ns["CONSOLE_EVENTS_FILE"] = data_dir / "console-events.jsonl"
    ns["OPERATIONS_DB_FILE"] = data_dir / "operations.sqlite3"
    ns["APPROVAL_DIR"] = data_dir / "approvals"
    ns["PREIMAGE_DIR"] = data_dir / "preimages"
    ns["TUNNEL_ENV_FILE"] = config_dir / "openai-tunnel.env"
    ns["TUNNEL_UNIT_FILE"] = config_dir / "systemd/user/hara-commander-openai-tunnel.service"

    config = ns["load_config"]()
    need(ns["transport_mode"](config) == "LOCAL_TUNNEL", "CONFIG_LOCAL_TUNNEL")

    # No lease -> fail closed before machine execution.
    ns["post_json"] = lambda *a, **k: (_ for _ in ()).throw(AssertionError("CLOUD_CALL_FOR_LOCAL_MCP"))
    try:
        ns["local_simple_mcp_call"](config, "ping", {})
        raise AssertionError("missing lease accepted")
    except ValueError as exc:
        need(str(exc) == "PRODUCT_LEASE_REQUIRED", "MISSING_LEASE_DENIED")

    auth_state = ns["local_mcp_operational_error"]("PRODUCT_LEASE_REQUIRED", "ping", {})
    need(auth_state["state"] == "AUTHORIZATION_EXPIRED", "EXPIRED_STATE_STRUCTURED")
    need(auth_state["result"]["reauthorize_url"].endswith("/#devices"), "EXPIRED_REAUTH_URL")

    # Insert a verified unmetered 6h local-tunnel lease.
    now = datetime.now(timezone.utc)
    lease = {
        "schema": "hara.commander-device-product-lease.v1",
        "lease_id": "HARA-PRODUCT-LEASE-TEST",
        "authority": "HARA_COMMANDER_CLOUD",
        "device_id": "HARA-DEVICE-TEST",
        "tenant_id": "HARA-TENANT-TEST",
        "entitlement_id": "HARA-ENTITLEMENT-TEST",
        "plan_code": "STANDARD",
        "plan_name": "Standard",
        "grants": ["DEVICE_READ"],
        "meter_id": "HARA_COMMANDER_GOVERNED_INVOKE",
        "period_kind": "NONE",
        "unit_limit": None,
        "usage_mode": "UNMETERED",
        "transport_mode": "LOCAL_TUNNEL",
        "manual_reauthorization_required": True,
        "issued_at_utc": now.isoformat(),
        "valid_until_utc": (now + timedelta(hours=6)).isoformat(),
    }
    ns["verify_product_lease_token"] = lambda _config, token: dict(lease) if token == "SIGNED_TEST" else (_ for _ in ()).throw(ValueError("bad"))
    with ns["_ops_connect"]() as db:
        db.execute(
            "INSERT OR REPLACE INTO product_lease(singleton,lease_json,lease_token,valid_until_utc,updated_at_utc) VALUES(1,?,?,?,?)",
            (json.dumps(lease, sort_keys=True, separators=(",",":")), "SIGNED_TEST", lease["valid_until_utc"], now.isoformat()),
        )
        db.commit()
    result = ns["local_simple_mcp_call"](config, "ping", {})
    need(result.get("state") == "PASS", "VALID_LEASE_LOCAL_EXECUTION")

    # Aggregate usage includes local MCP terminal events only.
    report = ns["local_usage_report"](config)
    need(report["lifetime_units"] >= 1, "LOCAL_USAGE_COUNTS_LOCAL_MCP")
    before = int(report["lifetime_units"])
    ns["append_console_event"](
        "PASS",
        {"tool_id":"hara.ping","request_id":"relay-test","_transport":"OUTBOUND_RELAY"},
        state="COMPLETED",
    )
    after_relay = ns["local_usage_report"](config)
    need(int(after_relay["lifetime_units"]) == before, "LOCAL_USAGE_EXCLUDES_RELAY")

    # Metering is start/stop only and has a local one-hour throttle. The
    # payload carries aggregate counters, never customer content.
    metering_calls=[]
    def fake_metering_post(url,token,payload,timeout=25):
        assert url.endswith("/api/device/metering-sync")
        assert token=="TEST_DEVICE_TOKEN"
        metering_calls.append(json.loads(json.dumps(payload)))
        return {
            "schema":"hara.commander-local-metering-sync-response.v1",
            "ok":True,
            "accepted":True,
            "event_type":payload["event_type"],
            "event_at_utc":datetime.now(timezone.utc).isoformat(),
            "min_interval_seconds":3600,
        }
    ns["post_json"]=fake_metering_post
    ns["_local_meta_set"]("local_metering_last_sync_at_utc","2000-01-01T00:00:00+00:00")
    m1=ns["local_metering_sync"](config,"MCP_START","session-metering",now.isoformat())
    need(m1.get("accepted") is True and len(metering_calls)==1, "METERING_START_SYNC")
    keys=set(metering_calls[0])
    need(keys=={
        "schema","event_type","session_id","session_started_at_utc",
        "session_duration_seconds","agent_version","transport_mode",
        "usage_report","metadata_only","customer_content_included",
    }, "METERING_PAYLOAD_MINIMAL_KEYS")
    need(metering_calls[0]["metadata_only"] is True and metering_calls[0]["customer_content_included"] is False, "METERING_PAYLOAD_PRIVACY")
    m2=ns["local_metering_sync"](config,"MCP_STOP","session-metering",now.isoformat(),1200)
    need(m2.get("reason")=="SESSION_UNDER_MIN_INTERVAL" and len(metering_calls)==1, "METERING_STOP_UNDER_1H_SKIPPED")
    ns["_local_meta_set"]("local_metering_last_sync_at_utc",(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat())
    m3=ns["local_metering_sync"](config,"MCP_STOP","session-metering",now.isoformat(),7200)
    need(m3.get("accepted") is True and len(metering_calls)==2, "METERING_STOP_AFTER_1H_SYNC")
    need(metering_calls[1]["event_type"]=="MCP_STOP" and metering_calls[1]["session_duration_seconds"]==7200, "METERING_STOP_DURATION")

    # Re-enrollment changes device identity and starts a fresh baseline instead
    # of reattributing the previous device's local history.
    config2 = dict(config)
    config2["HARA_DEVICE_ID"] = "HARA-DEVICE-REENROLLED"
    fresh = ns["local_usage_report"](config2)
    need(int(fresh["lifetime_units"]) == 0, "REENROLL_USAGE_BASELINE_ZERO")
    baseline = ns["local_usage_report"](config2)
    need(int(baseline["lifetime_units"]) == 0, "REENROLL_USAGE_BASELINE_STABLE")

    # Restore original device identity for the remaining authorization tests.
    with ns["_ops_connect"]() as restore_db:
        ns["_local_usage_baseline"](restore_db, config)

    # Authorization CLI consumes a portal code without echoing it.
    seen = {}
    ns["getpass"].getpass = lambda _prompt="": "ONE_TIME_SECRET_CODE"
    def fake_refresh(_config, authorization_code=None, requested_transport=None):
        seen["code"] = authorization_code
        seen["transport"] = requested_transport
        return {"product_lease": {"valid_until_utc": lease["valid_until_utc"]}}
    ns["refresh_product_lease"] = fake_refresh
    ns["subprocess"].run = lambda *args, **kwargs: type("R",(),{"returncode":0})()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = ns["authorize_local_tunnel"]()
    need(rc == 0 and seen == {"code":"ONE_TIME_SECRET_CODE","transport":"LOCAL_TUNNEL"}, "AUTHORIZE_CODE_BOUND")
    need("ONE_TIME_SECRET_CODE" not in output.getvalue(), "AUTHORIZE_CODE_NOT_ECHOED")
    need("HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL" in cfg.read_text(encoding="utf-8"), "AUTHORIZE_SETS_LOCAL_TUNNEL")

    # Tunnel config: secret only in 0600 env file, never command argv or unit.
    fake_bin = root / "tunnel-client"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(fake_bin, 0o700)
    calls = []
    ns["shutil"].which = lambda name: str(fake_bin) if name == "tunnel-client" else None
    ns["input"] = lambda _prompt="": "tunnel_0123456789abcdef0123456789abcdef"
    ns["getpass"].getpass = lambda _prompt="": "sk-runtime-TEST-0123456789abcdef0123456789abcdef"
    ns["subprocess"].run = lambda argv, **kwargs: calls.append((list(argv), dict(kwargs))) or type("R",(),{"returncode":0})()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = ns["configure_openai_tunnel"]()
    need(rc == 0, "TUNNEL_CONFIGURE")
    env_text = ns["TUNNEL_ENV_FILE"].read_text(encoding="utf-8")
    unit_text = ns["TUNNEL_UNIT_FILE"].read_text(encoding="utf-8")
    argv_text = json.dumps([call[0] for call in calls])
    need("sk-runtime-TEST-0123456789abcdef0123456789abcdef" in env_text, "TUNNEL_KEY_ENVFILE")
    need(stat.S_IMODE(ns["TUNNEL_ENV_FILE"].stat().st_mode) == 0o600, "TUNNEL_KEY_MODE_0600")
    need("sk-runtime-TEST-0123456789abcdef0123456789abcdef" not in argv_text and "sk-runtime-TEST-0123456789abcdef0123456789abcdef" not in unit_text and "sk-runtime-TEST-0123456789abcdef0123456789abcdef" not in output.getvalue(), "TUNNEL_KEY_NOT_EXPOSED")
    init = calls[0][0]
    need("--tunnel-id" in init and "tunnel_0123456789abcdef0123456789abcdef" in init and "--mcp-command" in init, "TUNNEL_INIT_SHAPE")
    need("--health-listen-addr" in init and "127.0.0.1:0" in init, "TUNNEL_HEALTH_EPHEMERAL")
    need(any("hara-commander mcp" in str(x) for x in init), "TUNNEL_POINTS_LOCAL_MCP")
    # Local-tunnel doctor must remain healthy when the H.A.R.A. control plane is
    # unreachable, provided the signed local lease and OpenAI tunnel are healthy.
    class OfflineOpener:
        def open(self,*_args,**_kwargs):
            raise OSError("control-plane-offline")
    ns["NO_REDIRECT_OPENER"] = OfflineOpener()
    ns["_openai_tunnel_doctor"] = lambda capture=False: (0, "ready")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        doctor_rc = ns["commander_doctor"]()
    doctor_text = output.getvalue()
    need(doctor_rc == 0, "DOCTOR_PASS_WITH_HARA_CLOUD_DOWN")
    need("HARA_COMMANDER_CONTROL_PLANE_HEALTH=DEGRADED_OPTIONAL" in doctor_text, "DOCTOR_CLOUD_OPTIONAL_RUNTIME")
    need("HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT" in doctor_text, "DOCTOR_DIRECT_RUNTIME")

print("COMMANDER_LOCAL_TUNNEL_CONTROL_PLANE=PASS")
