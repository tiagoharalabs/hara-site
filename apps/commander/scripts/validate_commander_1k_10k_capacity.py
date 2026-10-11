#!/usr/bin/env python3
"""Exact-source SQL capacity checks + explicit current-release traffic model.

All generated accounts/devices/sessions live in temporary in-memory SQLite.
No network, cloud writes, customer credentials or running Agents are used.
Local timings are diagnostic only: never report them as D1 or product SLOs.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'apps/commander'
AUTH = (APP / 'src/auth.js').read_text()
LINUX = (APP / 'release-bundles/commercial-0.3.43-v2/agent/linux.py').read_text()
CONFIG = json.loads((APP / 'wrangler.jsonc').read_text())


def integer_constant(source: str, name: str) -> int:
    match = re.search(r'\b' + re.escape(name) + r'\s*=\s*(\d+)\s*[;\n]', source)
    if not match:
        raise AssertionError('CAPACITY_SOURCE_CONSTANT_MISSING:' + name)
    value = int(match.group(1))
    assert value > 0
    return value


def source_sql(function: str) -> str:
    match = re.search(re.escape(function) + r'.*?\.prepare\(\s*`(.*?)`\s*\)', AUTH, re.S)
    if not match:
        raise AssertionError('CAPACITY_SOURCE_SQL_MISSING:' + function)
    sql = match.group(1)
    sql = sql.replace('${SESSION_RETENTION_BATCH}', str(integer_constant(AUTH, 'SESSION_RETENTION_BATCH')))
    assert '${' not in sql, 'UNRECOGNIZED_DYNAMIC_SQL'
    return sql


SESSION_SQL = source_sql('export async function resolvePortalSession')
RETENTION_SQL = source_sql('async function cleanupTerminalPortalSessions')
assert SESSION_SQL.lstrip().startswith('SELECT')
assert RETENTION_SQL.lstrip().startswith('DELETE FROM portal_sessions')


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))], 6)


def database_probe(users: int) -> dict:
    assert users in (1000, 10000)
    db = sqlite3.connect(':memory:')
    try:
        for migration in sorted((APP / 'migrations').glob('*.sql')):
            db.executescript(migration.read_text())
        now = datetime.now(timezone.utc)
        stamp = lambda offset=0: (now + timedelta(days=offset)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        db.executemany('INSERT INTO tenants VALUES (?,?,?,?,?)',
            ((f'CAP-T-{i}', 'Synthetic capacity tenant', 'ACTIVE', 'PRODUCTION', stamp()) for i in range(users)))
        db.executemany('''INSERT INTO users
            (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc)
            VALUES (?,?,?,?,?,?,?)''',
            ((f'CAP-U-{i}', f'CAP-T-{i}', 'https://example.invalid/', f'CAP-SUB-{i}', 'ACTIVE', 'OWNER', stamp()) for i in range(users)))
        session_insert = '''INSERT INTO portal_sessions
            (session_hash,subject_id,created_at_utc,expires_at_utc,last_seen_at_utc,revoked_at_utc)
            VALUES (?,?,?,?,?,?)'''
        db.executemany(session_insert, ((f'CAP-H-{i}', f'CAP-U-{i}', stamp(), stamp(1), stamp(), None) for i in range(users)))
        # 20 terminal sessions/user model historical accumulation, not just fresh data.
        db.executemany(session_insert,
            ((f'CAP-OLD-{i}-{j}', f'CAP-U-{i}', stamp(-60), stamp(-31), stamp(-60), None)
             for i in range(users) for j in range(20)))
        db.executemany('''INSERT INTO device_pairing_tokens
            (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc)
            VALUES (?,?,?,?,?,?,?)''',
            ((f'CAP-P-{i}-{j}',f'CAP-PHASH-{i}-{j}',f'CAP-T-{i}',f'CAP-U-{i}',stamp(),stamp(1),stamp())
             for i in range(users) for j in range(2)))
        db.executemany('''INSERT INTO commander_devices
            (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,
             architecture,agent_version,tunnel_mode,credential_hash,state,created_at_utc,last_seen_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ((f'CAP-D-{i}-{j}',f'CAP-P-{i}-{j}',f'CAP-T-{i}',f'CAP-U-{i}','synthetic-device',
              'LINUX','x86_64','0.3.43','OUTBOUND_RELAY',f'CAP-CRED-{i}-{j}','ACTIVE',stamp(),stamp())
             for i in range(users) for j in range(2)))
        db.commit()
        plan = [row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + SESSION_SQL, ('CAP-H-0',))]
        assert not any(re.search(r'\bSCAN (?:s|portal_sessions)\b', text, re.I) for text in plan)
        assert any('sqlite_autoindex_portal_sessions' in text for text in plan)
        cursor = db.execute(SESSION_SQL, ('CAP-H-0',))
        columns = [c[0] for c in cursor.description]
        tenant_column = columns.index('tenant_id')
        timings = []
        for i in range(users):
            started = time.perf_counter()
            row = db.execute(SESSION_SQL, (f'CAP-H-{i}',)).fetchone()
            timings.append((time.perf_counter()-started)*1000)
            assert row and row[tenant_column] == f'CAP-T-{i}', 'TENANT_IDENTITY_MISMATCH'
        cleanup_plan = [row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + RETENTION_SQL, (stamp(-30), stamp(-30)))]
        assert any('idx_portal_sessions_expiry' in text for text in cleanup_plan)
        assert any('idx_portal_sessions_revoked' in text for text in cleanup_plan)
        assert not any('USE TEMP B-TREE FOR ORDER BY' in text for text in cleanup_plan)
        assert not any(re.search(r'\bSCAN portal_sessions\b', text, re.I) for text in cleanup_plan)
        started = time.perf_counter()
        changes = db.execute(RETENTION_SQL, (stamp(-30), stamp(-30))).rowcount
        cleanup_ms = (time.perf_counter()-started)*1000
        assert changes == 100
        assert db.execute("SELECT COUNT(*) FROM portal_sessions WHERE session_hash LIKE 'CAP-H-%'").fetchone()[0] == users
        return {
            'users':users, 'tenants':users, 'devices':users*2, 'sessions_before_cleanup':users*21,
            'exact_source_session_lookups':users, 'tenant_identity_mismatches':0,
            'lookup_query_plan':plan, 'lookup_local_sqlite_mean_ms':round(statistics.mean(timings),6),
            'lookup_local_sqlite_p95_ms':percentile(timings,0.95),
            'lookup_local_sqlite_p99_ms':percentile(timings,0.99),
            'retention_query_plan':cleanup_plan, 'retention_local_sqlite_ms':round(cleanup_ms,6),
            'terminal_rows_deleted_in_one_statement':changes, 'valid_sessions_preserved':users,
        }
    finally:
        db.close()


def local_tunnel_contract() -> dict:
    tree = ast.parse(LINUX)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    branch = next(n for n in main.body if isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and any(isinstance(c, ast.Constant) and c.value == 'LOCAL_TUNNEL' for c in n.test.comparators))
    assert any(isinstance(n, ast.Return) for n in branch.body), 'LOCAL_TUNNEL_MUST_RETURN_BEFORE_RELAY_LOOP'
    calls = [n.func.id for n in ast.walk(branch) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert 'run_local_tunnel_agent_telemetry' in calls
    assert 'post_json' not in calls
    interval = next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'AGENT_TELEMETRY_INTERVAL_SECONDS' for t in n.targets))
    def arithmetic(n):
        if isinstance(n, ast.Constant) and type(n.value) is int:
            return n.value
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            return arithmetic(n.left)*arithmetic(n.right)
        raise AssertionError('TELEMETRY_CONSTANT_NOT_LITERAL_ARITHMETIC')
    seconds = arithmetic(interval)
    assert seconds == 3600
    return {'local_tunnel_queue_polling_enabled':False, 'local_tunnel_hourly_telemetry_interval_seconds':seconds}


def traffic_model(users: int) -> dict:
    devices = 2*users
    tunnel = local_tunnel_contract()
    idle_seconds = integer_constant(LINUX, 'CALL_POLL_IDLE_SECONDS')
    hot_seconds = integer_constant(LINUX, 'CALL_POLL_HOT_SECONDS')
    heartbeat_seconds = integer_constant(LINUX, 'HEARTBEAT_SECONDS')
    active_humans = 250 if users == 1000 else 2000
    idle_rps = devices*(1/idle_seconds + 1/heartbeat_seconds)
    hot_rps = devices*(1/hot_seconds + 1/heartbeat_seconds)
    monthly_requests_8h = idle_rps*8*3600*30
    rounds = integer_constant(AUTH,'AUTH_RETENTION_MAX_ROUNDS')
    tx_batch = integer_constant(AUTH,'TX_RETENTION_BATCH')
    session_batch = integer_constant(AUTH,'SESSION_RETENTION_BATCH')
    return {
        'registered_users':users,
        'polling_scenario_transport':'OUTBOUND_RELAY_ONLY_NOT_LOCAL_TUNNEL',
        'local_tunnel_contract':tunnel,
        'local_tunnel_hourly_telemetry_only_average_http_rps':round(devices/tunnel['local_tunnel_hourly_telemetry_interval_seconds'],6),
        'local_tunnel_telemetry_exclusions':['START/STOP lifecycle bursts','retries and queued events','lease and metering operations','portal HTTP','tunnel provider traffic','useful tool execution'], 'assumed_online_devices_per_user':2, 'all_assumed_devices_online':devices,
        'assumed_peak_portal_users':active_humans, 'assumed_portal_requests_per_user_per_minute':6,
        'portal_http_rps':active_humans*6/60,
        'public_linux_idle_poll_seconds':idle_seconds, 'public_linux_hot_poll_seconds':hot_seconds,
        'public_linux_presence_heartbeat_seconds':heartbeat_seconds,
        'relay_linux_idle_transport_http_rps':round(idle_rps,3),
        'relay_linux_hot_transport_http_rps':round(hot_rps,3),
        'relay_linux_idle_http_requests_month_8h_day':round(monthly_requests_8h),
        'relay_workers_request_only_usd_month_8h_day':round(5+max(0,monthly_requests_8h-10_000_000)/1_000_000*0.30,2),
        'cost_exclusions':['Workers CPU','D1','Durable Objects','Identity hosting','other account traffic','taxes','tool execution traffic'],
        'pricing_verified_on':'2026-10-11',
        'pricing_source':'https://developers.cloudflare.com/workers/platform/pricing/',
        'old_oidc_cleanup_nominal_max_per_day':24*tx_batch,
        'new_oidc_cleanup_nominal_max_per_day':24*tx_batch*rounds,
        'old_session_cleanup_nominal_max_per_day':24*session_batch,
        'new_session_cleanup_nominal_max_per_day':24*2*session_batch*rounds,
        'maintenance_limits_note':'Maximums, not guaranteed throughput; 5s soft wall budget between rounds, D1 service time and overlapping terminal sets may reduce achieved rows.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    rows = [database_probe(n) for n in (1000,10000)]
    traffic = [traffic_model(n) for n in (1000,10000)]
    assert traffic[1]['relay_linux_idle_transport_http_rps'] == 2333.333
    assert traffic[1]['new_oidc_cleanup_nominal_max_per_day'] == 48000
    assert traffic[1]['new_session_cleanup_nominal_max_per_day'] == 96000
    data = {
        'schema':'hara.commander-1k-10k-capacity-evidence.v1', 'state':'PASS',
        'at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'LOCAL_SQLITE_EXACT_SOURCE_SQL_PLUS_EXPLICIT_TRAFFIC_MODEL',
        'source_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'capacity_model_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'auth_source_sha256':hashlib.sha256(AUTH.encode()).hexdigest(),
        'signed_linux_source_sha256':hashlib.sha256(LINUX.encode()).hexdigest(),
        'cloudflare_live_clients_tested':0, 'production_load_certification':False,
        'event_v2_configured':CONFIG['vars'].get('DEVICE_EVENT_V2_ENABLED')=='true',
        'event_v2_canary_restricted':bool(CONFIG['vars'].get('DEVICE_EVENT_V2_CANARY_DEVICE_ID')),
        'database_probes':rows, 'traffic_scenarios':traffic,
        'open_gates':['choose and verify customer transport mix (LOCAL_TUNNEL vs OUTBOUND_RELAY)', 'commercial Event V2 rollout for high-volume relay users', 'real multi-tenant DEV ramp and soak',
                      'D1 service-time and rows-written measurements under real load', 'Identity login-burst and recovery tests'],
    }
    if args.check:
        print('COMMANDER_1K_10K_EXACT_SQL=PASS')
        print('COMMANDER_10K_USERS_20K_DEVICES_210K_SESSIONS=PASS_LOCAL_ONLY')
        print('COMMANDER_10K_ACTIVE_SESSIONS_PRESERVED=PASS')
        print('COMMANDER_AUTH_RETENTION_INDEXED_BOUNDED=PASS')
        print('COMMANDER_LOCAL_TUNNEL_NO_QUEUE_POLLING=PASS_SOURCE')
        print('COMMANDER_LOCAL_TUNNEL_AND_RELAY_SCENARIOS_SEPARATED=PASS')
        print('COMMANDER_PUBLIC_1K_10K_CONCURRENCY_CERTIFIED=FALSE')
    else:
        print(json.dumps(data,indent=2,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
