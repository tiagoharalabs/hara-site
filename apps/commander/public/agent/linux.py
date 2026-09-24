#!/usr/bin/env python3
import hashlib
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AGENT_VERSION = "0.3.5"
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hara-commander/device.env"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "hara-commander"
RECEIPT_DIR = DATA_DIR / "receipts"
STATUS_FILE = DATA_DIR / "runtime-status.json"
FUNCTION_ID = "device.info"

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def safe_error_code(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP_{int(exc.code)}"
    if isinstance(exc, urllib.error.URLError):
        return "NETWORK_ERROR"
    raw = str(exc or "").strip().upper()
    if raw and len(raw) <= 80 and all(c.isalnum() or c == "_" for c in raw):
        return raw
    name = type(exc).__name__.upper()
    if name and len(name) <= 80 and all(c.isalnum() or c == "_" for c in name):
        return name
    return "RUNTIME_ERROR"

def write_runtime_status(*, heartbeat_at=None, error_code=None, error_at=None, started_at=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = {}
    if STATUS_FILE.is_file():
        try:
            current = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    payload = {
        "schema":"hara.commander-agent-runtime-status.v1",
        "agent_version":AGENT_VERSION,
        "started_at_utc": started_at if started_at is not None else current.get("started_at_utc"),
        "last_successful_heartbeat_at_utc": heartbeat_at if heartbeat_at is not None else current.get("last_successful_heartbeat_at_utc"),
        "last_runtime_error_code":error_code,
        "last_runtime_error_at_utc":error_at,
        "updated_at_utc":utcnow(),
    }
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
    os.chmod(tmp,0o600)
    tmp.replace(STATUS_FILE)
    os.chmod(STATUS_FILE,0o600)

def try_write_runtime_status(**kwargs):
    try:
        write_runtime_status(**kwargs)
        return True
    except Exception:
        return False

def load_config():
    data = {}
    for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            data[key] = value
    required = ("HARA_COMMANDER_URL","HARA_DEVICE_ID","HARA_DEVICE_TOKEN","HARA_DEVICE_ARCH")
    if not all(data.get(k) for k in required):
        raise RuntimeError("DEVICE_CONFIG_INVALID")
    return data
def post_json(url, token, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload,separators=(",",":")).encode(),
        method="POST",
        headers={
            "content-type":"application/json",
            "accept":"application/json",
            "authorization":"Bearer "+token,
            "user-agent":"HARA-Commander-Agent/"+AGENT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            return None
        raise

def catalog():
    return {
        "registered_function_count":1,
        "executable_function_count":1,
        "active_function_count":1,
        "domains":["DEVICE"],
        "functions":[{"function_id":FUNCTION_ID,"state":"ACTIVE"}],
    }
def describe(function_id):
    if function_id != FUNCTION_ID:
        raise ValueError("UNKNOWN_FUNCTION_ID")
    return {
        "function_id":FUNCTION_ID,
        "state":"ACTIVE",
        "IDENTITY":{"domain":"DEVICE"},
        "PURPOSE":{"description_pt_br":"Consulta informações básicas e não sensíveis deste computador."},
        "EXECUTION_SEMANTICS":{"risk_class":"READ_ONLY","change_intent_required":False},
        "AUTHORITY":{"risk_class":"READ_ONLY","change_intent_required":False,"fail_closed":True},
        "FAILURE_ROLLBACK":{"fail_closed":True},
    }

def device_info(config):
    return {
        "device_id":config["HARA_DEVICE_ID"],
        "hostname":platform.node(),
        "platform":platform.system().upper(),
        "platform_release":platform.release(),
        "architecture":config["HARA_DEVICE_ARCH"],
        "python_version":platform.python_version(),
        "agent_version":AGENT_VERSION,
        "tunnel_mode":"OUTBOUND_RELAY",
    }

def invoke(config, function_id, arguments):
    if function_id != FUNCTION_ID:
        raise ValueError("UNKNOWN_FUNCTION_ID")
    argv = arguments.get("argv") if isinstance(arguments,dict) else None
    if argv != []:
        raise ValueError("FUNCTION_ARGUMENTS_DENIED")
    result = device_info(config)
    return {
        "function_id":FUNCTION_ID,
        "risk_class":"READ_ONLY",
        "process_exit_code":0,
        "stdout":json.dumps(result,sort_keys=True,separators=(",",":")),
        "domain_success_inferred":False,
    }
def write_receipt(config, call, state):
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = {
        "schema":"hara.commander-device-receipt.v1",
        "request_id":str(call.get("request_id") or ""),
        "device_id":config["HARA_DEVICE_ID"],
        "tool_id":str(call.get("tool_id") or ""),
        "function_id_if_any":(call.get("payload") or {}).get("function_id"),
        "transport_mode":"OUTBOUND_RELAY",
        "operational_authority":"HARA_SERVICES",
        "execution_authority":"HARA_COMMANDER_AGENT",
        "mutation_class":"READ_ONLY_OR_NONE_V1",
        "state":state,
        "payload_values_persisted":False,
        "completed_at_utc":utcnow(),
    }
    raw=json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()
    sha=hashlib.sha256(raw).hexdigest()
    path=RECEIPT_DIR/(sha+".json")
    path.write_bytes(raw)
    os.chmod(path,0o600)
    return sha

def read_receipt(identifier):
    value=str(identifier or "").lower()
    if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("RECEIPT_IDENTIFIER_INVALID")
    path=RECEIPT_DIR/(value+".json")
    if not path.is_file():
        raise ValueError("RECEIPT_NOT_FOUND")
    return json.loads(path.read_text(encoding="utf-8"))
def execute_tool(config, call):
    tool=str(call.get("tool_id") or "")
    payload=call.get("payload") or {}
    if tool=="hara.health":
        result={
            "services_bridge_state":"PASS",
            "hara_services_state":"PASS",
            "registered_function_count":1,
            "executable_function_count":1,
            "authority":"HARA_SERVICES",
            "device":device_info(config),
        }
    elif tool=="hara.functions.list":
        if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
        result=catalog()
    elif tool=="hara.functions.describe":
        result=describe(str(payload.get("function_id") or ""))
    elif tool=="hara.functions.invoke":
        result=invoke(config,str(payload.get("function_id") or ""),payload.get("arguments") or {})
    elif tool=="hara.receipts.get":
        result=read_receipt(payload.get("receipt_id_or_sha256"))
        return {
            "state":"PASS","operational_authority":"HARA_SERVICES",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":result,"blocker":None,
        }
    else:
        raise ValueError("TOOL_ID_INVALID")
    sha=write_receipt(config,call,"PASS")
    return {
        "state":"PASS","operational_authority":"HARA_SERVICES",
        "runtime_authority_from_chatgpt":False,"mutation_performed":False,
        "result":result,"blocker":None,"bridge_receipt_sha256":sha,
    }
def complete(config, call, state, result, error_code=None):
    body={"call_id":call["call_id"],"state":state,"result":result}
    if error_code: body["error_code"]=error_code
    post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/complete",config["HARA_DEVICE_TOKEN"],body)

def execute_call(config,call):
    try:
        complete(config,call,"COMPLETED",execute_tool(config,call))
    except Exception as exc:
        code=safe_error_code(exc)
        complete(config,call,"FAILED",{
            "state":"DENIED","operational_authority":"HARA_SERVICES",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":{},"blocker":{"code":code},
        },code)

def self_test():
    global RECEIPT_DIR
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        RECEIPT_DIR=Path(d)
        cfg={"HARA_DEVICE_ID":"selftest","HARA_DEVICE_ARCH":"test"}
        base={"call_id":"c","request_id":"selftest-001","payload":{}}
        assert execute_tool(cfg,{**base,"tool_id":"hara.health"})["state"]=="PASS"
        listing=execute_tool(cfg,{**base,"request_id":"selftest-002","tool_id":"hara.functions.list"})
        assert listing["result"]["functions"][0]["function_id"]==FUNCTION_ID
        desc=execute_tool(cfg,{**base,"request_id":"selftest-003","tool_id":"hara.functions.describe","payload":{"function_id":FUNCTION_ID}})
        assert desc["result"]["EXECUTION_SEMANTICS"]["risk_class"]=="READ_ONLY"
        inv=execute_tool(cfg,{**base,"request_id":"selftest-004","tool_id":"hara.functions.invoke","payload":{"function_id":FUNCTION_ID,"arguments":{"argv":[]}}})
        sha=inv["bridge_receipt_sha256"]
        got=execute_tool(cfg,{**base,"request_id":"selftest-005","tool_id":"hara.receipts.get","payload":{"receipt_id_or_sha256":sha}})
        assert got["result"]["tool_id"]=="hara.functions.invoke"
        try:
            execute_tool(cfg,{**base,"request_id":"selftest-006","tool_id":"hara.functions.invoke","payload":{"function_id":"shell.run","arguments":{"argv":[]}}})
            raise AssertionError("ARBITRARY_FUNCTION_NOT_DENIED")
        except ValueError as exc:
            assert str(exc)=="UNKNOWN_FUNCTION_ID"
    print("COMMANDER_LINUX_FIVE_TOOL_BRIDGE=PASS")
    print("COMMANDER_ARBITRARY_FUNCTION=DENIED")

def main():
    if "--version" in sys.argv:
        print(AGENT_VERSION); return
    if "--self-test" in sys.argv:
        self_test(); return
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not try_write_runtime_status(started_at=utcnow(), error_code=None, error_at=None):
        raise RuntimeError("RUNTIME_STATUS_STARTUP_WRITE_FAILED")
    last_heartbeat=0.0
    last_error_code=None
    last_error_write=0.0
    while True:
        now=time.monotonic()
        try:
            if now-last_heartbeat>=30:
                post_json(config["HARA_COMMANDER_URL"]+"/api/device/heartbeat",config["HARA_DEVICE_TOKEN"],{
                    "device_id":config["HARA_DEVICE_ID"],"architecture":config["HARA_DEVICE_ARCH"],"agent_version":AGENT_VERSION,
                })
                last_heartbeat=now
                last_error_code=None
                try_write_runtime_status(heartbeat_at=utcnow(),error_code=None,error_at=None)
            call=post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/next",config["HARA_DEVICE_TOKEN"],{})
            if call: execute_call(config,call)
        except Exception as exc:
            code=safe_error_code(exc)
            if code != last_error_code or now-last_error_write>=60:
                try_write_runtime_status(error_code=code,error_at=utcnow())
                last_error_code=code
                last_error_write=now
        time.sleep(2)

if __name__=="__main__":
    main()
