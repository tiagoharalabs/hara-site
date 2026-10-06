#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
DB="hara-commander-product-prod"
TARGET_TABLES={
    "commander_devices",
    "commander_slo_state",
    "commander_slo_incidents",
    "commander_slo_alert_deliveries",
}

def run_sql(sql: str):
    cmd=[
        "npx","--yes","wrangler@4.137.0","d1","execute",DB,
        "--remote","--command",sql,
    ]
    return subprocess.run(cmd,cwd=APP,text=True,capture_output=True)

def emit(proc):
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

def existing_tables():
    proc=run_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    emit(proc)
    if proc.returncode:
        raise SystemExit(proc.returncode)
    # Wrangler emits JSON in stdout. Extract table names conservatively.
    return {m.group(1) for m in re.finditer(r'"name"\s*:\s*"([^"]+)"',proc.stdout)}

def count_sql(tables):
    selects=[]
    if "commander_devices" in tables:
        selects.append("(SELECT COUNT(*) FROM commander_devices WHERE activity_summary_json IS NOT NULL OR activity_summary_at_utc IS NOT NULL) AS legacy_device_snapshots")
    if "commander_slo_state" in tables:
        selects.append("(SELECT COUNT(*) FROM commander_slo_state) AS slo_state_rows")
    if "commander_slo_incidents" in tables:
        selects.append("(SELECT COUNT(*) FROM commander_slo_incidents) AS slo_incident_rows")
    if "commander_slo_alert_deliveries" in tables:
        selects.append("(SELECT COUNT(*) FROM commander_slo_alert_deliveries) AS slo_delivery_rows")
    return "SELECT "+(",".join(selects) if selects else "0 AS diagnostic_rows")+";"

def purge_sql(tables):
    statements=[]
    if "commander_devices" in tables:
        statements.append("""UPDATE commander_devices
SET activity_summary_json=NULL, activity_summary_at_utc=NULL
WHERE activity_summary_json IS NOT NULL OR activity_summary_at_utc IS NOT NULL""")
    for table in ("commander_slo_alert_deliveries","commander_slo_incidents","commander_slo_state"):
        if table in tables:
            statements.append(f"DELETE FROM {table}")
    return ";\n".join(statements)+(";" if statements else "")

def main():
    ap=argparse.ArgumentParser(description="Purge legacy internal diagnostics from the public Commander D1 plane.")
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--confirm",default="")
    args=ap.parse_args()

    tables=existing_tables()
    present=sorted(TARGET_TABLES & tables)
    print("COMMANDER_PRODUCT_DIAGNOSTICS_TABLES_PRESENT="+",".join(present))

    read=run_sql(count_sql(tables))
    emit(read)
    if read.returncode:
        return read.returncode

    if not args.execute:
        print("COMMANDER_PRODUCT_DIAGNOSTICS_PURGE_EXECUTE=FALSE")
        return 0

    if args.confirm!="PURGE_INTERNAL_DIAGNOSTICS_FROM_PRODUCT_D1":
        raise SystemExit("COMMANDER_PRODUCT_DIAGNOSTICS_PURGE_CONFIRMATION_REQUIRED")

    sql=purge_sql(tables)
    if sql:
        result=run_sql(sql)
        emit(result)
        if result.returncode:
            return result.returncode

    verify=run_sql(count_sql(tables))
    emit(verify)
    if verify.returncode:
        return verify.returncode

    print("COMMANDER_PRODUCT_DIAGNOSTICS_PURGE=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
