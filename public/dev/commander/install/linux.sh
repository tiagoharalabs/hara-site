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
  "agent_version": "0.2.0",
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
#!/usr/bin/env python3
import json
import os
import platform
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hara-commander/device.env"
AGENT_VERSION = "0.2.0"

def load_config():
    data = {}
    for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            data[key] = value
    required = ("HARA_COMMANDER_URL", "HARA_DEVICE_ID", "HARA_DEVICE_TOKEN", "HARA_DEVICE_ARCH")
    if not all(data.get(key) for key in required):
        raise RuntimeError("DEVICE_CONFIG_INVALID")
    return data

def post_json(url, token, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": "Bearer " + token,
            "user-agent": "HARA-Commander-Agent/" + AGENT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if response.status == 204:
                return None
            raw = response.read()
            return json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            return None
        raise

def health_result(config):
    return {
        "ok": True,
        "agent_version": AGENT_VERSION,
        "device_id": config["HARA_DEVICE_ID"],
        "platform": "LINUX",
        "architecture": config["HARA_DEVICE_ARCH"],
        "hostname": platform.node(),
        "tunnel_mode": "OUTBOUND_RELAY",
    }

def complete(config, call, state, result, error_code=None):
    body = {
        "call_id": call["call_id"],
        "state": state,
        "result": result,
    }
    if error_code:
        body["error_code"] = error_code
    post_json(
        config["HARA_COMMANDER_URL"] + "/api/device/calls/complete",
        config["HARA_DEVICE_TOKEN"],
        body,
    )

def execute_call(config, call):
    tool_id = str(call.get("tool_id") or "")
    if tool_id == "hara.health":
        complete(config, call, "COMPLETED", health_result(config))
        return
    complete(
        config,
        call,
        "FAILED",
        {"tool_id": tool_id},
        "LOCAL_TOOL_BRIDGE_NOT_IMPLEMENTED",
    )

def main():
    config = load_config()
    last_heartbeat = 0.0
    while True:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= 30:
                post_json(
                    config["HARA_COMMANDER_URL"] + "/api/device/heartbeat",
                    config["HARA_DEVICE_TOKEN"],
                    {
                        "device_id": config["HARA_DEVICE_ID"],
                        "architecture": config["HARA_DEVICE_ARCH"],
                        "agent_version": AGENT_VERSION,
                    },
                )
                last_heartbeat = now

            call = post_json(
                config["HARA_COMMANDER_URL"] + "/api/device/calls/next",
                config["HARA_DEVICE_TOKEN"],
                {},
            )
            if call:
                execute_call(config, call)
        except Exception:
            pass
        time.sleep(2)

if __name__ == "__main__":
    main()
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
