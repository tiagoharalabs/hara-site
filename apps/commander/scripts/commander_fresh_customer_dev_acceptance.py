#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT = APP / "public" / "agent" / "linux.py"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
DEV_CONFIG = APP / "wrangler.dev.jsonc"
DEV_DB = "hara-commander-product-dev"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
ISSUER = "https://auth.haralabs.com.br/"

def fail(code: str):
    raise RuntimeError(code)

def q(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"

def b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

def d1(sql: str) -> list[dict]:
    proc = subprocess.run(
        [str(WRANGLER), "d1", "execute", DEV_DB, "--remote",
         "--config", str(DEV_CONFIG), "--command", sql, "--json"],
        cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=90,
    )
    if proc.returncode:
        raise fail("D1_EXECUTE_FAILED")
    try:
        payload=json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise fail("D1_JSON_INVALID") from exc
    if not isinstance(payload,list) or not payload:
        raise fail("D1_RESULT_INVALID")
    return payload

def rows(sql: str) -> list[dict]:
    out=d1(sql)
    result=out[-1].get("results")
    return result if isinstance(result,list) else []

def enroll(pairing_token: str, device_name: str) -> tuple[str,str]:
    body=json.dumps({
        "pairing_token":pairing_token,
        "device_name":device_name,
        "platform":"LINUX",
        "architecture":"x86_64",
        "agent_version":"0.3.30",
        "approval_mode":"PERSISTENT_TRUSTED",
    },separators=(",",":")).encode()
    req=urllib.request.Request(
        DEV_ORIGIN+"/api/device/enroll", data=body, method="POST",
        headers={"content-type":"application/json","accept":"application/json",
                 "user-agent":"HARA-Commander-FreshCustomer-DEV/1"},
    )
    try:
        with urllib.request.urlopen(req,timeout=20) as response:
            payload=json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        code="UNKNOWN"
        try:
            body=json.loads(raw or b"{}")
            code=str(body.get("code") or "UNKNOWN")
        except Exception:
            pass
        raise fail("ENROLL_HTTP_"+str(exc.code)+"_"+code) from None
    device_id=str(payload.get("device_id") or "")
    device_token=str(payload.get("device_token") or "")
    if not device_id.startswith("HARA-DEVICE-") or len(device_token)<32:
        raise fail("ENROLL_RESPONSE_INVALID")
    return device_id,device_token

class McpClient:
    def __init__(self, env: dict[str,str]):
        self.proc=subprocess.Popen(
            ["python3",str(AGENT),"mcp"], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.next_id=1

    def call(self, method: str, params: dict | None=None) -> dict:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise fail("MCP_PIPE_MISSING")
        req_id=self.next_id; self.next_id+=1
        self.proc.stdin.write(json.dumps({
            "jsonrpc":"2.0","id":req_id,"method":method,"params":params or {}
        },separators=(",",":"))+"\n")
        self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        if not line:
            err=self.proc.stderr.read() if self.proc.stderr else ""
            raise fail("MCP_RESPONSE_MISSING:"+err[:80])
        obj=json.loads(line)
        if obj.get("id")!=req_id:
            raise fail("MCP_RESPONSE_ID_MISMATCH")
        if "error" in obj:
            raise fail("MCP_PROTOCOL_ERROR")
        return obj["result"]

    def tool(self,name:str,args:dict|None=None) -> dict:
        result=self.call("tools/call",{"name":name,"arguments":args or {}})
        if result.get("isError"):
            content=result.get("content") or []
            code="UNKNOWN"
            if content:
                try: code=json.loads(content[0].get("text") or "{}").get("code") or code
                except Exception: pass
            raise fail("MCP_TOOL_ERROR:"+str(code))
        value=result.get("structuredContent")
        if not isinstance(value,dict):
            raise fail("MCP_STRUCTURED_RESULT_MISSING")
        return value

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=3)

def main() -> int:
    if not WRANGLER.is_file():
        fail("WRANGLER_MISSING")
    if not AGENT.is_file():
        fail("AGENT_MISSING")

    suffix=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")+"-"+secrets.token_hex(4)
    tenant="HARA-FRESH-T-"+suffix
    subject="HARA-FRESH-S-"+suffix
    binding="HARA-FRESH-I-"+suffix
    entitlement="HARA-FRESH-E-"+suffix
    pairing="HARA-FRESH-P-"+suffix
    ext_subject="fresh-"+suffix
    device_name="fresh-linux-"+suffix
    token=secrets.token_urlsafe(32)
    token_hash=b64url_sha256(token)
    now=datetime.now(timezone.utc)
    now_iso=now.isoformat(timespec="seconds").replace("+00:00","Z")
    exp=(now+timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00","Z")

    seed=f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc)
VALUES ({q(tenant)},'Fresh Customer','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(ISSUER)},{q(ext_subject)},NULL,'Fresh Customer','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES ({q(binding)},{q(subject)},'PRIMARY_OIDC',{q(ISSUER)},{q(ext_subject)},'ACTIVE',{q(now_iso)},NULL);
INSERT INTO entitlements
(entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc)
VALUES ({q(entitlement)},{q(tenant)},{q(subject)},'TRIAL','ACTIVE',{q(now_iso)},NULL);
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc)
VALUES ({q(pairing)},{q(token_hash)},{q(tenant)},{q(subject)},{q(now_iso)},{q(exp)},NULL,NULL);
"""
    cleanup=f"""
DELETE FROM commander_device_calls WHERE tenant_id={q(tenant)};
DELETE FROM commander_device_selections WHERE tenant_id={q(tenant)};
DELETE FROM commander_devices WHERE tenant_id={q(tenant)};
DELETE FROM device_pairing_tokens WHERE tenant_id={q(tenant)};
DELETE FROM portal_sessions WHERE subject_id={q(subject)};
DELETE FROM identity_bindings WHERE subject_id={q(subject)};
DELETE FROM entitlements WHERE tenant_id={q(tenant)};
DELETE FROM commander_beta_access_requests WHERE tenant_id={q(tenant)};
DELETE FROM users WHERE subject_id={q(subject)};
DELETE FROM tenants WHERE tenant_id={q(tenant)};
"""
    client=None
    device_token=""
    try:
        d1(seed)
        device_id,device_token=enroll(token,device_name)
        token=""

        enrolled=rows(
            f"SELECT tenant_id,enrolled_by_subject_id,device_name,approval_mode,state "
            f"FROM commander_devices WHERE device_id={q(device_id)};"
        )
        expected=[{
            "tenant_id":tenant,"enrolled_by_subject_id":subject,
            "device_name":device_name,"approval_mode":"PERSISTENT_TRUSTED","state":"ACTIVE"
        }]
        if enrolled!=expected:
            fail("ENROLLMENT_DB_BINDING_INVALID")
        print("FRESH_CUSTOMER_DEV_IDENTITY_TENANT=PASS")
        print("FRESH_CUSTOMER_DEV_PAIRING_ENROLLMENT=PASS")

        with tempfile.TemporaryDirectory(prefix="hara-fresh-customer-") as tmp:
            root=Path(tmp)
            xdg_config=root/"config"
            xdg_data=root/"data"
            workspace=root/"workspace"
            config_dir=xdg_config/"hara-commander"
            config_dir.mkdir(parents=True)
            xdg_data.mkdir()
            workspace.mkdir()
            cfg=config_dir/"device.env"
            cfg.write_text(
                f"HARA_COMMANDER_URL={DEV_ORIGIN}\n"
                f"HARA_DEVICE_ID={device_id}\n"
                f"HARA_DEVICE_TOKEN={device_token}\n"
                "HARA_DEVICE_ARCH=x86_64\n"
                "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n",
                encoding="utf-8",
            )
            os.chmod(cfg,0o600)
            device_token=""

            env=os.environ.copy()
            env["XDG_CONFIG_HOME"]=str(xdg_config)
            env["XDG_DATA_HOME"]=str(xdg_data)
            client=McpClient(env)

            init=client.call("initialize",{
                "protocolVersion":"2025-06-18",
                "capabilities":{},
                "clientInfo":{"name":"fresh-customer-acceptance","version":"1"},
            })
            if init.get("serverInfo",{}).get("name")!="H.A.R.A. Commander Local":
                fail("LOCAL_MCP_INIT_INVALID")
            listed=client.call("tools/list",{})
            names=[str(t.get("name") or "") for t in listed.get("tools",[])]
            if len(names)!=24 or any(name.startswith("hara.") for name in names):
                fail("LOCAL_MCP_TOOL_SURFACE_INVALID")
            print("FRESH_CUSTOMER_LOCAL_MCP_TOOLS=24")
            print("FRESH_CUSTOMER_LOCAL_MCP_HARA_PREFIX=ABSENT")

            devices=client.tool("list_devices")
            first=(devices.get("devices") or [{}])[0]
            if first.get("device_id")!=device_id or first.get("state")!="ONLINE" or first.get("transport")!="LOCAL_STDIO":
                fail("LOCAL_MCP_DEVICE_STATE_INVALID")

            usage=client.tool("get_usage_stats")
            if usage.get("relay_calls_per_local_tool_call")!=0 or usage.get("cloud_quota_consumed_by_local_tool_call") is not False:
                fail("LOCAL_MCP_ZERO_RELAY_INVALID")
            print("FRESH_CUSTOMER_LOCAL_MCP_ZERO_RELAY=PASS")

            path=str(workspace/"hello.txt")
            w=client.tool("write_file",{"path":path,"content":"fresh customer v1\n","mode":"rewrite"})
            if not Path(path).is_file():
                fail("LOCAL_MCP_WRITE_MISSING")
            r=client.tool("read_file",{"path":path})
            if "fresh customer v1" not in json.dumps(r):
                fail("LOCAL_MCP_READ_INVALID")
            client.tool("edit_block",{
                "path":path,
                "old_string":"fresh customer v1",
                "new_string":"fresh customer edited",
            })
            r2=client.tool("read_file",{"path":path})
            if "fresh customer edited" not in json.dumps(r2):
                fail("LOCAL_MCP_EDIT_INVALID")
            print("FRESH_CUSTOMER_LOCAL_MCP_FILESYSTEM=PASS")

            proc=client.tool("start_process",{
                "command":"printf 'FRESH_CUSTOMER_PROCESS_PASS\\n'",
                "cwd":str(workspace),
                "timeout_ms":3000,
                "max_lines":50,
            })
            rendered=json.dumps(proc)
            if "FRESH_CUSTOMER_PROCESS_PASS" not in rendered or proc.get("state") not in {"EXITED","COMPLETED"}:
                fail("LOCAL_MCP_PROCESS_INVALID")
            print("FRESH_CUSTOMER_LOCAL_MCP_PROCESS=PASS")

            activity=client.tool("get_activity",{"limit":20})
            if activity.get("metadata_only") is not True or not activity.get("events"):
                fail("LOCAL_MCP_ACTIVITY_INVALID")
            print("FRESH_CUSTOMER_LOCAL_MCP_ACTIVITY=PASS")

            receipt_dir=xdg_data/"hara-commander"/"receipts"
            receipts=list(receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []
            if len(receipts)<2:
                fail("LOCAL_MCP_RECEIPTS_MISSING")
            for receipt in receipts:
                if (receipt.stat().st_mode & 0o777)!=0o600:
                    fail("LOCAL_MCP_RECEIPT_MODE_INVALID")
                data=json.loads(receipt.read_text())
                blob=json.dumps(data).lower()
                if "fresh_customer_process_pass" in blob or '"command"' in blob or "payload_json" in blob:
                    fail("LOCAL_MCP_RECEIPT_RAW_CONTENT_PRESENT")
            print("FRESH_CUSTOMER_LOCAL_MCP_RECEIPTS=PASS")

        print("FRESH_CUSTOMER_ACCEPTANCE_LOCAL_PATH=PASS")
        print("FRESH_CUSTOMER_REMOTE_USAGE_PATH=NOT_EXERCISED_DO_CAPACITY")
        return 0
    finally:
        token=""
        device_token=""
        if client is not None:
            client.close()
        try:
            d1(cleanup)
            remaining=rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id={q(tenant)};")
            if remaining==[{"n":0}]:
                print("FRESH_CUSTOMER_DEV_FIXTURE_CLEANUP=PASS")
            else:
                print("FRESH_CUSTOMER_DEV_FIXTURE_CLEANUP=FAIL")
        except Exception:
            print("FRESH_CUSTOMER_DEV_FIXTURE_CLEANUP=ERROR")

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FRESH_CUSTOMER_ACCEPTANCE=FAIL:"+str(exc))
        raise SystemExit(1)
