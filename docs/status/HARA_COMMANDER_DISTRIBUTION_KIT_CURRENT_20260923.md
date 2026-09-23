# H.A.R.A. Commander — distribution kit current — 2026-09-23

State: **SCRIPT DISTRIBUTION HARDENED / NATIVE WINDOWS PACKAGE DEFERRED**

## Current kit

Linux:

- bootstrap installer: `/install/linux.sh`;
- Agent: `/agent/linux.py`;
- user-systemd persistence;
- status / doctor / support / update / uninstall;
- rollback-safe update;
- authenticated self-revoke.

Windows:

- bootstrap installer: `/install/windows.ps1`;
- Agent: `/agent/windows.ps1`;
- DPAPI-protected device token;
- Scheduled Task persistence;
- status / doctor / support / update / uninstall;
- rollback-safe update;
- authenticated self-revoke.

## Stable release integrity

Public release metadata:

- `/release/agent-manifest.json`;
- `/release/SHA256SUMS`.

The manifest binds stable Agent version `0.3.2` to SHA-256 and byte length for:

- `agent/linux.py`;
- `agent/windows.ps1`;
- `install/linux.sh`;
- `install/windows.ps1`.

Install/update downloads now fail closed on Agent SHA-256 mismatch or Agent-version/manifest mismatch. After server-side enrollment, bootstrap installation is transactional: if the local Agent/service/task setup fails, the installer attempts authenticated self-revocation and removes partial local state before returning the original failure.

Builder/checker:

`python3 apps/commander/scripts/build_release_manifest.py --check`

## External Windows canary position

The external Windows test is intentionally late in the sequence. It does **not** need OpenAI/ChatGPT publication to validate the customer endpoint. The canary only needs to prove:

1. native/bootstrap installer launches cleanly on a non-HARA Windows computer;
2. one-time pairing enrolls the machine;
3. the Agent establishes outbound HTTPS polling/heartbeat to Commander;
4. no inbound port, SSH or per-customer Cloudflare tunnel is created;
5. reboot/logon persistence works;
6. doctor/status work;
7. update and rollback work;
8. uninstall self-revokes and removes local state.

Only after the Linux/nucleo selected-device E2E is terminal should a native Windows EXE/MSI wrapper be finalized and sent to an external tester.

## Support contract

`support` emits `hara.commander-support-report.v1`. The report is safe to attach to a customer support case because it does not decrypt or print the device token. It contains only operational metadata such as platform, device ID, Commander URL, Agent version/SHA-256, config presence/permissions and service/task state.

Linux isolated proof:

`LINUX_SUPPORT_REPORT_SANITIZED=PASS`

Windows has the same schema contract implemented; live Windows output remains part of the later real-host canary.

## Release / compatibility policy

- stable channel is the only customer channel in V1;
- Agent semantic version is shared by Linux and Windows;
- manifest version and Agent-reported version must match before install/update;
- current stable Agent: `0.3.2`;
- update is fail-closed on manifest/hash/version mismatch;
- previous Agent is retained only as a short-lived rollback candidate during update;
- no forced update occurs merely because a newer manifest exists; update remains explicit until a later managed-update policy is approved;
- protocol expansion beyond the exact five MCP tools requires a separately reviewed compatibility gate.

## Native Windows packaging — intentionally pending

Before external distribution:

- choose EXE/MSI packaging technology;
- bind package version to the stable Agent manifest;
- embed or fetch the PowerShell bootstrap without widening privileges;
- acquire publisher code-signing identity/certificate;
- Authenticode-sign the native package;
- publish package SHA-256 in the Commander release manifest;
- verify SmartScreen/reputation behavior on a clean Windows host;
- document uninstall and support flow.

No unsigned EXE should be presented as the final customer installer.
