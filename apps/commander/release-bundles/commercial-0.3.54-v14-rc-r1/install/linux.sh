#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${HARA_COMMANDER_URL:-https://commander.haralabs.com.br}"
RELEASE_SIGNING_KID="commander-release-v2"
RELEASE_SIGNING_N="p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43"
RELEASE_SIGNING_E="AQAB"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hara-commander"
BIN_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/hara-commander"
USER_BIN="${HOME}/.local/bin"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_FILE="$CONFIG_DIR/device.env"
AGENT="$BIN_DIR/hara-commander-agent"
CLI="$USER_BIN/hara-commander"
TUNNEL_CLIENT="$BIN_DIR/tunnel-client"
TUNNEL_CLIENT_VERSION="0.0.15"
TUNNEL_CLIENT_BASE_URL="https://persistent.oaistatic.com/tunnel-client/v0.0.15"
TUNNEL_CLIENT_SHA256_AMD64="8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1"
TUNNEL_CLIENT_SHA256_ARM64="c51bfd883fc22e3445494a03c0179875176564bde470661b308fd83af5d01abb"
UNIT="$SYSTEMD_DIR/hara-commander-agent.service"
SERVICE="hara-commander-agent.service"
STATUS_FILE="$BIN_DIR/runtime-status.json"
APPROVAL_MODE_RAW="${HARA_COMMANDER_APPROVAL_MODE:-}"
TRANSPORT_MODE_RAW="${HARA_COMMANDER_TRANSPORT_MODE:-}"
TUNNEL_AUTOSTART_RAW="${HARA_COMMANDER_TUNNEL_AUTOSTART:-}"
ACTION="${1:-install}"
ACTION="${ACTION#--}"
REENROLL=FALSE
REENROLL_BACKUP=""
REENROLL_CONFIG_REPLACED=FALSE
REENROLL_SERVICE_WAS_ACTIVE=FALSE

# Reattach to the existing per-user systemd/DBus runtime when invoked from
# non-graphical SSH/automation sessions that omit the usual desktop env.
if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'HARA Commander requires %s.\n' "$1" >&2
    exit 2
  }
}

need curl
need python3
need systemctl

verify_release_manifest_signature() {
  local manifest="$1" signature="$2"
  python3 - "$manifest" "$signature" "$RELEASE_SIGNING_KID" "$RELEASE_SIGNING_N" "$RELEASE_SIGNING_E" <<'PYRELEASESIG'
import base64,hashlib,hmac,json,sys
manifest_path,sig_path,kid,n_b64,e_b64=sys.argv[1:6]
def b64ud(value):
    return base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))
raw=open(manifest_path,"rb").read()
obj=json.load(open(sig_path,encoding="utf-8"))
if obj.get("schema")!="hara.commander-release-signature.v1": raise SystemExit(2)
if obj.get("alg")!="RS256" or obj.get("kid")!=kid: raise SystemExit(2)
if obj.get("manifest_sha256")!=hashlib.sha256(raw).hexdigest(): raise SystemExit(3)
sig=b64ud(str(obj.get("signature") or ""))
n=int.from_bytes(b64ud(n_b64),"big"); e=int.from_bytes(b64ud(e_b64),"big")
size=(n.bit_length()+7)//8
if len(sig)!=size: raise SystemExit(4)
em=pow(int.from_bytes(sig,"big"),e,n).to_bytes(size,"big")
digest_info=bytes.fromhex("3031300d060960864801650304020105000420")+hashlib.sha256(raw).digest()
padding=size-len(digest_info)-3
expected=b"\x00\x01"+(b"\xff"*padding)+b"\x00"+digest_info
if padding<8 or not hmac.compare_digest(em,expected): raise SystemExit(5)
PYRELEASESIG
}

read_config_value() {
  local key="$1"
  [ -f "$CONFIG_FILE" ] || return 1
  python3 - "$CONFIG_FILE" "$key" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); key=sys.argv[2]
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith(key+"="):
        print(raw.split("=",1)[1]); raise SystemExit(0)
raise SystemExit(1)
PY
}

resolve_tunnel_autostart() {
  local mode="${TUNNEL_AUTOSTART_RAW:-}"
  if [ -z "$mode" ] && [ -f "$CONFIG_FILE" ]; then
    mode="$(read_config_value HARA_COMMANDER_TUNNEL_AUTOSTART 2>/dev/null || true)"
  fi
  mode="${mode^^}"
  case "$mode" in
    ""|OFF|FALSE|NO|0) printf 'OFF\n' ;;
    ON|TRUE|YES|1) printf 'ON\n' ;;
    *) echo 'OPENAI_TUNNEL_AUTOSTART_INVALID' >&2; return 64 ;;
  esac
}

resolve_approval_mode() {
  local mode="${APPROVAL_MODE_RAW:-}"
  if [ -z "$mode" ] && [ -f "$CONFIG_FILE" ]; then
    mode="$(read_config_value HARA_COMMANDER_APPROVAL_MODE 2>/dev/null || true)"
  fi
  # Safe customer default: unattended mutations require explicit opt-in.
  [ -n "$mode" ] || mode="ASK_EVERY_ACTION"
  mode="${mode^^}"
  case "$mode" in
    ASK|ASK_EVERY_ACTION) printf 'ASK_EVERY_ACTION
' ;;
    SESSION|SESSION_TRUSTED) printf 'SESSION_TRUSTED
' ;;
    AUTO|ALWAYS|PERSISTENT|PERSISTENT_TRUSTED) printf 'PERSISTENT_TRUSTED
' ;;
    *) echo 'DEVICE_APPROVAL_MODE_INVALID' >&2; return 64 ;;
  esac
}

read_runtime_status_value() {
  local key="$1"
  [ -f "$STATUS_FILE" ] || return 1
  python3 - "$STATUS_FILE" "$key" <<'PY'
import json,sys
from pathlib import Path
obj=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value=obj.get(sys.argv[2])
if value is None or value == "":
    raise SystemExit(1)
print(value)
PY
}

wait_for_agent_startup() {
  local expected_version="$1"
  local previous_started="${2:-}"
  local attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if python3 - "$STATUS_FILE" "$expected_version" "$previous_started" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]); expected=sys.argv[2]; previous=sys.argv[3]
if not path.is_file():
    raise SystemExit(1)
try:
    obj=json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
started=str(obj.get("started_at_utc") or "")
version=str(obj.get("agent_version") or "")
if version == expected and started and started != previous:
    raise SystemExit(0)
raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 1
  done
  return 1
}

download_agent() {
  mkdir -p "$BIN_DIR"
  local tmp manifest signature expected_sha expected_version actual_sha actual_version
  tmp="$(mktemp "$BIN_DIR/.hara-commander-agent.XXXXXX")"
  manifest="$(mktemp "$BIN_DIR/.hara-commander-manifest.XXXXXX")"
  signature="$(mktemp "$BIN_DIR/.hara-commander-signature.XXXXXX")"
  if ! curl -fsS --max-time 30 "$BASE_URL/agent/linux.py" -o "$tmp"; then
    rm -f "$tmp" "$manifest" "$signature"; return 1
  fi
  if ! curl -fsS --max-time 30 "$BASE_URL/release/agent-manifest.json" -o "$manifest"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_MANIFEST_DOWNLOAD_FAILED' >&2; return 1
  fi
  if ! curl -fsS --max-time 30 "$BASE_URL/release/agent-manifest.sig.json" -o "$signature"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_SIGNATURE_DOWNLOAD_FAILED' >&2; return 1
  fi
  if ! verify_release_manifest_signature "$manifest" "$signature"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_SIGNATURE_INVALID' >&2; return 1
  fi
  readarray -t META < <(python3 - "$manifest" <<'PYMANIFEST'
import json,sys
obj=json.load(open(sys.argv[1],encoding="utf-8"))
if obj.get("schema")!="hara.commander-agent-release.v1": raise SystemExit("AGENT_RELEASE_MANIFEST_INVALID")
version=obj.get("agent_version")
entry=next((item for item in obj.get("files",[]) if item.get("path")=="agent/linux.py"),None)
if not isinstance(version,str) or not entry or not isinstance(entry.get("sha256"),str): raise SystemExit("AGENT_RELEASE_MANIFEST_INVALID")
print(version); print(entry["sha256"].lower())
PYMANIFEST
  ) || { rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_MANIFEST_INVALID' >&2; return 1; }
  expected_version="${META[0]}"
  expected_sha="${META[1]}"
  actual_sha="$(python3 - "$tmp" <<'PYHASH'
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())
PYHASH
)"
  [ "$actual_sha" = "$expected_sha" ] || { rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_SHA256_MISMATCH' >&2; return 1; }
  chmod 700 "$tmp"
  actual_version="$(python3 "$tmp" --version 2>/dev/null || true)"
  [ "$actual_version" = "$expected_version" ] || { rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_VERSION_MANIFEST_MISMATCH' >&2; return 1; }
  if ! python3 "$tmp" --self-test >/dev/null; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_UPDATE_VALIDATION_FAILED' >&2; return 1
  fi
  rm -f "$manifest" "$signature"
  mv -f "$tmp" "$AGENT"
  chmod 700 "$AGENT"
  printf 'HARA_COMMANDER_AGENT_INTEGRITY=PASS\n'
}

install_tunnel_client() {
  local arch asset expected tmp
  case "$(uname -m)" in
    x86_64|amd64)
      arch="amd64"
      expected="$TUNNEL_CLIENT_SHA256_AMD64"
      ;;
    aarch64|arm64)
      arch="arm64"
      expected="$TUNNEL_CLIENT_SHA256_ARM64"
      ;;
    *)
      echo "OPENAI_TUNNEL_CLIENT_ARCH_UNSUPPORTED" >&2
      return 31
      ;;
  esac
  asset="tunnel-client-v${TUNNEL_CLIENT_VERSION}-linux-${arch}.zip"
  tmp="$(mktemp "$BIN_DIR/.tunnel-client.XXXXXX.zip")"
  python3 - "$TUNNEL_CLIENT_BASE_URL/$asset" "$tmp" "$expected" "$TUNNEL_CLIENT" <<'PYTC'
import hashlib,io,os,pathlib,sys,urllib.error,urllib.request,zipfile
url,dest,expected,target=sys.argv[1:5]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
req=urllib.request.Request(url,headers={"accept":"application/zip","user-agent":"HARA-Commander-Installer-Tunnel/1"})
try:
    with urllib.request.build_opener(NoRedirect).open(req,timeout=45) as response:
        if response.status != 200:
            raise SystemExit("OPENAI_TUNNEL_CLIENT_DOWNLOAD_HTTP")
        raw=response.read(80*1024*1024+1)
except Exception as exc:
    raise SystemExit("OPENAI_TUNNEL_CLIENT_DOWNLOAD_FAILED") from exc
if len(raw)>80*1024*1024:
    raise SystemExit("OPENAI_TUNNEL_CLIENT_DOWNLOAD_TOO_LARGE")
if hashlib.sha256(raw).hexdigest()!=expected:
    raise SystemExit("OPENAI_TUNNEL_CLIENT_SHA256_MISMATCH")
pathlib.Path(dest).write_bytes(raw)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=z.namelist()
    if names.count("tunnel-client") != 1:
        raise SystemExit("OPENAI_TUNNEL_CLIENT_ARCHIVE_INVALID")
    info=z.getinfo("tunnel-client")
    if info.file_size<1024*1024 or info.file_size>80*1024*1024:
        raise SystemExit("OPENAI_TUNNEL_CLIENT_BINARY_SIZE_INVALID")
    binary=z.read(info)
t=pathlib.Path(target)
t.parent.mkdir(parents=True,exist_ok=True)
tmp_target=t.with_suffix(".tmp")
tmp_target.write_bytes(binary)
os.chmod(tmp_target,0o700)
tmp_target.replace(t)
os.chmod(t,0o700)
PYTC
  rm -f "$tmp"
  if ! "$TUNNEL_CLIENT" --version 2>/dev/null | grep -F "$TUNNEL_CLIENT_VERSION" >/dev/null; then
    echo "OPENAI_TUNNEL_CLIENT_VERSION_INVALID" >&2
    return 32
  fi
  printf 'HARA_COMMANDER_OPENAI_TUNNEL_CLIENT_VERSION=%s\n' "$TUNNEL_CLIENT_VERSION"
  printf 'HARA_COMMANDER_OPENAI_TUNNEL_CLIENT_INTEGRITY=PASS\n'
}

manage_hara_wrapper() {
  local wrapper_action="$1" external_hara=FALSE
  command -v hara >/dev/null 2>&1 && external_hara=TRUE || true
  python3 - "$wrapper_action" "$USER_BIN/hara" "$BIN_DIR/installer-preimages" "$external_hara" <<'PYHARAWRAPPER'
import ctypes,errno,hashlib,json,os,secrets,stat,sys
from pathlib import Path

LEGACY_SHA256="f2e30d042dd00e894c5916afb81ed193ff46f0949bd048a98c3c51722e42acaf"
LEGACY_BODY=b'''#!/bin/sh
set -eu
if [ "${1:-}" != "commander" ]; then
  echo "Usage: hara commander [start|status|stop|mcp|doctor|support|approval-mode]" >&2
  exit 64
fi
shift
exec "$HOME/.local/bin/hara-commander" "${1:-status}"
'''
MANAGED53_BODY=LEGACY_BODY.replace(b"#!/bin/sh\n",b"#!/bin/sh\n# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\n",1)
MANAGED53_SHA256="c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953"
assert hashlib.sha256(MANAGED53_BODY).hexdigest()==MANAGED53_SHA256
MANAGED_BODY=MANAGED53_BODY.replace(b'exec "$HOME/.local/bin/hara-commander" "${1:-status}"\n',b'if [ "$#" -eq 0 ]; then\n  set -- status\nfi\nexec "$HOME/.local/bin/hara-commander" "$@"\n',1)
MANAGED_SHA256=hashlib.sha256(MANAGED_BODY).hexdigest()
assert hashlib.sha256(LEGACY_BODY).hexdigest()==LEGACY_SHA256
_RACE_ERRORS={errno.ENOENT,errno.ELOOP,errno.ENOTDIR,errno.ESTALE,errno.ENXIO}
_libc=ctypes.CDLL(None,use_errno=True)
_native_rename=getattr(_libc,"renameat2",None)
if _native_rename is not None:
    _native_rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    _native_rename.restype=ctypes.c_int

def report(state):
    print("HARA_COMMANDER_CLI_WRAPPER_STATE="+state)
    return state

def identity(st):
    # rename changes ctime; inode, owner, mode, content and mtime remain bound.
    return (st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_size,st.st_mtime_ns,st.st_nlink)

def open_owned_directory(path,create_leaf=False,private=False):
    path=Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("CLI_WRAPPER_DIRECTORY_PATH_INVALID")
    fd=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for n,part in enumerate(path.parts[1:]):
            last=n==len(path.parts[1:])-1
            if last and create_leaf:
                try:
                    os.mkdir(part,0o700,dir_fd=fd)
                    sync_fd=os.open(".",os.O_RDONLY|os.O_DIRECTORY,dir_fd=fd)
                    try:os.fsync(sync_fd)
                    finally:os.close(sync_fd)
                except FileExistsError:pass
            child=os.open(part,(os.O_RDONLY if last else os.O_PATH)|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        st=os.fstat(fd)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o022 or (private and stat.S_IMODE(st.st_mode)!=0o700):
            raise RuntimeError("CLI_WRAPPER_DIRECTORY_OWNER_OR_MODE_INVALID")
        return fd
    except BaseException:
        os.close(fd);raise

def read_owned_regular_at(dfd,name):
    try:before=os.stat(name,dir_fd=dfd,follow_symlinks=False)
    except FileNotFoundError:return None,None,"MISSING"
    if stat.S_ISLNK(before.st_mode):return None,before,"SYMLINK"
    if not stat.S_ISREG(before.st_mode):return None,before,"NONREGULAR"
    if before.st_uid!=os.getuid():return None,before,"UNOWNED"
    if before.st_nlink!=1:return None,before,"HARDLINK"
    try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
    except OSError as error:
        if error.errno in _RACE_ERRORS:return None,before,"RACED"
        raise
    try:
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid() or identity(opened)!=identity(before):
            return None,before,"RACED"
        if opened.st_size>16384:return None,before,"UNRELATED"
        with os.fdopen(fd,"rb",closefd=False) as handle:raw=handle.read(16385)
        after=os.fstat(fd)
    finally:os.close(fd)
    if len(raw)>16384 or identity(after)!=identity(before):return None,before,"RACED"
    return raw,before,"OWNED_REGULAR"

def rename_noreplace(sfd,source,tfd,target):
    if _native_rename is None:raise RuntimeError("CLI_WRAPPER_ATOMIC_COMMIT_UNSUPPORTED")
    if _native_rename(sfd,os.fsencode(source),tfd,os.fsencode(target),1)!=0:
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))

def write_new_file_at(dfd,name,body,mode):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=dfd)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),mode)
        handle.write(body);handle.flush();os.fsync(handle.fileno())

def restore_if_empty(wfd,captured,name):
    try:rename_noreplace(wfd,captured,wfd,name)
    except OSError as error:
        if error.errno==errno.EEXIST:
            # Keep the actual displaced inode; never overwrite the new target.
            os.fsync(wfd)
            print("HARA_COMMANDER_CLI_WRAPPER_RETAINED="+json.dumps({"retained_name":captured,"requested_name":name},sort_keys=True))
            return False
        raise
    os.fsync(wfd);return True

def new_wrapper_at(wfd,name):
    # The staged inode has no pathname to swap or unlink.
    fd=os.open(".",os.O_WRONLY|os.O_TMPFILE,0o700,dir_fd=wfd)
    try:
        with os.fdopen(fd,"wb",closefd=False) as handle:
            os.fchmod(fd,0o700)
            handle.write(MANAGED_BODY);handle.flush();os.fsync(fd)
        linkat=getattr(_libc,"linkat",None)
        if linkat is None:raise RuntimeError("CLI_WRAPPER_ATOMIC_COMMIT_UNSUPPORTED")
        linkat.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
        linkat.restype=ctypes.c_int
        # /proc refers to this open descriptor; AT_SYMLINK_FOLLOW binds that inode.
        if linkat(-100,os.fsencode("/proc/self/fd/"+str(fd)),wfd,os.fsencode(name),0x400)!=0:
            code=ctypes.get_errno()
            if code==errno.EEXIST:return False
            raise OSError(code,os.strerror(code))
        os.fsync(wfd);return True
    finally:os.close(fd)

def preimage_target(pfd,legacy,managed53=False):
    migrating=legacy or managed53
    known_sha=LEGACY_SHA256 if legacy else MANAGED53_SHA256
    known_body=LEGACY_BODY if legacy else MANAGED53_BODY
    base="hara-wrapper-"+known_sha+".preimage" if migrating else "hara-wrapper-uninstall-"+secrets.token_hex(12)+".preimage"
    raw,st,kind=read_owned_regular_at(pfd,base)
    if kind=="MISSING":return base
    if migrating and kind=="OWNED_REGULAR" and raw==known_body and stat.S_IMODE(st.st_mode)==0o600:
        return "hara-wrapper-"+known_sha+"-"+secrets.token_hex(12)+".preimage"
    raise RuntimeError("CLI_WRAPPER_PREIMAGE_COLLISION")

def manage(mode,path,preimages,external_hara=False):
    if mode not in {"install","uninstall"}:raise ValueError("CLI_WRAPPER_MODE_INVALID")
    path=Path(path);preimages=Path(preimages)
    try:wfd=open_owned_directory(path.parent)
    except (OSError,RuntimeError):return report("PRESERVED_PARENT_UNSAFE")
    pfd=None
    try:
        raw,before,kind=read_owned_regular_at(wfd,path.name)
        if kind not in {"MISSING","OWNED_REGULAR"}:return report("PRESERVED_"+kind)
        if kind=="MISSING":
            if mode=="uninstall":return report("NOT_PRESENT")
            if external_hara:return report("PRESERVED_EXTERNAL_COMMAND")
            return report("FRESH_CREATED" if new_wrapper_at(wfd,path.name) else "PRESERVED_RACED")
        sha=hashlib.sha256(raw).hexdigest()
        legacy=sha==LEGACY_SHA256 and raw==LEGACY_BODY
        managed53=sha==MANAGED53_SHA256 and raw==MANAGED53_BODY
        managed=sha==MANAGED_SHA256 and raw==MANAGED_BODY
        if not legacy and not managed53 and not managed:return report("PRESERVED_UNRELATED")
        if mode=="install" and managed:return report("ALREADY_MANAGED")
        # Both reviewed directories are bound before any namespace mutation.
        bfd=open_owned_directory(preimages.parent,create_leaf=True,private=True)
        os.close(bfd)
        pfd=open_owned_directory(preimages,create_leaf=True,private=True)
        if os.fstat(wfd).st_dev!=os.fstat(pfd).st_dev:
            raise RuntimeError("CLI_WRAPPER_CROSS_FILESYSTEM_UNSUPPORTED")
        target=preimage_target(pfd,legacy,managed53)
        captured=".hara-cli-wrapper-displaced-"+secrets.token_hex(12)
        try:rename_noreplace(wfd,path.name,wfd,captured)
        except OSError as error:
            if error.errno in _RACE_ERRORS:return report("PRESERVED_RACED")
            raise
        try:moved,moved_st,moved_kind=read_owned_regular_at(wfd,captured)
        except BaseException:
            restore_if_empty(wfd,captured,path.name)
            raise
        if moved_kind!="OWNED_REGULAR" or identity(moved_st)!=identity(before) or moved!=raw:
            restored=restore_if_empty(wfd,captured,path.name)
            return report("PRESERVED_RACED" if restored else "PRESERVED_RACED_DISPLACED")
        try:
            # Retain the exact displaced inode, not just an earlier byte copy.
            rename_noreplace(wfd,captured,pfd,target)
        except OSError:
            restore_if_empty(wfd,captured,path.name)
            raise
        owned_fd=None
        try:
            owned_fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=pfd)
            if identity(os.fstat(owned_fd))!=identity(moved_st):
                raise RuntimeError("CLI_WRAPPER_PREIMAGE_IDENTITY_CHANGED")
            os.fchmod(owned_fd,0o600);os.fsync(owned_fd)
            os.fsync(pfd);os.fsync(wfd)
            metadata=target.rsplit(".",1)[0]+".json"
            record=json.dumps({"schema":"hara.commander-owned-cli-preimage.v2","preimage_sha256":sha,"target_sha256":MANAGED_SHA256 if mode=="install" else None,"owner_uid":os.getuid(),"original_mode":oct(stat.S_IMODE(before.st_mode)),"displaced_inode":moved_st.st_ino,"preimage_name":target},sort_keys=True).encode()+b"\n"
            write_new_file_at(pfd,metadata,record,0o600);os.fsync(pfd)
            if mode=="uninstall":
                try:os.stat(path.name,dir_fd=wfd,follow_symlinks=False)
                except FileNotFoundError:return report("LEGACY_REMOVED" if legacy else "MANAGED_REMOVED")
                return report("PRESERVED_RACED_TARGET")
            if not new_wrapper_at(wfd,path.name):return report("PRESERVED_RACED_TARGET")
            return report("LEGACY_MIGRATED" if legacy else "MANAGED53_MIGRATED")
        except BaseException:
            # Preserve availability on downstream errors without clobbering a new name.
            if owned_fd is not None and os.fstat(owned_fd).st_ino==moved_st.st_ino:
                os.fchmod(owned_fd,stat.S_IMODE(before.st_mode));os.fsync(owned_fd)
            try:rename_noreplace(pfd,target,wfd,path.name)
            except OSError as error:
                if error.errno!=errno.EEXIST:raise
                print("HARA_COMMANDER_CLI_WRAPPER_RETAINED="+json.dumps({"retained_name":target,"relative_directory":"installer-preimages","requested_name":path.name},sort_keys=True))
            os.fsync(pfd);os.fsync(wfd)
            raise
        finally:
            if owned_fd is not None:os.close(owned_fd)
    finally:
        if pfd is not None:os.close(pfd)
        os.close(wfd)

if __name__=="__main__":
    manage(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]=="TRUE")
PYHARAWRAPPER
}

install_cli() {
  mkdir -p "$USER_BIN"
  ln -sfn "$AGENT" "$CLI"
  manage_hara_wrapper install
  printf 'HARA_COMMANDER_CLI=%s\n' "$CLI"
}

status_agent() {
  local device_id="" enrolled=FALSE active=FALSE enabled=FALSE version="unknown" approval_mode=""
  device_id="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
  approval_mode="$(read_config_value HARA_COMMANDER_APPROVAL_MODE 2>/dev/null || true)"
  [ -n "$device_id" ] && enrolled=TRUE
  systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && active=TRUE || true
  systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null && enabled=TRUE || true
  [ ! -f "$AGENT" ] || version="$(python3 "$AGENT" --version 2>/dev/null || echo unknown)"
  printf 'HARA_COMMANDER_DEVICE_ENROLLED=%s\n' "$enrolled"
  printf 'HARA_COMMANDER_AGENT_ACTIVE=%s\n' "$active"
  printf 'HARA_COMMANDER_AGENT_ENABLED=%s\n' "$enabled"
  printf 'HARA_COMMANDER_AGENT_VERSION=%s\n' "$version"
  [ -z "$approval_mode" ] || printf 'HARA_COMMANDER_APPROVAL_MODE=%s\n' "$approval_mode"
  [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
  if [ -f "$AGENT" ]; then python3 "$AGENT" --session-status 2>/dev/null || true; fi
  printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
}

remote_device_action() {
  local action="$1"
  python3 - "$CONFIG_FILE" "$action" <<'PYREMOTE'
import json,sys,urllib.request,urllib.error
from pathlib import Path
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)
opener=urllib.request.build_opener(NoRedirectHandler)
path=Path(sys.argv[1]); action=sys.argv[2]
values={}
for raw in path.read_text(encoding="utf-8").splitlines():
    if "=" in raw:
        key,value=raw.split("=",1); values[key]=value
base=values.get("HARA_COMMANDER_URL","").rstrip("/")
token=values.get("HARA_DEVICE_TOKEN","")
device_id=values.get("HARA_DEVICE_ID","")
arch=values.get("HARA_DEVICE_ARCH","")
if not base or not token or not device_id:
    raise SystemExit(2)
if action=="heartbeat":
    endpoint="/api/device/heartbeat"
    payload={"device_id":device_id,"architecture":arch,"agent_version":"0.3.54","approval_mode":values.get("HARA_COMMANDER_APPROVAL_MODE","ASK_EVERY_ACTION")}
elif action=="revoke":
    endpoint="/api/device/revoke-self"
    payload={}
else:
    raise SystemExit(2)
req=urllib.request.Request(
    base+endpoint, data=json.dumps(payload,separators=(",",":")).encode(), method="POST",
    headers={"content-type":"application/json","accept":"application/json","user-agent":"HARA-Commander-Installer/0.3.43","authorization":"Bearer "+token},
)
try:
    with opener.open(req,timeout=15) as response:
        obj=json.loads(response.read().decode() or "{}")
except Exception:
    raise SystemExit(3)
if action=="heartbeat":
    if not obj.get("ok") or obj.get("device_id")!=device_id:
        raise SystemExit(4)
else:
    if not obj.get("ok") or obj.get("state")!="REVOKED" or obj.get("device_id")!=device_id:
        raise SystemExit(4)
PYREMOTE
}

rollback_enrolled_device() {
  [ -n "${DEVICE_ID:-}" ] && [ -n "${DEVICE_TOKEN:-}" ] || return 1
  printf '%s\n' "$DEVICE_TOKEN" | python3 -c '
import json,sys,urllib.request,urllib.error
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)
opener=urllib.request.build_opener(NoRedirectHandler)
base=sys.argv[1].rstrip("/")
device_id=sys.argv[2]
token=sys.stdin.readline().rstrip("\n")
if not device_id or not token: raise SystemExit(2)
req=urllib.request.Request(
    base+"/api/device/revoke-self", data=b"{}", method="POST",
    headers={"content-type":"application/json","accept":"application/json","authorization":"Bearer "+token,"user-agent":"HARA-Commander-Installer-Rollback/0.3.43"},
)
with opener.open(req,timeout=15) as response:
    obj=json.loads(response.read().decode() or "{}")
if not obj.get("ok") or obj.get("state")!="REVOKED" or obj.get("device_id")!=device_id:
    raise SystemExit(3)
' "$BASE_URL" "$DEVICE_ID"
}

cleanup_failed_install() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "${INSTALL_ENROLLED:-FALSE}" = TRUE ]; then
    local revoke_state=PENDING
    rollback_enrolled_device >/dev/null 2>&1 && revoke_state=PASS || true
    systemctl --user disable --now "$SERVICE" >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -rf "$BIN_DIR" "$CONFIG_DIR"
    printf 'HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=%s\n' "$revoke_state" >&2
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n' >&2
  fi
  unset DEVICE_TOKEN || true
  exit "$rc"
}

verify_existing_enrollment_rejected() {
  python3 - "$CONFIG_FILE" <<'PYREENROLLCHECK'
import json,sys,urllib.request,urllib.error
from pathlib import Path
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)
opener=urllib.request.build_opener(NoRedirectHandler)
path=Path(sys.argv[1]); values={}
for raw in path.read_text(encoding="utf-8").splitlines():
    if "=" in raw:
        key,value=raw.split("=",1); values[key]=value
base=values.get("HARA_COMMANDER_URL","").rstrip("/")
token=values.get("HARA_DEVICE_TOKEN","")
device_id=values.get("HARA_DEVICE_ID","")
arch=values.get("HARA_DEVICE_ARCH","")
if not base or not token or not device_id:
    print("REENROLL_LOCAL_ENROLLMENT_INVALID",file=sys.stderr); raise SystemExit(12)
payload=json.dumps({"device_id":device_id,"architecture":arch,"agent_version":"0.3.54"},separators=(",",":")).encode()
req=urllib.request.Request(
    base+"/api/device/heartbeat", data=payload, method="POST",
    headers={"content-type":"application/json","accept":"application/json",
             "user-agent":"HARA-Commander-Reenroll-Check/0.3.43","authorization":"Bearer "+token},
)
try:
    with opener.open(req,timeout=15) as response:
        obj=json.loads(response.read().decode() or "{}")
        if response.status==200 and obj.get("ok") is True:
            print("REENROLL_REFUSED_CURRENT_DEVICE_STILL_ACTIVE",file=sys.stderr); raise SystemExit(13)
        print("REENROLL_AUTH_CHECK_AMBIGUOUS",file=sys.stderr); raise SystemExit(14)
except urllib.error.HTTPError as exc:
    if exc.code != 401:
        print("REENROLL_AUTH_CHECK_AMBIGUOUS",file=sys.stderr); raise SystemExit(14)
    try: obj=json.loads(exc.read().decode() or "{}")
    except Exception:
        print("REENROLL_AUTH_CHECK_AMBIGUOUS",file=sys.stderr); raise SystemExit(14)
    if obj.get("code") != "DEVICE_AUTH_INVALID":
        print("REENROLL_AUTH_CHECK_AMBIGUOUS",file=sys.stderr); raise SystemExit(14)
    print("HARA_COMMANDER_REENROLL_OLD_CREDENTIAL_REJECTED=PASS")
except Exception:
    print("REENROLL_AUTH_CHECK_AMBIGUOUS",file=sys.stderr); raise SystemExit(14)
PYREENROLLCHECK
}

cleanup_failed_reenroll() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "${INSTALL_ENROLLED:-FALSE}" = TRUE ]; then
    local revoke_state=PENDING
    rollback_enrolled_device >/dev/null 2>&1 && revoke_state=PASS || true
    if [ "${REENROLL_CONFIG_REPLACED:-FALSE}" = TRUE ] && [ -n "${REENROLL_BACKUP:-}" ] && [ -f "$REENROLL_BACKUP" ]; then
      mv -f "$REENROLL_BACKUP" "$CONFIG_FILE"
      chmod 600 "$CONFIG_FILE"
      if [ "${REENROLL_SERVICE_WAS_ACTIVE:-FALSE}" = TRUE ]; then
        systemctl --user restart "$SERVICE" >/dev/null 2>&1 || true
      else
        systemctl --user stop "$SERVICE" >/dev/null 2>&1 || true
      fi
    fi
    printf 'HARA_COMMANDER_FAILED_REENROLL_ROLLBACK=%s\n' "$revoke_state" >&2
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n' >&2
  fi
  [ -z "${REENROLL_BACKUP:-}" ] || rm -f "$REENROLL_BACKUP"
  unset DEVICE_TOKEN || true
  exit "$rc"
}

preflight_agent() {
  local manifest signature health persistence_ready=FALSE arch
  manifest="$(mktemp)"
  signature="$(mktemp)"
  health="$(mktemp)"
  trap 'rm -f "$manifest" "$signature" "$health"' RETURN
  curl -fsS --max-time 15 "$BASE_URL/api/health" -o "$health" || { echo 'COMMANDER_HEALTH_UNREACHABLE' >&2; return 10; }
  curl -fsS --max-time 15 "$BASE_URL/release/agent-manifest.json" -o "$manifest" || { echo 'AGENT_RELEASE_MANIFEST_UNREACHABLE' >&2; return 11; }
  curl -fsS --max-time 15 "$BASE_URL/release/agent-manifest.sig.json" -o "$signature" || { echo 'AGENT_RELEASE_SIGNATURE_UNREACHABLE' >&2; return 11; }
  verify_release_manifest_signature "$manifest" "$signature" || { echo 'AGENT_RELEASE_SIGNATURE_INVALID' >&2; return 11; }
  systemctl --user show-environment >/dev/null 2>&1 && persistence_ready=TRUE || true
  arch="$(uname -m)"
  python3 - "$health" "$manifest" "$BASE_URL" "$arch" "$persistence_ready" <<'PYPREFLIGHT'
import json,sys
health=json.load(open(sys.argv[1],encoding="utf-8"))
manifest=json.load(open(sys.argv[2],encoding="utf-8"))
if health.get("ok") is not True or health.get("service")!="hara-commander": raise SystemExit("COMMANDER_HEALTH_INVALID")
if manifest.get("schema")!="hara.commander-agent-release.v1": raise SystemExit("AGENT_RELEASE_MANIFEST_INVALID")
version=manifest.get("agent_version")
if not isinstance(version,str) or not version: raise SystemExit("AGENT_RELEASE_VERSION_INVALID")
ready=sys.argv[5]=="TRUE"
report={
  "schema":"hara.commander-device-preflight.v1",
  "platform":"LINUX",
  "architecture":sys.argv[4],
  "commander_url":sys.argv[3],
  "commander_health":True,
  "release_manifest":True,
  "release_signature":True,
  "stable_agent_version":version,
  "persistence":"systemd-user",
  "persistence_ready":ready,
  "mutation_performed":False,
}
print(json.dumps(report,separators=(",",":"),sort_keys=True))
if not ready: raise SystemExit(12)
PYPREFLIGHT
}

support_agent() {
  if [ -f "$AGENT" ]; then
    if python3 "$AGENT" support; then
      return 0
    fi
  fi
  local active=FALSE enabled=FALSE
  systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && active=TRUE || true
  systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null && enabled=TRUE || true
  python3 - "$CONFIG_FILE" "$AGENT" "$UNIT" "$STATUS_FILE" "$active" "$enabled" <<'PYSUPPORT'
import hashlib,json,os,platform,stat,sys
from pathlib import Path
config_path=Path(sys.argv[1]); agent_path=Path(sys.argv[2]); unit_path=Path(sys.argv[3]); status_path=Path(sys.argv[4])
active=sys.argv[5]=="TRUE"; enabled=sys.argv[6]=="TRUE"
values={}
if config_path.is_file():
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key,value=raw.split("=",1)
            if key != "HARA_DEVICE_TOKEN": values[key]=value
version="unknown"
agent_sha=None
if agent_path.is_file():
    try:
        import subprocess
        version=subprocess.run([sys.executable,str(agent_path),"--version"],capture_output=True,text=True,timeout=5).stdout.strip() or "unknown"
    except Exception: pass
    agent_sha=hashlib.sha256(agent_path.read_bytes()).hexdigest()
mode=None
if config_path.exists(): mode=oct(stat.S_IMODE(config_path.stat().st_mode))[2:]
runtime={}
if status_path.is_file():
    try: runtime=json.loads(status_path.read_text(encoding="utf-8"))
    except Exception: runtime={}
report={
  "schema":"hara.commander-support-report.v1",
  "platform":"LINUX",
  "device_id":values.get("HARA_DEVICE_ID"),
  "architecture":values.get("HARA_DEVICE_ARCH") or platform.machine(),
  "commander_url":values.get("HARA_COMMANDER_URL"),
  "transport_mode":values.get("HARA_COMMANDER_TRANSPORT_MODE") or "OUTBOUND_RELAY",
  "agent_version":version,
  "agent_sha256":agent_sha,
  "config_present":config_path.is_file(),
  "config_mode":mode,
  "service_unit_present":unit_path.is_file(),
  "service_active":active,
  "service_enabled":enabled,
  "device_token_present":bool(config_path.is_file() and any(line.startswith("HARA_DEVICE_TOKEN=") for line in config_path.read_text(encoding="utf-8").splitlines())),
  "device_token_exposed":False,
  "last_successful_heartbeat_at_utc":runtime.get("last_successful_heartbeat_at_utc"),
  "last_runtime_error_code":runtime.get("last_runtime_error_code"),
  "last_runtime_error_at_utc":runtime.get("last_runtime_error_at_utc"),
}
print(json.dumps(report,separators=(",",":"),sort_keys=True))
PYSUPPORT
}

doctor_agent() {
  [ -f "$CONFIG_FILE" ] || { echo 'DEVICE_NOT_ENROLLED' >&2; return 5; }
  [ -f "$AGENT" ] || { echo 'AGENT_BINARY_MISSING' >&2; return 6; }
  [ -f "$UNIT" ] || { echo 'AGENT_SERVICE_NOT_INSTALLED' >&2; return 6; }
  # Manual-on-demand units are deliberately disabled at boot.
  systemctl --user is-active --quiet "$SERVICE" || { echo 'AGENT_SERVICE_NOT_ACTIVE' >&2; return 7; }
  python3 "$AGENT" --self-test >/dev/null || { echo 'AGENT_SELF_TEST_FAILED' >&2; return 8; }
  local transport
  transport="$(read_config_value HARA_COMMANDER_TRANSPORT_MODE 2>/dev/null || true)"
  if [ "$transport" = "LOCAL_TUNNEL" ]; then
    python3 "$AGENT" doctor || return $?
    printf 'COMMANDER_REMOTE_HEALTH=CONTROL_PLANE_OPTIONAL\n'
    status_agent
    return 0
  fi
  preflight_agent >/dev/null || { echo 'COMMANDER_REMOTE_HEALTH=FAIL' >&2; return 9; }
  printf 'HARA_COMMANDER_AGENT_DOCTOR=PASS\n'
  printf 'COMMANDER_REMOTE_HEALTH=PASS\n'
  printf 'COMMANDER_REMOTE_HEARTBEAT=SKIPPED_LOCAL_SESSION_REQUIRED\n'
  status_agent
}

case "$ACTION" in
  status)
    status_agent; exit 0 ;;
  preflight)
    preflight_agent; exit $? ;;
  doctor)
    doctor_agent; exit $? ;;
  support)
    support_agent; exit $? ;;
  update)
    [ -f "$CONFIG_FILE" ] || { echo 'DEVICE_NOT_ENROLLED' >&2; exit 5; }
    [ -f "$UNIT" ] || { echo 'AGENT_SERVICE_NOT_INSTALLED' >&2; exit 6; }
    configured_url="$(read_config_value HARA_COMMANDER_URL 2>/dev/null || true)"
    [ -z "$configured_url" ] || BASE_URL="${configured_url%/}"
    previous_started="$(read_runtime_status_value started_at_utc 2>/dev/null || true)"
    UPDATE_SERVICE_WAS_ACTIVE=FALSE
    systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && UPDATE_SERVICE_WAS_ACTIVE=TRUE || true
    existing_transport="$(read_config_value HARA_COMMANDER_TRANSPORT_MODE 2>/dev/null || true)"
    if [ "$existing_transport" = "LOCAL_TUNNEL" ]; then
      install_tunnel_client
    fi
    backup="$AGENT.rollback"
    rm -f "$backup"
    [ ! -f "$AGENT" ] || cp -p "$AGENT" "$backup"
    download_agent
    install_cli
    expected_version="$(python3 "$AGENT" --version)"
    systemctl --user daemon-reload
    if [ "$UPDATE_SERVICE_WAS_ACTIVE" = TRUE ]; then
      systemctl --user restart "$SERVICE"
      sleep 1
      if ! systemctl --user is-active --quiet "$SERVICE" || ! wait_for_agent_startup "$expected_version" "$previous_started"; then
        if [ -f "$backup" ]; then
          mv -f "$backup" "$AGENT"
          chmod 700 "$AGENT"
          systemctl --user restart "$SERVICE" || true
          sleep 1
          systemctl --user is-active --quiet "$SERVICE" && printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS\n' >&2
        fi
        echo 'HARA Commander Agent failed after update; previous agent restored when available.' >&2
        exit 7
      fi
      printf 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS\n'
    else
      # Updating a manually stopped agent must not establish a new connection.
      printf 'HARA_COMMANDER_AGENT_UPDATE_RUNTIME_ATTESTATION=SKIPPED_MANUAL_STOP\n'
    fi
    rm -f "$backup"
    printf 'HARA_COMMANDER_AGENT_UPDATE_SERVICE_WAS_ACTIVE=%s\n' "$UPDATE_SERVICE_WAS_ACTIVE"
    printf 'HARA_COMMANDER_AGENT_UPDATE=PASS\n'
    printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE\n'
    status_agent; exit 0 ;;
  uninstall)
    device_id="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
    revoke_state=PENDING
    if [ -f "$CONFIG_FILE" ] && remote_device_action revoke; then revoke_state=PASS; fi
    systemctl --user disable --now "$SERVICE" >/dev/null 2>&1 || true
    systemctl --user disable --now hara-commander-openai-tunnel.service >/dev/null 2>&1 || true
    rm -f "$UNIT" "$SYSTEMD_DIR/hara-commander-openai-tunnel.service"
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/tunnel-client/hara-commander.yaml"
    rmdir "${XDG_CONFIG_HOME:-$HOME/.config}/tunnel-client" >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -f "$CLI"
    manage_hara_wrapper uninstall
    rm -rf "$BIN_DIR" "$CONFIG_DIR"
    printf 'HARA_COMMANDER_AGENT_UNINSTALL=PASS\n'
    [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
    printf 'SERVER_DEVICE_REVOKE=%s\n' "$revoke_state"
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n'
    printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
    exit 0 ;;
  re-enroll|reenroll)
    [ -f "$CONFIG_FILE" ] || { echo 'DEVICE_NOT_ENROLLED: use install.' >&2; exit 5; }
    [ -f "$AGENT" ] || { echo 'AGENT_BINARY_MISSING' >&2; exit 6; }
    [ -f "$UNIT" ] || { echo 'AGENT_SERVICE_NOT_INSTALLED' >&2; exit 6; }
    configured_url="$(read_config_value HARA_COMMANDER_URL 2>/dev/null || true)"
    [ -z "$configured_url" ] || BASE_URL="${configured_url%/}"
    verify_existing_enrollment_rejected
    REENROLL=TRUE
    REENROLL_OLD_DEVICE_ID="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
    systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && REENROLL_SERVICE_WAS_ACTIVE=TRUE || true
    ;;
  install) ;;
  *) echo 'Usage: linux.sh [install|re-enroll|preflight|status|doctor|support|update|uninstall]' >&2; exit 64 ;;
esac

if [ "$REENROLL" != TRUE ] && [ -f "$CONFIG_FILE" ]; then
  cat >&2 <<'EOF_ALREADY'
DEVICE_ALREADY_ENROLLED
This computer already has a Commander enrollment.
If the device was revoked and you want to pair it again, run:
  bash linux.sh re-enroll
To inspect the current state, run:
  bash linux.sh status
EOF_ALREADY
  exit 8
fi

APPROVAL_MODE="$(resolve_approval_mode)"
printf 'HARA Commander — Linux device pairing\n'
printf 'Approval mode: %s\n' "$APPROVAL_MODE"
printf 'Pairing token: '
IFS= read -r -s PAIRING_TOKEN </dev/tty
printf '\n'
[ -n "$PAIRING_TOKEN" ] || { echo 'Pairing token cannot be empty.' >&2; exit 3; }

DEVICE_NAME="${HOSTNAME:-$(hostname 2>/dev/null || echo linux-device)}"
ARCH="$(uname -m)"

PAYLOAD="$(printf '%s\n' "$PAIRING_TOKEN" | python3 -c '
import json,sys
token=sys.stdin.readline().rstrip("\n")
print(json.dumps({
  "pairing_token": token,
  "device_name": sys.argv[1],
  "platform": "LINUX",
  "architecture": sys.argv[2],
  "agent_version": "0.3.54",
  "approval_mode": sys.argv[3],
}, separators=(",",":")))
' "$DEVICE_NAME" "$ARCH" "$APPROVAL_MODE")"

RESPONSE="$(printf '%s' "$PAYLOAD" | curl -fsS --max-time 30   -H 'content-type: application/json'   -H 'accept: application/json'   --data-binary @-   "$BASE_URL/api/device/enroll")"

readarray -t VALUES < <(printf '%s' "$RESPONSE" | python3 -c '
import json,sys
obj=json.load(sys.stdin)
for key in ("device_id","device_token"):
    value=obj.get(key)
    if not isinstance(value,str) or not value:
        raise SystemExit("DEVICE_ENROLLMENT_RESPONSE_INVALID")
    print(value)
')

DEVICE_ID="${VALUES[0]}"
DEVICE_TOKEN="${VALUES[1]}"
unset PAIRING_TOKEN RESPONSE PAYLOAD VALUES
INSTALL_ENROLLED=TRUE
if [ "$REENROLL" = TRUE ]; then
  REENROLL_BACKUP="$(mktemp "$CONFIG_DIR/.device.env.reenroll.XXXXXX")"
  cp -p "$CONFIG_FILE" "$REENROLL_BACKUP"
  chmod 600 "$REENROLL_BACKUP"
  trap cleanup_failed_reenroll EXIT
else
  trap cleanup_failed_install EXIT
fi

if [ -n "$TRANSPORT_MODE_RAW" ]; then
  case "$(printf '%s' "$TRANSPORT_MODE_RAW" | tr '[:lower:]' '[:upper:]' | tr '-' '_')" in
    LOCAL_TUNNEL|TUNNEL|LOCAL) TRANSPORT_MODE="LOCAL_TUNNEL" ;;
    OUTBOUND_RELAY|RELAY|LEGACY) TRANSPORT_MODE="OUTBOUND_RELAY" ;;
    *) echo 'DEVICE_TRANSPORT_MODE_INVALID' >&2; exit 64 ;;
  esac
elif [ "$REENROLL" = TRUE ]; then
  TRANSPORT_MODE="$(read_config_value HARA_COMMANDER_TRANSPORT_MODE 2>/dev/null || true)"
  [ -n "$TRANSPORT_MODE" ] || TRANSPORT_MODE="OUTBOUND_RELAY"
else
  # Public plugin onboarding uses the Cloudflare customer MCP gateway;
  # no OpenAI Platform API key/tunnel required for a normal customer.
  TRANSPORT_MODE="OUTBOUND_RELAY"
fi

TUNNEL_AUTOSTART="$(resolve_tunnel_autostart)"
if [ "$TRANSPORT_MODE" != "LOCAL_TUNNEL" ] && [ "$TUNNEL_AUTOSTART" != "OFF" ]; then
  echo "OPENAI_TUNNEL_AUTOSTART_REQUIRES_DIRECT_TRANSPORT" >&2
  exit 64
fi
umask 077
mkdir -p "$CONFIG_DIR" "$BIN_DIR" "$SYSTEMD_DIR"
if [ "$TRANSPORT_MODE" = "LOCAL_TUNNEL" ]; then
  install_tunnel_client
fi
cat >"$CONFIG_FILE" <<EOF
HARA_COMMANDER_URL=$BASE_URL
HARA_DEVICE_ID=$DEVICE_ID
HARA_DEVICE_TOKEN=$DEVICE_TOKEN
HARA_DEVICE_ARCH=$ARCH
HARA_COMMANDER_APPROVAL_MODE=$APPROVAL_MODE
HARA_COMMANDER_TRANSPORT_MODE=$TRANSPORT_MODE
HARA_COMMANDER_TUNNEL_AUTOSTART=$TUNNEL_AUTOSTART
EOF
chmod 600 "$CONFIG_FILE"

if [ "$REENROLL" = TRUE ]; then
  REENROLL_CONFIG_REPLACED=TRUE
  expected_version="$(python3 "$AGENT" --version 2>/dev/null || true)"
  [ -n "$expected_version" ] || { echo 'AGENT_VERSION_INVALID' >&2; exit 6; }
  previous_started="$(read_runtime_status_value started_at_utc 2>/dev/null || true)"
  # Re-enrollment verifies startup once but does not change an inactive
  # agent into a persistent background connection.
  if [ "$REENROLL_SERVICE_WAS_ACTIVE" = TRUE ]; then
    systemctl --user restart "$SERVICE"
  else
    systemctl --user start "$SERVICE"
  fi
  sleep 1
  if ! systemctl --user is-active --quiet "$SERVICE" || ! wait_for_agent_startup "$expected_version" "$previous_started"; then
    echo 'HARA Commander Agent failed re-enroll startup attestation.' >&2
    exit 4
  fi
  if [ "$REENROLL_SERVICE_WAS_ACTIVE" != TRUE ]; then
    systemctl --user stop "$SERVICE"
  fi
  install_cli
  printf 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS\n'
  INSTALL_ENROLLED=FALSE
  trap - EXIT
  rm -f "$REENROLL_BACKUP"
  REENROLL_BACKUP=""
  unset DEVICE_TOKEN
  printf 'HARA_COMMANDER_DEVICE_REENROLL=PASS\n'
  printf 'OLD_DEVICE_AUTHORITY_RESURRECTED=FALSE\n'
  [ -z "${REENROLL_OLD_DEVICE_ID:-}" ] || printf 'OLD_DEVICE_ID=%s\n' "$REENROLL_OLD_DEVICE_ID"
  printf 'DEVICE_ID=%s\n' "$DEVICE_ID"
  printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
  exit 0
fi

download_agent
install_cli
expected_version="$(python3 "$AGENT" --version)"

cat >"$UNIT" <<EOF
[Unit]
Description=HARA Commander Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$AGENT
# The service may restart after a failure only while explicitly started.
# It is NOT enabled at boot by the installer.
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=default.target
EOF
chmod 600 "$UNIT"

systemctl --user daemon-reload
# New customer: run immediately for installation attestation, but never
# enable automatic start on future logins or reboots.
systemctl --user disable "$SERVICE" >/dev/null 2>&1 || true
systemctl --user start "$SERVICE"
if systemctl --user is-enabled --quiet "$SERVICE"; then
  echo 'AGENT_MANUAL_START_POLICY_VIOLATED' >&2
  exit 8
fi

sleep 1
if ! systemctl --user is-active --quiet hara-commander-agent.service || ! wait_for_agent_startup "$expected_version" ""; then
  echo 'HARA Commander Agent failed startup attestation.' >&2
  exit 4
fi
printf 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS\n'

INSTALL_ENROLLED=FALSE
trap - EXIT
unset DEVICE_TOKEN
printf 'HARA_COMMANDER_DEVICE_ENROLLMENT=PASS\n'
printf 'HARA_COMMANDER_AGENT_SERVICE=ACTIVE_LOCAL_CONTROL_PLANE\n'
printf 'HARA_COMMANDER_AGENT_AUTOSTART=OFF\n'
printf 'HARA_COMMANDER_AGENT_START_MODE=MANUAL_AFTER_INSTALL\n'
printf 'DEVICE_ID=%s\n' "$DEVICE_ID"
printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
printf 'HARA_COMMANDER_APPROVAL_MODE=%s\n' "$APPROVAL_MODE"
printf 'HARA_COMMANDER_TRANSPORT_MODE=%s\n' "$TRANSPORT_MODE"
printf 'HARA_COMMANDER_TUNNEL_AUTOSTART=%s\n' "$TUNNEL_AUTOSTART"
if [ "$TRANSPORT_MODE" = "LOCAL_TUNNEL" ]; then
  printf 'HARA_COMMANDER_TUNNEL_AUTOSTART_PENDING_CONFIGURATION=TRUE\n'
  printf 'NEXT_COMMAND=hara-commander tunnel configure\n'
  printf 'DIRECT_CONNECT_COMMAND=hara-commander tunnel connect\n'
  printf 'DIRECT_OPENAI_PLATFORM_TUNNEL_REQUIRED=TRUE\n'
  printf 'TUNNEL_MANUAL_START_COMMAND=hara-commander tunnel start\n'
  printf 'TUNNEL_MANUAL_STOP_COMMAND=hara-commander tunnel stop\n'
else
  printf 'HARA_COMMANDER_CLOUD_PLUGIN_MODE=TRUE\n'
  printf 'OPENAI_PLATFORM_API_KEY_REQUIRED=FALSE\n'
  printf 'NEXT_STEP=Abra hara-commander start no terminal para conectar e autorizar a sessão; depois conecte o plugin via HARA Identity OAuth\n'
  printf 'CUSTOMER_MCP_ENDPOINT=https://commander.haralabs.com.br/api/mcp?profile=simple\n'
fi
printf 'OPERATOR_SESSION_COMMAND=hara-commander start\n'
printf 'MANUAL_CONNECTION_COMMAND=hara-commander start\n'
printf 'STATUS_COMMAND=hara-commander status\n'
printf 'STOP_COMMAND=hara-commander stop\n'
printf 'LOCAL_MCP_COMMAND=hara-commander mcp\n'
printf 'AUTHORIZATION_COMMAND=hara-commander authorize\n'
printf 'SESSION_AUTHORITY=LOCAL_OPERATOR_TERMINAL\n'
