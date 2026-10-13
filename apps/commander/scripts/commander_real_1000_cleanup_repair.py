#!/usr/bin/env python3
"""Exact smoke cleanup repair. Literal PRAGMA batches; never repeat product calls."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, stat
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BASE_CONTROLLER_SHA="c0d143e3e84319057cef7facefdae72b81d8543cd7be678a915d9993a683b682"
ORDER=("commander_device_calls","commander_device_selections","commander_device_authorization_codes",
 "commander_device_metering_events","commander_device_usage_daily","commander_device_usage_totals",
 "commander_device_agent_telemetry","commander_device_telemetry_snapshot","commander_device_budget_blocks",
 "commander_tenant_budget_baselines","commander_devices","device_pairing_tokens","entitlements",
 "commander_beta_access_requests","portal_sessions","identity_bindings","users","tenants")
def need(ok,code):
    if not ok:raise RuntimeError(code)
def q(v):return "'"+str(v).replace("'","''")+"'"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe(exc):
    v=str(exc);return v if re.fullmatch(r"[A-Z][A-Z0-9_:-]{0,159}",v) else type(exc).__name__.upper()
def utc():return datetime.now(timezone.utc).isoformat(timespec="seconds")
def flatten(out):
    need(isinstance(out,list) and all(isinstance(x,dict) and isinstance(x.get("results"),list) for x in out),"CAPACITY_REPAIR_D1_RESULTS")
    return [row for block in out for row in block["results"]]
def schema(d1):
    names=[x["name"] for x in flatten(d1("SELECT name FROM sqlite_master WHERE type='table';"))]
    public=sorted(n for n in names if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",n) and not n.startswith("sqlite_"))
    columns={}
    # D1 rejects table-valued pragma_table_info. Individual literal statements
    # in a bounded batch preserve the association with every result set.
    for start in range(0,len(public),20):
        batch=public[start:start+20]
        out=d1("\n".join("PRAGMA table_info("+q(n)+");" for n in batch))
        need(isinstance(out,list) and len(out)==len(batch),"CAPACITY_REPAIR_PRAGMA_BATCH")
        for name,block in zip(batch,out):
            rows=block.get("results")
            need(isinstance(rows,list) and bool(rows),"CAPACITY_REPAIR_TABLE_COLUMNS")
            columns[name]={x["name"] for x in rows}
    return columns
def scoped_sql(columns,rows,run_id):
    prefix=hashlib.sha256(run_id.encode()).hexdigest()[:12]
    need(1<=len(rows)<=10 and all(r["tenant_id"].startswith("HARA-CAP1K-T-"+prefix+"-") and
        r["subject_id"].startswith("HARA-CAP1K-S-"+prefix+"-") and r.get("collision_checked") is True for r in rows),"CAPACITY_REPAIR_EXACT_SCOPE")
    tenants=",".join(q(r["tenant_id"]) for r in rows);subjects=",".join(q(r["subject_id"]) for r in rows)
    devices=[r["device_id"] for r in rows if r.get("device_id")]
    need(all(re.fullmatch(r"HARA-DEVICE-[A-Za-z0-9._:-]{1,180}",d) for d in devices),"CAPACITY_REPAIR_DEVICE_SCOPE")
    extras=sorted(t for t,c in columns.items() if t not in ORDER and any(k in c for k in ("tenant_id","subject_id","device_id")))
    deletes=[];counts=[];tables=[]
    for table in extras+list(ORDER):
        cols=columns.get(table,set())
        predicate="tenant_id IN ("+tenants+")" if "tenant_id" in cols else (
            "subject_id IN ("+subjects+")" if "subject_id" in cols else (
            "device_id IN ("+",".join(q(d) for d in devices)+")" if "device_id" in cols and devices else None))
        if predicate:
            deletes.append("DELETE FROM "+table+" WHERE "+predicate+";")
            counts.append("SELECT "+q(table)+" AS table_name, COUNT(*) AS n FROM "+table+" WHERE "+predicate+";")
            tables.append(table)
    need("tenants" in tables and "users" in tables,"CAPACITY_REPAIR_REQUIRED_TABLES")
    return deletes,counts,tables

def main():
    p=argparse.ArgumentParser();p.add_argument("--run-id",required=True);p.add_argument("--ssh-config",required=True)
    p.add_argument("--execute",action="store_true");a=p.parse_args()
    need(a.execute,"CAPACITY_REPAIR_EXECUTE_REQUIRED")
    source=HERE/"commander_real_1000_controller.py";need(sha(source)==BASE_CONTROLLER_SHA,"CAPACITY_REPAIR_CONTROLLER_PIN")
    spec=importlib.util.spec_from_file_location("capacity_repair_controller",source)
    ctl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctl)
    c=ctl.Controller(a.run_id,a.ssh_config,cleanup_only=True)
    rows=c.journal["rows"];need(len(rows)==2,"CAPACITY_REPAIR_TWO_FIXTURES_ONLY")
    status=c.ev/"status.json";previous=ctl.private_read(status)
    need(previous.get("cleanup_state")=="FAIL" and previous.get("state")=="SMOKE_COMPLETED","CAPACITY_REPAIR_PRIOR_PROOF")
    retained=c.ev/"smoke-original-cleanup-failed.json"
    if not retained.exists():
        fd=os.open(retained,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as f:f.write(status.read_bytes());f.flush();os.fsync(f.fileno())
    need(sha(retained)==sha(status),"CAPACITY_REPAIR_ORIGINAL_PIN")
    report=dict(schema="hara.commander-capacity-smoke-cleanup-repair.v1",run_id=a.run_id,state="RUNNING",
      started_at_utc=utc(),original_failure_sha256=sha(retained),repair_script_sha256=sha(Path(__file__)),
      backend_mutations="EXACT_OWNED_FIXTURE_CLEANUP_ONLY",invokes_repeated=0,enrollments_repeated=0,
      Agents_started=0,DO_retained_state="UNKNOWN_NOT_CERTIFIED")
    output=c.ev/"cleanup-repair-r1.json"
    def emit():ctl.atomic(output,report)
    emit()
    try:
        # This is reconciliation of an idempotent own cleanup, not an Agent start.
        vm=c.remote({"action":"cleanup"})
        need(vm.get("remaining")==0 and vm.get("credentials_removed") is True,"CAPACITY_REPAIR_VM_RECONCILIATION")
        report["vm_cleanup"]=vm;emit()
        columns=schema(lambda sql:c.d1(sql,cleanup=True))
        deletes,counts,tables=scoped_sql(columns,rows,a.run_id)
        report["exact_fixture_count"]=len(rows);report["tables_in_scope"]=tables
        report["delete_state"]="PENDING";emit()
        c.d1("\n".join(deletes),cleanup=True)
        report["delete_state"]="ACKNOWLEDGED";emit()
        results=flatten(c.d1("\n".join(counts),cleanup=True))
        need(len(results)==len(tables) and {x["table_name"] for x in results}==set(tables),"CAPACITY_REPAIR_COUNTS_COVERAGE")
        need(all(type(x.get("n")) is int and x["n"]==0 for x in results),"CAPACITY_REPAIR_ROWS_REMAIN")
        report["remaining_by_table"]=results
        for row in rows:
            own=Path(row["private_root"])
            need(own.parent==c.home and own.name=="fixture-"+str(row["index"]),"CAPACITY_REPAIR_PRIVATE_SCOPE")
            if own.exists():ctl.private_dir(own);import shutil;shutil.rmtree(own)
            c.update_row(row,state="CLEANED")
        c.journal["cleanup_state"]="PASS";c.journal["cleanup_repair_report"]=str(output);c.save()
        report.update(state="PASS",credentials_removed=True,own_Agents_remaining=0,cleanup_commands=c.budget.cleanup_used,
            application_http_and_d1_commands=c.budget.used,finished_at_utc=utc())
    except BaseException as exc:
        report.update(state="FAIL",error_code=safe(exc),finished_at_utc=utc())
        if report.get("delete_state")=="PENDING":report["delete_state"]="UNKNOWN_NO_AUTOMATIC_RETRY"
        emit();raise
    emit()
    print(json.dumps(dict(state=report["state"],cleanup="PASS",exact_fixture_count=2,original_proof_preserved=True,
        invokes_repeated=0,enrollments_repeated=0,DO_retained_state="UNKNOWN_NOT_CERTIFIED")))
    return 0

if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(state="HOLD",code=safe(exc))));raise SystemExit(1)
