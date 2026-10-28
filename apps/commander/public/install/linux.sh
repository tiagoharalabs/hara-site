#!/usr/bin/env bash
set -euo pipefail
# HARA Commander commercial release 0.3.60
# HARA_COMMANDER_PAIR_EXISTING=1

BASE_URL="${HARA_COMMANDER_URL:-https://commander.haralabs.com.br}"
RELEASE_SIGNING_KID="commander-release-v2"
RELEASE_SIGNING_N="p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43"
RELEASE_SIGNING_E="AQAB"
release_url() {
  python3 - "${HARA_COMMANDER_RELEASE_URL:-${BASE_URL%/}/releases/0.3.60}" <<'PYRELEASEURL'
import sys,urllib.parse
url=sys.argv[1].rstrip("/");p=urllib.parse.urlsplit(url)
if p.scheme!="https" or not p.hostname or p.username or p.password or p.query or p.fragment:
    raise SystemExit("RELEASE_ORIGIN_INVALID")
print(url)
PYRELEASEURL
}
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
ACTION="${1:-connect}"
ACTION="${ACTION#--}"
REENROLL=FALSE
REENROLL_BACKUP=""
REENROLL_CONFIG_REPLACED=FALSE
REENROLL_CONFIG_EXISTED=TRUE
PAIR_EXISTING=FALSE
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

validate_commander_origin() {
  python3 - "$BASE_URL" <<'PYORIGIN'
import sys,urllib.parse
p=urllib.parse.urlsplit(sys.argv[1])
if p.scheme!="https" or not p.hostname or p.username is not None or p.password is not None or p.path not in ("","/") or p.query or p.fragment:
    raise SystemExit("COMMANDER_ORIGIN_INVALID")
PYORIGIN
}
validate_commander_origin

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

assert_agent_version_floor() {
  python3 - "$1" "$AGENT" <<'PYVERSIONFLOOR'
from pathlib import Path
import re,sys
offered=sys.argv[1]
installed=Path(sys.argv[2])
def parse(value):
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)",value):
        raise SystemExit("AGENT_RELEASE_INVALID_SEMVER")
    return tuple(map(int,value.split(".")))
candidate=parse(offered)
if candidate < (0,3,54):
    raise SystemExit("AGENT_RELEASE_BELOW_LINUX_FLOOR")
if installed.is_symlink():
    raise SystemExit("AGENT_INSTALLED_SYMLINK_UNTRUSTED")
if installed.exists():
    if not installed.is_file():
        raise SystemExit("AGENT_INSTALLED_FILE_INVALID")
    matches=re.findall(r'(?m)^\s*AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$',installed.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise SystemExit("AGENT_INSTALLED_VERSION_UNKNOWN")
    if candidate < parse(matches[0]):
        raise SystemExit("AGENT_DOWNGRADE_REFUSED")
PYVERSIONFLOOR
}

read_release_metadata() {
  python3 - "$1" "${2:-0.3.60}" <<'PYMANIFEST'
import json,re,sys
def unique(pairs):
    obj={}
    for k,v in pairs:
        if k in obj: raise SystemExit("AGENT_RELEASE_DUPLICATE_KEY")
        obj[k]=v
    return obj
obj=json.load(open(sys.argv[1],encoding="utf-8"),object_pairs_hook=unique)
paths=["agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1"]
if set(obj)!={"schema","product","channel","agent_version","files"} or obj.get("schema")!="hara.commander-agent-release.v1" or obj.get("product")!="H.A.R.A. Commander" or obj.get("channel")!="stable":
    raise SystemExit("AGENT_RELEASE_MANIFEST_INVALID")
rows=obj["files"]
if not isinstance(rows,list) or len(rows)!=4 or [r.get("path") for r in rows if isinstance(r,dict)]!=paths:
    raise SystemExit("AGENT_RELEASE_FILESET_INVALID")
for row in rows:
    if set(row)!={"path","bytes","sha256"} or type(row["bytes"]) is not int or not 0<row["bytes"]<=2097152 or not isinstance(row["sha256"],str) or not re.fullmatch(r"[0-9a-f]{64}",row["sha256"]):
        raise SystemExit("AGENT_RELEASE_MANIFEST_INVALID")
version=obj["agent_version"]
if version!=sys.argv[2]: raise SystemExit("INSTALLER_AGENT_VERSION_MISMATCH")
print(version);print(rows[0]["sha256"]);print(rows[0]["bytes"])
PYMANIFEST
}

precheck_release_before_pairing() {
  local manifest signature metadata version rc=0
  manifest="$(mktemp)"; signature="$(mktemp)"
  if curl -fsS --max-time 30 "$(release_url)/release/agent-manifest.json" -o "$manifest" &&
     curl -fsS --max-time 30 "$(release_url)/release/agent-manifest.sig.json" -o "$signature" &&
     verify_release_manifest_signature "$manifest" "$signature"; then
    if metadata="$(read_release_metadata "$manifest")"; then
      version="${metadata%%$'\n'*}"
      assert_agent_version_floor "$version" || rc=1
    else rc=1; fi
  else rc=1; fi
  rm -f "$manifest" "$signature"
  [ "$rc" -eq 0 ] || { echo 'AGENT_RELEASE_PREPAIR_HOLD' >&2; return 1; }
}

download_agent() {
  mkdir -p "$BIN_DIR"
  local tmp manifest signature expected_sha expected_version actual_sha actual_version
  tmp="$(mktemp "$BIN_DIR/.hara-commander-agent.XXXXXX")"
  manifest="$(mktemp "$BIN_DIR/.hara-commander-manifest.XXXXXX")"
  signature="$(mktemp "$BIN_DIR/.hara-commander-signature.XXXXXX")"
  if ! curl -fsS --max-time 30 "$(release_url)/agent/linux.py" -o "$tmp"; then
    rm -f "$tmp" "$manifest" "$signature"; return 1
  fi
  if ! curl -fsS --max-time 30 "$(release_url)/release/agent-manifest.json" -o "$manifest"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_MANIFEST_DOWNLOAD_FAILED' >&2; return 1
  fi
  if ! curl -fsS --max-time 30 "$(release_url)/release/agent-manifest.sig.json" -o "$signature"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_SIGNATURE_DOWNLOAD_FAILED' >&2; return 1
  fi
  if ! verify_release_manifest_signature "$manifest" "$signature"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_SIGNATURE_INVALID' >&2; return 1
  fi
  local metadata expected_bytes actual_bytes
  if ! metadata="$(read_release_metadata "$manifest")"; then
    rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_RELEASE_MANIFEST_INVALID' >&2; return 1
  fi
  readarray -t META <<< "$metadata"
  expected_version="${META[0]}"
  expected_sha="${META[1]}"
  expected_bytes="${META[2]}"
  actual_bytes="$(wc -c < "$tmp" | tr -d '[:space:]')"
  [ "$actual_bytes" = "$expected_bytes" ] || { rm -f "$tmp" "$manifest" "$signature"; echo 'AGENT_SIZE_MISMATCH' >&2; return 1; }
  if ! assert_agent_version_floor "$expected_version"; then
    rm -f "$tmp" "$manifest" "$signature"
    echo 'AGENT_RELEASE_FLOOR_HOLD' >&2
    return 1
  fi
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

install_pair_cli() {
  python3 - "$BIN_DIR" "$USER_BIN" <<'PYINSTALLPAIR'
import json,os,stat,sys,tempfile
from pathlib import Path
root,userbin=map(Path,sys.argv[1:])
files=json.loads('{"commander_pair.py": "#!/usr/bin/env python3\\n\\"\\"\\"Explicit pairing for an existing installation; no download or Agent update.\\n\\nQA entry point, separate from the immutable signed Agent. The installed Agent\\nmust match a locally retained, cryptographically verified release manifest.\\n\\"\\"\\"\\nimport argparse\\nimport datetime as dt\\nimport getpass\\nimport hashlib\\nimport json\\nimport os\\nfrom pathlib import Path\\nimport platform\\nimport re\\nimport sqlite3\\nimport stat\\nimport subprocess\\nimport sys\\nimport tempfile\\nimport time\\n\\nimport commander_connect as c\\n\\n\\ndef digest(raw):\\n    return hashlib.sha256(raw).hexdigest()\\n\\n\\ndef read(path, private=False):\\n    for parent in path.parents:\\n        c.need(not parent.is_symlink(), \\"SYMLINK_PARENT\\")\\n    c.need(c.owned_regular(path, private=private), \\"REQUIRED_FILE_MISSING\\")\\n    c.need(path.stat().st_nlink == 1 and path.stat().st_size <= 2 * 1024 * 1024,\\n           \\"FILE_SIZE_OR_LINK_INVALID\\")\\n    return path.read_bytes()\\n\\n\\ndef atomic(path, data):\\n    fd, name = tempfile.mkstemp(prefix=\\".pair-\\", dir=path.parent)\\n    try:\\n        with os.fdopen(fd, \\"wb\\") as stream:\\n            stream.write(data)\\n            stream.flush()\\n            os.fsync(stream.fileno())\\n        os.replace(name, path)\\n        directory = os.open(path.parent, os.O_DIRECTORY)\\n        try:\\n            os.fsync(directory)\\n        finally:\\n            os.close(directory)\\n    finally:\\n        if os.path.exists(name):\\n            os.unlink(name)\\n\\n\\ndef enrollment_context(config):\\n    values = [config[\\"HARA_COMMANDER_URL\\"], config[\\"HARA_DEVICE_ID\\"],\\n              config.get(\\"HARA_TENANT_ID\\", \\"\\"), digest(config[\\"HARA_DEVICE_TOKEN\\"].encode())]\\n    return digest(json.dumps(values, separators=(\\",\\", \\":\\")).encode())\\n\\n\\nclass Pair:\\n    def __init__(self, http=None):\\n        self.http = http or c.Http()\\n        self.paths = c.Connect(self.http)\\n        self.proof = Path(__file__).resolve().parent / \\"pair-release\\"\\n        self.work = None\\n        self.version = None\\n\\n    def service(self, *args, check=True):\\n        result = subprocess.run([\\"systemctl\\", \\"--user\\", *args], capture_output=True,\\n                                text=True, timeout=25)\\n        c.need(not check or result.returncode == 0, \\"SERVICE_\\" + args[0].upper() + \\"_FAILED\\")\\n        return result.stdout.strip()\\n\\n    def verify_agent(self):\\n        if self.proof.is_dir():\\n            manifest = c.verify_manifest(read(self.proof / \\"agent-manifest.json\\"),\\n                                         read(self.proof / \\"agent-manifest.sig.json\\"))\\n        else:\\n            current = c.installed_version(self.paths.agent)\\n            # Pairing verifies the installed version\'s immutable release, not\\n            # the latest update catalog. A newer offer cannot force an update.\\n            config = c.read_config(self.paths.config_file)\\n            c.need(config is not None and current is not None, \\"EXISTING_INSTALLATION_REQUIRED\\")\\n            base = c.origin(config[\\"HARA_COMMANDER_URL\\"]) + \\"/releases/\\" + current + \\"/release/\\"\\n            manifest = c.verify_manifest(self.http.get(base + \\"agent-manifest.json\\", 16384),\\n                                         self.http.get(base + \\"agent-manifest.sig.json\\", 16384))\\n        payload = manifest[\\"files\\"][0]\\n        raw = read(self.paths.agent)\\n        c.need(len(raw) == payload[\\"bytes\\"] and digest(raw) == payload[\\"sha256\\"],\\n               \\"INSTALLED_AGENT_INTEGRITY_FAILED\\")\\n        current = c.installed_version(self.paths.agent)\\n        c.need(current == manifest[\\"agent_version\\"], \\"INSTALLED_AGENT_VERSION_MISMATCH\\")\\n        self.version = current\\n        return digest(raw)\\n\\n    def idle(self, config):\\n        database = self.paths.agent.parent / \\"enrollments\\" / enrollment_context(config) / \\"operations.sqlite3\\"\\n        if not database.exists():\\n            return\\n        for path in (database, *database.parents):\\n            c.need(not path.is_symlink(), \\"DATABASE_SYMLINK\\")\\n        with sqlite3.connect(database.as_uri() + \\"?mode=ro\\", uri=True) as db:\\n            tables = {row[0] for row in db.execute(\\"SELECT name FROM sqlite_master WHERE type=\'table\'\\")}\\n            if \\"relay_call_journal\\" not in tables:\\n                return\\n            rows = list(db.execute(\\"SELECT DISTINCT phase,delivery_state FROM relay_call_journal\\"))\\n        c.need(not any(phase in (\\"PREPARING\\", \\"RESERVED\\", \\"EXECUTING\\", \\"UNCERTAIN\\")\\n                       or delivery in (\\"PENDING\\", \\"RETRY\\", \\"SENDING\\") for phase, delivery in rows),\\n               \\"UNFINISHED_COMMANDS\\")\\n\\n    def post(self, config, path, payload, authenticated=True):\\n        status, raw = self.http.request(c.origin(config[\\"HARA_COMMANDER_URL\\"]) + path,\\n                                       payload=payload,\\n                                       token=config[\\"HARA_DEVICE_TOKEN\\"] if authenticated else None,\\n                                       limit=65536)\\n        c.need(status == (201 if path == \\"/api/device/enroll\\" else 200),\\n               \\"HTTP_\\" + str(status) + \\"_\\" + path.rsplit(\\"/\\", 1)[-1].upper())\\n        result = c.unique_json(raw)\\n        c.need(isinstance(result, dict), \\"SERVER_RESPONSE_INVALID\\")\\n        return result\\n\\n    def heartbeat(self, config):\\n        result = self.post(config, \\"/api/device/heartbeat\\", {\\n            \\"device_id\\": config[\\"HARA_DEVICE_ID\\"],\\n            \\"architecture\\": config.get(\\"HARA_DEVICE_ARCH\\", platform.machine()),\\n            \\"agent_version\\": self.version,\\n            \\"approval_mode\\": config.get(\\"HARA_COMMANDER_APPROVAL_MODE\\", \\"ASK_EVERY_ACTION\\")})\\n        c.need(result.get(\\"ok\\") is True and result.get(\\"device_id\\") == config[\\"HARA_DEVICE_ID\\"],\\n               \\"HEARTBEAT_IDENTITY_MISMATCH\\")\\n\\n    def preflight(self):\\n        self.verify_agent()\\n        self.old = read(self.paths.config_file, private=True)\\n        self.config = c.read_config(self.paths.config_file)\\n        c.need(self.config is not None, \\"EXISTING_INSTALLATION_REQUIRED\\")\\n        c.need(not self.config.get(\\"HARA_TENANT_ID\\"), \\"EXPLICIT_TENANT_REQUIRES_REVIEW\\")\\n        c.need(self.config.get(\\"HARA_COMMANDER_TRANSPORT_MODE\\", \\"OUTBOUND_RELAY\\") == \\"OUTBOUND_RELAY\\",\\n               \\"PAIRING_REQUIRES_RELAY_INSTALLATION\\")\\n        self.unit_before = read(self.paths.unit)\\n        for key, expected in ((\\"FragmentPath\\", str(self.paths.unit)), (\\"DropInPaths\\", \\"\\"), (\\"Type\\", \\"simple\\")):\\n            c.need(self.service(\\"show\\", c.SERVICE, \\"--property=\\" + key, \\"--value\\") == expected,\\n                   \\"SERVICE_DEFINITION_CHANGED\\")\\n        command = self.service(\\"show\\", c.SERVICE, \\"--property=ExecStart\\", \\"--value\\")\\n        c.need(\\"path=\\" + str(self.paths.agent) + \\" ;\\" in command, \\"SERVICE_EXECUTABLE_MISMATCH\\")\\n        self.was_active = self.service(\\"is-active\\", c.SERVICE, check=False) == \\"active\\"\\n        # A rejected previous credential may be replaced, but an ambiguous\\n        # network failure cannot be treated as an invalid enrollment.\\n        self.old_state = c.enrollment_state(self.http, self.config, self.version)\\n        self.idle(self.config)\\n        return {\\"state\\": \\"READY_FOR_NEW_CODE\\", \\"version\\": self.version,\\n                \\"origin\\": self.config[\\"HARA_COMMANDER_URL\\"], \\"existing_binding\\": self.old_state}\\n\\n    def runtime_start(self):\\n        try:\\n            return c.unique_json(read(self.paths.status)).get(\\"started_at_utc\\")\\n        except (OSError, c.Hold, ValueError):\\n            return None\\n\\n    def wait_runtime(self, previous, since):\\n        deadline = time.monotonic() + 55\\n        while time.monotonic() < deadline:\\n            try:\\n                row = c.unique_json(read(self.paths.status))\\n                stamp = dt.datetime.fromisoformat(row[\\"last_successful_heartbeat_at_utc\\"].replace(\\"Z\\", \\"+00:00\\"))\\n                if (row.get(\\"agent_version\\") == self.version and row.get(\\"started_at_utc\\") != previous\\n                        and stamp.timestamp() >= since\\n                        and self.service(\\"is-active\\", c.SERVICE, check=False) == \\"active\\"):\\n                    return\\n            except (OSError, ValueError, KeyError, c.Hold):\\n                pass\\n            time.sleep(1)\\n        raise c.Hold(\\"FRESH_RUNTIME_NOT_CONFIRMED\\")\\n\\n    def revoke(self, config):\\n        response = self.post(config, \\"/api/device/revoke-self\\", {})\\n        c.need(response.get(\\"ok\\") is True, \\"REVOCATION_NOT_CONFIRMED\\")\\n\\n    def unchanged(self):\\n        c.need(read(self.paths.config_file, private=True) == self.old, \\"CONFIG_CHANGED\\")\\n        c.need(read(self.paths.unit) == self.unit_before, \\"SERVICE_DEFINITION_CHANGED\\")\\n        self.verify_agent()\\n\\n    def replace(self, code):\\n        c.need(8 <= len(code) <= 512 and not any(ch.isspace() for ch in code), \\"PAIRING_CODE_FORMAT\\")\\n        self.unchanged()\\n        self.idle(self.config)\\n        self.work = Path(tempfile.mkdtemp(prefix=\\"pair-recovery-\\", dir=self.paths.config_file.parent))\\n        atomic(self.work / \\"previous.env\\", self.old)\\n        enrolled, switched, stopped = None, False, False\\n        previous = self.runtime_start()\\n        try:\\n            reply = self.post(self.config, \\"/api/device/enroll\\", {\\n                \\"pairing_token\\": code, \\"device_name\\": platform.node(), \\"platform\\": \\"LINUX\\",\\n                \\"architecture\\": platform.machine(), \\"agent_version\\": self.version,\\n                \\"approval_mode\\": self.config.get(\\"HARA_COMMANDER_APPROVAL_MODE\\", \\"ASK_EVERY_ACTION\\")}, False)\\n            code = None\\n            device, token = reply.get(\\"device_id\\"), reply.get(\\"device_token\\")\\n            c.need(isinstance(device, str) and re.fullmatch(r\\"HARA-DEVICE-[a-zA-Z0-9-]{20,80}\\", device), \\"ENROLL_DEVICE_INVALID\\")\\n            c.need(isinstance(token, str) and 16 <= len(token) <= 2048\\n                   and not any(ch.isspace() for ch in token), \\"ENROLL_TOKEN_INVALID\\")\\n            c.need(device != self.config[\\"HARA_DEVICE_ID\\"], \\"NEW_DEVICE_ID_REQUIRED\\")\\n            enrolled = dict(self.config, HARA_DEVICE_ID=device, HARA_DEVICE_TOKEN=token)\\n            replacements = {key: enrolled[key] for key in (\\"HARA_DEVICE_ID\\", \\"HARA_DEVICE_TOKEN\\")}\\n            new = \\"\\".join((key + \\"=\\" + replacements[key] if (key := line.split(\\"=\\", 1)[0]) in replacements\\n                           else line) + \\"\\\\n\\" for line in self.old.decode().splitlines()).encode()\\n            atomic(self.work / \\"new.env\\", new)\\n            self.heartbeat(enrolled)\\n            self.unchanged()\\n            stopped = True\\n            self.service(\\"stop\\", c.SERVICE)\\n            c.need(self.service(\\"show\\", c.SERVICE, \\"--property=MainPID\\", \\"--value\\") == \\"0\\", \\"OLD_SERVICE_RUNNING\\")\\n            self.idle(self.config)\\n            self.unchanged()\\n            # Set before the atomic write: fsync can fail after replacement.\\n            switched = True\\n            atomic(self.paths.config_file, new)\\n            since = time.time() - 1\\n            self.service(\\"start\\", c.SERVICE)\\n            self.wait_runtime(previous, since)\\n            self.heartbeat(enrolled)\\n            self.verify_agent()\\n            c.need(read(self.paths.config_file, private=True) == new\\n                   and read(self.paths.unit) == self.unit_before, \\"POSTCHECK_CHANGED\\")\\n        except BaseException:\\n            restored = not stopped\\n            if stopped:\\n                try:\\n                    self.service(\\"stop\\", c.SERVICE)\\n                    if switched:\\n                        atomic(self.paths.config_file, self.old)\\n                    if self.was_active:\\n                        previous_restore = self.runtime_start()\\n                        restore_since = time.time() - 1\\n                        self.service(\\"start\\", c.SERVICE)\\n                        if self.old_state == \\"PAIRED\\":\\n                            self.wait_runtime(previous_restore, restore_since)\\n                            self.heartbeat(self.config)\\n                    restored = (read(self.paths.config_file, private=True) == self.old and\\n                                (self.service(\\"is-active\\", c.SERVICE, check=False) == \\"active\\") == self.was_active)\\n                except Exception:\\n                    restored = False\\n            revoked = enrolled is None\\n            if enrolled is not None:\\n                try:\\n                    self.revoke(enrolled)\\n                    revoked = True\\n                except Exception:\\n                    pass\\n            atomic(self.work / \\"result.json\\", json.dumps({\\"state\\": \\"FAILED\\", \\"previous_restored\\": restored,\\n                   \\"new_revoked\\": revoked, \\"credentials_exposed\\": False}).encode())\\n            c.need(restored and revoked, \\"PAIR_RECOVERY_REQUIRED\\")\\n            raise\\n        # Never revoke the old credential until the new runtime is verified.\\n        old_revoked = self.old_state == \\"REJECTED\\"\\n        if not old_revoked:\\n            try:\\n                self.revoke(self.config)\\n                old_revoked = True\\n            except Exception:\\n                pass\\n        result = {\\"state\\": \\"PAIRED\\", \\"version\\": self.version, \\"device_id\\": device,\\n                  \\"previous_revoked\\": old_revoked, \\"credentials_exposed\\": False}\\n        atomic(self.work / \\"result.json\\", json.dumps(result).encode())\\n        if old_revoked:\\n            (self.work / \\"previous.env\\").unlink()\\n            (self.work / \\"new.env\\").unlink()\\n        return result\\n\\n\\ndef main():\\n    parser = argparse.ArgumentParser(description=\\"Parear a instala\\u00e7\\u00e3o existente com um novo c\\u00f3digo do portal.\\")\\n    parser.add_argument(\\"--check\\", action=\\"store_true\\", help=\\"Verificar sem pedir ou trocar o c\\u00f3digo.\\")\\n    args = parser.parse_args()\\n    c.need(os.geteuid() != 0, \\"RUN_AS_DESKTOP_USER\\")\\n    runtime = Path(\\"/run/user\\") / str(os.getuid())\\n    os.environ.setdefault(\\"XDG_RUNTIME_DIR\\", str(runtime))\\n    os.environ.setdefault(\\"DBUS_SESSION_BUS_ADDRESS\\", \\"unix:path=\\" + str(runtime / \\"bus\\"))\\n    with c.connection_lock():\\n        flow = Pair()\\n        ready = flow.preflight()\\n        if args.check:\\n            print(json.dumps(ready))\\n            return 0\\n        c.need(sys.stdin.isatty(), \\"PAIRING_REQUIRES_LOCAL_TERMINAL\\")\\n        print(\\"Parear H.A.R.A. Commander com novo c\\u00f3digo\\")\\n        print(\\"Abra \\" + ready[\\"origin\\"] + \\"/auth/login e gere um c\\u00f3digo na conta desejada.\\")\\n        print(\\"A instala\\u00e7\\u00e3o ser\\u00e1 preservada. O v\\u00ednculo atual s\\u00f3 ser\\u00e1 substitu\\u00eddo ap\\u00f3s validar o novo.\\")\\n        print(\\"Enter vazio cancela. O c\\u00f3digo n\\u00e3o aparece enquanto voc\\u00ea digita ou cola.\\")\\n        code = getpass.getpass(\\"Novo c\\u00f3digo de pareamento: \\")\\n        if not code:\\n            print(\\"Cancelado. Pareamento atual preservado.\\")\\n            return 0\\n        result = flow.replace(code.strip())\\n        print(\\"Pareamento conclu\\u00eddo. Commander conectado.\\")\\n        if not result[\\"previous_revoked\\"]:\\n            print(\\"O novo v\\u00ednculo funciona; a revoga\\u00e7\\u00e3o do v\\u00ednculo anterior ficou pendente.\\")\\n        return 0\\n\\n\\nif __name__ == \\"__main__\\":\\n    try:\\n        sys.exit(main())\\n    except (KeyboardInterrupt, EOFError):\\n        print(\\"Opera\\u00e7\\u00e3o cancelada.\\")\\n        sys.exit(130)\\n    except Exception as exc:\\n        code = exc.code if isinstance(exc, c.Hold) else \\"PAIR_OPERATION_FAILED\\"\\n        print(\\"Pareamento n\\u00e3o conclu\\u00eddo: \\" + code, file=sys.stderr)\\n        sys.exit(2)\\n", "commander_connect.py": "#!/usr/bin/env python3\\n\\"\\"\\"Source candidate: explicit connection, enrollment, and signed auto-update.\\n\\nThis controller is not a signed release asset. Native deployment and public\\ndistribution require separate admission. No password or token is logged.\\n\\"\\"\\"\\nfrom __future__ import annotations\\n\\nimport argparse\\nimport base64\\nimport contextlib\\nimport datetime as dt\\nimport fcntl\\nimport hashlib\\nimport hmac\\nimport json\\nimport os\\nfrom pathlib import Path\\nimport re\\nimport ssl\\nimport stat\\nimport subprocess\\nimport sys\\nimport tempfile\\nimport time\\nimport urllib.error\\nimport urllib.parse\\nimport urllib.request\\n\\nKID = \\"commander-release-v2\\"\\nMODULUS = \\"p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43\\"\\nEXPONENT = \\"AQAB\\"\\nPATHS = [\\"agent/linux.py\\", \\"agent/windows.ps1\\", \\"install/linux.sh\\", \\"install/windows.ps1\\"]\\nPAIR_MARKER = b\\"# HARA_COMMANDER_PAIR_EXISTING=1\\"\\nSERVICE = \\"hara-commander-agent.service\\"\\n\\n\\nclass Hold(Exception):\\n    def __init__(self, code: str):\\n        self.code = code\\n        super().__init__(code)\\n\\n\\ndef need(ok: bool, code: str) -> None:\\n    if not ok:\\n        raise Hold(code)\\n\\n\\ndef version(value: str) -> tuple[int, int, int]:\\n    need(bool(re.fullmatch(r\\"(?:0|[1-9]\\\\d*)\\\\.(?:0|[1-9]\\\\d*)\\\\.(?:0|[1-9]\\\\d*)\\", value)), \\"INVALID_AGENT_VERSION\\")\\n    return tuple(int(x) for x in value.split(\\".\\"))\\n\\n\\ndef origin(value: str) -> str:\\n    p = urllib.parse.urlsplit(value)\\n    need(p.scheme == \\"https\\" and bool(p.hostname) and p.username is None and p.password is None\\n         and p.path in (\\"\\", \\"/\\") and not p.query and not p.fragment, \\"COMMANDER_ORIGIN_INVALID\\")\\n    return value.rstrip(\\"/\\")\\n\\n\\ndef unique_json(raw: bytes):\\n    def unique(pairs):\\n        result = {}\\n        for key, value in pairs:\\n            need(key not in result, \\"JSON_DUPLICATE_KEY\\")\\n            result[key] = value\\n        return result\\n    try:\\n        return json.loads(raw, object_pairs_hook=unique)\\n    except (ValueError, UnicodeError) as exc:\\n        raise Hold(\\"JSON_INVALID\\") from exc\\n\\n\\ndef b64ud(value: str) -> bytes:\\n    need(isinstance(value, str) and bool(re.fullmatch(r\\"[A-Za-z0-9_-]+\\", value)), \\"RELEASE_SIGNATURE_ENCODING_INVALID\\")\\n    return base64.urlsafe_b64decode(value + \\"=\\" * ((4 - len(value) % 4) % 4))\\n\\n\\ndef verify_manifest(raw: bytes, signature: bytes) -> dict:\\n    sig = unique_json(signature)\\n    need(isinstance(sig, dict) and sig.get(\\"schema\\") == \\"hara.commander-release-signature.v1\\"\\n         and sig.get(\\"alg\\") == \\"RS256\\" and sig.get(\\"kid\\") == KID, \\"RELEASE_SIGNATURE_INVALID\\")\\n    need(sig.get(\\"manifest_sha256\\") == hashlib.sha256(raw).hexdigest(), \\"RELEASE_MANIFEST_HASH_MISMATCH\\")\\n    n = int.from_bytes(b64ud(MODULUS), \\"big\\")\\n    e = int.from_bytes(b64ud(EXPONENT), \\"big\\")\\n    signed = b64ud(sig.get(\\"signature\\", \\"\\"))\\n    size = (n.bit_length() + 7) // 8\\n    need(len(signed) == size and int.from_bytes(signed, \\"big\\") < n, \\"RELEASE_SIGNATURE_INVALID\\")\\n    actual = pow(int.from_bytes(signed, \\"big\\"), e, n).to_bytes(size, \\"big\\")\\n    digest_info = bytes.fromhex(\\"3031300d060960864801650304020105000420\\") + hashlib.sha256(raw).digest()\\n    padding = size - len(digest_info) - 3\\n    expected = b\\"\\\\x00\\\\x01\\" + b\\"\\\\xff\\" * padding + b\\"\\\\x00\\" + digest_info\\n    need(padding >= 8 and hmac.compare_digest(actual, expected), \\"RELEASE_SIGNATURE_INVALID\\")\\n    obj = unique_json(raw)\\n    need(isinstance(obj, dict) and set(obj) == {\\"schema\\", \\"product\\", \\"channel\\", \\"agent_version\\", \\"files\\"}\\n         and obj.get(\\"schema\\") == \\"hara.commander-agent-release.v1\\"\\n         and obj.get(\\"product\\") == \\"H.A.R.A. Commander\\" and obj.get(\\"channel\\") == \\"stable\\", \\"RELEASE_MANIFEST_INVALID\\")\\n    need(isinstance(obj.get(\\"agent_version\\"), str), \\"RELEASE_MANIFEST_INVALID\\")\\n    need(version(obj[\\"agent_version\\"]) >= (0, 3, 54), \\"RELEASE_BELOW_LINUX_FLOOR\\")\\n    rows = obj.get(\\"files\\")\\n    need(isinstance(rows, list) and len(rows) == 4 and all(isinstance(r, dict) for r in rows)\\n         and [r.get(\\"path\\") for r in rows] == PATHS, \\"RELEASE_FILESET_INVALID\\")\\n    for row in rows:\\n        need(set(row) == {\\"path\\", \\"bytes\\", \\"sha256\\"} and type(row[\\"bytes\\"]) is int\\n             and 0 < row[\\"bytes\\"] <= 2 * 1024 * 1024 and isinstance(row[\\"sha256\\"], str)\\n             and bool(re.fullmatch(r\\"[0-9a-f]{64}\\", row[\\"sha256\\"])), \\"RELEASE_MANIFEST_INVALID\\")\\n    return obj\\n\\n\\nclass NoRedirect(urllib.request.HTTPRedirectHandler):\\n    def redirect_request(self, req, fp, code, msg, headers, newurl):\\n        return None\\n\\n\\nclass Http:\\n    def __init__(self):\\n        self.opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))\\n\\n    def request(self, url: str, *, payload=None, token=None, limit=2 * 1024 * 1024):\\n        headers = {\\"Accept\\": \\"application/json\\", \\"User-Agent\\": \\"HARA-Commander-Connect/1\\"}\\n        body = None\\n        if payload is not None:\\n            headers[\\"Content-Type\\"] = \\"application/json\\"\\n            body = json.dumps(payload, separators=(\\",\\", \\":\\")).encode()\\n        if token is not None:\\n            headers[\\"Authorization\\"] = \\"Bearer \\" + token\\n        request = urllib.request.Request(url, data=body, headers=headers, method=\\"POST\\" if body is not None else \\"GET\\")\\n        try:\\n            response = self.opener.open(request, timeout=30)\\n        except urllib.error.HTTPError as exc:\\n            response = exc\\n        except (OSError, urllib.error.URLError, ValueError) as exc:\\n            raise Hold(\\"CONNECTION_UNAVAILABLE\\") from exc\\n        with response:\\n            raw = response.read(limit + 1)\\n            need(len(raw) <= limit, \\"HTTP_RESPONSE_TOO_LARGE\\")\\n            return response.code, raw\\n\\n    def get(self, url: str, limit=2 * 1024 * 1024) -> bytes:\\n        status, raw = self.request(url, limit=limit)\\n        need(status == 200, \\"RELEASE_DOWNLOAD_HTTP_\\" + str(status))\\n        return raw\\n\\n\\ndef owned_regular(path: Path, *, private=False) -> bool:\\n    try:\\n        info = path.lstat()\\n    except FileNotFoundError:\\n        return False\\n    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), \\"LOCAL_FILE_OWNERSHIP_INVALID\\")\\n    need(not info.st_mode & 0o022, \\"LOCAL_FILE_WRITABLE_BY_OTHERS\\")\\n    if private:\\n        need(not info.st_mode & 0o077, \\"DEVICE_CONFIG_NOT_PRIVATE\\")\\n    return True\\n\\n\\ndef read_config(path: Path) -> dict | None:\\n    if not owned_regular(path, private=True):\\n        return None\\n    raw = path.read_bytes()\\n    need(len(raw) <= 16384, \\"DEVICE_CONFIG_TOO_LARGE\\")\\n    values = {}\\n    try:\\n        for line in raw.decode(\\"utf-8\\").splitlines():\\n            if not line or line.startswith(\\"#\\"):\\n                continue\\n            need(\\"=\\" in line, \\"DEVICE_CONFIG_INVALID\\")\\n            key, value = line.split(\\"=\\", 1)\\n            need(key not in values, \\"DEVICE_CONFIG_DUPLICATE_KEY\\")\\n            values[key] = value\\n    except UnicodeError as exc:\\n        raise Hold(\\"DEVICE_CONFIG_INVALID\\") from exc\\n    need(all(values.get(k) for k in (\\"HARA_COMMANDER_URL\\", \\"HARA_DEVICE_ID\\", \\"HARA_DEVICE_TOKEN\\")), \\"DEVICE_CONFIG_INCOMPLETE\\")\\n    origin(values[\\"HARA_COMMANDER_URL\\"])\\n    return values\\n\\n\\ndef installed_version(path: Path) -> str | None:\\n    if not owned_regular(path):\\n        return None\\n    raw = path.read_bytes()\\n    need(len(raw) <= 2 * 1024 * 1024, \\"INSTALLED_AGENT_TOO_LARGE\\")\\n    matches = re.findall(rb\'^AGENT_VERSION\\\\s*=\\\\s*\\"([0-9]+\\\\.[0-9]+\\\\.[0-9]+)\\"\\\\s*$\', raw, re.M)\\n    need(len(matches) == 1, \\"INSTALLED_AGENT_VERSION_INVALID\\")\\n    value = matches[0].decode(\\"ascii\\")\\n    version(value)\\n    return value\\n\\n\\ndef enrollment_state(http: Http, config: dict | None, current: str | None) -> str:\\n    if config is None:\\n        return \\"UNPAIRED\\"\\n    need(current is not None, \\"PAIRED_AGENT_MISSING\\")\\n    status, raw = http.request(origin(config[\\"HARA_COMMANDER_URL\\"]) + \\"/api/device/heartbeat\\", payload={\\n        \\"device_id\\": config[\\"HARA_DEVICE_ID\\"], \\"architecture\\": config.get(\\"HARA_DEVICE_ARCH\\", \\"\\"),\\n        \\"agent_version\\": current, \\"approval_mode\\": config.get(\\"HARA_COMMANDER_APPROVAL_MODE\\", \\"ASK_EVERY_ACTION\\"),\\n    }, token=config[\\"HARA_DEVICE_TOKEN\\"], limit=65536)\\n    obj = unique_json(raw)\\n    need(isinstance(obj, dict), \\"ENROLLMENT_VALIDATION_AMBIGUOUS\\")\\n    if status == 200 and obj.get(\\"ok\\") is True and obj.get(\\"device_id\\") == config[\\"HARA_DEVICE_ID\\"]:\\n        return \\"PAIRED\\"\\n    if status == 401 and obj.get(\\"code\\") == \\"DEVICE_AUTH_INVALID\\":\\n        return \\"REJECTED\\"\\n    raise Hold(\\"ENROLLMENT_VALIDATION_AMBIGUOUS\\")\\n\\n\\ndef decide(state: str, current: str | None, offered: str, pair_existing_supported: bool) -> tuple[str | None, bool]:\\n    newer = current is None or version(offered) > version(current)\\n    if current is not None:\\n        need(version(offered) >= version(current), \\"AUTO_DOWNGRADE_REFUSED\\")\\n    if state == \\"PAIRED\\":\\n        return (\\"update\\" if newer else None), False\\n    if state == \\"REJECTED\\":\\n        return \\"re-enroll\\", newer\\n    need(state == \\"UNPAIRED\\", \\"ENROLLMENT_STATE_INVALID\\")\\n    if current is not None:\\n        need(pair_existing_supported, \\"SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED\\")\\n        return \\"pair-existing\\", newer\\n    return \\"install\\", False\\n\\n\\nclass Release:\\n    def __init__(self, http: Http, base: str, selected_url: str | None = None, current: str | None = None):\\n        self.http = http\\n        self.base = base\\n        # An explicit QA release selection is not an update channel. It remains\\n        # same-origin, versioned, signed, and never opts out of TLS validation.\\n        if selected_url:\\n            parsed = urllib.parse.urlsplit(selected_url)\\n            need(parsed.scheme == \\"https\\" and origin(parsed.scheme + \\"://\\" + parsed.netloc) == base\\n                 and re.fullmatch(r\\"/releases/\\\\d+\\\\.\\\\d+\\\\.\\\\d+\\", parsed.path)\\n                 and not parsed.query and not parsed.fragment, \\"QA_RELEASE_SELECTION_INVALID\\")\\n            latest_base = selected_url.rstrip(\\"/\\")\\n        else:\\n            latest_base = base\\n        latest = http.get(latest_base + \\"/release/agent-manifest.json\\", 16384)\\n        latest_sig = http.get(latest_base + \\"/release/agent-manifest.sig.json\\", 16384)\\n        self.manifest = verify_manifest(latest, latest_sig)\\n        self.version = self.manifest[\\"agent_version\\"]\\n        if current is not None:\\n            need(version(self.version) >= version(current), \\"AUTO_DOWNGRADE_REFUSED\\")\\n        self.url = base + \\"/releases/\\" + self.version\\n        immutable = http.get(self.url + \\"/release/agent-manifest.json\\", 16384)\\n        immutable_sig = http.get(self.url + \\"/release/agent-manifest.sig.json\\", 16384)\\n        verify_manifest(immutable, immutable_sig)\\n        need(immutable == latest, \\"LATEST_IMMUTABLE_MANIFEST_MISMATCH\\")\\n        self.agent = self.payload(\\"agent/linux.py\\")\\n        self.installer = self.payload(\\"install/linux.sh\\")\\n        matches = re.findall(rb\'^AGENT_VERSION\\\\s*=\\\\s*\\"([0-9]+\\\\.[0-9]+\\\\.[0-9]+)\\"\\\\s*$\', self.agent, re.M)\\n        need(matches == [self.version.encode()], \\"AGENT_RELEASE_VERSION_MISMATCH\\")\\n        self.pair_existing_supported = PAIR_MARKER in self.installer.splitlines()\\n\\n    def payload(self, name: str) -> bytes:\\n        row = next(row for row in self.manifest[\\"files\\"] if row[\\"path\\"] == name)\\n        raw = self.http.get(self.url + \\"/\\" + name, row[\\"bytes\\"])\\n        need(len(raw) == row[\\"bytes\\"] and hashlib.sha256(raw).hexdigest() == row[\\"sha256\\"], \\"RELEASE_PAYLOAD_MISMATCH\\")\\n        return raw\\n\\n    def verify_old_agent(self, path: Path, current: str) -> None:\\n        old_base = self.base + \\"/releases/\\" + current\\n        raw = self.http.get(old_base + \\"/release/agent-manifest.json\\", 16384)\\n        signature = self.http.get(old_base + \\"/release/agent-manifest.sig.json\\", 16384)\\n        metadata = verify_manifest(raw, signature)\\n        need(metadata[\\"agent_version\\"] == current, \\"INSTALLED_AGENT_RELEASE_MISMATCH\\")\\n        expected = metadata[\\"files\\"][0]\\n        actual = path.read_bytes()\\n        need(len(actual) == expected[\\"bytes\\"] and hashlib.sha256(actual).hexdigest() == expected[\\"sha256\\"], \\"INSTALLED_AGENT_INTEGRITY_FAILED\\")\\n\\n\\nclass Connect:\\n    def __init__(self, http=None):\\n        self.http = http or Http()\\n        self.home = Path.home()\\n        self.config_root = Path(os.environ.get(\\"XDG_CONFIG_HOME\\", self.home / \\".config\\"))\\n        self.data_root = Path(os.environ.get(\\"XDG_DATA_HOME\\", self.home / \\".local/share\\"))\\n        self.config_file = self.config_root / \\"hara-commander/device.env\\"\\n        self.agent = self.data_root / \\"hara-commander/hara-commander-agent\\"\\n        self.status = self.data_root / \\"hara-commander/runtime-status.json\\"\\n        self.unit = self.config_root / \\"systemd/user\\" / SERVICE\\n        self.report = {\\"state\\": \\"PENDING\\", \\"pairing_validated\\": False, \\"phase\\": \\"VALIDATE_PAIRING\\", \\"token_exposed\\": False}\\n\\n    def invoke_installer(self, path: Path, action: str, base: str, release: Release) -> None:\\n        environment = os.environ.copy()\\n        environment[\\"HARA_COMMANDER_URL\\"] = base\\n        environment[\\"HARA_COMMANDER_RELEASE_URL\\"] = release.url\\n        # Inherit the controlling terminal for the signed installer\'s hidden\\n        # token prompt. The controller never places the token in argv or logs.\\n        result = subprocess.run([\\"bash\\", str(path), action], env=environment)\\n        need(result.returncode == 0, \\"SIGNED_INSTALLER_ACTION_FAILED\\")\\n\\n    def require_terminal(self) -> None:\\n        try:\\n            terminal = os.open(\\"/dev/tty\\", os.O_RDWR | os.O_NOCTTY)\\n            os.close(terminal)\\n        except OSError as exc:\\n            raise Hold(\\"PAIRING_REQUIRES_LOCAL_TERMINAL\\") from exc\\n\\n    def invoke_and_recheck_failure(self, path: Path, action: str, base: str, release: Release) -> None:\\n        validated_before = self.report.get(\\"pairing_validated\\", False)\\n        prior_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if validated_before else None\\n        self.report[\\"pairing_validated\\"] = False\\n        try:\\n            self.invoke_installer(path, action, base, release)\\n        except Hold:\\n            # A failed update may have rolled back successfully. Revalidate the\\n            # same credential before reporting that its pairing still works.\\n            if validated_before:\\n                try:\\n                    config = read_config(self.config_file)\\n                    unchanged = hashlib.sha256(self.config_file.read_bytes()).hexdigest() == prior_sha\\n                    current = installed_version(self.agent)\\n                    if unchanged and enrollment_state(self.http, config, current) == \\"PAIRED\\":\\n                        self.report.update(pairing_validated=True, agent_version=current)\\n                except (Hold, OSError, ValueError):\\n                    pass\\n            raise\\n\\n    def start_and_verify(self, expected: str, device_id: str) -> None:\\n        need(owned_regular(self.unit), \\"AGENT_SERVICE_MISSING\\")\\n        was_active = subprocess.run([\\"systemctl\\", \\"--user\\", \\"is-active\\", \\"--quiet\\", SERVICE]).returncode == 0\\n        started_after = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)\\n        completed = subprocess.run([\\"systemctl\\", \\"--user\\", \\"start\\", SERVICE], capture_output=True)\\n        need(completed.returncode == 0, \\"AGENT_SERVICE_START_FAILED\\")\\n        # A connection command deliberately starts the service; it never enables\\n        # login/boot autostart. Current local approval mode is preserved.\\n        floor = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=90) if was_active else started_after\\n        for _ in range(45):\\n            try:\\n                if owned_regular(self.status):\\n                    obj = unique_json(self.status.read_bytes())\\n                    last = dt.datetime.fromisoformat(str(obj.get(\\"last_successful_heartbeat_at_utc\\", \\"\\")).replace(\\"Z\\", \\"+00:00\\"))\\n                    started = dt.datetime.fromisoformat(str(obj.get(\\"started_at_utc\\", \\"\\")).replace(\\"Z\\", \\"+00:00\\"))\\n                    device_matches = obj.get(\\"device_id\\", device_id) == device_id\\n                    if obj.get(\\"agent_version\\") == expected and last >= floor and device_matches and (was_active or started >= started_after):\\n                        active = subprocess.run([\\"systemctl\\", \\"--user\\", \\"is-active\\", \\"--quiet\\", SERVICE])\\n                        if active.returncode == 0:\\n                            return\\n            except (ValueError, Hold):\\n                pass\\n            time.sleep(1)\\n        raise Hold(\\"FRESH_AGENT_HEARTBEAT_NOT_CONFIRMED\\")\\n\\n    def run(self, selected_url=None) -> dict:\\n        need(os.geteuid() != 0, \\"RUN_AS_DESKTOP_USER\\")\\n        # Explicit desktop connect may be invoked through SSH with an existing\\n        # user bus; no new login session or global system service is created.\\n        runtime = Path(\\"/run/user\\") / str(os.getuid())\\n        if runtime.is_dir():\\n            os.environ.setdefault(\\"XDG_RUNTIME_DIR\\", str(runtime))\\n            if (runtime / \\"bus\\").exists():\\n                os.environ.setdefault(\\"DBUS_SESSION_BUS_ADDRESS\\", \\"unix:path=\\" + str(runtime / \\"bus\\"))\\n        config = read_config(self.config_file)\\n        config_before = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if config else None\\n        current = installed_version(self.agent)\\n        state = enrollment_state(self.http, config, current)\\n        base = origin(config[\\"HARA_COMMANDER_URL\\"] if config else os.environ.get(\\"HARA_COMMANDER_URL\\", \\"https://commander.haralabs.com.br\\"))\\n        self.report.update(initial_state=state, initial_pairing_validated=state == \\"PAIRED\\", pairing_validated=state == \\"PAIRED\\", agent_version=current,\\n                           commander_url=base, phase=\\"CHECK_UPDATE\\")\\n        print(\\"Validando a conexao e a versao assinada do Commander...\\", flush=True)\\n        release = Release(self.http, base, selected_url, current)\\n        action, update_after_pair = decide(state, current, release.version, release.pair_existing_supported)\\n        if current is not None:\\n            release.verify_old_agent(self.agent, current)\\n        if action in (\\"install\\", \\"pair-existing\\", \\"re-enroll\\"):\\n            self.require_terminal()\\n            print(\\"Abra \\" + base + \\"/auth/login, entre na sua conta e gere um codigo de pareamento.\\", flush=True)\\n            print(\\"Digite somente esse codigo quando o instalador solicitar. A senha fica no site.\\", flush=True)\\n        else:\\n            print(\\"Maquina ja pareada; o vinculo existente sera preservado.\\", flush=True)\\n        with tempfile.TemporaryDirectory(prefix=\\"hara-connect-\\") as directory:\\n            installer = Path(directory) / \\"linux.sh\\"\\n            installer.write_bytes(release.installer)\\n            os.chmod(installer, 0o700)\\n            if action:\\n                self.report[\\"phase\\"] = \\"PAIRING\\" if action != \\"update\\" else \\"UPDATE\\"\\n                self.invoke_and_recheck_failure(installer, action, base, release)\\n            after = read_config(self.config_file)\\n            actual = installed_version(self.agent)\\n            if state == \\"PAIRED\\":\\n                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_before, \\"EXISTING_ENROLLMENT_CHANGED\\")\\n            need(enrollment_state(self.http, after, actual) == \\"PAIRED\\", \\"PAIRING_NOT_CONFIRMED\\")\\n            self.report.update(pairing_validated=True, agent_version=actual, device_id=after[\\"HARA_DEVICE_ID\\"])\\n            if update_after_pair:\\n                self.report[\\"phase\\"] = \\"UPDATE\\"\\n                post_pair_config_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest()\\n                self.invoke_and_recheck_failure(installer, \\"update\\", base, release)\\n                after = read_config(self.config_file)\\n                actual = installed_version(self.agent)\\n                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == post_pair_config_sha, \\"POST_PAIR_ENROLLMENT_CHANGED\\")\\n                need(enrollment_state(self.http, after, actual) == \\"PAIRED\\", \\"POST_UPDATE_PAIRING_NOT_CONFIRMED\\")\\n                self.report.update(pairing_validated=True, agent_version=actual)\\n            need(actual == release.version, \\"AGENT_UPDATE_NOT_CONFIRMED\\")\\n            release.verify_old_agent(self.agent, actual)\\n            self.report[\\"phase\\"] = \\"START_AND_VERIFY_RUNTIME\\"\\n            config_after_actions = hashlib.sha256(self.config_file.read_bytes()).hexdigest()\\n            self.start_and_verify(actual, after[\\"HARA_DEVICE_ID\\"])\\n            final = read_config(self.config_file)\\n            need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_after_actions,\\n                 \\"ENROLLMENT_CHANGED_DURING_START\\")\\n            need(enrollment_state(self.http, final, actual) == \\"PAIRED\\", \\"FINAL_CONNECTION_NOT_CONFIRMED\\")\\n        return {\\"state\\": \\"CONNECTED\\", \\"agent_version\\": actual, \\"initial_state\\": state,\\n                \\"action\\": action or \\"already-current\\", \\"updated_after_pair\\": update_after_pair,\\n                \\"commander_url\\": base, \\"device_id\\": after[\\"HARA_DEVICE_ID\\"], \\"token_exposed\\": False}\\n\\n\\n@contextlib.contextmanager\\ndef connection_lock():\\n    runtime = Path(os.environ.get(\\"XDG_RUNTIME_DIR\\", \\"/run/user/\\" + str(os.getuid())))\\n    info = runtime.lstat()\\n    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,\\n         \\"PRIVATE_USER_RUNTIME_REQUIRED\\")\\n    path = runtime / \\"hara-commander-connect.lock\\"\\n    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)\\n    try:\\n        info = os.fstat(fd)\\n        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,\\n             \\"CONNECT_LOCK_INVALID\\")\\n        try:\\n            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\\n        except BlockingIOError as exc:\\n            raise Hold(\\"CONNECTION_ALREADY_IN_PROGRESS\\") from exc\\n        yield\\n    finally:\\n        os.close(fd)\\n\\n\\ndef main():\\n    parser = argparse.ArgumentParser(description=\\"Conectar, parear quando necessario e atualizar o HARA Commander.\\")\\n    parser.add_argument(\\"action\\", nargs=\\"?\\", default=\\"connect\\", choices=(\\"connect\\", \\"conectar\\"))\\n    parser.add_argument(\\"--qa-release-url\\", help=\\"Selecao QA assinada, versionada e na mesma origem; nao substitui o canal publico.\\")\\n    args = parser.parse_args()\\n    flow = Connect()\\n    try:\\n        with connection_lock():\\n            report = flow.run(args.qa_release_url)\\n        print(json.dumps(report, sort_keys=True))\\n        return 0\\n    except Hold as exc:\\n        report = dict(flow.report)\\n        report.update(state=\\"HOLD\\", error_code=exc.code)\\n        if report.get(\\"pairing_validated\\") and report.get(\\"phase\\") in (\\"CHECK_UPDATE\\", \\"UPDATE\\"):\\n            report[\\"state\\"] = \\"PAIRING_VALID_UPDATE_HOLD\\"\\n            print(\\"Pareamento validado; atualizacao pendente: \\" + exc.code, file=sys.stderr)\\n        else:\\n            print(\\"Commander nao concluiu a conexao: \\" + exc.code, file=sys.stderr)\\n        print(json.dumps(report, sort_keys=True))\\n        return 2\\n    except (OSError, ValueError, TypeError, subprocess.SubprocessError):\\n        # Do not copy arbitrary exception text containing request/auth data.\\n        print(\\"Commander nao concluiu a conexao: CONNECT_OPERATION_FAILED\\", file=sys.stderr)\\n        return 2\\n\\n\\nif __name__ == \\"__main__\\":\\n    raise SystemExit(main())\\n"}')
uid=os.getuid()
def checked_dir(p):
    for q in (p,*p.parents):
        if q.is_symlink():raise SystemExit("PAIR_PARENT_SYMLINK")
    p.mkdir(parents=True,exist_ok=True,mode=0o700)
    st=p.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=uid or st.st_mode&0o022:raise SystemExit("PAIR_DIRECTORY_PERMISSIONS")
def write(p,data):
    if p.exists() or p.is_symlink():
        st=p.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=uid or st.st_mode&0o022:raise SystemExit("PAIR_FILE_CONFLICT")
    fd,name=tempfile.mkstemp(prefix='.pair-install-',dir=p.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o700);os.replace(name,p)
    finally:
        if os.path.exists(name):os.unlink(name)
checked_dir(root/'pair');checked_dir(userbin)
for name,source in files.items():write(root/'pair'/name,source)
launcher='#!/bin/sh\nset -eu\nexec /usr/bin/python3 "'+str(root/'pair/commander_pair.py')+'" "$@"\n'
write(userbin/'hara-commander-pair',launcher)
hara=userbin/'hara'
if hara.is_file() and not hara.is_symlink() and '# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1' in hara.read_text():
    # Retire the QA-only dispatch; the signed Agent now handles pair itself.
    write(hara, '#!/bin/sh\n# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\nset -eu\n[ "${1:-}" = commander ] || exit 64\nshift\n[ "$#" -gt 0 ] || set -- status\nexec "$HOME/.local/bin/hara-commander" "$@"\n')
PYINSTALLPAIR
}

install_cli() {
  install_pair_cli || return 1
  if [ -e "$CLI" ] || [ -L "$CLI" ]; then
    if [ ! -L "$CLI" ] || [ "$(readlink "$CLI")" != "$AGENT" ]; then
      echo 'HARA_COMMANDER_CLI_PATH_CONFLICT' >&2
      return 1
    fi
  fi
  mkdir -p "$USER_BIN" || return 1
  ln -sfn "$AGENT" "$CLI" || return 1
  if [ ! -e "$USER_BIN/hara" ] && ! command -v hara >/dev/null 2>&1; then
    cat >"$USER_BIN/hara" <<'EOHARA' || return 1
#!/bin/sh
set -eu
if [ "${1:-}" != "commander" ]; then
  echo "Usage: hara commander [pair|status|stop|mcp|doctor|support|approval-mode]" >&2
  exit 64
fi
shift
[ "$#" -gt 0 ] || set -- status
exec "$HOME/.local/bin/hara-commander" "$@"
EOHARA
    chmod 700 "$USER_BIN/hara" || return 1
  fi
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
    payload={"device_id":device_id,"architecture":arch,"agent_version":"0.3.60","approval_mode":values.get("HARA_COMMANDER_APPROVAL_MODE","ASK_EVERY_ACTION")}
elif action=="revoke":
    endpoint="/api/device/revoke-self"
    payload={}
else:
    raise SystemExit(2)
req=urllib.request.Request(
    base+endpoint, data=json.dumps(payload,separators=(",",":")).encode(), method="POST",
    headers={"content-type":"application/json","accept":"application/json","user-agent":"HARA-Commander-Installer/0.3.60","authorization":"Bearer "+token},
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
    headers={"content-type":"application/json","accept":"application/json","authorization":"Bearer "+token,"user-agent":"HARA-Commander-Installer-Rollback/0.3.60"},
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
    # Remove only entrypoints owned by this failed installation.
    if [ -L "$CLI" ] && [ "$(readlink "$CLI")" = "$AGENT" ]; then rm -f "$CLI"; fi
    if [ -f "$USER_BIN/hara" ] && [ ! -L "$USER_BIN/hara" ] && grep -Fqx '# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1' "$USER_BIN/hara"; then rm -f "$USER_BIN/hara"; fi
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
payload=json.dumps({"device_id":device_id,"architecture":arch,"agent_version":"0.3.60"},separators=(",",":")).encode()
req=urllib.request.Request(
    base+"/api/device/heartbeat", data=payload, method="POST",
    headers={"content-type":"application/json","accept":"application/json",
             "user-agent":"HARA-Commander-Reenroll-Check/0.3.60","authorization":"Bearer "+token},
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
    if [ "${REENROLL_CONFIG_REPLACED:-FALSE}" = TRUE ]; then
      if [ "${REENROLL_CONFIG_EXISTED:-TRUE}" = TRUE ] && [ -n "${REENROLL_BACKUP:-}" ] && [ -f "$REENROLL_BACKUP" ]; then
        mv -f "$REENROLL_BACKUP" "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE"
      elif [ "${REENROLL_CONFIG_EXISTED:-TRUE}" = FALSE ]; then
        # Only the config created by this attach transaction is removed.
        # Existing Agent, unit, CLI, directories, and user data are preserved.
        rm -f "$CONFIG_FILE"
      fi
      if [ "${REENROLL_SERVICE_WAS_ACTIVE:-FALSE}" = TRUE ]; then
        systemctl --user restart "$SERVICE" >/dev/null 2>&1 || true
      else
        systemctl --user stop "$SERVICE" >/dev/null 2>&1 || true
      fi
    fi
    if [ "$revoke_state" != PASS ]; then
      record_pending_revoke || printf 'HARA_COMMANDER_PENDING_REVOKE_RECOVERY_SAVED=FALSE\n' >&2
    fi
    printf 'HARA_COMMANDER_FAILED_REENROLL_ROLLBACK=%s\n' "$revoke_state" >&2
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n' >&2
  fi
  [ -z "${REENROLL_BACKUP:-}" ] || rm -f "$REENROLL_BACKUP"
  [ -z "${CONFIG_PENDING:-}" ] || rm -f "$CONFIG_PENDING"
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
  curl -fsS --max-time 15 "$(release_url)/release/agent-manifest.json" -o "$manifest" || { echo 'AGENT_RELEASE_MANIFEST_UNREACHABLE' >&2; return 11; }
  curl -fsS --max-time 15 "$(release_url)/release/agent-manifest.sig.json" -o "$signature" || { echo 'AGENT_RELEASE_SIGNATURE_UNREACHABLE' >&2; return 11; }
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

validate_pair_existing_preimage() {
  python3 - "$CONFIG_FILE" "$CONFIG_DIR" "$BIN_DIR" "$AGENT" "$UNIT" "$CLI" <<'PYPAIRPREIMAGE'
import os,stat,subprocess,sys
from pathlib import Path
config,configdir,bindir,agent,unit,cli=map(Path,sys.argv[1:])
uid=os.getuid()
def fail(code): raise SystemExit(code)
def checked(path,kind,required=True):
    try: st=path.lstat()
    except FileNotFoundError:
        if required: fail("PAIR_EXISTING_PATH_MISSING")
        return False
    if st.st_uid!=uid or st.st_mode&0o022: fail("PAIR_EXISTING_PATH_OWNERSHIP_INVALID")
    if kind=="dir" and not stat.S_ISDIR(st.st_mode): fail("PAIR_EXISTING_DIRECTORY_INVALID")
    if kind=="file" and not stat.S_ISREG(st.st_mode): fail("PAIR_EXISTING_FILE_INVALID")
    for parent in path.parents:
        if parent.is_symlink(): fail("PAIR_EXISTING_PARENT_SYMLINK_REFUSED")
    return True
if config.exists() or config.is_symlink(): fail("PAIR_EXISTING_CONFIG_ALREADY_PRESENT")
checked(configdir,"dir",False)
checked(bindir,"dir")
checked(agent,"file")
checked(unit,"file")
text=unit.read_text(encoding="utf-8")
expected="""[Unit]
Description=HARA Commander Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart="""+str(agent)+"""
# The service may restart after a failure only while explicitly started.
# It is NOT enabled at boot by the installer.
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=default.target
"""
if text!=expected:
    fail("PAIR_EXISTING_UNIT_UNEXPECTED")
dropin=unit.with_name(unit.name+".d")
if dropin.exists() or dropin.is_symlink(): fail("PAIR_EXISTING_UNIT_OVERRIDE_REVIEW_REQUIRED")
if cli.exists() or cli.is_symlink():
    if not cli.is_symlink() or os.readlink(cli)!=str(agent) or cli.lstat().st_uid!=uid:
        fail("PAIR_EXISTING_CLI_CONFLICT")
reload=subprocess.run(["systemctl","--user","daemon-reload"],capture_output=True)
if reload.returncode: fail("PAIR_EXISTING_DAEMON_RELOAD_FAILED")
def show(name):
    result=subprocess.run(["systemctl","--user","show","hara-commander-agent.service","--property="+name,"--value"],capture_output=True,text=True)
    if result.returncode: fail("PAIR_EXISTING_EFFECTIVE_UNIT_UNAVAILABLE")
    return result.stdout.strip()
if show("FragmentPath")!=str(unit) or show("DropInPaths") or show("LoadState")!="loaded" or show("Type")!="simple":
    fail("PAIR_EXISTING_EFFECTIVE_UNIT_MISMATCH")
effective=show("ExecStart")
parts=[p.strip() for p in effective.split(";")]
if len(parts)<3 or parts[0]!="{ path="+str(agent) or parts[1]!="argv[]="+str(agent) or effective.count("{ path=")!=1:
    fail("PAIR_EXISTING_EFFECTIVE_EXECSTART_MISMATCH")
print("HARA_COMMANDER_PAIR_EXISTING_PREIMAGE=PASS")
PYPAIRPREIMAGE
  if systemctl --user is-active --quiet "$SERVICE"; then
    echo 'PAIR_EXISTING_UNPAIRED_SERVICE_ACTIVE' >&2
    return 9
  fi
}

verify_pair_existing_agent() {
  local installed_version metadata manifest signature rc=0
  installed_version="$(python3 - "$AGENT" <<'PYPAIRVERSION'
from pathlib import Path
import re,sys
matches=re.findall(r'^AGENT_VERSION\s*=\s*"((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"\s*$',Path(sys.argv[1]).read_text(),re.M)
if len(matches)!=1: raise SystemExit("PAIR_EXISTING_VERSION_INVALID")
print(matches[0])
PYPAIRVERSION
)"
  assert_agent_version_floor "$installed_version"
  manifest="$(mktemp)"; signature="$(mktemp)"
  if curl -fsS --max-time 30 "${BASE_URL%/}/releases/$installed_version/release/agent-manifest.json" -o "$manifest" &&
     curl -fsS --max-time 30 "${BASE_URL%/}/releases/$installed_version/release/agent-manifest.sig.json" -o "$signature" &&
     verify_release_manifest_signature "$manifest" "$signature"; then
    if metadata="$(read_release_metadata "$manifest" "$installed_version")"; then
      if ! python3 - "$AGENT" "$metadata" <<'PYPAIRHASH'
import hashlib,sys
from pathlib import Path
parts=sys.argv[2].splitlines()
raw=Path(sys.argv[1]).read_bytes()
if len(parts)!=3 or len(raw)!=int(parts[2]) or hashlib.sha256(raw).hexdigest()!=parts[1]:
    raise SystemExit("PAIR_EXISTING_AGENT_HASH_MISMATCH")
PYPAIRHASH
      then rc=1; fi
    else rc=1; fi
  else rc=1; fi
  rm -f "$manifest" "$signature"
  [ "$rc" -eq 0 ] || { echo 'PAIR_EXISTING_AGENT_INTEGRITY_FAILED' >&2; return 1; }
}

record_pending_revoke() {
  # Network failure must not silently discard the only credential capable of
  # cleaning up a newly enrolled device. Store only in the owner's private config.
  printf '%s\n' "$DEVICE_TOKEN" | python3 -c '
import json,os,stat,sys,tempfile
from pathlib import Path
base,device,directory=sys.argv[1:4]
token=sys.stdin.readline().rstrip("\n")
if not token or not device: raise SystemExit(2)
parent=Path(directory)
parent.mkdir(mode=0o700,parents=True,exist_ok=True)
st=parent.lstat()
if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077: raise SystemExit(3)
fd,path=tempfile.mkstemp(prefix=".pending-device-revoke-",suffix=".json",dir=parent)
with os.fdopen(fd,"w") as f:
    json.dump({"schema":"hara.commander.pending-revoke.v1","base_url":base,"device_id":device,"device_token":token},f)
    f.flush();os.fsync(f.fileno())
print("HARA_COMMANDER_PENDING_REVOKE_RECOVERY_SAVED=TRUE")
' "$BASE_URL" "$DEVICE_ID" "$CONFIG_DIR"
}

case "$ACTION" in
  pair|parear|re-pair)
    install_pair_cli
    exec "$USER_BIN/hara-commander-pair" ;;
  connect|conectar)
    python3 - connect <<'PYHARA_COMMANDER_CONNECT_A696A233'
#!/usr/bin/env python3
"""Source candidate: explicit connection, enrollment, and signed auto-update.

This controller is not a signed release asset. Native deployment and public
distribution require separate admission. No password or token is logged.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

KID = "commander-release-v2"
MODULUS = "p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43"
EXPONENT = "AQAB"
PATHS = ["agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1"]
PAIR_MARKER = b"# HARA_COMMANDER_PAIR_EXISTING=1"
SERVICE = "hara-commander-agent.service"


class Hold(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Hold(code)


def version(value: str) -> tuple[int, int, int]:
    need(bool(re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)), "INVALID_AGENT_VERSION")
    return tuple(int(x) for x in value.split("."))


def origin(value: str) -> str:
    p = urllib.parse.urlsplit(value)
    need(p.scheme == "https" and bool(p.hostname) and p.username is None and p.password is None
         and p.path in ("", "/") and not p.query and not p.fragment, "COMMANDER_ORIGIN_INVALID")
    return value.rstrip("/")


def unique_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise Hold("JSON_INVALID") from exc


def b64ud(value: str) -> bytes:
    need(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", value)), "RELEASE_SIGNATURE_ENCODING_INVALID")
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def verify_manifest(raw: bytes, signature: bytes) -> dict:
    sig = unique_json(signature)
    need(isinstance(sig, dict) and sig.get("schema") == "hara.commander-release-signature.v1"
         and sig.get("alg") == "RS256" and sig.get("kid") == KID, "RELEASE_SIGNATURE_INVALID")
    need(sig.get("manifest_sha256") == hashlib.sha256(raw).hexdigest(), "RELEASE_MANIFEST_HASH_MISMATCH")
    n = int.from_bytes(b64ud(MODULUS), "big")
    e = int.from_bytes(b64ud(EXPONENT), "big")
    signed = b64ud(sig.get("signature", ""))
    size = (n.bit_length() + 7) // 8
    need(len(signed) == size and int.from_bytes(signed, "big") < n, "RELEASE_SIGNATURE_INVALID")
    actual = pow(int.from_bytes(signed, "big"), e, n).to_bytes(size, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(raw).digest()
    padding = size - len(digest_info) - 3
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
    need(padding >= 8 and hmac.compare_digest(actual, expected), "RELEASE_SIGNATURE_INVALID")
    obj = unique_json(raw)
    need(isinstance(obj, dict) and set(obj) == {"schema", "product", "channel", "agent_version", "files"}
         and obj.get("schema") == "hara.commander-agent-release.v1"
         and obj.get("product") == "H.A.R.A. Commander" and obj.get("channel") == "stable", "RELEASE_MANIFEST_INVALID")
    need(isinstance(obj.get("agent_version"), str), "RELEASE_MANIFEST_INVALID")
    need(version(obj["agent_version"]) >= (0, 3, 54), "RELEASE_BELOW_LINUX_FLOOR")
    rows = obj.get("files")
    need(isinstance(rows, list) and len(rows) == 4 and all(isinstance(r, dict) for r in rows)
         and [r.get("path") for r in rows] == PATHS, "RELEASE_FILESET_INVALID")
    for row in rows:
        need(set(row) == {"path", "bytes", "sha256"} and type(row["bytes"]) is int
             and 0 < row["bytes"] <= 2 * 1024 * 1024 and isinstance(row["sha256"], str)
             and bool(re.fullmatch(r"[0-9a-f]{64}", row["sha256"])), "RELEASE_MANIFEST_INVALID")
    return obj


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Http:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self, url: str, *, payload=None, token=None, limit=2 * 1024 * 1024):
        headers = {"Accept": "application/json", "User-Agent": "HARA-Commander-Connect/1"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode()
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise Hold("CONNECTION_UNAVAILABLE") from exc
        with response:
            raw = response.read(limit + 1)
            need(len(raw) <= limit, "HTTP_RESPONSE_TOO_LARGE")
            return response.code, raw

    def get(self, url: str, limit=2 * 1024 * 1024) -> bytes:
        status, raw = self.request(url, limit=limit)
        need(status == 200, "RELEASE_DOWNLOAD_HTTP_" + str(status))
        return raw


def owned_regular(path: Path, *, private=False) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), "LOCAL_FILE_OWNERSHIP_INVALID")
    need(not info.st_mode & 0o022, "LOCAL_FILE_WRITABLE_BY_OTHERS")
    if private:
        need(not info.st_mode & 0o077, "DEVICE_CONFIG_NOT_PRIVATE")
    return True


def read_config(path: Path) -> dict | None:
    if not owned_regular(path, private=True):
        return None
    raw = path.read_bytes()
    need(len(raw) <= 16384, "DEVICE_CONFIG_TOO_LARGE")
    values = {}
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            need("=" in line, "DEVICE_CONFIG_INVALID")
            key, value = line.split("=", 1)
            need(key not in values, "DEVICE_CONFIG_DUPLICATE_KEY")
            values[key] = value
    except UnicodeError as exc:
        raise Hold("DEVICE_CONFIG_INVALID") from exc
    need(all(values.get(k) for k in ("HARA_COMMANDER_URL", "HARA_DEVICE_ID", "HARA_DEVICE_TOKEN")), "DEVICE_CONFIG_INCOMPLETE")
    origin(values["HARA_COMMANDER_URL"])
    return values


def installed_version(path: Path) -> str | None:
    if not owned_regular(path):
        return None
    raw = path.read_bytes()
    need(len(raw) <= 2 * 1024 * 1024, "INSTALLED_AGENT_TOO_LARGE")
    matches = re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', raw, re.M)
    need(len(matches) == 1, "INSTALLED_AGENT_VERSION_INVALID")
    value = matches[0].decode("ascii")
    version(value)
    return value


def enrollment_state(http: Http, config: dict | None, current: str | None) -> str:
    if config is None:
        return "UNPAIRED"
    need(current is not None, "PAIRED_AGENT_MISSING")
    status, raw = http.request(origin(config["HARA_COMMANDER_URL"]) + "/api/device/heartbeat", payload={
        "device_id": config["HARA_DEVICE_ID"], "architecture": config.get("HARA_DEVICE_ARCH", ""),
        "agent_version": current, "approval_mode": config.get("HARA_COMMANDER_APPROVAL_MODE", "ASK_EVERY_ACTION"),
    }, token=config["HARA_DEVICE_TOKEN"], limit=65536)
    obj = unique_json(raw)
    need(isinstance(obj, dict), "ENROLLMENT_VALIDATION_AMBIGUOUS")
    if status == 200 and obj.get("ok") is True and obj.get("device_id") == config["HARA_DEVICE_ID"]:
        return "PAIRED"
    if status == 401 and obj.get("code") == "DEVICE_AUTH_INVALID":
        return "REJECTED"
    raise Hold("ENROLLMENT_VALIDATION_AMBIGUOUS")


def decide(state: str, current: str | None, offered: str, pair_existing_supported: bool) -> tuple[str | None, bool]:
    newer = current is None or version(offered) > version(current)
    if current is not None:
        need(version(offered) >= version(current), "AUTO_DOWNGRADE_REFUSED")
    if state == "PAIRED":
        return ("update" if newer else None), False
    if state == "REJECTED":
        return "re-enroll", newer
    need(state == "UNPAIRED", "ENROLLMENT_STATE_INVALID")
    if current is not None:
        need(pair_existing_supported, "SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED")
        return "pair-existing", newer
    return "install", False


class Release:
    def __init__(self, http: Http, base: str, selected_url: str | None = None, current: str | None = None):
        self.http = http
        self.base = base
        # An explicit QA release selection is not an update channel. It remains
        # same-origin, versioned, signed, and never opts out of TLS validation.
        if selected_url:
            parsed = urllib.parse.urlsplit(selected_url)
            need(parsed.scheme == "https" and origin(parsed.scheme + "://" + parsed.netloc) == base
                 and re.fullmatch(r"/releases/\d+\.\d+\.\d+", parsed.path)
                 and not parsed.query and not parsed.fragment, "QA_RELEASE_SELECTION_INVALID")
            latest_base = selected_url.rstrip("/")
        else:
            latest_base = base
        latest = http.get(latest_base + "/release/agent-manifest.json", 16384)
        latest_sig = http.get(latest_base + "/release/agent-manifest.sig.json", 16384)
        self.manifest = verify_manifest(latest, latest_sig)
        self.version = self.manifest["agent_version"]
        if current is not None:
            need(version(self.version) >= version(current), "AUTO_DOWNGRADE_REFUSED")
        self.url = base + "/releases/" + self.version
        immutable = http.get(self.url + "/release/agent-manifest.json", 16384)
        immutable_sig = http.get(self.url + "/release/agent-manifest.sig.json", 16384)
        verify_manifest(immutable, immutable_sig)
        need(immutable == latest, "LATEST_IMMUTABLE_MANIFEST_MISMATCH")
        self.agent = self.payload("agent/linux.py")
        self.installer = self.payload("install/linux.sh")
        matches = re.findall(rb'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', self.agent, re.M)
        need(matches == [self.version.encode()], "AGENT_RELEASE_VERSION_MISMATCH")
        self.pair_existing_supported = PAIR_MARKER in self.installer.splitlines()

    def payload(self, name: str) -> bytes:
        row = next(row for row in self.manifest["files"] if row["path"] == name)
        raw = self.http.get(self.url + "/" + name, row["bytes"])
        need(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "RELEASE_PAYLOAD_MISMATCH")
        return raw

    def verify_old_agent(self, path: Path, current: str) -> None:
        old_base = self.base + "/releases/" + current
        raw = self.http.get(old_base + "/release/agent-manifest.json", 16384)
        signature = self.http.get(old_base + "/release/agent-manifest.sig.json", 16384)
        metadata = verify_manifest(raw, signature)
        need(metadata["agent_version"] == current, "INSTALLED_AGENT_RELEASE_MISMATCH")
        expected = metadata["files"][0]
        actual = path.read_bytes()
        need(len(actual) == expected["bytes"] and hashlib.sha256(actual).hexdigest() == expected["sha256"], "INSTALLED_AGENT_INTEGRITY_FAILED")


class Connect:
    def __init__(self, http=None):
        self.http = http or Http()
        self.home = Path.home()
        self.config_root = Path(os.environ.get("XDG_CONFIG_HOME", self.home / ".config"))
        self.data_root = Path(os.environ.get("XDG_DATA_HOME", self.home / ".local/share"))
        self.config_file = self.config_root / "hara-commander/device.env"
        self.agent = self.data_root / "hara-commander/hara-commander-agent"
        self.status = self.data_root / "hara-commander/runtime-status.json"
        self.unit = self.config_root / "systemd/user" / SERVICE
        self.report = {"state": "PENDING", "pairing_validated": False, "phase": "VALIDATE_PAIRING", "token_exposed": False}

    def invoke_installer(self, path: Path, action: str, base: str, release: Release) -> None:
        environment = os.environ.copy()
        environment["HARA_COMMANDER_URL"] = base
        environment["HARA_COMMANDER_RELEASE_URL"] = release.url
        # Inherit the controlling terminal for the signed installer's hidden
        # token prompt. The controller never places the token in argv or logs.
        result = subprocess.run(["bash", str(path), action], env=environment)
        need(result.returncode == 0, "SIGNED_INSTALLER_ACTION_FAILED")

    def require_terminal(self) -> None:
        try:
            terminal = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
            os.close(terminal)
        except OSError as exc:
            raise Hold("PAIRING_REQUIRES_LOCAL_TERMINAL") from exc

    def invoke_and_recheck_failure(self, path: Path, action: str, base: str, release: Release) -> None:
        validated_before = self.report.get("pairing_validated", False)
        prior_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if validated_before else None
        self.report["pairing_validated"] = False
        try:
            self.invoke_installer(path, action, base, release)
        except Hold:
            # A failed update may have rolled back successfully. Revalidate the
            # same credential before reporting that its pairing still works.
            if validated_before:
                try:
                    config = read_config(self.config_file)
                    unchanged = hashlib.sha256(self.config_file.read_bytes()).hexdigest() == prior_sha
                    current = installed_version(self.agent)
                    if unchanged and enrollment_state(self.http, config, current) == "PAIRED":
                        self.report.update(pairing_validated=True, agent_version=current)
                except (Hold, OSError, ValueError):
                    pass
            raise

    def start_and_verify(self, expected: str, device_id: str) -> None:
        need(owned_regular(self.unit), "AGENT_SERVICE_MISSING")
        was_active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE]).returncode == 0
        started_after = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
        completed = subprocess.run(["systemctl", "--user", "start", SERVICE], capture_output=True)
        need(completed.returncode == 0, "AGENT_SERVICE_START_FAILED")
        # A connection command deliberately starts the service; it never enables
        # login/boot autostart. Current local approval mode is preserved.
        floor = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=90) if was_active else started_after
        for _ in range(45):
            try:
                if owned_regular(self.status):
                    obj = unique_json(self.status.read_bytes())
                    last = dt.datetime.fromisoformat(str(obj.get("last_successful_heartbeat_at_utc", "")).replace("Z", "+00:00"))
                    started = dt.datetime.fromisoformat(str(obj.get("started_at_utc", "")).replace("Z", "+00:00"))
                    device_matches = obj.get("device_id", device_id) == device_id
                    if obj.get("agent_version") == expected and last >= floor and device_matches and (was_active or started >= started_after):
                        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE])
                        if active.returncode == 0:
                            return
            except (ValueError, Hold):
                pass
            time.sleep(1)
        raise Hold("FRESH_AGENT_HEARTBEAT_NOT_CONFIRMED")

    def run(self, selected_url=None) -> dict:
        need(os.geteuid() != 0, "RUN_AS_DESKTOP_USER")
        # Explicit desktop connect may be invoked through SSH with an existing
        # user bus; no new login session or global system service is created.
        runtime = Path("/run/user") / str(os.getuid())
        if runtime.is_dir():
            os.environ.setdefault("XDG_RUNTIME_DIR", str(runtime))
            if (runtime / "bus").exists():
                os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=" + str(runtime / "bus"))
        config = read_config(self.config_file)
        config_before = hashlib.sha256(self.config_file.read_bytes()).hexdigest() if config else None
        current = installed_version(self.agent)
        state = enrollment_state(self.http, config, current)
        base = origin(config["HARA_COMMANDER_URL"] if config else os.environ.get("HARA_COMMANDER_URL", "https://commander.haralabs.com.br"))
        self.report.update(initial_state=state, initial_pairing_validated=state == "PAIRED", pairing_validated=state == "PAIRED", agent_version=current,
                           commander_url=base, phase="CHECK_UPDATE")
        print("Validando a conexao e a versao assinada do Commander...", flush=True)
        release = Release(self.http, base, selected_url, current)
        action, update_after_pair = decide(state, current, release.version, release.pair_existing_supported)
        if current is not None:
            release.verify_old_agent(self.agent, current)
        if action in ("install", "pair-existing", "re-enroll"):
            self.require_terminal()
            print("Abra " + base + "/auth/login, entre na sua conta e gere um codigo de pareamento.", flush=True)
            print("Digite somente esse codigo quando o instalador solicitar. A senha fica no site.", flush=True)
        else:
            print("Maquina ja pareada; o vinculo existente sera preservado.", flush=True)
        with tempfile.TemporaryDirectory(prefix="hara-connect-") as directory:
            installer = Path(directory) / "linux.sh"
            installer.write_bytes(release.installer)
            os.chmod(installer, 0o700)
            if action:
                self.report["phase"] = "PAIRING" if action != "update" else "UPDATE"
                self.invoke_and_recheck_failure(installer, action, base, release)
            after = read_config(self.config_file)
            actual = installed_version(self.agent)
            if state == "PAIRED":
                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_before, "EXISTING_ENROLLMENT_CHANGED")
            need(enrollment_state(self.http, after, actual) == "PAIRED", "PAIRING_NOT_CONFIRMED")
            self.report.update(pairing_validated=True, agent_version=actual, device_id=after["HARA_DEVICE_ID"])
            if update_after_pair:
                self.report["phase"] = "UPDATE"
                post_pair_config_sha = hashlib.sha256(self.config_file.read_bytes()).hexdigest()
                self.invoke_and_recheck_failure(installer, "update", base, release)
                after = read_config(self.config_file)
                actual = installed_version(self.agent)
                need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == post_pair_config_sha, "POST_PAIR_ENROLLMENT_CHANGED")
                need(enrollment_state(self.http, after, actual) == "PAIRED", "POST_UPDATE_PAIRING_NOT_CONFIRMED")
                self.report.update(pairing_validated=True, agent_version=actual)
            need(actual == release.version, "AGENT_UPDATE_NOT_CONFIRMED")
            release.verify_old_agent(self.agent, actual)
            self.report["phase"] = "START_AND_VERIFY_RUNTIME"
            config_after_actions = hashlib.sha256(self.config_file.read_bytes()).hexdigest()
            self.start_and_verify(actual, after["HARA_DEVICE_ID"])
            final = read_config(self.config_file)
            need(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == config_after_actions,
                 "ENROLLMENT_CHANGED_DURING_START")
            need(enrollment_state(self.http, final, actual) == "PAIRED", "FINAL_CONNECTION_NOT_CONFIRMED")
        return {"state": "CONNECTED", "agent_version": actual, "initial_state": state,
                "action": action or "already-current", "updated_after_pair": update_after_pair,
                "commander_url": base, "device_id": after["HARA_DEVICE_ID"], "token_exposed": False}


@contextlib.contextmanager
def connection_lock():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid())))
    info = runtime.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
         "PRIVATE_USER_RUNTIME_REQUIRED")
    path = runtime / "hara-commander-connect.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
             "CONNECT_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold("CONNECTION_ALREADY_IN_PROGRESS") from exc
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description="Conectar, parear quando necessario e atualizar o HARA Commander.")
    parser.add_argument("action", nargs="?", default="connect", choices=("connect", "conectar"))
    parser.add_argument("--qa-release-url", help="Selecao QA assinada, versionada e na mesma origem; nao substitui o canal publico.")
    args = parser.parse_args()
    flow = Connect()
    try:
        with connection_lock():
            report = flow.run(args.qa_release_url)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Hold as exc:
        report = dict(flow.report)
        report.update(state="HOLD", error_code=exc.code)
        if report.get("pairing_validated") and report.get("phase") in ("CHECK_UPDATE", "UPDATE"):
            report["state"] = "PAIRING_VALID_UPDATE_HOLD"
            print("Pareamento validado; atualizacao pendente: " + exc.code, file=sys.stderr)
        else:
            print("Commander nao concluiu a conexao: " + exc.code, file=sys.stderr)
        print(json.dumps(report, sort_keys=True))
        return 2
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        # Do not copy arbitrary exception text containing request/auth data.
        print("Commander nao concluiu a conexao: CONNECT_OPERATION_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
PYHARA_COMMANDER_CONNECT_A696A233
    exit $? ;;
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
    validate_commander_origin
    previous_started="$(read_runtime_status_value started_at_utc 2>/dev/null || true)"
    UPDATE_SERVICE_WAS_ACTIVE=FALSE
    systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && UPDATE_SERVICE_WAS_ACTIVE=TRUE || true
    existing_transport="$(read_config_value HARA_COMMANDER_TRANSPORT_MODE 2>/dev/null || true)"
    if [ "$existing_transport" = "LOCAL_TUNNEL" ]; then
      install_tunnel_client
    fi
    [ -f "$AGENT" ] && [ ! -L "$AGENT" ] || { echo 'AGENT_UPDATE_PREIMAGE_REQUIRED' >&2; exit 7; }
    backup="$AGENT.rollback"
    rm -f "$backup"
    cp -p "$AGENT" "$backup"
    previous_version="$(python3 - "$backup" <<'PYPREVIOUSVERSION'
from pathlib import Path
import re,sys
matches=re.findall(r'^AGENT_VERSION\s*=\s*"((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"\s*$',Path(sys.argv[1]).read_text(encoding="utf-8"),re.M)
if len(matches)!=1: raise SystemExit("AGENT_INSTALLED_VERSION_UNKNOWN")
print(matches[0])
PYPREVIOUSVERSION
)"
    download_agent
    if ! install_cli || ! systemctl --user daemon-reload; then
      if [ -f "$backup" ]; then cp -p "$backup" "$AGENT"; chmod 700 "$AGENT"; fi
      echo 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=AGENT_RESTORED' >&2
      exit 7
    fi
    expected_version="$(python3 "$AGENT" --version)"
    if [ "$UPDATE_SERVICE_WAS_ACTIVE" = TRUE ]; then
      restart_succeeded=FALSE
      if systemctl --user restart "$SERVICE"; then restart_succeeded=TRUE; sleep 1; fi
      if [ "$restart_succeeded" != TRUE ] || ! systemctl --user is-active --quiet "$SERVICE" || ! wait_for_agent_startup "$expected_version" "$previous_started"; then
        if [ -f "$backup" ]; then
          cp -p "$backup" "$AGENT"
          chmod 700 "$AGENT"
          rollback_previous_started="$(read_runtime_status_value started_at_utc 2>/dev/null || true)"
          if systemctl --user restart "$SERVICE"; then
            sleep 1
            if systemctl --user is-active --quiet "$SERVICE"; then
              if wait_for_agent_startup "$previous_version" "$rollback_previous_started"; then
                printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS\n' >&2
              else printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=STARTUP_ATTESTATION_FAILED\n' >&2; fi
            else printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=SERVICE_INACTIVE\n' >&2; fi
          else printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=SERVICE_RESTART_FAILED\n' >&2; fi
        fi
        echo 'HARA Commander Agent failed after update; previous agent restored when available.' >&2
        exit 7
      fi
      printf 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS\n'
    else
      # Updating a manually stopped agent must not establish a new connection.
      printf 'HARA_COMMANDER_AGENT_UPDATE_RUNTIME_ATTESTATION=SKIPPED_MANUAL_STOP\n'
    fi
    # Retain the exact preimage advertised by ROLLBACK_READY, also on success.
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
    rm -rf "$BIN_DIR" "$CONFIG_DIR"
    printf 'HARA_COMMANDER_AGENT_UNINSTALL=PASS\n'
    [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
    printf 'SERVER_DEVICE_REVOKE=%s\n' "$revoke_state"
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n'
    printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
    exit 0 ;;
  pair-existing)
    validate_pair_existing_preimage
    verify_pair_existing_agent
    PAIR_EXISTING=TRUE
    REENROLL=TRUE
    REENROLL_CONFIG_EXISTED=FALSE
    REENROLL_OLD_DEVICE_ID=""
    REENROLL_SERVICE_WAS_ACTIVE=FALSE
    ;;
  re-enroll|reenroll)
    [ -f "$CONFIG_FILE" ] || { echo 'DEVICE_NOT_ENROLLED: use install.' >&2; exit 5; }
    [ -f "$AGENT" ] || { echo 'AGENT_BINARY_MISSING' >&2; exit 6; }
    [ -f "$UNIT" ] || { echo 'AGENT_SERVICE_NOT_INSTALLED' >&2; exit 6; }
    configured_url="$(read_config_value HARA_COMMANDER_URL 2>/dev/null || true)"
    [ -z "$configured_url" ] || BASE_URL="${configured_url%/}"
    validate_commander_origin
    verify_existing_enrollment_rejected
    REENROLL=TRUE
    REENROLL_OLD_DEVICE_ID="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
    systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && REENROLL_SERVICE_WAS_ACTIVE=TRUE || true
    ;;
  install) ;;
  *) echo 'Usage: linux.sh [connect|conectar|pair|install|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall]' >&2; exit 64 ;;
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

if [ "$REENROLL" != TRUE ]; then
  for owned in "$CLI" "$CONFIG_DIR" "$BIN_DIR" "$UNIT"; do
    if [ -e "$owned" ] || [ -L "$owned" ]; then
      echo 'HARA_COMMANDER_FIRST_INSTALL_PATH_CONFLICT' >&2
      exit 8
    fi
  done
fi
precheck_release_before_pairing
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
  "agent_version": "0.3.60",
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
  # Install rollback before any post-enrollment filesystem operation.
  trap cleanup_failed_reenroll EXIT
  if [ "$REENROLL_CONFIG_EXISTED" = TRUE ]; then
    REENROLL_BACKUP="$(mktemp "$CONFIG_DIR/.device.env.reenroll.XXXXXX")"
    cp -p "$CONFIG_FILE" "$REENROLL_BACKUP"
    chmod 600 "$REENROLL_BACKUP"
  fi
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
if [ "$REENROLL" = TRUE ]; then
  CONFIG_PENDING="$(mktemp "$CONFIG_DIR/.device.env.pending.XXXXXX")"
else
  CONFIG_PENDING="$CONFIG_FILE"
fi
cat >"$CONFIG_PENDING" <<EOF
HARA_COMMANDER_URL=$BASE_URL
HARA_DEVICE_ID=$DEVICE_ID
HARA_DEVICE_TOKEN=$DEVICE_TOKEN
HARA_DEVICE_ARCH=$ARCH
HARA_COMMANDER_APPROVAL_MODE=$APPROVAL_MODE
HARA_COMMANDER_TRANSPORT_MODE=$TRANSPORT_MODE
HARA_COMMANDER_TUNNEL_AUTOSTART=$TUNNEL_AUTOSTART
EOF
chmod 600 "$CONFIG_PENDING"
if [ "$REENROLL" = TRUE ]; then
  mv -f "$CONFIG_PENDING" "$CONFIG_FILE"
  REENROLL_CONFIG_REPLACED=TRUE
  CONFIG_PENDING=""
fi

if [ "$REENROLL" = TRUE ]; then
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
  [ -z "$REENROLL_BACKUP" ] || rm -f "$REENROLL_BACKUP"
  REENROLL_BACKUP=""
  unset DEVICE_TOKEN
  if [ "$PAIR_EXISTING" = TRUE ]; then printf 'HARA_COMMANDER_DEVICE_PAIR_EXISTING=PASS\n'; else printf 'HARA_COMMANDER_DEVICE_REENROLL=PASS\n'; fi
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
