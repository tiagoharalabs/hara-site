#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${HARA_COMMANDER_URL:-https://commander.haralabs.com.br}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hara-commander"
BIN_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/hara-commander"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_FILE="$CONFIG_DIR/device.env"
AGENT="$BIN_DIR/hara-commander-agent"
UNIT="$SYSTEMD_DIR/hara-commander-agent.service"
SERVICE="hara-commander-agent.service"
STATUS_FILE="$BIN_DIR/runtime-status.json"
ACTION="${1:-install}"
ACTION="${ACTION#--}"

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

download_agent() {
  mkdir -p "$BIN_DIR"
  local tmp manifest expected_sha expected_version actual_sha actual_version
  tmp="$(mktemp "$BIN_DIR/.hara-commander-agent.XXXXXX")"
  manifest="$(mktemp "$BIN_DIR/.hara-commander-manifest.XXXXXX")"
  if ! curl -fsS --max-time 30 "$BASE_URL/agent/linux.py" -o "$tmp"; then
    rm -f "$tmp" "$manifest"; return 1
  fi
  if ! curl -fsS --max-time 30 "$BASE_URL/release/agent-manifest.json" -o "$manifest"; then
    rm -f "$tmp" "$manifest"; echo 'AGENT_RELEASE_MANIFEST_DOWNLOAD_FAILED' >&2; return 1
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
  ) || { rm -f "$tmp" "$manifest"; echo 'AGENT_RELEASE_MANIFEST_INVALID' >&2; return 1; }
  expected_version="${META[0]}"
  expected_sha="${META[1]}"
  actual_sha="$(python3 - "$tmp" <<'PYHASH'
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())
PYHASH
)"
  [ "$actual_sha" = "$expected_sha" ] || { rm -f "$tmp" "$manifest"; echo 'AGENT_SHA256_MISMATCH' >&2; return 1; }
  chmod 700 "$tmp"
  actual_version="$(python3 "$tmp" --version 2>/dev/null || true)"
  [ "$actual_version" = "$expected_version" ] || { rm -f "$tmp" "$manifest"; echo 'AGENT_VERSION_MANIFEST_MISMATCH' >&2; return 1; }
  if ! python3 "$tmp" --self-test >/dev/null; then
    rm -f "$tmp" "$manifest"; echo 'AGENT_UPDATE_VALIDATION_FAILED' >&2; return 1
  fi
  rm -f "$manifest"
  mv -f "$tmp" "$AGENT"
  chmod 700 "$AGENT"
  printf 'HARA_COMMANDER_AGENT_INTEGRITY=PASS\n'
}

status_agent() {
  local device_id="" enrolled=FALSE active=FALSE enabled=FALSE version="unknown"
  device_id="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
  [ -n "$device_id" ] && enrolled=TRUE
  systemctl --user is-active --quiet "$SERVICE" 2>/dev/null && active=TRUE || true
  systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null && enabled=TRUE || true
  [ ! -f "$AGENT" ] || version="$(python3 "$AGENT" --version 2>/dev/null || echo unknown)"
  printf 'HARA_COMMANDER_DEVICE_ENROLLED=%s\n' "$enrolled"
  printf 'HARA_COMMANDER_AGENT_ACTIVE=%s\n' "$active"
  printf 'HARA_COMMANDER_AGENT_ENABLED=%s\n' "$enabled"
  printf 'HARA_COMMANDER_AGENT_VERSION=%s\n' "$version"
  [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
  printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
}

remote_device_action() {
  local action="$1"
  python3 - "$CONFIG_FILE" "$action" <<'PYREMOTE'
import json,sys,urllib.request,urllib.error
from pathlib import Path
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
    payload={"device_id":device_id,"architecture":arch,"agent_version":"0.3.3"}
elif action=="revoke":
    endpoint="/api/device/revoke-self"
    payload={}
else:
    raise SystemExit(2)
req=urllib.request.Request(
    base+endpoint, data=json.dumps(payload,separators=(",",":")).encode(), method="POST",
    headers={"content-type":"application/json","accept":"application/json","authorization":"Bearer "+token},
)
try:
    with urllib.request.urlopen(req,timeout=15) as response:
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
import json,sys,urllib.request
base=sys.argv[1].rstrip("/")
device_id=sys.argv[2]
token=sys.stdin.readline().rstrip("\n")
if not device_id or not token: raise SystemExit(2)
req=urllib.request.Request(
    base+"/api/device/revoke-self", data=b"{}", method="POST",
    headers={"content-type":"application/json","accept":"application/json","authorization":"Bearer "+token,"user-agent":"HARA-Commander-Installer-Rollback/0.3.3"},
)
with urllib.request.urlopen(req,timeout=15) as response:
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

preflight_agent() {
  local manifest health persistence_ready=FALSE arch
  manifest="$(mktemp)"
  health="$(mktemp)"
  trap 'rm -f "$manifest" "$health"' RETURN
  curl -fsS --max-time 15 "$BASE_URL/api/health" -o "$health" || { echo 'COMMANDER_HEALTH_UNREACHABLE' >&2; return 10; }
  curl -fsS --max-time 15 "$BASE_URL/release/agent-manifest.json" -o "$manifest" || { echo 'AGENT_RELEASE_MANIFEST_UNREACHABLE' >&2; return 11; }
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
  systemctl --user is-enabled --quiet "$SERVICE" || { echo 'AGENT_SERVICE_NOT_ENABLED' >&2; return 7; }
  systemctl --user is-active --quiet "$SERVICE" || { echo 'AGENT_SERVICE_NOT_ACTIVE' >&2; return 7; }
  python3 "$AGENT" --self-test >/dev/null || { echo 'AGENT_SELF_TEST_FAILED' >&2; return 8; }
  remote_device_action heartbeat || { echo 'COMMANDER_REMOTE_HEARTBEAT=FAIL' >&2; return 9; }
  printf 'HARA_COMMANDER_AGENT_DOCTOR=PASS\n'
  printf 'COMMANDER_REMOTE_HEARTBEAT=PASS\n'
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
    backup="$AGENT.rollback"
    rm -f "$backup"
    [ ! -f "$AGENT" ] || cp -p "$AGENT" "$backup"
    download_agent
    systemctl --user daemon-reload
    systemctl --user restart "$SERVICE"
    sleep 1
    if ! systemctl --user is-active --quiet "$SERVICE"; then
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
    rm -f "$backup"
    printf 'HARA_COMMANDER_AGENT_UPDATE=PASS\n'
    printf 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE\n'
    status_agent; exit 0 ;;
  uninstall)
    device_id="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
    revoke_state=PENDING
    if [ -f "$CONFIG_FILE" ] && remote_device_action revoke; then revoke_state=PASS; fi
    systemctl --user disable --now "$SERVICE" >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -rf "$BIN_DIR" "$CONFIG_DIR"
    printf 'HARA_COMMANDER_AGENT_UNINSTALL=PASS\n'
    [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
    printf 'SERVER_DEVICE_REVOKE=%s\n' "$revoke_state"
    [ "$revoke_state" = PASS ] || printf 'SERVER_DEVICE_REVOKE_PENDING=TRUE\n'
    printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
    exit 0 ;;
  install) ;;
  *) echo 'Usage: linux.sh [install|preflight|status|doctor|support|update|uninstall]' >&2; exit 64 ;;
esac

[ ! -f "$CONFIG_FILE" ] || { echo 'DEVICE_ALREADY_ENROLLED: use status, update, or uninstall.' >&2; exit 8; }

printf 'HARA Commander — Linux device pairing\n'
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
  "agent_version": "0.3.3",
}, separators=(",",":")))
' "$DEVICE_NAME" "$ARCH")"

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
trap cleanup_failed_install EXIT

umask 077
mkdir -p "$CONFIG_DIR" "$BIN_DIR" "$SYSTEMD_DIR"
cat >"$CONFIG_FILE" <<EOF
HARA_COMMANDER_URL=$BASE_URL
HARA_DEVICE_ID=$DEVICE_ID
HARA_DEVICE_TOKEN=$DEVICE_TOKEN
HARA_DEVICE_ARCH=$ARCH
EOF
chmod 600 "$CONFIG_FILE"

download_agent

cat >"$UNIT" <<EOF
[Unit]
Description=HARA Commander Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$AGENT
Restart=always
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=default.target
EOF
chmod 600 "$UNIT"

systemctl --user daemon-reload
systemctl --user enable --now hara-commander-agent.service

sleep 1
if ! systemctl --user is-active --quiet hara-commander-agent.service; then
  echo 'HARA Commander Agent failed to start.' >&2
  exit 4
fi

INSTALL_ENROLLED=FALSE
trap - EXIT
unset DEVICE_TOKEN
printf 'HARA_COMMANDER_DEVICE_ENROLLMENT=PASS\n'
printf 'HARA_COMMANDER_AGENT_SERVICE=ACTIVE\n'
printf 'DEVICE_ID=%s\n' "$DEVICE_ID"
printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
