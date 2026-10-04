#!/usr/bin/env python3
import hashlib
import json
import fnmatch
import difflib
import shutil
import os
import platform
import pty
import re
import select
import signal
import sys
import uuid
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AGENT_VERSION = "0.3.24"
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hara-commander/device.env"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "hara-commander"
RECEIPT_DIR = DATA_DIR / "receipts"
STATUS_FILE = DATA_DIR / "runtime-status.json"
SESSION_FILE = DATA_DIR / "operator-session.json"
CONSOLE_EVENTS_FILE = DATA_DIR / "console-events.jsonl"
APPROVAL_DIR = DATA_DIR / "approvals"
PREIMAGE_DIR = DATA_DIR / "preimages"
SESSION_MAX_SECONDS = 12 * 60 * 60
FUNCTION_ID = "device.info"
FUNCTION_IDS = (
    "device.info", "device.ping", "system.uptime", "system.resources", "workspace.inspect", "process.list",
    "filesystem.info", "filesystem.hash", "filesystem.diff", "filesystem.search", "filesystem.list", "filesystem.read", "filesystem.read_many",
)
DIRECT_TOOL_FUNCTIONS = {
    "hara.device.info":"device.info",
    "hara.ping":"device.ping",
    "hara.system.uptime":"system.uptime",
    "hara.system.resources":"system.resources",
    "hara.workspace.inspect":"workspace.inspect",
    "hara.processes.list":"process.list",
    "hara.files.info":"filesystem.info",
    "hara.files.hash":"filesystem.hash",
    "hara.files.diff":"filesystem.diff",
    "hara.files.search":"filesystem.search",
    "hara.files.list":"filesystem.list",
    "hara.files.read":"filesystem.read",
    "hara.files.read_many":"filesystem.read_many",
}

FILESYSTEM_MUTATION_TOOLS = {
    "hara.files.create_directory",
    "hara.files.write",
    "hara.files.edit",
    "hara.files.move",
    "hara.files.copy",
    "hara.files.delete",
    "hara.files.rollback",
}
PROCESS_TOOLS = {
    "hara.process.sessions",
    "hara.process.start",
    "hara.process.output",
    "hara.process.interact",
    "hara.process.kill",
}
PROCESS_MUTATION_TOOLS = {
    "hara.process.start",
    "hara.process.interact",
    "hara.process.kill",
}
PROCESS_SESSIONS = {}
MAX_PROCESS_LINES = 5000

def _is_process_tool(tool_id):
    return str(tool_id or "") in PROCESS_TOOLS

def _is_mutation_tool(tool_id):
    tool=str(tool_id or "")
    return tool in FILESYSTEM_MUTATION_TOOLS or tool in PROCESS_MUTATION_TOOLS

def _mutation_class(tool_id):
    tool=str(tool_id or "")
    if tool in PROCESS_MUTATION_TOOLS: return "PROCESS_EXECUTION_V1"
    if tool == "hara.files.rollback": return "FILESYSTEM_ROLLBACK_V1"
    if tool in FILESYSTEM_MUTATION_TOOLS: return "FILESYSTEM_MUTATION_V1"
    return "READ_ONLY_OR_NONE_V1"

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

def append_console_event(event, call=None, *, state=None, error_code=None, receipt_sha256=None, approval_id=None, action_summary=None):
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
        "approval_id":approval_id,
        "action_summary":action_summary,
        "payload_values_exposed":False,
        "secret_material_exposed":False,
    }
    if isinstance(call, dict):
        payload["tool_id"] = str(call.get("tool_id") or "") or None
        inner = call.get("payload") or {}
        payload["function_id"] = str(inner.get("function_id") or DIRECT_TOOL_FUNCTIONS.get(payload["tool_id"]) or "") or None
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
    request_id = str(payload.get("request_id") or "")
    state = str(payload.get("state") or "")
    error = str(payload.get("error_code") or "")
    receipt = str(payload.get("receipt_sha256") or "")
    approval_id = str(payload.get("approval_id") or "")
    action_summary = str(payload.get("action_summary") or "")
    command = tool if tool != "-" else function_id
    suffix = f" cliente=MCP comando={command} tool={tool}"
    if function_id != "-" and function_id != tool:
        suffix += " funcao=" + function_id
    if request_id:
        suffix += " request=" + request_id[:12] + ("..." if len(request_id) > 12 else "")
    if state:
        suffix += " state=" + state
    if error:
        suffix += " error=" + error
    if receipt:
        suffix += " receipt=" + receipt[:12] + "..."
    if action_summary:
        suffix += " acao=" + action_summary
    if approval_id:
        suffix += " approval=" + approval_id[:12] + "..."
    return f"[{stamp}] {event:<18}{suffix}"

def _redact_command_preview(value):
    text=str(value or "")
    text=re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*=\s*([^\s]+)",lambda m:m.group(1)+"=<redacted>",text)
    text=re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",r"\1<redacted>",text)
    return text if len(text)<=240 else text[:237]+"..."

def _safe_action_summary(call):
    tool=str(call.get("tool_id") or "")
    p=call.get("payload") or {}
    if tool=="hara.files.create_directory": return f"mkdir path={p.get('path')}"
    if tool=="hara.files.write": return f"write mode={p.get('mode','rewrite')} path={p.get('path')} bytes={len(str(p.get('content') or '').encode('utf-8'))}"
    if tool=="hara.files.edit": return f"edit path={p.get('path')} old_bytes={len(str(p.get('old_text') or '').encode('utf-8'))} new_bytes={len(str(p.get('new_text') or '').encode('utf-8'))} all={bool(p.get('replace_all'))}"
    if tool=="hara.files.move": return f"move {p.get('source')} -> {p.get('destination')}"
    if tool=="hara.files.copy": return f"copy {p.get('source')} -> {p.get('destination')}"
    if tool=="hara.files.delete": return f"delete file path={p.get('path')} (preimage required)"
    if tool=="hara.files.rollback": return f"rollback preimage={p.get('preimage_id')}"
    if tool=="hara.process.start": return f"process.start cwd={p.get('cwd') or '~'} command={_redact_command_preview(p.get('command'))}"
    if tool=="hara.process.interact": return f"process.interact session={p.get('session_id')} input={_redact_command_preview(p.get('input'))}"
    if tool=="hara.process.kill": return f"process.kill session={p.get('session_id')} force={bool(p.get('force'))}"
    return tool or "mutation"

def _approval_paths(approval_id):
    safe=re.sub(r"[^A-Za-z0-9_.-]","_",str(approval_id))[:180]
    return APPROVAL_DIR/(safe+".request.json"), APPROVAL_DIR/(safe+".response.json")

def request_local_approval(call, timeout_seconds=30):
    session=read_operator_session()
    if not session: raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
    if str(session.get("agent_version") or "") != AGENT_VERSION:
        raise ValueError("LOCAL_OPERATOR_SESSION_UPGRADE_REQUIRED")
    APPROVAL_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    approval_id=str(call.get("call_id") or call.get("request_id") or "")
    if not approval_id: raise ValueError("APPROVAL_ID_MISSING")
    req_path,res_path=_approval_paths(approval_id)
    res_path.unlink(missing_ok=True)
    summary=_safe_action_summary(call)
    request={"schema":"hara.commander-local-approval.v1","approval_id":approval_id,"tool_id":str(call.get("tool_id") or ""),"action_summary":summary,"requested_at_utc":utcnow(),"expires_at_epoch":int(time.time()+timeout_seconds)}
    tmp=req_path.with_suffix(".tmp"); tmp.write_text(json.dumps(request,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(tmp,0o600); tmp.replace(req_path); os.chmod(req_path,0o600)
    append_console_event("APPROVAL_REQUIRED",call,state="WAITING",approval_id=approval_id,action_summary=summary)
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if not operator_session_active(): raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
        if res_path.is_file():
            try: response=json.loads(res_path.read_text(encoding="utf-8"))
            except Exception: response={}
            decision=str(response.get("decision") or "DENIED").upper()
            req_path.unlink(missing_ok=True); res_path.unlink(missing_ok=True)
            if decision!="APPROVED":
                append_console_event("APPROVAL_DENIED",call,state="DENIED",approval_id=approval_id,action_summary=summary)
                raise ValueError("LOCAL_OPERATOR_APPROVAL_DENIED")
            append_console_event("APPROVAL_GRANTED",call,state="APPROVED",approval_id=approval_id,action_summary=summary)
            return {"state":"APPROVED","approval_id":approval_id,"decided_at_utc":str(response.get("decided_at_utc") or utcnow())}
        time.sleep(0.1)
    req_path.unlink(missing_ok=True); res_path.unlink(missing_ok=True)
    append_console_event("APPROVAL_TIMEOUT",call,state="DENIED",approval_id=approval_id,action_summary=summary)
    raise ValueError("LOCAL_OPERATOR_APPROVAL_TIMEOUT")

def _preimage_paths(preimage_id):
    value=str(preimage_id or "")
    if not re.fullmatch(r"HARA-PREIMAGE-[0-9a-f]{32}",value): raise ValueError("PREIMAGE_ID_INVALID")
    return PREIMAGE_DIR/(value+".json"), PREIMAGE_DIR/(value+".bin")

def _load_preimage(preimage_id):
    meta_path,data_path=_preimage_paths(preimage_id)
    if not meta_path.is_file() or not data_path.is_file(): raise ValueError("PREIMAGE_NOT_FOUND")
    try: meta=json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception: raise ValueError("PREIMAGE_METADATA_INVALID")
    if meta.get("schema")!="hara.commander-file-preimage.v1" or meta.get("preimage_id")!=preimage_id: raise ValueError("PREIMAGE_METADATA_INVALID")
    data=data_path.read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    if sha!=str(meta.get("sha256") or "") or len(data)!=int(meta.get("bytes") or -1): raise ValueError("PREIMAGE_INTEGRITY_FAILED")
    return meta,data

def _store_preimage(path, call_id, source_tool=None):
    if not path.exists() or not path.is_file(): return None
    resolved=path.resolve(strict=True)
    data=resolved.read_bytes()
    if len(data)>2*1024*1024: raise ValueError("PREIMAGE_FILE_TOO_LARGE")
    sha=hashlib.sha256(data).hexdigest()
    st=resolved.stat()
    preimage_id="HARA-PREIMAGE-"+uuid.uuid4().hex
    PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    meta_path,data_path=_preimage_paths(preimage_id)
    data_tmp=data_path.with_suffix(".tmp")
    data_tmp.write_bytes(data); os.chmod(data_tmp,0o600); os.replace(data_tmp,data_path); os.chmod(data_path,0o600)
    meta={
        "schema":"hara.commander-file-preimage.v1",
        "preimage_id":preimage_id,
        "original_path":str(resolved),
        "sha256":sha,
        "bytes":len(data),
        "mode":int(st.st_mode & 0o777),
        "source_call_id":str(call_id or "")[:180],
        "source_tool":str(source_tool or "")[:120] or None,
        "created_at_utc":utcnow(),
    }
    meta_tmp=meta_path.with_suffix(".tmp")
    meta_tmp.write_text(json.dumps(meta,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(meta_tmp,0o600); os.replace(meta_tmp,meta_path); os.chmod(meta_path,0o600)
    return meta

def filesystem_preimages_list(limit=50,path_filter=None):
    PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    wanted=None
    if path_filter:
        wanted=str(Path(path_filter).expanduser().resolve(strict=False))
    items=[]
    for meta_path in PREIMAGE_DIR.glob("HARA-PREIMAGE-*.json"):
        try:
            meta=json.loads(meta_path.read_text(encoding="utf-8"))
            pid=str(meta.get("preimage_id") or "")
            _load_preimage(pid)
            if wanted and str(meta.get("original_path") or "")!=wanted: continue
            items.append({
                "preimage_id":pid,
                "original_path":meta.get("original_path"),
                "sha256":meta.get("sha256"),
                "bytes":meta.get("bytes"),
                "source_tool":meta.get("source_tool"),
                "created_at_utc":meta.get("created_at_utc"),
            })
        except Exception:
            continue
    items.sort(key=lambda x:str(x.get("created_at_utc") or ""),reverse=True)
    capped=items[:max(1,min(100,int(limit)))]
    return {"count":len(capped),"preimages":capped,"truncated":len(items)>len(capped)}

def filesystem_rollback(call,preimage_id):
    meta,data=_load_preimage(preimage_id)
    target=Path(str(meta["original_path"]))
    if target.exists() and not target.is_file(): raise ValueError("ROLLBACK_TARGET_NOT_FILE")
    if not target.parent.exists() or not target.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    current=_store_preimage(target,(call.get("call_id") or "rollback")+"-current","hara.files.rollback") if target.exists() else None
    tmp=target.with_name("."+target.name+".hara-rollback-"+str(os.getpid()))
    tmp.write_bytes(data); os.chmod(tmp,int(meta.get("mode") or 0o600)); os.replace(tmp,target); os.chmod(target,int(meta.get("mode") or 0o600))
    restored_sha=hashlib.sha256(target.read_bytes()).hexdigest()
    if restored_sha!=meta["sha256"]: raise ValueError("ROLLBACK_VERIFY_FAILED")
    return {
        "path":str(target),
        "restored_from_preimage_id":preimage_id,
        "restored_sha256":restored_sha,
        "bytes_restored":len(data),
        "rollback_preimage_id":current.get("preimage_id") if current else None,
        "rollback_preimage_sha256":current.get("sha256") if current else None,
    }

def _append_process_output(session,text):
    combined=session.get("partial","")+str(text)
    parts=combined.split("\n")
    session["partial"]=parts.pop() if parts else ""
    session["lines"].extend(parts)
    if len(session["lines"])>MAX_PROCESS_LINES:
        drop=len(session["lines"])-MAX_PROCESS_LINES
        session["lines"]=session["lines"][drop:]
        session["base_line"]+=drop
        session["cursor"]=max(session["cursor"],session["base_line"])
        session["truncated"]=True

def _process_update_state(session):
    if session.get("exit_code") is not None: return
    try:
        pid,status=os.waitpid(int(session["pid"]),os.WNOHANG)
    except ChildProcessError:
        pid=int(session["pid"]); status=0
    if pid:
        session["exit_code"]=os.waitstatus_to_exitcode(status) if hasattr(os,"waitstatus_to_exitcode") else 0
        if session.get("partial"):
            session["lines"].append(session["partial"]); session["partial"]=""
        try: os.close(int(session["fd"]))
        except OSError: pass
        session["fd"]=-1

def _drain_process(session,wait_ms=0):
    fd=int(session.get("fd",-1))
    if fd<0:
        _process_update_state(session); return
    deadline=time.monotonic()+max(0,min(3000,int(wait_ms)))/1000.0
    first=True
    while True:
        timeout=max(0.0,deadline-time.monotonic()) if wait_ms else 0.0
        try: ready,_,_=select.select([fd],[],[],timeout if first else 0.0)
        except (OSError,ValueError): ready=[]
        first=False
        if not ready: break
        try: data=os.read(fd,65536)
        except BlockingIOError: break
        except OSError: data=b""
        if not data: break
        _append_process_output(session,data.decode("utf-8",errors="replace"))
        if time.monotonic()>=deadline: break
    _process_update_state(session)

def _process_get(session_id):
    sid=str(session_id or "")
    session=PROCESS_SESSIONS.get(sid)
    if not session: raise ValueError("PROCESS_SESSION_NOT_FOUND")
    return session

def _process_output_payload(session,offset=None,length=200,wait_ms=0):
    _drain_process(session,wait_ms)
    base=int(session.get("base_line",0)); lines=session.get("lines",[])
    start=int(session.get("cursor",base)) if offset is None else int(offset)
    truncated_before=start<base
    if start<base: start=base
    rel=max(0,start-base); selected=lines[rel:rel+max(1,min(500,int(length)))]
    next_offset=start+len(selected)
    if offset is None: session["cursor"]=next_offset
    state="EXITED" if session.get("exit_code") is not None else "RUNNING"
    return {"session_id":session["session_id"],"pid":session["pid"],"state":state,"exit_code":session.get("exit_code"),"offset":start,"next_offset":next_offset,"base_line":base,"total_lines":base+len(lines),"text":"\n".join(selected),"partial":session.get("partial","")[:1000],"truncated_before":truncated_before,"buffer_truncated":bool(session.get("truncated"))}

def process_start(command,cwd=None,timeout_ms=1000):
    command=str(command or "")
    if not command or len(command)>4096 or "\x00" in command: raise ValueError("PROCESS_COMMAND_INVALID")
    work=Path(cwd).expanduser().resolve(strict=True) if cwd else Path.home()
    if not work.is_dir(): raise ValueError("PROCESS_CWD_INVALID")
    pid,fd=pty.fork()
    if pid==0:
        try:
            os.chdir(work)
            os.execv("/bin/bash",["/bin/bash","-lc",command])
        except Exception:
            os._exit(127)
    os.set_blocking(fd,False)
    sid="HARA-PROC-"+uuid.uuid4().hex
    session={"session_id":sid,"pid":pid,"fd":fd,"started_at_utc":utcnow(),"command_sha256":hashlib.sha256(command.encode()).hexdigest(),"cwd":str(work),"lines":[],"partial":"","base_line":0,"cursor":0,"truncated":False,"exit_code":None}
    PROCESS_SESSIONS[sid]=session
    output=_process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)
    return {**output,"cwd":str(work),"command_sha256":session["command_sha256"],"command_preview":_redact_command_preview(command)}

def process_sessions():
    items=[]
    for sid,session in list(PROCESS_SESSIONS.items()):
        _drain_process(session,0)
        items.append({"session_id":sid,"pid":session["pid"],"state":"EXITED" if session.get("exit_code") is not None else "RUNNING","exit_code":session.get("exit_code"),"started_at_utc":session["started_at_utc"],"cwd":session["cwd"],"command_sha256":session["command_sha256"]})
    return {"count":len(items),"sessions":items}

def process_interact(session_id,input_text,timeout_ms=1000):
    session=_process_get(session_id); _process_update_state(session)
    if session.get("exit_code") is not None or int(session.get("fd",-1))<0: raise ValueError("PROCESS_SESSION_EXITED")
    text=str(input_text or "")
    if len(text)>4096 or "\x00" in text: raise ValueError("PROCESS_INPUT_INVALID")
    data=(text+"\n").encode("utf-8")
    os.write(int(session["fd"]),data)
    return _process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)

def process_kill(session_id,force=False):
    session=_process_get(session_id); _process_update_state(session)
    if session.get("exit_code") is not None:
        return {"session_id":session_id,"pid":session["pid"],"state":"EXITED","exit_code":session.get("exit_code"),"existing":True}
    sig=signal.SIGKILL if force else signal.SIGTERM
    try:
        try: os.killpg(int(session["pid"]),sig)
        except ProcessLookupError: pass
        except OSError: os.kill(int(session["pid"]),sig)
    except ProcessLookupError: pass
    deadline=time.monotonic()+0.5
    while time.monotonic()<deadline and session.get("exit_code") is None:
        _drain_process(session,50)
    return {"session_id":session_id,"pid":session["pid"],"state":"EXITED" if session.get("exit_code") is not None else "TERMINATING","exit_code":session.get("exit_code"),"signal":"SIGKILL" if force else "SIGTERM"}

def cleanup_process_sessions():
    killed=0
    for sid,session in list(PROCESS_SESSIONS.items()):
        _process_update_state(session)
        if session.get("exit_code") is None:
            try:
                try: os.killpg(int(session["pid"]),signal.SIGKILL)
                except OSError: os.kill(int(session["pid"]),signal.SIGKILL)
                killed+=1
            except ProcessLookupError: pass
            _drain_process(session,50)
    return killed

def filesystem_create_directory(path_value,parents=True):
    path=Path(path_value).expanduser()
    existed=path.exists()
    if existed and not path.is_dir(): raise ValueError("PATH_EXISTS_NOT_DIRECTORY")
    path.mkdir(parents=bool(parents),exist_ok=True)
    return {"path":str(path.resolve()),"created":not existed,"parents":bool(parents)}

def filesystem_write(call,path_value,content,mode="rewrite"):
    path=Path(path_value).expanduser()
    if path.exists() and not path.is_file(): raise ValueError("PATH_NOT_FILE")
    data=str(content)
    if len(data.encode("utf-8"))>65536: raise ValueError("WRITE_TOO_LARGE")
    preimage=_store_preimage(path,call.get("call_id") or "write","hara.files.write") if path.exists() else None
    if not path.parent.exists() or not path.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    if mode=="append":
        with path.open("a",encoding="utf-8") as fh: fh.write(data)
    elif mode=="rewrite":
        tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid()))
        tmp.write_text(data,encoding="utf-8"); os.replace(tmp,path)
    else: raise ValueError("WRITE_MODE_INVALID")
    return {"path":str(path.resolve()),"mode":mode,"bytes_written":len(data.encode("utf-8")),"preimage_id":preimage.get("preimage_id") if preimage else None,"preimage_sha256":preimage.get("sha256") if preimage else None}

def filesystem_edit(call,path_value,old_text,new_text,replace_all=False):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    text=path.read_text(encoding="utf-8",errors="strict")
    count=text.count(old_text)
    if count==0: raise ValueError("EDIT_MATCH_NOT_FOUND")
    if not replace_all and count!=1: raise ValueError("EDIT_MATCH_AMBIGUOUS")
    preimage=_store_preimage(path,call.get("call_id") or "edit","hara.files.edit")
    updated=text.replace(old_text,new_text) if replace_all else text.replace(old_text,new_text,1)
    tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid())); tmp.write_text(updated,encoding="utf-8"); os.replace(tmp,path)
    return {"path":str(path),"replacements":count if replace_all else 1,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":preimage.get("sha256")}

def filesystem_move(source_value,destination_value):
    src=Path(source_value).expanduser().resolve(strict=True)
    dst=Path(destination_value).expanduser()
    if dst.exists(): raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    moved=shutil.move(str(src),str(dst))
    return {"source":str(src),"destination":str(Path(moved).resolve()),"overwrote":False}

def filesystem_copy(source_value,destination_value):
    src=Path(source_value).expanduser().resolve(strict=True)
    if not src.is_file(): raise ValueError("SOURCE_NOT_FILE")
    if src.stat().st_size>2*1024*1024: raise ValueError("COPY_FILE_TOO_LARGE")
    dst=Path(destination_value).expanduser()
    if dst.exists(): raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    shutil.copy2(str(src),str(dst))
    return {"source":str(src),"destination":str(dst.resolve(strict=True)),"bytes":int(dst.stat().st_size),"sha256":hashlib.sha256(dst.read_bytes()).hexdigest(),"overwrote":False}

def filesystem_delete(call,path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("DELETE_TARGET_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("DELETE_FILE_TOO_LARGE")
    preimage=_store_preimage(path,call.get("call_id") or "delete","hara.files.delete")
    if not preimage: raise ValueError("PREIMAGE_REQUIRED")
    expected=preimage.get("sha256")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError("PREIMAGE_SOURCE_MISMATCH")
    path.unlink()
    if path.exists(): raise ValueError("DELETE_VERIFY_FAILED")
    return {"path":str(path),"deleted":True,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":expected}

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
        "agent_version":AGENT_VERSION,
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
    print("  hara.health / hara.ping / hara.device.info")
    print("  hara.system.uptime / hara.system.resources / hara.workspace.inspect")
    print("  hara.processes.list")
    print("  hara.files.info / hash / diff / search / list")
    print("  hara.files.read / hara.files.read_many")
    print("  hara.files.create_directory / write / edit / move / copy  [aprovação local]")
    print("  hara.files.delete  [preimage + aprovação local]")
    print("  hara.files.preimages.list / rollback  [rollback requer aprovação]")
    print("  hara.process.sessions / output")
    print("  hara.process.start / interact / kill  [aprovação local]")
    print("  hara.functions.list / hara.functions.describe")
    print("  hara.functions.invoke (compatibilidade; somente funções governadas)")
    print("  hara.receipts.get")
    print("")
    print("Origem     : OpenAI / cliente MCP autorizado")
    print("Acesso     : ativo somente enquanto este terminal permanecer aberto")
    print("Argumentos sensíveis, tokens e segredos nunca são exibidos.")
    print("Cada ação será mostrada abaixo com tool, função, estado e receipt.")
    print("Pressione Ctrl+C para revogar o acesso imediatamente.")
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
                        if payload.get("event") == "APPROVAL_REQUIRED" and payload.get("approval_id"):
                            approval_id=str(payload.get("approval_id"))
                            summary=str(payload.get("action_summary") or payload.get("tool_id") or "mutação")
                            try:
                                answer=input(f"\nAutorizar {summary}? [y/N]: ").strip().lower()
                            except EOFError:
                                answer=""
                            decision="APPROVED" if answer in ("y","yes","s","sim") else "DENIED"
                            _,res_path=_approval_paths(approval_id)
                            response={"schema":"hara.commander-local-approval-response.v1","approval_id":approval_id,"decision":decision,"decided_at_utc":utcnow()}
                            tmp=res_path.with_suffix(".tmp"); tmp.write_text(json.dumps(response,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(tmp,0o600); tmp.replace(res_path); os.chmod(res_path,0o600)
                            print(f"LOCAL_APPROVAL={decision}",flush=True)
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
        killed=cleanup_process_sessions()
        if killed: append_console_event("PROCESS_REVOKE",state="KILLED",action_summary=f"managed_processes={killed}")
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

def _function_spec(function_id):
    specs={
        "device.info":("DEVICE","Consulta informações básicas e não sensíveis deste computador."),
        "device.ping":("DEVICE","Valida conectividade ponta a ponta com este Agent."),
        "system.uptime":("SYSTEM","Consulta uptime e load average do sistema."),
        "system.resources":("SYSTEM","Consulta CPU, memória, swap, load average e capacidade do disco raiz sem shell."),
        "workspace.inspect":("WORKSPACE","Inspeciona metadados limitados de projeto e Git HEAD sem executar comandos externos."),
        "process.list":("PROCESS","Lista processos com metadados sanitizados, sem linha de comando ou ambiente."),
        "filesystem.info":("FILESYSTEM","Consulta metadados de um caminho sem ler conteúdo."),
        "filesystem.hash":("FILESYSTEM","Calcula SHA-256 e tamanho de um arquivo regular."),
        "filesystem.diff":("FILESYSTEM","Compara dois arquivos texto com diff unificado limitado."),
        "filesystem.search":("FILESYSTEM","Busca nomes de arquivos ou texto com limites de tempo, tamanho e quantidade."),
        "filesystem.list":("FILESYSTEM","Lista entradas e metadados de um diretório sem ler conteúdo de arquivos."),
        "filesystem.read":("FILESYSTEM","Lê um intervalo limitado de um arquivo texto acessível ao usuário local."),
        "filesystem.read_many":("FILESYSTEM","Lê intervalos limitados de até dez arquivos texto sem abortar o lote por falha individual."),
    }
    if function_id not in specs: raise ValueError("UNKNOWN_FUNCTION_ID")
    domain,description=specs[function_id]
    return {
        "function_id":function_id,"state":"ACTIVE","IDENTITY":{"domain":domain},
        "PURPOSE":{"description_pt_br":description},
        "EXECUTION_SEMANTICS":{"risk_class":"READ_ONLY","change_intent_required":False},
        "AUTHORITY":{"risk_class":"READ_ONLY","change_intent_required":False,"fail_closed":True},
        "FAILURE_ROLLBACK":{"fail_closed":True},
    }

def catalog():
    return {
        "registered_function_count":len(FUNCTION_IDS),
        "executable_function_count":len(FUNCTION_IDS),
        "active_function_count":len(FUNCTION_IDS),
        "domains":["DEVICE","SYSTEM","WORKSPACE","PROCESS","FILESYSTEM"],
        "functions":[{"function_id":fid,"state":"ACTIVE"} for fid in FUNCTION_IDS],
    }

def describe(function_id):
    return _function_spec(function_id)

def device_info(config):
    return {
        "device_id":config["HARA_DEVICE_ID"],"hostname":platform.node(),
        "platform":platform.system().upper(),"platform_release":platform.release(),
        "architecture":config["HARA_DEVICE_ARCH"],"python_version":platform.python_version(),
        "agent_version":AGENT_VERSION,"tunnel_mode":"OUTBOUND_RELAY",
    }

def device_ping(config):
    return {"pong":True,"hostname":platform.node(),"device_id":config["HARA_DEVICE_ID"],"agent_version":AGENT_VERSION,"at_utc":utcnow()}

def system_uptime():
    uptime=float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    load=os.getloadavg()
    return {"uptime_seconds":round(uptime,2),"load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2]}

def system_resources():
    mem={}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8",errors="replace").splitlines():
            if ":" not in line: continue
            key,raw=line.split(":",1)
            m=re.search(r"([0-9]+)",raw)
            if m: mem[key]=int(m.group(1))*1024
    except (FileNotFoundError,PermissionError,OSError):
        mem={}
    disk=shutil.disk_usage("/")
    load=os.getloadavg()
    return {
        "cpu_logical":int(os.cpu_count() or 0),
        "load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2],
        "memory_total_bytes":mem.get("MemTotal"),"memory_available_bytes":mem.get("MemAvailable"),
        "swap_total_bytes":mem.get("SwapTotal"),"swap_free_bytes":mem.get("SwapFree"),
        "root_disk_total_bytes":int(disk.total),"root_disk_used_bytes":int(disk.used),"root_disk_free_bytes":int(disk.free),
    }

def _workspace_git_metadata(root):
    marker=root/".git"
    if not marker.exists(): return {"present":False}
    try:
        gitdir=marker
        if marker.is_file():
            raw=marker.read_text(encoding="utf-8",errors="replace")[:4096].strip()
            if not raw.lower().startswith("gitdir:"): return {"present":True,"branch":None,"head_oid":None,"head_state":"UNRESOLVED"}
            value=raw.split(":",1)[1].strip()
            gitdir=(root/value).resolve(strict=True) if not Path(value).is_absolute() else Path(value).resolve(strict=True)
        common=gitdir
        common_file=gitdir/"commondir"
        if common_file.is_file():
            common_raw=common_file.read_text(encoding="utf-8",errors="replace")[:4096].strip()
            if common_raw:
                common=(gitdir/common_raw).resolve(strict=True) if not Path(common_raw).is_absolute() else Path(common_raw).resolve(strict=True)
        head=(gitdir/"HEAD").read_text(encoding="utf-8",errors="replace")[:4096].strip()
        branch=None; oid=None; state="DETACHED"
        if head.startswith("ref: "):
            ref=head[5:].strip()
            branch=ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
            state="BRANCH"
            for base in (gitdir,common):
                refpath=base/ref
                if refpath.is_file():
                    candidate=refpath.read_text(encoding="utf-8",errors="replace")[:128].strip()
                    if re.fullmatch(r"[0-9a-fA-F]{40,64}",candidate):
                        oid=candidate.lower(); break
            packed=common/"packed-refs"
            if oid is None and packed.is_file() and packed.stat().st_size <= 4*1024*1024:
                for line in packed.read_text(encoding="utf-8",errors="replace").splitlines():
                    if line.startswith("#") or line.startswith("^") or " " not in line: continue
                    candidate,name=line.split(" ",1)
                    if name.strip()==ref and re.fullmatch(r"[0-9a-fA-F]{40,64}",candidate):
                        oid=candidate.lower(); break
        elif re.fullmatch(r"[0-9a-fA-F]{40,64}",head):
            oid=head.lower()
        return {"present":True,"branch":branch,"head_oid":oid,"head_state":state,"dirty_state":"UNKNOWN_NOT_EVALUATED"}
    except (FileNotFoundError,PermissionError,OSError,ValueError):
        return {"present":True,"branch":None,"head_oid":None,"head_state":"UNRESOLVED","dirty_state":"UNKNOWN_NOT_EVALUATED"}

def workspace_inspect(path_value,max_entries=80):
    target=Path(path_value).expanduser().resolve(strict=True)
    start=target if target.is_dir() else target.parent
    markers=(".git","pyproject.toml","package.json","Cargo.toml","go.mod","pom.xml","build.gradle","build.gradle.kts","requirements.txt","CMakeLists.txt","Makefile")
    root=start; root_marker=None
    current=start
    for _ in range(13):
        found=next((name for name in markers if (current/name).exists()),None)
        if found:
            root=current; root_marker=found; break
        if current.parent==current: break
        current=current.parent
    max_entries=max(1,min(200,int(max_entries)))
    children=[]; discovered=[]; scan_truncated=False
    try:
        with os.scandir(root) as it:
            for item in it:
                if len(discovered)>=2000:
                    scan_truncated=True; break
                try:
                    kind="symlink" if item.is_symlink() else "directory" if item.is_dir(follow_symlinks=False) else "file" if item.is_file(follow_symlinks=False) else "other"
                    discovered.append({"name":item.name,"type":kind})
                except (FileNotFoundError,PermissionError,OSError):
                    continue
        discovered.sort(key=lambda item:item["name"].lower())
        children=discovered[:max_entries]
    except PermissionError:
        children=[]; discovered=[]
    manifests=[name for name in markers if name!=".git" and (root/name).is_file()]
    return {
        "requested_path":str(target),"root":str(root),"root_marker":root_marker,
        "manifests":manifests,"entries":children,"entry_count":len(children),
        "entries_truncated":scan_truncated or len(discovered)>max_entries,
        "git":_workspace_git_metadata(root),
        "shell_invoked":False,"external_command_invoked":False,
    }

def process_list(limit=50):
    out=[]
    for name in os.listdir("/proc"):
        if not name.isdigit(): continue
        pid=int(name); base=Path("/proc")/name
        try:
            comm=(base/"comm").read_text(encoding="utf-8",errors="replace").strip()[:160]
            state=None; rss_kb=0
            for line in (base/"status").read_text(encoding="utf-8",errors="replace").splitlines():
                if line.startswith("State:"): state=line.split(":",1)[1].strip()[:80]
                elif line.startswith("VmRSS:"):
                    m=re.search(r"([0-9]+)",line); rss_kb=int(m.group(1)) if m else 0
            out.append({"pid":pid,"name":comm,"state":state,"rss_kb":rss_kb})
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            continue
    out.sort(key=lambda item:(-int(item.get("rss_kb") or 0), int(item["pid"])))
    return {"count":min(len(out),limit),"processes":out[:limit],"command_lines_exposed":False,"environment_exposed":False}

def filesystem_info(path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    st=path.lstat()
    kind="symlink" if path.is_symlink() else "directory" if path.is_dir() else "file" if path.is_file() else "other"
    return {
        "path":str(path),"name":path.name,"type":kind,
        "size_bytes":int(st.st_size) if kind=="file" else None,
        "mode_octal":oct(st.st_mode & 0o777),
        "modified_at_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),
    }

def filesystem_hash(path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    h=hashlib.sha256(); total=0
    with path.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):
            total+=len(chunk)
            if total>128*1024*1024: raise ValueError("HASH_FILE_TOO_LARGE")
            h.update(chunk)
    return {"path":str(path),"bytes":total,"sha256":h.hexdigest()}

def filesystem_diff(left_value,right_value,max_lines=200):
    left=Path(left_value).expanduser().resolve(strict=True); right=Path(right_value).expanduser().resolve(strict=True)
    for path in (left,right):
        if not path.is_file(): raise ValueError("PATH_NOT_FILE")
        if path.stat().st_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
        with path.open("rb") as fh:
            if b"\x00" in fh.read(4096): raise ValueError("BINARY_FILE_DENIED")
    a=left.read_text(encoding="utf-8",errors="replace").splitlines()
    b=right.read_text(encoding="utf-8",errors="replace").splitlines()
    lines=list(difflib.unified_diff(a,b,fromfile=str(left),tofile=str(right),lineterm=""))
    cap=max(1,min(400,int(max_lines))); chosen=lines[:cap]
    return {"left":str(left),"right":str(right),"different":bool(lines),"line_count":len(chosen),"diff":"\n".join(chosen),"truncated":len(lines)>cap}

def filesystem_search(path_value,search_type,pattern,max_results=50,include_hidden=False,ignore_case=True,file_glob=""):
    root=Path(path_value).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    if search_type not in ("files","content"): raise ValueError("SEARCH_TYPE_INVALID")
    if not pattern or len(pattern)>256: raise ValueError("SEARCH_PATTERN_INVALID")
    max_results=max(1,min(100,int(max_results)))
    deadline=time.monotonic()+3.0
    scan_cap=5000
    scanned=0; matches=[]; truncated=False
    needle=pattern.lower() if ignore_case else pattern
    for current,dirs,files in os.walk(root):
        if time.monotonic()>deadline or scanned>=scan_cap:
            truncated=True; break
        if not include_hidden:
            dirs[:]=[d for d in dirs if not d.startswith(".")]
            files=[f for f in files if not f.startswith(".")]
        for name in files:
            if time.monotonic()>deadline or scanned>=scan_cap:
                truncated=True; break
            scanned+=1
            if file_glob and not fnmatch.fnmatch(name,file_glob): continue
            path=Path(current)/name
            rel=str(path.relative_to(root))
            if search_type=="files":
                hay=name.lower() if ignore_case else name
                if needle in hay:
                    matches.append({"path":rel,"type":"file"})
            else:
                try:
                    st=path.stat()
                    if st.st_size>2*1024*1024: continue
                    with path.open("rb") as fh:
                        if b"\x00" in fh.read(4096): continue
                    with path.open("r",encoding="utf-8",errors="replace") as fh:
                        for line_no,line in enumerate(fh,1):
                            hay=line.lower() if ignore_case else line
                            if needle in hay:
                                snippet=line.rstrip("\n")[:300]
                                matches.append({"path":rel,"line":line_no,"text":snippet})
                                if len(matches)>=max_results: break
                except (FileNotFoundError,PermissionError,OSError):
                    continue
            if len(matches)>=max_results:
                truncated=True; break
        if truncated and len(matches)>=max_results: break
    return {"path":str(root),"search_type":search_type,"pattern":pattern,"count":len(matches),"matches":matches[:max_results],"scanned_files":scanned,"truncated":truncated}

def filesystem_list(path_value,limit=100,depth=1):
    root=Path(path_value).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    limit=max(1,min(200,int(limit))); depth=max(1,min(5,int(depth)))
    entries=[]; truncated=False
    def walk(current,level):
        nonlocal truncated
        if truncated or level>depth: return
        try: children=sorted(current.iterdir(),key=lambda e:e.name.lower())
        except PermissionError: return
        for entry in children:
            if len(entries)>=limit: truncated=True; return
            try:
                st=entry.lstat(); kind="symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
                entries.append({"path":str(entry.relative_to(root)),"name":entry.name,"type":kind,"size_bytes":int(st.st_size) if kind=="file" else None,"depth":level})
                if kind=="directory" and level<depth: walk(entry,level+1)
            except (FileNotFoundError,PermissionError,OSError):
                continue
    walk(root,1)
    return {"path":str(root),"count":len(entries),"entries":entries,"depth":depth,"truncated":truncated}

def filesystem_read(path_value,offset=0,length=200):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    if path.stat().st_size > 2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    lines=[]; binary=False
    with path.open("rb") as fh:
        head=fh.read(4096)
        binary=b"\x00" in head
    if binary: raise ValueError("BINARY_FILE_DENIED")
    with path.open("r",encoding="utf-8",errors="replace") as fh:
        for idx,line in enumerate(fh):
            if idx < offset: continue
            if len(lines)>=length: break
            lines.append(line.rstrip("\n"))
    text="\n".join(lines)
    if len(text)>65536: text=text[:65536]+"\n[HARA_COMMANDER_OUTPUT_TRUNCATED]"
    return {"path":str(path),"offset":offset,"line_count":len(lines),"text":text}

def filesystem_read_many(paths,offset=0,length=100):
    out=[]
    for raw in paths[:10]:
        try:
            item=filesystem_read(str(raw),offset,length)
            out.append({"path":item["path"],"state":"PASS","offset":item["offset"],"line_count":item["line_count"],"text":item["text"]})
        except Exception as exc:
            out.append({"path":str(raw),"state":"FAILED","error_code":safe_error_code(exc)})
    return {"count":len(out),"files":out,"offset":offset,"length":length}

def invoke(config, function_id, arguments):
    if function_id not in FUNCTION_IDS: raise ValueError("UNKNOWN_FUNCTION_ID")
    argv=arguments.get("argv") if isinstance(arguments,dict) else None
    if not isinstance(argv,list): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
    if function_id=="device.info":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=device_info(config)
    elif function_id=="device.ping":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=device_ping(config)
    elif function_id=="system.uptime":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=system_uptime()
    elif function_id=="system.resources":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=system_resources()
    elif function_id=="workspace.inspect":
        if len(argv)<1 or len(argv)>2: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        max_entries=int(argv[1]) if len(argv)>=2 else 80
        if not 1<=max_entries<=200: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=workspace_inspect(str(argv[0]),max_entries)
    elif function_id=="process.list":
        if len(argv)>1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        limit=int(argv[0]) if argv else 50
        if not 1<=limit<=200: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=process_list(limit)
    elif function_id=="filesystem.hash":
        if len(argv)!=1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_hash(str(argv[0]))
    elif function_id=="filesystem.diff":
        if len(argv)<2 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_diff(str(argv[0]),str(argv[1]),int(argv[2]) if len(argv)>=3 else 200)
    elif function_id=="filesystem.search":
        if len(argv)<3 or len(argv)>7: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_search(str(argv[0]),str(argv[1]),str(argv[2]),int(argv[3]) if len(argv)>=4 else 50,argv[4]=="1" if len(argv)>=5 else False,argv[5]!="0" if len(argv)>=6 else True,str(argv[6]) if len(argv)>=7 else "")
    elif function_id=="filesystem.info":
        if len(argv)!=1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_info(str(argv[0]))
    elif function_id=="filesystem.list":
        if len(argv)<1 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        limit=int(argv[1]) if len(argv)>=2 else 100; depth=int(argv[2]) if len(argv)>=3 else 1
        if not 1<=limit<=200 or not 1<=depth<=5: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_list(str(argv[0]),limit,depth)
    elif function_id=="filesystem.read_many":
        if len(argv)<3 or len(argv)>12: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        offset=int(argv[0]); length=int(argv[1]); paths=argv[2:]
        if offset<0 or not 1<=length<=100 or not 1<=len(paths)<=10: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_read_many(paths,offset,length)
    elif function_id=="filesystem.read":
        if len(argv)<1 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        offset=int(argv[1]) if len(argv)>=2 else 0; length=int(argv[2]) if len(argv)>=3 else 200
        if offset<0 or not 1<=length<=400: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_read(str(argv[0]),offset,length)
    return {"function_id":function_id,"risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}

def write_receipt(config, call, state, result=None):
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool_id = str(call.get("tool_id") or "")
    result_binding = "NONE"
    result_stdout_sha256 = None
    if tool_id == "hara.functions.invoke" or tool_id in DIRECT_TOOL_FUNCTIONS or _is_mutation_tool(tool_id) or _is_process_tool(tool_id):
        stdout = str((result or {}).get("stdout") or "")
        result_binding = "STDOUT_SHA256_V1"
        result_stdout_sha256 = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    approval=call.get("_local_approval") or {}
    mutation=_is_mutation_tool(tool_id)
    preimage=(result or {}).get("preimage_sha256") if isinstance(result,dict) else None
    preimage_id=(result or {}).get("preimage_id") if isinstance(result,dict) else None
    rollback_preimage_id=(result or {}).get("rollback_preimage_id") if isinstance(result,dict) else None
    receipt = {
        "schema":"hara.commander-device-receipt.v1",
        "request_id":str(call.get("request_id") or ""),
        "device_id":config["HARA_DEVICE_ID"],
        "tool_id":tool_id,
        "function_id_if_any":(call.get("payload") or {}).get("function_id") or DIRECT_TOOL_FUNCTIONS.get(tool_id) or ((result or {}).get("function_id") if isinstance(result,dict) else None),
        "transport_mode":"OUTBOUND_RELAY",
        "operational_authority":"HARA_SERVICES",
        "execution_authority":"HARA_COMMANDER_AGENT",
        "mutation_class":_mutation_class(tool_id),
        "human_approval_required":mutation,
        "human_approval_state":approval.get("state") if mutation else None,
        "preimage_sha256":preimage,
        "preimage_id":preimage_id,
        "rollback_preimage_id":rollback_preimage_id,
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
            "registered_function_count":len(FUNCTION_IDS),
            "executable_function_count":len(FUNCTION_IDS),
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
    elif tool in DIRECT_TOOL_FUNCTIONS:
        fid=DIRECT_TOOL_FUNCTIONS[tool]
        if tool in ("hara.device.info","hara.ping","hara.system.uptime","hara.system.resources"):
            if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
            argv=[]
        elif tool=="hara.workspace.inspect":
            if "path" not in payload or any(k not in ("path","max_entries") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "max_entries" in payload: argv.append(str(payload["max_entries"]))
        elif tool=="hara.processes.list":
            if any(k not in ("limit",) for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[] if "limit" not in payload else [str(payload["limit"])]
        elif tool=="hara.files.hash":
            if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
        elif tool=="hara.files.diff":
            if not {"left","right"}.issubset(payload) or any(k not in ("left","right","max_lines") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["left"]),str(payload["right"]),str(payload.get("max_lines",200))]
        elif tool=="hara.files.search":
            required={"path","search_type","pattern"}
            allowed=required|{"max_results","include_hidden","ignore_case","file_glob"}
            if not required.issubset(payload) or any(k not in allowed for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"]),str(payload["search_type"]),str(payload["pattern"]),str(payload.get("max_results",50)),"1" if payload.get("include_hidden") else "0","0" if payload.get("ignore_case") is False else "1",str(payload.get("file_glob", ""))]
        elif tool=="hara.files.info":
            if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
        elif tool=="hara.files.list":
            if "path" not in payload or any(k not in ("path","limit","depth") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "limit" in payload or "depth" in payload: argv.append(str(payload.get("limit",100)))
            if "depth" in payload: argv.append(str(payload["depth"]))
        elif tool=="hara.files.read_many":
            required={"paths"}; allowed=required|{"offset","length"}
            if not required.issubset(payload) or any(k not in allowed for k in payload) or not isinstance(payload.get("paths"),list): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            paths=payload["paths"]
            if not 1<=len(paths)<=10: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload.get("offset",0)),str(payload.get("length",100))]+[str(x) for x in paths]
        elif tool=="hara.files.read":
            if "path" not in payload or any(k not in ("path","offset","length") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "offset" in payload or "length" in payload: argv.append(str(payload.get("offset",0)))
            if "length" in payload: argv.append(str(payload["length"]))
        result=invoke(config,fid,{"argv":argv})
    elif tool=="hara.files.preimages.list":
        if any(k not in ("limit","path") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_preimages_list(int(payload.get("limit",50)),payload.get("path"))
        result={"function_id":"filesystem.preimages.list","risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.rollback":
        if set(payload)!={"preimage_id"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_rollback(call,str(payload["preimage_id"]))
        result={"function_id":"filesystem.rollback","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_id":str(payload["preimage_id"]),"preimage_sha256":data.get("restored_sha256"),"rollback_preimage_id":data.get("rollback_preimage_id")}
    elif tool=="hara.process.sessions":
        if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
        data=process_sessions()
        result={"function_id":"process.sessions","risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.start":
        if "command" not in payload or any(k not in ("command","cwd","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_start(str(payload["command"]),payload.get("cwd"),int(payload.get("timeout_ms",1000)))
        result={"function_id":"process.start","risk_class":"PROCESS_EXECUTION","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.output":
        if "session_id" not in payload or any(k not in ("session_id","offset","length","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=_process_output_payload(_process_get(str(payload["session_id"])),payload.get("offset"),int(payload.get("length",200)),int(payload.get("timeout_ms",500)))
        result={"function_id":"process.output","risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.interact":
        if not {"session_id","input"}.issubset(payload) or any(k not in ("session_id","input","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_interact(str(payload["session_id"]),str(payload["input"]),int(payload.get("timeout_ms",1000)))
        result={"function_id":"process.interact","risk_class":"PROCESS_EXECUTION","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.kill":
        if "session_id" not in payload or any(k not in ("session_id","force") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_kill(str(payload["session_id"]),bool(payload.get("force",False)))
        result={"function_id":"process.kill","risk_class":"PROCESS_EXECUTION","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.create_directory":
        if set(payload)-{"path","parents"} or "path" not in payload: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_create_directory(str(payload["path"]),payload.get("parents",True))
        result={"function_id":"filesystem.create_directory","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,**({"preimage_sha256":data.get("preimage_sha256")} if data.get("preimage_sha256") else {})}
    elif tool=="hara.files.write":
        if set(payload)-{"path","content","mode"} or not {"path","content"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_write(call,str(payload["path"]),str(payload["content"]),str(payload.get("mode","rewrite")))
        result={"function_id":"filesystem.write","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.files.edit":
        if set(payload)-{"path","old_text","new_text","replace_all"} or not {"path","old_text","new_text"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_edit(call,str(payload["path"]),str(payload["old_text"]),str(payload["new_text"]),bool(payload.get("replace_all",False)))
        result={"function_id":"filesystem.edit","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.files.move":
        if set(payload)!={"source","destination"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_move(str(payload["source"]),str(payload["destination"]))
        result={"function_id":"filesystem.move","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.copy":
        if set(payload)!={"source","destination"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_copy(str(payload["source"]),str(payload["destination"]))
        result={"function_id":"filesystem.copy","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.delete":
        if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_delete(call,str(payload["path"]))
        result={"function_id":"filesystem.delete","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_id":data.get("preimage_id"),"preimage_sha256":data.get("preimage_sha256")}
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
    mutation=_is_mutation_tool(tool)
    if mutation and isinstance(result,dict):
        result["human_approval_state"]=(call.get("_local_approval") or {}).get("state")
    return {
        "state":"PASS","operational_authority":"HARA_SERVICES",
        "runtime_authority_from_chatgpt":False,"mutation_performed":mutation,
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
        if _is_mutation_tool(call.get("tool_id")):
            call["_local_approval"]=request_local_approval(call)
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
        assert any(x["function_id"]==FUNCTION_ID for x in listing["result"]["functions"])
        assert any(x["function_id"]=="system.uptime" for x in listing["result"]["functions"])
        assert any(x["function_id"]=="system.resources" for x in listing["result"]["functions"])
        assert any(x["function_id"]=="workspace.inspect" for x in listing["result"]["functions"])
        desc=execute_tool(cfg,{**base,"request_id":"selftest-003","tool_id":"hara.functions.describe","payload":{"function_id":FUNCTION_ID}})
        assert desc["result"]["EXECUTION_SEMANTICS"]["risk_class"]=="READ_ONLY"
        inv=execute_tool(cfg,{**base,"request_id":"selftest-004","tool_id":"hara.functions.invoke","payload":{"function_id":FUNCTION_ID,"arguments":{"argv":[]}}})
        uptime=execute_tool(cfg,{**base,"request_id":"selftest-004b","tool_id":"hara.functions.invoke","payload":{"function_id":"system.uptime","arguments":{"argv":[]}}})
        assert "uptime_seconds" in json.loads(uptime["result"]["stdout"])
        resources=execute_tool(cfg,{**base,"request_id":"selftest-resources","tool_id":"hara.system.resources","payload":{}})
        assert json.loads(resources["result"]["stdout"])["cpu_logical"]>=1
        workspace=execute_tool(cfg,{**base,"request_id":"selftest-workspace","tool_id":"hara.workspace.inspect","payload":{"path":d,"max_entries":20}})
        workspace_data=json.loads(workspace["result"]["stdout"]); assert workspace_data["root"]==str(Path(d).resolve()) and workspace_data["external_command_invoked"] is False
        procs=execute_tool(cfg,{**base,"request_id":"selftest-004c","tool_id":"hara.functions.invoke","payload":{"function_id":"process.list","arguments":{"argv":["3"]}}})
        assert len(json.loads(procs["result"]["stdout"])["processes"])<=3
        direct_ping=execute_tool(cfg,{**base,"request_id":"selftest-004d","tool_id":"hara.ping","payload":{}})
        assert json.loads(direct_ping["result"]["stdout"])["pong"] is True
        direct_proc=execute_tool(cfg,{**base,"request_id":"selftest-004e","tool_id":"hara.processes.list","payload":{"limit":2}})
        assert len(json.loads(direct_proc["result"]["stdout"])["processes"])<=2
        mut_call={**base,"call_id":"selftest-mut","request_id":"selftest-004f","tool_id":"hara.files.write","payload":{"path":str(Path(d)/"mut.txt"),"content":"alpha","mode":"rewrite"},"_local_approval":{"state":"APPROVED"}}
        mut=execute_tool(cfg,mut_call)
        assert mut["mutation_performed"] is True
        mut_receipt=read_receipt(mut["bridge_receipt_sha256"])
        assert mut_receipt["mutation_class"]=="FILESYSTEM_MUTATION_V1" and mut_receipt["human_approval_state"]=="APPROVED"
        src=Path(d)/"copy-source.txt"; src.write_text("copy-me",encoding="utf-8")
        cp=execute_tool(cfg,{**base,"call_id":"selftest-copy","request_id":"selftest-copy","tool_id":"hara.files.copy","payload":{"source":str(src),"destination":str(Path(d)/"copy-dest.txt")},"_local_approval":{"state":"APPROVED"}})
        assert json.loads(cp["result"]["stdout"])["sha256"]==hashlib.sha256(b"copy-me").hexdigest()
        doomed=Path(d)/"delete-me.txt"; doomed.write_text("restore-me",encoding="utf-8")
        deleted=execute_tool(cfg,{**base,"call_id":"selftest-delete","request_id":"selftest-delete","tool_id":"hara.files.delete","payload":{"path":str(doomed)},"_local_approval":{"state":"APPROVED"}})
        deleted_data=json.loads(deleted["result"]["stdout"]); assert not doomed.exists() and deleted_data["preimage_id"].startswith("HARA-PREIMAGE-")
        restore=execute_tool(cfg,{**base,"call_id":"selftest-delete-rollback","request_id":"selftest-delete-rollback","tool_id":"hara.files.rollback","payload":{"preimage_id":deleted_data["preimage_id"]},"_local_approval":{"state":"APPROVED"}})
        assert doomed.read_text(encoding="utf-8")=="restore-me"
        target=Path(d)/"rollback.txt"; target.write_text("before",encoding="utf-8")
        write2=execute_tool(cfg,{**base,"call_id":"selftest-preimage-write","request_id":"selftest-preimage-write","tool_id":"hara.files.write","payload":{"path":str(target),"content":"after","mode":"rewrite"},"_local_approval":{"state":"APPROVED"}})
        write2_data=json.loads(write2["result"]["stdout"]); pid=write2_data["preimage_id"]
        assert pid.startswith("HARA-PREIMAGE-") and target.read_text()=="after"
        plist=filesystem_preimages_list(10,str(target)); assert any(x["preimage_id"]==pid for x in plist["preimages"])
        rb=execute_tool(cfg,{**base,"call_id":"selftest-rollback","request_id":"selftest-rollback","tool_id":"hara.files.rollback","payload":{"preimage_id":pid},"_local_approval":{"state":"APPROVED"}})
        rb_data=json.loads(rb["result"]["stdout"]); assert target.read_text()=="before" and rb_data["rollback_preimage_id"].startswith("HARA-PREIMAGE-")
        rb_receipt=read_receipt(rb["bridge_receipt_sha256"]); assert rb_receipt["mutation_class"]=="FILESYSTEM_ROLLBACK_V1"
        proc_call={**base,"call_id":"selftest-proc","request_id":"selftest-004g","tool_id":"hara.process.start","payload":{"command":"printf 'hello\n'","timeout_ms":300},"_local_approval":{"state":"APPROVED"}}
        proc=execute_tool(cfg,proc_call); proc_data=json.loads(proc["result"]["stdout"]); sid=proc_data["session_id"]
        assert proc["mutation_performed"] is True and sid.startswith("HARA-PROC-")
        pout=execute_tool(cfg,{**base,"call_id":"selftest-procout","request_id":"selftest-004h","tool_id":"hara.process.output","payload":{"session_id":sid,"length":20,"timeout_ms":100}})
        pout_data=json.loads(pout["result"]["stdout"])
        observed="\n".join([str(proc_data.get("text") or ""),str(proc_data.get("partial") or ""),str(pout_data.get("text") or ""),str(pout_data.get("partial") or "")])
        assert "hello" in observed
        proc_receipt=read_receipt(proc["bridge_receipt_sha256"]); assert proc_receipt["mutation_class"]=="PROCESS_EXECUTION_V1"
        assert "secret=<redacted>" in _redact_command_preview("echo secret=abc123")
        longp=process_start("sleep 30",None,100)
        longsid=longp["session_id"]; assert _process_get(longsid).get("exit_code") is None
        assert cleanup_process_sessions() >= 1
        _drain_process(_process_get(longsid),100)
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
    global SESSION_FILE, CONSOLE_EVENTS_FILE, APPROVAL_DIR
    with tempfile.TemporaryDirectory() as session_dir:
        SESSION_FILE=Path(session_dir)/"operator-session.json"
        CONSOLE_EVENTS_FILE=Path(session_dir)/"console-events.jsonl"
        APPROVAL_DIR=Path(session_dir)/"approvals"
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
        approval_call={"call_id":"approval-selftest","request_id":"approval-r","tool_id":"hara.files.create_directory","payload":{"path":"/tmp/hara-approval-selftest"}}
        try:
            request_local_approval(approval_call,timeout_seconds=1)
            raise AssertionError("OLD_SESSION_MUTATION_NOT_DENIED")
        except ValueError as exc:
            assert str(exc)=="LOCAL_OPERATOR_SESSION_UPGRADE_REQUIRED"
        session=json.loads(SESSION_FILE.read_text(encoding="utf-8")); session["agent_version"]=AGENT_VERSION
        SESSION_FILE.write_text(json.dumps(session,sort_keys=True,separators=(",",":")),encoding="utf-8")
        import threading
        def approve_selftest():
            req_path,res_path=_approval_paths("approval-selftest")
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline and not req_path.exists(): time.sleep(0.02)
            assert req_path.exists()
            response={"schema":"hara.commander-local-approval-response.v1","approval_id":"approval-selftest","decision":"APPROVED","decided_at_utc":utcnow()}
            res_path.parent.mkdir(parents=True,exist_ok=True); res_path.write_text(json.dumps(response),encoding="utf-8")
        thread=threading.Thread(target=approve_selftest,daemon=True); thread.start()
        approval=request_local_approval(approval_call,timeout_seconds=2); thread.join(timeout=1)
        assert approval["state"]=="APPROVED"
    print("COMMANDER_LINUX_OPERATOR_SESSION_GATE=PASS")
    print("COMMANDER_LOCAL_MUTATION_APPROVAL=PASS")
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
    if len(sys.argv) > 1 and sys.argv[1] in {"help", "--help", "-h"}:
        print("Usage: hara-commander [start|status|stop|help]")
        return
    if len(sys.argv) > 1:
        print("HARA_COMMANDER_UNKNOWN_COMMAND=" + str(sys.argv[1]), file=sys.stderr)
        print("Usage: hara-commander [start|status|stop|help]", file=sys.stderr)
        raise SystemExit(64)
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not try_write_runtime_status(started_at=utcnow(), error_code=None, error_at=None):
        raise RuntimeError("RUNTIME_STATUS_STARTUP_WRITE_FAILED")
    last_heartbeat=0.0
    last_error_code=None
    last_error_write=0.0
    was_authorized=False
    if not operator_session_active():
        mark_device_offline(config)
        append_console_event("AGENT_INERT", state="LOCAL_SESSION_REQUIRED")
    while True:
        now=time.monotonic()
        authorized=operator_session_active()
        if not authorized:
            if was_authorized:
                killed=cleanup_process_sessions()
                if killed: append_console_event("PROCESS_REVOKE",state="KILLED",action_summary=f"managed_processes={killed}")
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
