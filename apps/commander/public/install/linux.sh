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
ACTION="${1:-install}"
ACTION="${ACTION#--}"

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
  local tmp
  tmp="$(mktemp "$BIN_DIR/.hara-commander-agent.XXXXXX")"
  if ! curl -fsS --max-time 30 "$BASE_URL/agent/linux.py" -o "$tmp"; then
    rm -f "$tmp"; return 1
  fi
  chmod 700 "$tmp"
  if ! python3 "$tmp" --self-test >/dev/null; then
    rm -f "$tmp"; echo 'AGENT_UPDATE_VALIDATION_FAILED' >&2; return 1
  fi
  mv -f "$tmp" "$AGENT"
  chmod 700 "$AGENT"
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

case "$ACTION" in
  status)
    status_agent; exit 0 ;;
  update)
    [ -f "$CONFIG_FILE" ] || { echo 'DEVICE_NOT_ENROLLED' >&2; exit 5; }
    [ -f "$UNIT" ] || { echo 'AGENT_SERVICE_NOT_INSTALLED' >&2; exit 6; }
    configured_url="$(read_config_value HARA_COMMANDER_URL 2>/dev/null || true)"
    [ -z "$configured_url" ] || BASE_URL="${configured_url%/}"
    download_agent
    systemctl --user daemon-reload
    systemctl --user restart "$SERVICE"
    sleep 1
    systemctl --user is-active --quiet "$SERVICE" || { echo 'HARA Commander Agent failed after update.' >&2; exit 7; }
    printf 'HARA_COMMANDER_AGENT_UPDATE=PASS\n'
    status_agent; exit 0 ;;
  uninstall)
    device_id="$(read_config_value HARA_DEVICE_ID 2>/dev/null || true)"
    systemctl --user disable --now "$SERVICE" >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -rf "$BIN_DIR" "$CONFIG_DIR"
    printf 'HARA_COMMANDER_AGENT_UNINSTALL=PASS\n'
    [ -z "$device_id" ] || printf 'DEVICE_ID=%s\n' "$device_id"
    printf 'SERVER_DEVICE_REVOKE_REQUIRED=TRUE\n'
    printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
    exit 0 ;;
  install) ;;
  *) echo 'Usage: linux.sh [install|status|update|uninstall]' >&2; exit 64 ;;
esac

[ ! -f "$CONFIG_FILE" ] || { echo 'DEVICE_ALREADY_ENROLLED: use status, update, or uninstall.' >&2; exit 8; }

printf 'HARA Commander — Linux device pairing\n'
printf 'Pairing token: '
IFS= read -r -s PAIRING_TOKEN </dev/tty
printf '\n'
[ -n "$PAIRING_TOKEN" ] || { echo 'Pairing token cannot be empty.' >&2; exit 3; }

DEVICE_NAME="${HOSTNAME:-$(hostname 2>/dev/null || echo linux-device)}"
ARCH="$(uname -m)"

PAYLOAD="$(python3 - "$PAIRING_TOKEN" "$DEVICE_NAME" "$ARCH" <<'PY'
import json,sys
print(json.dumps({
  "pairing_token": sys.argv[1],
  "device_name": sys.argv[2],
  "platform": "LINUX",
  "architecture": sys.argv[3],
  "agent_version": "0.3.1",
}, separators=(",",":")))
PY
)"

RESPONSE="$(curl -fsS --max-time 30   -H 'content-type: application/json'   -H 'accept: application/json'   --data "$PAYLOAD"   "$BASE_URL/api/device/enroll")"

readarray -t VALUES < <(python3 - "$RESPONSE" <<'PY'
import json,sys
obj=json.loads(sys.argv[1])
for key in ("device_id","device_token"):
    value=obj.get(key)
    if not isinstance(value,str) or not value:
        raise SystemExit("DEVICE_ENROLLMENT_RESPONSE_INVALID")
    print(value)
PY
)

DEVICE_ID="${VALUES[0]}"
DEVICE_TOKEN="${VALUES[1]}"
unset PAIRING_TOKEN RESPONSE PAYLOAD VALUES

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

printf 'HARA_COMMANDER_DEVICE_ENROLLMENT=PASS\n'
printf 'HARA_COMMANDER_AGENT_SERVICE=ACTIVE\n'
printf 'DEVICE_ID=%s\n' "$DEVICE_ID"
printf 'DEVICE_TOKEN_EXPOSED=FALSE\n'
