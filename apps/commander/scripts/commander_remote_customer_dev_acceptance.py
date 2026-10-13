#!/usr/bin/env python3
"""Measured DEV remote Agent acceptance with seeded QA identity; OAuth is separate."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, pty, secrets, subprocess, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
def load(name):
    spec=importlib.util.spec_from_file_location(name,APP/"scripts"/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
fixtures=load("full_acceptance_dev_fixtures")
budget=load("commander_local_budget_dev_canary")

def request(data,method,path,body=None,internal=False,cookie=False):
    headers={"user-agent":"HARA-DEV-Remote-Acceptance/1","accept":"application/json"}
    raw=None
    if body is not None:
        raw=json.dumps(body,separators=(",",":")).encode()
        headers["content-type"]="application/json"
    if internal:
        token_path=Path(data["canary_token_file"])
        assert (token_path.stat().st_mode&0o777)==0o600 and not token_path.is_symlink()
        headers["x-hara-mcp-product-token"]=token_path.read_text().strip()
    if cookie: headers["Cookie"]="hara_commander_session="+data["session_cookie"]
    if method!="GET": headers["origin"]=data["dev_origin"];headers["referer"]=data["dev_origin"]+"/"
    req=Request(data["dev_origin"]+path,data=raw,method=method,headers=headers)
    try:
        with urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read() or "{}")
    except HTTPError as e:
        raw=e.read()
        try: result=json.loads(raw or "{}")
        except Exception: result={}
        return e.code, {"code":result.get("code") or result.get("error") or ("HTTP_"+str(e.code)), "content_type":e.headers.get("content-type"),"response_sha256":hashlib.sha256(raw).hexdigest()}

def ensure(condition,code):
    if not condition: raise RuntimeError(code)

def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)

def main(plan="TRIAL"):
    assert plan in ("TRIAL","STANDARD")
    report={"schema":"hara.dev-remote-customer-acceptance.v1","started_at":datetime.now(timezone.utc).isoformat(),
        "environment":"DEV","oauth_frontend_exercised":False,"identity_setup":"ISOLATED_QA_D1_SEED",
        "prod_mutated":False,"founder_mutated":False,"secret_output":False,"checks":{},"receipts":[]}
    report["plan"]=plan;report["billing_checkout_exercised"]=False
    path=None;proc=None;operator=None;tty_master=None
    try:
        path=fixtures.create("remote-customer-"+plan.lower())
        data=fixtures.read_private(path);q=fixtures.fresh.q
        if plan=="STANDARD":
            fixtures.fresh.d1("UPDATE entitlements SET plan_code='STANDARD' WHERE entitlement_id="+q(data["entitlement_id"])+" AND tenant_id="+q(data["tenant_id"])+";")
        device_id,device_token=fixtures.fresh.enroll(data["pairing_token"],"acceptance-remote-customer")
        report["checks"]["real_pairing_enrollment"]="PASS"
        with tempfile.TemporaryDirectory(prefix="hara-accept-remote-") as tmp:
            t=Path(tmp);config=t/"config"/"hara-commander";config.mkdir(parents=True)
            (t/"data").mkdir();(t/"workspace").mkdir()
            cfg=config/"device.env"
            cfg.write_text("HARA_COMMANDER_URL="+data["dev_origin"]+"\nHARA_DEVICE_ID="+device_id+"\nHARA_DEVICE_TOKEN="+device_token+"\nHARA_DEVICE_ARCH=x86_64\nHARA_COMMANDER_APPROVAL_MODE="+("SESSION_TRUSTED" if plan=="STANDARD" else "PERSISTENT_TRUSTED")+"\n")
            cfg.chmod(0o600);device_token=""
            agent=t/"agent.py";version=budget.download_agent(agent)
            report["served_agent_version"]=version
            report["served_agent_sha256"]=hashlib.sha256(agent.read_bytes()).hexdigest()
            report["approval_mode"]="SESSION_TRUSTED" if plan=="STANDARD" else "PERSISTENT_TRUSTED"
            env=os.environ.copy();env.update(XDG_CONFIG_HOME=str(t/"config"),XDG_DATA_HOME=str(t/"data"),HARA_COMMANDER_LOCAL_PORT="0")
            if plan=="STANDARD":
                tty_master,slave=pty.openpty()
                operator=subprocess.Popen(["python3","-u","-c","import runpy,sys; runpy.run_path(sys.argv[1])['start_operator_console']()",str(agent)],env=env,cwd=t,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
                os.close(slave);time.sleep(0.5)
                ensure(operator.poll() is None,"QA_SESSION_OPERATOR_FAILED")
                report["checks"]["bounded_operator_session"]="PASS"
            proc=subprocess.Popen(["python3",str(agent)],env=env,cwd=t,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                rows=fixtures.fresh.rows("SELECT agent_version,tunnel_mode FROM commander_devices WHERE device_id="+q(device_id)+";")
                if rows and rows[0]["agent_version"]==version:break
                ensure(proc.poll() is None,"ISOLATED_AGENT_EXITED")
                time.sleep(0.5)
            ensure(rows and rows[0]["agent_version"]==version,"ISOLATED_AGENT_HEARTBEAT_TIMEOUT")
            report["checks"]["real_agent_online"]="PASS"
            report["transport"]=rows[0]["tunnel_mode"]
            status,initial=request(data,"GET","/api/portal/dashboard",cookie=True)
            ensure(status==200,"INITIAL_DASHBOARD_"+str(status))
            report["usage_before"]=initial.get("usage")
            calls=[]
            file=str(t/"workspace"/"acceptance.txt")
            Path(file).write_text("QA UTF-8: ação 🚀 日本語\n")
            operations=[
                ("hara.device.info",{},"device"),
                ("hara.files.info",{"path":file},"filesystem"),
                ("hara.files.read",{"path":file},"filesystem")
            ]
            if plan=="STANDARD":
                operations=[("hara.files.write",{"path":file,"content":"QA UTF-8: ação 🚀 日本語\n","mode":"rewrite"},"filesystem"),("hara.files.read",{"path":file},"filesystem"),("hara.process.run",{"command":"printf HARA_PRO_REMOTE_PROCESS_PASS","cwd":str(t/"workspace"),"timeout_ms":3000,"max_lines":20},"process")]
            for tool,payload,kind in operations:
                rid="HARA-QA-REMOTE-"+secrets.token_hex(12)
                body={"issuer":data["issuer"],"subject":data["external_subject"],"request_id":rid,"tool_id":tool,"device_id":device_id,"payload":payload}
                status,call=request(data,"POST","/api/internal/device/calls",body,internal=True)
                ensure(status in (200,201) and call.get("call_id"),"REAL_ENQUEUE_"+str(status)+"_"+str(call.get("code")))
                call_id=call["call_id"];deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    status,result=request(data,"POST","/api/internal/device/calls/status",{"issuer":data["issuer"],"subject":data["external_subject"],"call_id":call_id},internal=True)
                    ensure(status==200,"REAL_STATUS_"+str(status))
                    if result.get("state") in ("COMPLETED","FAILED","EXPIRED","CANCELLED"):break
                    time.sleep(0.5)
                ensure(result.get("state")=="COMPLETED" and not result.get("error_code"),"REAL_CALL_NOT_COMPLETED_"+str(result.get("error_code")))
                proof=result.get("result") or {}
                ensure(proof.get("state")=="PASS","REAL_AGENT_RESULT_NOT_PASS")
                receipt=proof.get("bridge_receipt_sha256")
                ensure(isinstance(receipt,str) and len(receipt)==64,"REAL_RECEIPT_MISSING")
                report["receipts"].append({"tool":tool,"call_id":call_id,"receipt_sha256":receipt,"usage_mode":call.get("usage_mode"),"usage_units":call.get("usage_units")})
                if tool=="hara.files.read":
                    rendered=json.dumps(proof,ensure_ascii=False)
                    ensure(all(x in rendered for x in ("ação","🚀","日本語")),"REMOTE_READ_UNICODE_NOT_PRESERVED")
                if tool=="hara.process.run":ensure("HARA_PRO_REMOTE_PROCESS_PASS" in json.dumps(proof),"REMOTE_PROCESS_OUTPUT_MISSING")
                calls.append(body)
            ensure(Path(file).read_text()=="QA UTF-8: ação 🚀 日本語\n","UTF8_PHYSICAL_ROUNDTRIP_FAILED")
            report["checks"]["remote_read_utf8"]="PASS"
            if plan=="TRIAL":
                denied=[]
                for tool,payload in [("hara.files.write",{"path":file,"content":"must never apply","mode":"rewrite"}),("hara.process.run",{"command":"printf must_never_run","timeout_ms":1000,"max_lines":10})]:
                    status,result=request(data,"POST","/api/internal/device/calls",{"issuer":data["issuer"],"subject":data["external_subject"],"request_id":"HARA-QA-DENY-"+secrets.token_hex(10),"tool_id":tool,"device_id":device_id,"payload":payload},internal=True)
                    ensure(status==403 and result.get("code")=="GRANT_MISSING","FREE_GRANT_DENIAL_FAILED")
                    denied.append({"tool":tool,"http":status,"code":result.get("code")})
                ensure(Path(file).read_text()=="QA UTF-8: ação 🚀 日本語\n","DENIED_MUTATION_CHANGED_FILE")
                report["free_denied_tools"]=denied
                report["checks"]["free_mutation_process_policy_denied"]="PASS"
            else:
                report["checks"]["pro_remote_write_and_process"]="PASS"
            before=fixtures.fresh.rows("SELECT SUM(units_issued) AS issued FROM commander_device_budget_blocks WHERE tenant_id="+q(data["tenant_id"])+";")
            status,replay=request(data,"POST","/api/internal/device/calls",calls[0],internal=True)
            report["idempotency_replay"]={"http":status,"response":replay}
            if status in (403,502,503) and str(replay.get("code") or "").startswith("HTTP_"):
                status,replay=request(data,"POST","/api/internal/device/calls",calls[0],internal=True)
                report["idempotency_retry"]={"http":status,"response":replay,"same_request_id":True}
            ensure(status in (200,201) and replay.get("existing") is True and replay.get("call_id")==report["receipts"][0]["call_id"],"REAL_ENQUEUE_IDEMPOTENCY_FAILED")
            after=fixtures.fresh.rows("SELECT SUM(units_issued) AS issued FROM commander_device_budget_blocks WHERE tenant_id="+q(data["tenant_id"])+";")
            ensure(before==after,"REPLAY_BUDGET_INCREASED")
            report["checks"]["same_request_no_reexecution_or_usage"]="PASS"
            report["cloud_budget_issued"]=after
            if plan=="TRIAL":
                stop(proc);proc=None
                proc=subprocess.Popen(["python3",str(agent)],env=env,cwd=t,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    blocks=fixtures.fresh.rows("SELECT units_issued,units_reported,state FROM commander_device_budget_blocks WHERE tenant_id="+q(data["tenant_id"])+";")
                    if blocks and sum(int(x["units_reported"]) for x in blocks)>=3:break
                    time.sleep(.5)
                ensure(blocks and sum(int(x["units_reported"]) for x in blocks)==3,"CLOUD_USAGE_REPORT_NOT_EXACT")
            else:
                blocks=[]
            status,dashboard=request(data,"GET","/api/portal/dashboard",cookie=True)
            ensure(status==200,"FINAL_DASHBOARD_"+str(status))
            report["usage_after"]=dashboard.get("usage")
            report["cloud_budget_final"]=blocks
            report["checks"]["remote_metered_usage_report" if plan=="TRIAL" else "pro_unmetered_policy"]="PASS"
            if plan=="STANDARD":ensure((dashboard.get("usage") or {}).get("metered") is False,"PRO_POLICY_NOT_UNMETERED")
            status,mcp=request(data,"POST","/api/mcp?profile=simple",{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
            report["customer_mcp_without_oauth_http"]=status
            ensure(status in (401,404),"CUSTOMER_MCP_AUTH_GATE_UNEXPECTED_STATUS")
            report["customer_mcp_fresh_oauth_proof"]="PENDING_REAL_IDP_BEARER" if status==401 else "DEV_CUSTOMER_ROUTE_DISABLED_BEFORE_OPTIN"
            report["state"]="PASS_REMOTE_AGENT_USAGE_OAUTH_SEPARATE"
    except Exception as e:
        report["state"]="FAIL";report["error"]=str(e)[:180]
    finally:
        stop(proc);stop(operator)
        if tty_master is not None:os.close(tty_master)
        if path:
            try:report["cleanup"]=fixtures.cleanup(path)
            except Exception as e:report["cleanup"]={"state":"FAIL","code":str(e)[:100]}
        report["completed_at"]=datetime.now(timezone.utc).isoformat()
        out=ROOT/("docs/evidence/commander-full-acceptance-20261012/client-quota/remote-customer-"+plan.lower()+"-live.json")
        print(json.dumps(report,ensure_ascii=False),flush=True)
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    return 0 if report["state"].startswith("PASS") else 1
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--plan",choices=["TRIAL","STANDARD"],default="TRIAL")
    raise SystemExit(main(parser.parse_args().plan))
