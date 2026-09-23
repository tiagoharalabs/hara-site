# H.A.R.A. Commander — customer support workflow V1 — 2026-09-23

## Scope

Customer-side Agent triage without shell access to the customer computer and without exposing the device token.

## Host preflight before pairing

Linux:

```bash
curl -fsS https://commander.haralabs.com.br/install/linux.sh -o /tmp/hara-commander-linux.sh
bash /tmp/hara-commander-linux.sh preflight
```

Windows PowerShell:

```powershell
Invoke-WebRequest https://commander.haralabs.com.br/install/windows.ps1 -OutFile $env:TEMP\hara-commander-windows.ps1
& $env:TEMP\hara-commander-windows.ps1 -Action preflight
```

Preflight is non-mutating, consumes no pairing token and must report `mutation_performed=false`. It validates Commander health, release-manifest reachability/version and the local persistence mechanism.

## First-line collection

Linux:

```bash
curl -fsS https://commander.haralabs.com.br/install/linux.sh -o /tmp/hara-commander-linux.sh
bash /tmp/hara-commander-linux.sh support
```

Windows PowerShell:

```powershell
Invoke-WebRequest https://commander.haralabs.com.br/install/windows.ps1 -OutFile $env:TEMP\hara-commander-windows.ps1
& $env:TEMP\hara-commander-windows.ps1 -Action support
```

The returned JSON schema is `hara.commander-support-report.v1`.

## Safe fields

Expected fields include platform, device ID, architecture, Commander URL, Agent version, Agent SHA-256, config presence, and service/task state. The report exposes only a boolean indicating whether a device token exists.

It must always contain:

`"device_token_exposed": false`

It must never contain the device token, pairing token, OAuth secret, Cloudflare token or Product Plane token.

## Escalation sequence

1. `preflight` — before pairing; validates host readiness without mutation.
2. `support` — offline/sanitized state snapshot.
3. `status` — concise local lifecycle state.
4. `doctor` — local self-test plus authenticated Commander heartbeat.
5. `update` — explicit stable-channel update with manifest/SHA/version verification and rollback.
6. `uninstall` — server-side self-revoke followed by local cleanup.

Do not request SSH, RDP, inbound port forwarding or a per-customer Cloudflare Tunnel as part of standard Commander support.

## Common states

- config absent: device is not enrolled locally;
- Agent absent: local installation incomplete;
- service/task absent or stopped: lifecycle problem;
- Agent hash/version mismatch: do not bypass integrity validation;
- doctor local PASS + remote heartbeat FAIL: investigate internet/DNS/Commander availability before modifying the customer host;
- uninstall reports `SERVER_DEVICE_REVOKE_PENDING=TRUE`: local cleanup completed but server revocation should be reconciled from the portal/support plane.

## Privacy boundary

Support artifacts are metadata-only. No generic filesystem capture, process dump, browser history, personal files, arbitrary logs or shell transcript is collected by this V1 report.
