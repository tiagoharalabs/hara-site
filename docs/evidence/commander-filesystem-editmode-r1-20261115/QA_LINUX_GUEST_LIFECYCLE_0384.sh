#!/bin/bash
# Offline ephemeral VM only. Never use on a physical H.A.R.A. node.
set -u
LOG=/var/log/hara-commander-0384-linux-e2e-v4.log
exec >"$LOG" 2>&1
echo HARA_QA_LINUX_V4_BEGIN
echo HARA_QA_BASE_IMAGE_UNTOUCHED_OVERLAY_ONLY
echo QGA_VIRTIO_MODPROBE
modprobe virtio_console
echo QGA_MODPROBE_RC=$?
if test -e /dev/virtio-ports/org.qemu.guest_agent.0; then
  echo QGA_PORT_PRESENT
else
  echo QGA_PORT_NOT_PRESENT
fi
systemctl daemon-reload
systemctl reset-failed qemu-guest-agent.service
systemctl start qemu-guest-agent.service
qgarc=$?
echo QGA_START_RC=$qgarc
if systemctl is-active --quiet qemu-guest-agent.service;then
  echo HARA_QA_QGA_SERVICE_ACTIVE
  printf 'HARA_QA_V4_QGA_READY\n' > /dev/ttyS0 || true
else
  echo HARA_QA_QGA_SERVICE_HOLD
fi

DATA=/mnt/hara-qa-cidata
SIGNED=/mnt/hara-qa-signed
mkdir -p "$SIGNED"
if ! mountpoint -q "$SIGNED"; then
  mount -o ro /dev/disk/by-label/HARA0384QA "$SIGNED"
fi
rc=$?
if test "$rc" -ne 0; then echo HARA_QA_SIGNED_MEDIA_MOUNT_HOLD;exit 21;fi
MAN="$SIGNED/release/agent-manifest.json"
NEW="$SIGNED/agent/linux.py"
OLD="$DATA/agent-0383-linux.py"
test "$(sha256sum "$MAN" | cut -d' ' -f1)" = b0350ec8dc9f2b995742cf07df91df8ad5aaa324a9948b16753f178cef2820fe || exit 22
test "$(sha256sum "$NEW" | cut -d' ' -f1)" = 2177b4d6e049e5886a1df6a42c38ca0a1838e4e7406536882e81eaa2c8c2d509 || exit 23
test "$(sha256sum "$OLD" | cut -d' ' -f1)" = a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733 || exit 24
echo HARA_QA_SIGNED_AND_BASELINE_SHA_PASS

if ! id haraqa >/dev/null 2>&1; then echo HARA_QA_USER_NOT_AVAILABLE;exit 25;fi
runuser -u haraqa -- env HOME=/home/haraqa XDG_CONFIG_HOME=/home/haraqa/.config XDG_DATA_HOME=/home/haraqa/.local/share HARA_COMMANDER_DEFER_CONSOLE=1 bash "$SIGNED/install/linux.sh" update > /var/log/hara-commander-0384-offline-installer-update.log 2>&1
updaterc=$?
echo INSTALLER_OFFLINE_UPDATE_RC=$updaterc
if test "$updaterc" -eq 5 && grep -q 'DEVICE_NOT_ENROLLED' /var/log/hara-commander-0384-offline-installer-update.log &&
   test ! -e /home/haraqa/.local/share/hara-commander/hara-commander-agent;then
  echo HARA_QA_OFFICIAL_INSTALLER_REJECTS_UNENROLLED_PASS
else
  echo HARA_QA_OFFICIAL_INSTALLER_UNENROLLED_HOLD
fi

UID_HARAQA="$(id -u haraqa)"
echo HARA_QA_USER_ID_VALIDATED
install -d -o haraqa -g haraqa -m 0700 /home/haraqa/qa0384
install -d -o haraqa -g haraqa -m 0700 /home/haraqa/.config/systemd/user
install -o haraqa -g haraqa -m 0700 "$OLD" /home/haraqa/qa0384/agent.py
cat > /home/haraqa/.config/systemd/user/hara-qa0384.service <<'UNIT'
[Unit]
Description=H.A.R.A. Commander PRIVATE QA native user service test
[Service]
Type=oneshot
RemainAfterExit=yes
NoNewPrivileges=yes
ExecStart=/usr/bin/python3 -I -B /home/haraqa/qa0384/agent.py --self-test
[Install]
WantedBy=default.target
UNIT
chown haraqa:haraqa /home/haraqa/.config/systemd/user/hara-qa0384.service
chmod 0600 /home/haraqa/.config/systemd/user/hara-qa0384.service

systemctl start "user-runtime-dir@$UID_HARAQA.service"
runtime_rc=$?
systemctl start "user@$UID_HARAQA.service"
user_rc=$?
echo USER_MANAGER_START_RC=$user_rc
echo USER_RUNTIME_START_RC=$runtime_rc
function qa_systemctl() {
  runuser -u haraqa -- env HOME=/home/haraqa XDG_RUNTIME_DIR="/run/user/$UID_HARAQA" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$UID_HARAQA/bus" systemctl --user "$@"
}
if qa_systemctl daemon-reload && qa_systemctl start hara-qa0384.service &&
   qa_systemctl is-active --quiet hara-qa0384.service;then
  echo HARA_QA_0383_USER_SERVICE_START_PASS
  qa_systemctl stop hara-qa0384.service
  if ! qa_systemctl is-active --quiet hara-qa0384.service;then
    echo HARA_QA_0383_USER_SERVICE_STOP_PASS
  fi
  install -o haraqa -g haraqa -m 0700 "$NEW" /home/haraqa/qa0384/agent.py
  if test "$(sha256sum /home/haraqa/qa0384/agent.py | cut -d' ' -f1)" = 2177b4d6e049e5886a1df6a42c38ca0a1838e4e7406536882e81eaa2c8c2d509 &&
     qa_systemctl start hara-qa0384.service && qa_systemctl is-active --quiet hara-qa0384.service;then
    echo HARA_QA_0384_NATIVE_USER_SERVICE_START_PASS
  else
    echo HARA_QA_0384_NATIVE_USER_SERVICE_HOLD
  fi
  qa_systemctl stop hara-qa0384.service
  install -o haraqa -g haraqa -m 0700 "$OLD" /home/haraqa/qa0384/agent.py
  if test "$(sha256sum /home/haraqa/qa0384/agent.py | cut -d' ' -f1)" = a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733 &&
     qa_systemctl start hara-qa0384.service && qa_systemctl is-active --quiet hara-qa0384.service;then
    echo HARA_QA_0383_NATIVE_USER_SERVICE_ROLLBACK_PASS
  else
    echo HARA_QA_0383_NATIVE_USER_SERVICE_ROLLBACK_HOLD
  fi
  qa_systemctl stop hara-qa0384.service
  if ! qa_systemctl is-enabled --quiet hara-qa0384.service;then
    echo HARA_QA_MANUAL_SERVICE_NOT_ENABLED_PASS
  else
    echo HARA_QA_MANUAL_SERVICE_ENABLEMENT_HOLD
  fi
else
  echo HARA_QA_SYSTEMD_USER_SERVICE_HOLD
fi
echo HARA_QA_LINUX_V4_END
printf 'HARA_QA_LINUX_V4_REPORT_READY\n' > /dev/ttyS0 || true
