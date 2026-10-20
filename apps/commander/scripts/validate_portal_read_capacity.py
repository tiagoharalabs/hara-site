#!/usr/bin/env python3
"""Exact-source portal SQL, full schema, isolated 1k/10k-account fixtures.
No HTTP, cloud mutation, customer data or capacity certification.
SQLite VM steps are comparative work evidence, not Cloudflare latency.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timedelta

APP = Path(__file__).resolve().parents[1]
SOURCE = (APP / 'src/worker.js').read_text()
MIGRATION = APP / 'migrations/0033_portal_read_indexes_20261011.sql'

def sql_for(name: str) -> str:
    start = SOURCE.index('async function ' + name + '(')
    match = re.search(r'\.prepare\(\s*`(.*?)`\s*\)', SOURCE[start:], re.S)
    assert match, name
    sql = match.group(1)
    assert '${' not in sql
    return sql

HISTORY = sql_for('productTransactionHistory')
DEVICES = sql_for('listDevices')
SINCE = '2026-10-04T13:00:00.000Z'
NEXT_HOUR = (datetime.fromisoformat(SINCE.replace('Z','+00:00')).replace(minute=0,second=0,microsecond=0)
             + timedelta(hours=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
NOW = '2026-10-11T13:00:00.000Z'
OLD = '2026-08-01T00:00:00.000Z'
OLD_TOTAL = 'SELECT COALESCE(SUM(lifetime_units),0) FROM commander_device_usage_totals WHERE tenant_id=? AND subject_id=?'

def args(tenant: str, subject: str) -> tuple:
    return (tenant,subject,tenant,subject,tenant,subject,SINCE[:13],
            tenant,subject,SINCE,NEXT_HOUR,
            tenant,subject,SINCE[:10])

def plan(db, sql, params):
    return [r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, params)]

def steps(db, sql, params):
    count = 0
    def progress():
        nonlocal count
        count += 1
        return 0
    db.set_progress_handler(progress, 1)
    try:
        result = db.execute(sql, params).fetchall()
    finally:
        db.set_progress_handler(None, 0)
    return count, result

def legacy(db, tenant, subject):
    row = db.execute('SELECT COUNT(*),COALESCE(SUM(CASE WHEN created_at_utc>=? THEN 1 ELSE 0 END),0) FROM commander_device_calls WHERE tenant_id=? AND subject_id=?', (SINCE,tenant,subject)).fetchone()
    total = db.execute(OLD_TOTAL, (tenant,subject)).fetchone()[0]
    recent = db.execute('SELECT COALESCE(SUM(units),0) FROM commander_device_usage_daily WHERE tenant_id=? AND subject_id=? AND day_key>=?', (tenant,subject,SINCE[:10])).fetchone()[0]
    return (row[0]+total, row[1]+recent)

def probe(users: int):
    db = sqlite3.connect(':memory:')
    try:
        for path in sorted((APP/'migrations').glob('*.sql')):
            if path != MIGRATION:
                db.executescript(path.read_text())
        db.executemany('INSERT INTO tenants VALUES (?,?,?,?,?)', ((f'PRT-{i}','Synthetic','ACTIVE','PRODUCTION',NOW) for i in range(users)))
        db.executemany('INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES (?,?,?,?,?,?,?)', ((f'PRS-{i}',f'PRT-{i}','https://example.invalid/',f's-{i}','ACTIVE','OWNER',NOW) for i in range(users)))
        db.executemany('INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc) VALUES (?,?,?,?,?,?,?)', ((f'PRP-{i}-{j}',f'PH-{i}-{j}',f'PRT-{i}',f'PRS-{i}',NOW,NOW,NOW) for i in range(users) for j in range(2)))
        db.executemany('INSERT INTO commander_devices (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,architecture,agent_version,tunnel_mode,credential_hash,state,created_at_utc,last_seen_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', ((f'PRD-{i}-{j}',f'PRP-{i}-{j}',f'PRT-{i}',f'PRS-{i}','Synthetic','LINUX','x86_64','0.3.43','OUTBOUND_RELAY',f'C-{i}-{j}','ACTIVE',NOW if j else OLD,NOW) for i in range(users) for j in range(2)))
        db.executemany('INSERT INTO commander_device_usage_totals VALUES (?,?,?,?,?)', ((f'PRD-{i}-{j}',f'PRT-{i}',f'PRS-{i}',1000+i*2+j,NOW) for i in range(users) for j in range(2)))
        db.executemany('INSERT INTO commander_device_usage_daily VALUES (?,?,?,?,?,?)', ((f'PRD-{i}-{j}',day,f'PRT-{i}',f'PRS-{i}',units,NOW) for i in range(users) for j in range(2) for day,units in [('2026-10-11',3),('2026-08-01',100)]))
        db.executemany('INSERT INTO commander_device_calls (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,created_at_utc,expires_at_utc,usage_mode,usage_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', ((f'CALL-{i}-{j}-{k}',f'REQ-{i}-{j}-{k}',f'PRT-{i}',f'PRS-{i}',f'PRD-{i}-{j}','hara.ping','{}',state,stamp,NOW,'UNMETERED',0) for i in range(users) for j in range(2) for k,(state,stamp) in enumerate([('COMPLETED',NOW),('FAILED',OLD),('CANCELLED',SINCE)])))
        db.commit()
        params = ('PRT-0','PRS-0')
        before_plan = plan(db, OLD_TOTAL, params)
        before_steps, old_answer = steps(db, OLD_TOTAL, params)
        device_before = plan(db, DEVICES, ('PRT-0',))
        expected = {(t,s):legacy(db,t,s) for t,s in [('PRT-0','PRS-0'),(f'PRT-{users//2}',f'PRS-{users//2}'),(f'PRT-{users-1}',f'PRS-{users-1}'),('PRT-0','PRS-1'),('missing','missing')]}
        db.executescript(MIGRATION.read_text())
        db.executescript(MIGRATION.read_text())  # Migration is additive/idempotent.
        after_steps, new_answer = steps(db, OLD_TOTAL, params)
        assert old_answer == new_answer
        assert after_steps < before_steps / 10
        history_plan = plan(db, HISTORY, args(*params))
        after_plan = plan(db, OLD_TOTAL, params)
        device_after = plan(db, DEVICES, ('PRT-0',))
        assert any('COVERING INDEX idx_device_usage_totals_subject_units' in p for p in after_plan)
        assert not any('TEMP B-TREE' in p for p in device_after)
        assert any('idx_commander_devices_tenant_created' in p for p in device_after)
        assert any('idx_device_calls_activity_subject_created' in p for p in history_plan)
        assert any('idx_device_usage_daily_subject_day' in p for p in history_plan)
        assert any('commander_device_call_history_hourly' in p for p in history_plan)
        assert any('commander_device_call_history_totals' in p for p in history_plan)
        for (tenant,subject), value in expected.items():
            assert db.execute(HISTORY,args(tenant,subject)).fetchone() == value
        for i in range(users):
            assert db.execute(HISTORY,args(f'PRT-{i}',f'PRS-{i}')).fetchone() == (2007+4*i,10), f'TENANT_TOTAL_MISMATCH:{i}'
        assert db.execute('SELECT COUNT(*) FROM commander_device_calls').fetchone()[0] == users*6
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        # Prior Worker reads remain correct after additive schema change.
        assert legacy(db,*params) == expected[params]
        return {'registered_accounts':users,'devices':users*2,'call_rows':users*6,'daily_rows':users*4,'exact_source_account_checks':users,'cross_account_mismatches':0,'migration_idempotence':'PASS','old_worker_compatibility':'PASS','old_lifetime_query_plan':before_plan,'new_lifetime_query_plan':after_plan,'old_sqlite_vm_steps':before_steps,'new_sqlite_vm_steps':after_steps,'device_plan_before':device_before,'device_plan_after':device_after,'combined_history_plan':history_plan,'legacy_fixture_sql_queries':3,'old_worker_history_d1_round_trips':1,'new_worker_history_d1_round_trips':1,'certifies_cloudflare_concurrency':False}
    finally:
        db.close()

if __name__ == '__main__':
    report={'state':'PASS','source_worker_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),'schema_migration_sha256':hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),'environment':'ISOLATED_SQLITE_NOT_CLOUDFLARE','scenarios':[probe(1000),probe(10000)]}
    print(json.dumps(report,indent=2))
