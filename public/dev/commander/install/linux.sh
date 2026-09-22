#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${HARA_COMMANDER_URL:-https://hara-commander-dev-v2.tiago-sartori.workers.dev}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hara-commander"
BIN_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/hara-commander"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_FILE="$CONFIG_DIR/device.env"
AGENT="$BIN_DIR/hara-commander-agent"
UNIT="$SYSTEMD_DIR/hara-commander-agent.service"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'HARA Commander requires %s.\n' "$1" >&2
    exit 2
  }
}

need curl
need python3
need systemctl

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
  "agent_version": "0.1.0",
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

cat >"$AGENT" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/hara-commander/device.env"
[ -r "$CONFIG_FILE" ] || exit 78
# shellcheck disable=SC1090
. "$CONFIG_FILE"

heartbeat() {
  local payload
  payload="$(python3 - "$HARA_DEVICE_ID" "$HARA_DEVICE_ARCH" <<'PY'
import json,sys
print(json.dumps({
  "device_id":sys.argv[1],
  "architecture":sys.argv[2],
  "agent_version":"0.1.0",
},separators=(",",":")))
PY
)"
  curl -fsS --max-time 20     -H 'content-type: application/json'     -H "authorization: Bearer $HARA_DEVICE_TOKEN"     --data "$payload"     "$HARA_COMMANDER_URL/api/device/heartbeat" >/dev/null
}

while :; do
  heartbeat || true
  sleep 30
done
EOF
chmod 700 "$AGENT"

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
