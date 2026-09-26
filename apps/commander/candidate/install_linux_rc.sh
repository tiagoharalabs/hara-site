#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-status}"
ACTION="${ACTION#--}"

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
COMMANDER_CONFIG_DIR="$CONFIG_HOME/hara-commander"
DEVICE_CONFIG="$COMMANDER_CONFIG_DIR/device.env"
RC_ENV="$COMMANDER_CONFIG_DIR/rc.env"
SYSTEMD_DIR="$CONFIG_HOME/systemd/user"
STABLE_UNIT="$SYSTEMD_DIR/hara-commander-agent.service"
RC_UNIT="$SYSTEMD_DIR/hara-commander-agent-rc.service"
STABLE_SERVICE="hara-commander-agent.service"
RC_SERVICE="hara-commander-agent-rc.service"
RC_ROOT="$DATA_HOME/hara-commander-rc"
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SOURCE_COMMANDER="$SOURCE_ROOT/apps/commander"

die() {
  printf '%s\n' "$1" >&2
  exit 2
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "RC_REQUIREMENT_MISSING:$1"
}

need python3
need systemctl
need install

if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

secure_regular_file() {
  local path="$1"
  [ -f "$path" ] || die "RC_REQUIRED_FILE_MISSING:$path"
  [ ! -L "$path" ] || die "RC_SYMLINK_DENIED:$path"
  if [ "$(id -u)" -ne 0 ]; then
    [ "$(stat -c '%u' "$path")" = "$(id -u)" ] || die "RC_FILE_OWNER_INVALID:$path"
  fi
  local mode
  mode="$(stat -c '%a' "$path")"
  case "$mode" in
    600|400) ;;
    *) die "RC_FILE_MODE_INVALID:$path:$mode" ;;
  esac
}

read_device_id() {
  python3 - "$DEVICE_CONFIG" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith("HARA_DEVICE_ID="):
        value=raw.split("=",1)[1].strip()
        if not value:
            raise SystemExit(2)
        print(value)
        raise SystemExit(0)
raise SystemExit(2)
PY
}

read_mode() {
  if [ ! -f "$RC_ENV" ]; then
    printf 'POLL_V1\n'
    return
  fi
  python3 - "$RC_ENV" <<'PY'
from pathlib import Path
import sys
value="POLL_V1"
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if raw.startswith("HARA_DEVICE_TRANSPORT_MODE="):
        value=raw.split("=",1)[1].strip().upper()
if value not in {"POLL_V1","EVENT_V2"}:
    raise SystemExit(2)
print(value)
PY
}

write_mode() {
  local mode="$1"
  case "$mode" in
    POLL_V1|EVENT_V2) ;;
    *) die "RC_TRANSPORT_MODE_INVALID" ;;
  esac
  umask 077
  mkdir -p "$COMMANDER_CONFIG_DIR"
  local tmp
  tmp="$(mktemp "$COMMANDER_CONFIG_DIR/.rc.env.XXXXXX")"
  printf 'HARA_DEVICE_TRANSPORT_MODE=%s\n' "$mode" >"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$RC_ENV"
}

validate_source() {
  local rel
  for rel in     public/agent/linux.py     candidate/linux_agent_rc.py     candidate/poll_v1_customer_loop.py     experimental/event_v2_agent_loop.py     experimental/event_v2_customer_agent.py     experimental/event_v2_websocket.py
  do
    [ -f "$SOURCE_COMMANDER/$rel" ] || die "RC_SOURCE_MISSING:$rel"
  done
  python3 "$SOURCE_COMMANDER/candidate/linux_agent_rc.py" --self-test >/dev/null
  python3 "$SOURCE_COMMANDER/candidate/poll_v1_customer_loop.py" --self-test >/dev/null
  python3 "$SOURCE_COMMANDER/experimental/event_v2_agent_loop.py" --self-test >/dev/null
  python3 "$SOURCE_COMMANDER/experimental/event_v2_customer_agent.py" --self-test >/dev/null
  python3 "$SOURCE_COMMANDER/experimental/event_v2_websocket.py" --self-test >/dev/null
}

validate_existing_identity() {
  secure_regular_file "$DEVICE_CONFIG"
  local device_id
  device_id="$(read_device_id)" || die "RC_DEVICE_ID_MISSING"
  [ -n "$device_id" ] || die "RC_DEVICE_ID_MISSING"
  grep -q '^HARA_DEVICE_TOKEN=' "$DEVICE_CONFIG" || die "RC_DEVICE_TOKEN_MISSING"
  grep -q '^HARA_COMMANDER_URL=' "$DEVICE_CONFIG" || die "RC_COMMANDER_URL_MISSING"
}

install_source_tree() {
  validate_source
  validate_existing_identity

  if systemctl --user is-active --quiet "$RC_SERVICE"; then
    die "RC_INSTALL_WHILE_ACTIVE_DENIED"
  fi

  mkdir -p     "$RC_ROOT/apps/commander/public/agent"     "$RC_ROOT/apps/commander/candidate"     "$RC_ROOT/apps/commander/experimental"     "$SYSTEMD_DIR"

  install -m 700 "$SOURCE_COMMANDER/public/agent/linux.py"     "$RC_ROOT/apps/commander/public/agent/linux.py"
  install -m 700 "$SOURCE_COMMANDER/candidate/linux_agent_rc.py"     "$RC_ROOT/apps/commander/candidate/linux_agent_rc.py"
  install -m 700 "$SOURCE_COMMANDER/candidate/poll_v1_customer_loop.py"     "$RC_ROOT/apps/commander/candidate/poll_v1_customer_loop.py"
  install -m 700 "$SOURCE_COMMANDER/experimental/event_v2_agent_loop.py"     "$RC_ROOT/apps/commander/experimental/event_v2_agent_loop.py"
  install -m 700 "$SOURCE_COMMANDER/experimental/event_v2_customer_agent.py"     "$RC_ROOT/apps/commander/experimental/event_v2_customer_agent.py"
  install -m 700 "$SOURCE_COMMANDER/experimental/event_v2_websocket.py"     "$RC_ROOT/apps/commander/experimental/event_v2_websocket.py"

  if [ ! -f "$RC_ENV" ]; then
    write_mode POLL_V1
  else
    secure_regular_file "$RC_ENV"
    read_mode >/dev/null || die "RC_ENV_INVALID"
  fi

  cat >"$RC_UNIT" <<EOF
[Unit]
Description=HARA Commander Agent RC
After=network-online.target
Wants=network-online.target
Conflicts=hara-commander-agent.service

[Service]
Type=simple
Environment="XDG_CONFIG_HOME=$CONFIG_HOME"
Environment="XDG_DATA_HOME=$DATA_HOME"
EnvironmentFile=-$RC_ENV
ExecStart=/usr/bin/python3 "$RC_ROOT/apps/commander/candidate/linux_agent_rc.py"
Restart=always
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=default.target
EOF
  chmod 600 "$RC_UNIT"
  systemctl --user daemon-reload

  # Source install is deliberately inert. Activation is a separate action.
  systemctl --user disable "$RC_SERVICE" >/dev/null 2>&1 || true

  printf 'COMMANDER_AGENT_RC_INSTALL=PASS\n'
  printf 'COMMANDER_AGENT_RC_INSTALLED_MODE=%s\n' "$(read_mode)"
  printf 'COMMANDER_AGENT_RC_AUTO_START=FALSE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_REPAIRING=FALSE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE\n'
}

wait_active() {
  local service="$1"
  local attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if systemctl --user is-active --quiet "$service"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

attest_active() {
  local service="$1"
  local check
  for check in 1 2 3; do
    systemctl --user is-active --quiet "$service" || return 1
    sleep 1
  done
  return 0
}

rollback_to_stable() {
  systemctl --user stop "$RC_SERVICE" >/dev/null 2>&1 || true
  write_mode POLL_V1
  systemctl --user start "$STABLE_SERVICE"
  if ! wait_active "$STABLE_SERVICE"; then
    die "RC_ROLLBACK_STABLE_START_FAILED"
  fi
  printf 'COMMANDER_AGENT_RC_ROLLBACK=PASS\n'
  printf 'COMMANDER_AGENT_STABLE_SERVICE=ACTIVE\n'
  printf 'COMMANDER_AGENT_RC_SERVICE=INACTIVE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_REPAIRING=FALSE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE\n'
}

activate_event_v2() {
  validate_existing_identity
  [ -f "$RC_UNIT" ] || die "RC_NOT_INSTALLED"
  [ -f "$RC_ROOT/apps/commander/candidate/linux_agent_rc.py" ] || die "RC_NOT_INSTALLED"

  write_mode EVENT_V2
  systemctl --user daemon-reload

  # Never permit the stable and RC agents to use the same device token at once.
  systemctl --user stop "$STABLE_SERVICE"

  if ! systemctl --user start "$RC_SERVICE"; then
    rollback_to_stable
    die "RC_EVENT_V2_START_FAILED_ROLLED_BACK"
  fi
  if ! wait_active "$RC_SERVICE" || ! attest_active "$RC_SERVICE"; then
    rollback_to_stable
    die "RC_EVENT_V2_ATTESTATION_FAILED_ROLLED_BACK"
  fi
  if systemctl --user is-active --quiet "$STABLE_SERVICE"; then
    rollback_to_stable
    die "RC_DUAL_AGENT_DENIED_ROLLED_BACK"
  fi

  printf 'COMMANDER_AGENT_RC_EVENT_V2_ACTIVATION=PASS\n'
  printf 'COMMANDER_AGENT_RC_TRANSPORT=EVENT_V2\n'
  printf 'COMMANDER_AGENT_RC_SERVICE=ACTIVE\n'
  printf 'COMMANDER_AGENT_STABLE_SERVICE=INACTIVE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_REPAIRING=FALSE\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE\n'
}

status() {
  local stable=INACTIVE rc=INACTIVE installed=FALSE mode=POLL_V1
  [ -f "$RC_ROOT/apps/commander/candidate/linux_agent_rc.py" ] && installed=TRUE
  systemctl --user is-active --quiet "$STABLE_SERVICE" && stable=ACTIVE || true
  systemctl --user is-active --quiet "$RC_SERVICE" && rc=ACTIVE || true
  mode="$(read_mode 2>/dev/null || printf 'INVALID\n')"

  printf 'COMMANDER_AGENT_RC_INSTALLED=%s\n' "$installed"
  printf 'COMMANDER_AGENT_RC_TRANSPORT=%s\n' "$mode"
  printf 'COMMANDER_AGENT_STABLE_SERVICE=%s\n' "$stable"
  printf 'COMMANDER_AGENT_RC_SERVICE=%s\n' "$rc"
  printf 'COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE\n'
}

self_check() {
  validate_source
  printf 'COMMANDER_AGENT_RC_INSTALLER_SOURCE=PASS\n'
  printf 'COMMANDER_AGENT_RC_DEFAULT_TRANSPORT=POLL_V1\n'
  printf 'COMMANDER_AGENT_RC_AUTO_START=FALSE\n'
  printf 'COMMANDER_AGENT_RC_REPAIRING=ABSENT\n'
  printf 'COMMANDER_AGENT_RC_DUAL_AGENT=DENY\n'
  printf 'COMMANDER_AGENT_RC_ROLLBACK=SOURCE_READY\n'
  printf 'COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE\n'
}

case "$ACTION" in
  check) self_check ;;
  install) install_source_tree ;;
  activate-event-v2) activate_event_v2 ;;
  rollback) rollback_to_stable ;;
  status) status ;;
  *) die "RC_ACTION_INVALID:$ACTION" ;;
esac
