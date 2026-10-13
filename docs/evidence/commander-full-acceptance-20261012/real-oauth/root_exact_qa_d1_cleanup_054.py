from pathlib import Path
import importlib.util,json,os,re,stat,datetime
root=Path("/tmp_hara/commander-win50-utf8-20261012")
os.environ["PATH"]="/home/sartorius/.nvm/versions/node/v24.15.0/bin:"+os.environ.get("PATH","")
p=root/"apps/commander/scripts/full_acceptance_dev_fixtures.py"
s=importlib.util.spec_from_file_location("qa54_owned_d1_cleanup",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.guard()
ev=root/"docs/evidence/commander-full-acceptance-20261012/real-oauth"
assert json.loads((ev/"exact-qa-idp-cleanup-054.json").read_text())["state"]=="PASS"
expected=[
 {"subject_id":"HARA-ACCEPT-S-20261013001608-ea8cefa9","tenant_id":"HARA-ACCEPT-T-20261013001608-ea8cefa9","oidc_subject":"394859086664957956"},
 {"subject_id":"HARA-SUBJECT-NECJJGQPSMLXM5NBYEU","tenant_id":"HARA-TENANT-BNRKHV5P7_1SBJSL8FZ_HYYR","oidc_subject":"394861028946477060"}]
q=m.fresh.q;subjects=",".join(q(x["subject_id"]) for x in expected);tenants=",".join(q(x["tenant_id"]) for x in expected);external=",".join(q(x["oidc_subject"]) for x in expected)
users=m.fresh.rows("SELECT subject_id,tenant_id,oidc_subject FROM users WHERE oidc_issuer="+q("https://auth.haralabs.com.br/")+" AND oidc_subject IN ("+external+");")
assert sorted(users,key=lambda x:x["oidc_subject"])==sorted(expected,key=lambda x:x["oidc_subject"]),"QA54_EXACT_D1_IDENTITY_DRIFT"
shared=m.fresh.rows("SELECT tenant_id,COUNT(*) AS n FROM users WHERE tenant_id IN ("+tenants+") GROUP BY tenant_id;")
assert len(shared)==2 and all(x["n"]==1 for x in shared),"QA54_SHARED_TENANT_REFUSED"
devices=m.fresh.rows("SELECT device_id,state FROM commander_devices WHERE tenant_id IN ("+tenants+");")
assert all(x["state"]=="REVOKED" for x in devices),"QA54_ACTIVE_DEVICE_CLEANUP_REFUSED"
tables=m.fresh.rows("SELECT name FROM sqlite_master WHERE type='table';")
assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",x["name"]) for x in tables)
tables=[x for x in tables if not x["name"].startswith(("_","sqlite_"))]
metadata=m.fresh.d1("\n".join("PRAGMA table_info("+q(x["name"])+");" for x in tables))
assert len(metadata)==len(tables),"QA54_SCHEMA_METADATA_RESULT_COUNT"
cols=[{"table_name":table["name"],"column_name":column["name"]} for table,item in zip(tables,metadata) for column in item.get("results",[]) if column["name"] in ("tenant_id","subject_id")]
scopes={}
for x in cols:
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",x["table_name"])
    scopes.setdefault(x["table_name"],set()).add(x["column_name"])
def where(table):
    return "tenant_id IN ("+tenants+")" if "tenant_id" in scopes[table] else "subject_id IN ("+subjects+")"
def counts():
    sql="\n".join("SELECT "+q(t)+" AS table_name,COUNT(*) AS n FROM \""+t+"\" WHERE "+where(t)+";" for t in sorted(scopes))
    results=m.fresh.d1(sql)
    return [row for item in results for row in item.get("results",[])]
before=counts()
ordered=["commander_device_calls","commander_device_selections","commander_device_authorization_codes","commander_device_metering_events","commander_device_usage_daily","commander_device_usage_totals","commander_device_agent_telemetry","commander_device_telemetry_snapshot","commander_device_budget_blocks","commander_tenant_budget_baselines","commander_devices","device_pairing_tokens","entitlements","commander_beta_access_requests","portal_sessions","identity_bindings","users","tenants"]
unknown=[x for x in before if x["n"] and x["table_name"] not in ordered]
plan={"state":"PREPARED" if not unknown else "HOLD_UNKNOWN_OWNED_TABLE","at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"scope":"EXACT_TWO_COMPLETED_QA_DEV_TENANTS_ONLY","identities":expected,"before":before,"unknown_owned_tables":unknown,"all_devices_revoked_before_cleanup":True,"prod_changed":False}
(ev/"exact-qa-d1-cleanup-plan-054.json").write_text(json.dumps(plan,sort_keys=True,indent=2)+"\n")
assert not unknown,"QA54_UNREVIEWED_OWNED_TABLE"
sql="\n".join("DELETE FROM "+t+" WHERE "+where(t)+";" for t in ordered if t in scopes)
m.fresh.d1(sql)
after=counts();assert all(x["n"]==0 for x in after),"QA54_D1_CLEANUP_REMAINING"
removed=0
for path in m.PRIVATE.glob("*.json"):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o600 or st.st_uid!=os.getuid():continue
    data=m.read_private(path)
    if any(data.get("tenant_id")==x["tenant_id"] and data.get("subject_id")==x["subject_id"] and data.get("external_subject")==x["oidc_subject"] for x in expected):
        path.unlink();removed+=1
report={"state":"PASS","at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"identities":expected,"before":before,"after":after,"owned_private_fixture_files_removed":removed,"other_tenants_targeted":False,"prod_changed":False,"credential_values_exposed":False}
(ev/"exact-qa-d1-cleanup-054.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
print(json.dumps({"state":"PASS","owned_tenants_removed":2,"owned_private_fixture_files_removed":removed,"other_tenants_targeted":False,"prod_changed":False}))
