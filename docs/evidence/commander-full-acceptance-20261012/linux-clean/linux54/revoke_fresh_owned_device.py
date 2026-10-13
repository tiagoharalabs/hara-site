#!/usr/bin/env python3
"""Normal portal revocation of OWN fresh54 fixture device before re-enrollment."""
import argparse,json,re,runpy
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
R=Path("/tmp_hara/commander-win50-utf8-20261012");E=R/"docs/evidence/commander-full-acceptance-20261012/linux-clean/linux54"
BASE=R/"apps/commander/.generated/full-acceptance-20261012/linux54-baseline53-20261013033631-4f624d30.json"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--fresh-evidence",type=Path,required=True);a=p.parse_args()
def require(ok,code):
 if not ok:raise RuntimeError(code)
out=E/"fresh-portal-revoke-054-r2.json";require(not out.exists(),"REVOCATION_ALREADY_RECORDED")
read_private=runpy.run_path(str(R/"apps/commander/scripts/full_acceptance_dev_fixtures.py"))["read_private"]
f=read_private(a.fixture);b=read_private(BASE)
require(f["environment"]=="DEV" and f["dev_origin"]==DEV and f["tenant_id"]==b["tenant_id"] and f["subject_id"]==b["subject_id"],"OWN_NEW_QA_FIXTURE_GUARD")
require(a.fresh_evidence.parent==E and not a.fresh_evidence.is_symlink(),"OWN_FRESH_EVIDENCE_GUARD")
fresh=json.loads(a.fresh_evidence.read_text())
device=fresh.get("device_id")
require(fresh.get("state")=="PASS" and fresh.get("expected_version")=="0.3.54" and re.fullmatch("HARA-DEVICE-[a-f0-9-]{36}",str(device)),"OWN_FRESH_DEVICE_GUARD")
require(device not in ("HARA-DEVICE-1b987909-0cc0-46cd-8ac4-d09132640e45","HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889"),"OLD_OR_SOAK_DEVICE_REVOCATION_DENIED")
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):raise HTTPError(req.full_url,code,"QA_REDIRECT_REJECTED",headers,fp)
req=Request(DEV+"/api/portal/devices/revoke",data=json.dumps({"device_id":device}).encode(),method="POST",headers={"content-type":"application/json","user-agent":"HARA-Commander-LinuxClean-DEV/1","cookie":"hara_commander_session="+f["session_cookie"],"origin":DEV,"referer":DEV+"/","sec-fetch-site":"same-origin"})
try:
 with build_opener(NoRedirect()).open(req,timeout=20) as r:
  status=r.status;response=json.load(r)
except HTTPError as error:
 status=error.code;response={}
result={"schema":"hara.commander-linux054-normal-portal-revocation.v1","device_id":device,"http":status,"portal_fixture_session_scope":"seeded_QA_2h; not_OAuth_proof","secret_material_exposed":False,"own_new_qa_tenant_guard":True,"state":"PASS" if status==200 and response.get("schema")=="hara.commander-device-revocation.v1" and response.get("ok") is True and response.get("state")=="REVOKED" and response.get("device_id")==device else "FAIL","revoked_at_utc":response.get("revoked_at_utc")}
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
raise SystemExit(0 if result["state"]=="PASS" else 1)
