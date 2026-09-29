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

AGENT_VERSION = "0.3.9"
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hara-commander/device.env"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "hara-commander"
RECEIPT_DIR = DATA_DIR / "receipts"
STATUS_FILE = DATA_DIR / "runtime-status.json"
SESSION_FILE = DATA_DIR / "operator-session.json"
CONSOLE_EVENTS_FILE = DATA_DIR / "console-events.jsonl"
SESSION_MAX_SECONDS = 12 * 60 * 60
FUNCTION_ID = "device.info"

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)

NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler)

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

def _pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _pid_start_marker(pid):
    try:
        raw = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        tail = raw[raw.rfind(")") + 2:].split()
        return tail[19] if len(tail) > 19 else None
    except Exception:
        return None

def read_operator_session():
    if not SESSION_FILE.is_file():
        return None
    try:
        session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if session.get("schema") != "hara.commander-operator-session.v1":
        return None
    started = session.get("started_at_epoch")
    if not isinstance(started, (int, float)):
        return None
    if time.time() - float(started) > SESSION_MAX_SECONDS:
        return None
    pid = session.get("owner_pid")
    if not _pid_alive(pid):
        return None
    marker = _pid_start_marker(pid)
    if not marker or marker != str(session.get("owner_start_marker") or ""):
        return None
    return session

def operator_session_active():
    return read_operator_session() is not None

def append_console_event(event, call=None, *, state=None, error_code=None, receipt_sha256=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "schema":"hara.commander-console-event.v1",
        "at_utc":utcnow(),
        "event":str(event),
        "state":state,
        "tool_id":None,
        "function_id":None,
        "request_id":None,
        "error_code":error_code,
        "receipt_sha256":receipt_sha256,
        "payload_values_exposed":False,
        "secret_material_exposed":False,
    }
    if isinstance(call, dict):
        payload["tool_id"] = str(call.get("tool_id") or "") or None
        inner = call.get("payload") or {}
        payload["function_id"] = str(inner.get("function_id") or "") or None
        payload["request_id"] = str(call.get("request_id") or "") or None
    with CONSOLE_EVENTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(CONSOLE_EVENTS_FILE, 0o600)

def _format_console_event(payload):
    at = str(payload.get("at_utc") or "")
    stamp = at[11:19] if len(at) >= 19 else "--:--:--"
    event = str(payload.get("event") or "EVENT")
    tool = str(payload.get("tool_id") or "-")
    function_id = str(payload.get("function_id") or "-")
    state = str(payload.get("state") or "")
    error = str(payload.get("error_code") or "")
    receipt = str(payload.get("receipt_sha256") or "")
    suffix = ""
    if state:
        suffix += " state=" + state
    if error:
        suffix += " error=" + error
    if receipt:
        suffix += " receipt=" + receipt[:12] + "..."
    return f"[{stamp}] {event:<10} tool={tool} function={function_id}{suffix}"

def mark_device_offline(config):
    try:
        result = post_json(
            config["HARA_COMMANDER_URL"] + "/api/device/offline",
            config["HARA_DEVICE_TOKEN"],
            {"device_id":config["HARA_DEVICE_ID"],"agent_version":AGENT_VERSION,"architecture":config["HARA_DEVICE_ARCH"]},
            timeout=5,
        )
        ok = isinstance(result, dict) and result.get("ok") is True and result.get("state") == "OFFLINE"
        append_console_event("AGENT_OFFLINE", state="OFFLINE" if ok else "FAILED")
        return ok
    except Exception as exc:
        append_console_event("OFFLINE_SYNC_ERROR", state="FAILED", error_code=safe_error_code(exc))
        return False

def start_operator_console():
    config = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = read_operator_session()
    if existing and int(existing.get("owner_pid") or 0) != os.getpid():
        raise RuntimeError("OPERATOR_SESSION_ALREADY_ACTIVE")
    session = {
        "schema":"hara.commander-operator-session.v1",
        "owner_pid":os.getpid(),
        "owner_start_marker":_pid_start_marker(os.getpid()),
        "started_at_epoch":int(time.time()),
        "started_at_utc":utcnow(),
        "device_id":config["HARA_DEVICE_ID"],
        "authorization":"LOCAL_OPERATOR_TERMINAL",
    }
    tmp = SESSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(SESSION_FILE)
    os.chmod(SESSION_FILE, 0o600)
    append_console_event("SESSION_OPEN", state="AUTHORIZED")
    print("")
    print("H.A.R.A. Labs — Commander")
    print("=" * 58)
    print("Sessão local autorizada para clientes de IA")
    print("Computador:", platform.node())
    print("Device ID :", config["HARA_DEVICE_ID"])
    print("Agent     :", AGENT_VERSION)
    print("")
    print("Comandos permitidos nesta sessão:")
    print("  hara.health")
    print("  hara.functions.list")
    print("  hara.functions.describe")
    print("  hara.functions.invoke (somente funções governadas)")
    print("  hara.receipts.get")
    print("")
    print("Argumentos sensíveis e tokens nunca são exibidos.")
    print("Pressione Ctrl+C para encerrar o acesso.")
    print("-" * 58)
    position = CONSOLE_EVENTS_FILE.stat().st_size if CONSOLE_EVENTS_FILE.exists() else 0
    try:
        while True:
            current = read_operator_session()
            if not current or int(current.get("owner_pid") or 0) != os.getpid():
                print("\nSessão encerrada externamente.")
                break
            if CONSOLE_EVENTS_FILE.is_file():
                with CONSOLE_EVENTS_FILE.open("r", encoding="utf-8") as handle:
                    handle.seek(position)
                    while True:
                        raw = handle.readline()
                        if not raw:
                            break
                        position = handle.tell()
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        print(_format_console_event(payload), flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nEncerrando acesso do H.A.R.A. Commander...")
    finally:
        try:
            current = json.loads(SESSION_FILE.read_text(encoding="utf-8")) if SESSION_FILE.is_file() else {}
            if not current or int(current.get("owner_pid") or 0) == os.getpid():
                SESSION_FILE.unlink(missing_ok=True)
        except Exception as exc:
            SESSION_FILE.unlink(missing_ok=True)
            append_console_event("SESSION_CLEANUP_ERROR", state="FAILED", error_code=safe_error_code(exc))
        mark_device_offline(config)
        append_console_event("SESSION_CLOSE", state="REVOKED")
        print("HARA_COMMANDER_SESSION=INACTIVE")

def session_status():
    session = read_operator_session()
    print("HARA_COMMANDER_SESSION=" + ("ACTIVE" if session else "INACTIVE"))
    if session:
        print("SESSION_STARTED_AT_UTC=" + str(session.get("started_at_utc") or ""))
    print("SECRET_MATERIAL_EXPOSED=FALSE")

def stop_operator_session():
    existed = SESSION_FILE.is_file()
    SESSION_FILE.unlink(missing_ok=True)
    try:
        config = load_config()
        mark_device_offline(config)
    except Exception as exc:
        append_console_event("OFFLINE_SYNC_ERROR", state="FAILED", error_code=safe_error_code(exc))
    append_console_event("SESSION_CLOSE", state="REVOKED")
    print("HARA_COMMANDER_SESSION=INACTIVE")
    print("SESSION_WAS_ACTIVE=" + ("TRUE" if existed else "FALSE"))
    print("SECRET_MATERIAL_EXPOSED=FALSE")

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
def post_json(url, token, payload, timeout=25):
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
        with NO_REDIRECT_OPENER.open(req, timeout=timeout) as response:
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
def write_receipt(config, call, state, result=None):
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool_id = str(call.get("tool_id") or "")
    result_binding = "NONE"
    result_stdout_sha256 = None
    if tool_id == "hara.functions.invoke":
        stdout = str((result or {}).get("stdout") or "")
        result_binding = "STDOUT_SHA256_V1"
        result_stdout_sha256 = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    receipt = {
        "schema":"hara.commander-device-receipt.v1",
        "request_id":str(call.get("request_id") or ""),
        "device_id":config["HARA_DEVICE_ID"],
        "tool_id":tool_id,
        "function_id_if_any":(call.get("payload") or {}).get("function_id"),
        "transport_mode":"OUTBOUND_RELAY",
        "operational_authority":"HARA_SERVICES",
        "execution_authority":"HARA_COMMANDER_AGENT",
        "mutation_class":"READ_ONLY_OR_NONE_V1",
        "state":state,
        "payload_values_persisted":False,
        "result_binding":result_binding,
        "result_stdout_sha256":result_stdout_sha256,
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
    sha=write_receipt(config,call,"PASS",result)
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
    if not operator_session_active():
        code="LOCAL_OPERATOR_SESSION_REQUIRED"
        append_console_event("DENIED",call,state="DENIED",error_code=code)
        complete(config,call,"FAILED",{
            "state":"DENIED","operational_authority":"LOCAL_OPERATOR_SESSION",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":{},"blocker":{"code":code},
        },code)
        return
    append_console_event("RECEIVED",call,state="PENDING")
    try:
        append_console_event("EXECUTING",call,state="EXECUTING")
        result=execute_tool(config,call)
        complete(config,call,"COMPLETED",result)
        append_console_event(
            "PASS",call,state="COMPLETED",
            receipt_sha256=result.get("bridge_receipt_sha256") if isinstance(result,dict) else None,
        )
    except Exception as exc:
        code=safe_error_code(exc)
        append_console_event("DENIED",call,state="FAILED",error_code=code)
        complete(config,call,"FAILED",{
            "state":"DENIED","operational_authority":"LOCAL_OPERATOR_SESSION",
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
        expected_stdout_sha=hashlib.sha256(str(inv["result"]["stdout"]).encode("utf-8")).hexdigest()
        assert got["result"]["result_binding"]=="STDOUT_SHA256_V1"
        assert got["result"]["result_stdout_sha256"]==expected_stdout_sha
        try:
            execute_tool(cfg,{**base,"request_id":"selftest-006","tool_id":"hara.functions.invoke","payload":{"function_id":"shell.run","arguments":{"argv":[]}}})
            raise AssertionError("ARBITRARY_FUNCTION_NOT_DENIED")
        except ValueError as exc:
            assert str(exc)=="UNKNOWN_FUNCTION_ID"
    global SESSION_FILE, CONSOLE_EVENTS_FILE
    with tempfile.TemporaryDirectory() as session_dir:
        SESSION_FILE=Path(session_dir)/"operator-session.json"
        CONSOLE_EVENTS_FILE=Path(session_dir)/"console-events.jsonl"
        assert operator_session_active() is False
        SESSION_FILE.write_text(json.dumps({
            "schema":"hara.commander-operator-session.v1",
            "owner_pid":os.getpid(),
            "owner_start_marker":_pid_start_marker(os.getpid()),
            "started_at_epoch":int(time.time()),
            "started_at_utc":utcnow(),
        }),encoding="utf-8")
        assert operator_session_active() is True
        append_console_event("SELFTEST",{"request_id":"r","tool_id":"hara.health","payload":{"secret":"never"}})
        event=json.loads(CONSOLE_EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-1])
        assert event["payload_values_exposed"] is False
        assert event["secret_material_exposed"] is False
        assert "secret" not in event
    print("COMMANDER_LINUX_OPERATOR_SESSION_GATE=PASS")
    print("COMMANDER_LINUX_CONSOLE_SANITIZATION=PASS")
    print("COMMANDER_LINUX_FIVE_TOOL_BRIDGE=PASS")
    print("COMMANDER_ARBITRARY_FUNCTION=DENIED")

def main():
    if "--version" in sys.argv:
        print(AGENT_VERSION); return
    if "--self-test" in sys.argv:
        self_test(); return
    if "--session-start" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="start"):
        start_operator_console(); return
    if "--session-status" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="status"):
        session_status(); return
    if "--session-stop" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="stop"):
        stop_operator_session(); return
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not try_write_runtime_status(started_at=utcnow(), error_code=None, error_at=None):
        raise RuntimeError("RUNTIME_STATUS_STARTUP_WRITE_FAILED")
    last_heartbeat=0.0
    last_error_code=None
    last_error_write=0.0
    was_authorized=False
    while True:
        now=time.monotonic()
        authorized=operator_session_active()
        if not authorized:
            was_authorized=False
            time.sleep(1)
            continue
        if not was_authorized:
            last_heartbeat=0.0
            append_console_event("AGENT_ONLINE",state="AUTHORIZED")
            was_authorized=True
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
