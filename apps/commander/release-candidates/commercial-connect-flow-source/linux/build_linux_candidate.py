#!/usr/bin/env python3
"""Build unsigned embedded-connect installer proposal; preserve signed .56."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORIGINAL_CANDIDATES = (
    ROOT.parents[1] / "linux.sh",
    ROOT.parents[1] / "commercial-0.3.56-source" / "install" / "linux.sh",
)
ORIGINAL = next((path for path in ORIGINAL_CANDIDATES if path.is_file()), None)
if ORIGINAL is None:
    raise SystemExit("SIGNED_SOURCE_NOT_FOUND")
source = ORIGINAL.read_text()
if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != "a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f":
    raise SystemExit("SIGNED_SOURCE_PIN_MISMATCH")
original = source


def replace(old, new):
    global source
    if source.count(old) != 1:
        raise SystemExit("SOURCE_ANCHOR_NOT_UNIQUE: " + old[:60])
    source = source.replace(old, new, 1)


replace('set -euo pipefail\n', 'set -euo pipefail\n# SOURCE-ONLY CANDIDATE: requires new signed release before distribution.\n# HARA_COMMANDER_PAIR_EXISTING=1\n')
replace('REENROLL_CONFIG_REPLACED=FALSE\n', 'REENROLL_CONFIG_REPLACED=FALSE\nREENROLL_CONFIG_EXISTED=TRUE\nPAIR_EXISTING=FALSE\n')
replace('  python3 - "$1" <<\'PYMANIFEST\'\n', '  python3 - "$1" "${2:-0.3.56}" <<\'PYMANIFEST\'\n')
replace('if version!="0.3.56": raise SystemExit("INSTALLER_AGENT_VERSION_MISMATCH")', 'if version!=sys.argv[2]: raise SystemExit("INSTALLER_AGENT_VERSION_MISMATCH")')

old = '''    if [ "${REENROLL_CONFIG_REPLACED:-FALSE}" = TRUE ] && [ -n "${REENROLL_BACKUP:-}" ] && [ -f "$REENROLL_BACKUP" ]; then
      mv -f "$REENROLL_BACKUP" "$CONFIG_FILE"
      chmod 600 "$CONFIG_FILE"
      if [ "${REENROLL_SERVICE_WAS_ACTIVE:-FALSE}" = TRUE ]; then
        systemctl --user restart "$SERVICE" >/dev/null 2>&1 || true
      else
        systemctl --user stop "$SERVICE" >/dev/null 2>&1 || true
      fi
    fi'''
new = '''    if [ "${REENROLL_CONFIG_REPLACED:-FALSE}" = TRUE ]; then
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
    fi'''
replace(old, new)

# The owning user may attach a previously installed, inactive managed Agent.
# No path moves/deletions are used to make an existing tree resemble a clean one.
validation = r'''validate_pair_existing_preimage() {
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

'''
replace('case "$ACTION" in\n  status)', validation + 'case "$ACTION" in\n  status)')
replace('  re-enroll|reenroll)\n', '''  pair-existing)
    validate_pair_existing_preimage
    verify_pair_existing_agent
    PAIR_EXISTING=TRUE
    REENROLL=TRUE
    REENROLL_CONFIG_EXISTED=FALSE
    REENROLL_OLD_DEVICE_ID=""
    REENROLL_SERVICE_WAS_ACTIVE=FALSE
    ;;
  re-enroll|reenroll)
''')
replace("Usage: linux.sh [install|re-enroll|preflight|status|doctor|support|update|uninstall]", "Usage: linux.sh [install|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall]")
old = '''if [ "$REENROLL" = TRUE ]; then
  REENROLL_BACKUP="$(mktemp "$CONFIG_DIR/.device.env.reenroll.XXXXXX")"
  cp -p "$CONFIG_FILE" "$REENROLL_BACKUP"
  chmod 600 "$REENROLL_BACKUP"
  trap cleanup_failed_reenroll EXIT
else'''
new = '''if [ "$REENROLL" = TRUE ]; then
  # Install rollback before any post-enrollment filesystem operation.
  trap cleanup_failed_reenroll EXIT
  if [ "$REENROLL_CONFIG_EXISTED" = TRUE ]; then
    REENROLL_BACKUP="$(mktemp "$CONFIG_DIR/.device.env.reenroll.XXXXXX")"
    cp -p "$CONFIG_FILE" "$REENROLL_BACKUP"
    chmod 600 "$REENROLL_BACKUP"
  fi
else'''
replace(old, new)

# Atomic config publish makes the precise ownership of a failed new config clear.
old = '''cat >"$CONFIG_FILE" <<EOF
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
  REENROLL_CONFIG_REPLACED=TRUE'''
new = '''if [ "$REENROLL" = TRUE ]; then
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

if [ "$REENROLL" = TRUE ]; then'''
replace(old, new)
replace('  [ -z "${REENROLL_BACKUP:-}" ] || rm -f "$REENROLL_BACKUP"\n', '  [ -z "${REENROLL_BACKUP:-}" ] || rm -f "$REENROLL_BACKUP"\n  [ -z "${CONFIG_PENDING:-}" ] || rm -f "$CONFIG_PENDING"\n')
replace('''    printf 'HARA_COMMANDER_FAILED_REENROLL_ROLLBACK=%s\\n' "$revoke_state" >&2
''', '''    if [ "$revoke_state" != PASS ]; then
      record_pending_revoke || printf 'HARA_COMMANDER_PENDING_REVOKE_RECOVERY_SAVED=FALSE\\n' >&2
    fi
    printf 'HARA_COMMANDER_FAILED_REENROLL_ROLLBACK=%s\\n' "$revoke_state" >&2
''')
replace("  printf 'HARA_COMMANDER_DEVICE_REENROLL=PASS\\n'\n", "  if [ \"$PAIR_EXISTING\" = TRUE ]; then printf 'HARA_COMMANDER_DEVICE_PAIR_EXISTING=PASS\\n'; else printf 'HARA_COMMANDER_DEVICE_REENROLL=PASS\\n'; fi\n")
replace('  rm -f "$REENROLL_BACKUP"\n  REENROLL_BACKUP=""\n', '  [ -z "$REENROLL_BACKUP" ] || rm -f "$REENROLL_BACKUP"\n  REENROLL_BACKUP=""\n')

# The next release keeps the existing four-file manifest: the controller is
# covered by install/linux.sh's signature rather than becoming an unsigned asset.
# Explicit child actions remain explicit and never recurse through connect.
controller_bytes = (ROOT / "commander_connect.py").read_bytes()
controller_sha = hashlib.sha256(controller_bytes).hexdigest()
if controller_sha != "a696a233e81b1b89b536fd4097af7b571762c953e54266cba49349308db74c1d":
    raise SystemExit("FROZEN_CONTROLLER_PIN_MISMATCH")
controller = controller_bytes.decode("utf-8")
delimiter = "PYHARA_COMMANDER_CONNECT_A696A233"
if delimiter in controller.splitlines() or not controller.endswith("\n"):
    raise SystemExit("EMBEDDED_CONTROLLER_DELIMITER_OR_NEWLINE_INVALID")
replace('ACTION="${1:-install}"\n', 'ACTION="${1:-connect}"\n')
dispatch = '  connect|conectar)\n    python3 - connect <<\'' + delimiter + "'\n" + controller + delimiter + '\n    exit $? ;;\n'
replace('case "$ACTION" in\n  status)', 'case "$ACTION" in\n' + dispatch + '  status)')
replace('Usage: linux.sh [install|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall]',
        'Usage: linux.sh [connect|conectar|install|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall]')

candidate = ROOT / "linux.source-only-candidate.sh"
candidate.write_text(source)
(ROOT / "linux.source-only.patch").write_text("".join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile="signed-0.3.56-linux.sh", tofile=candidate.name)))
print(json.dumps({"original_sha256": hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(), "embedded_controller_sha256": controller_sha, "default_action": "connect", "native": "NOT_RUN", "signed": False}))
