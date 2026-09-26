# H.A.R.A. Commander Windows Acceptance CURRENT — 2026-09-26

Owner: `#240`

This file is the current machine/operator handoff for the canonical Windows 11
acceptance VM. It supersedes the earlier `PENDING_GUEST_UNLOCK` checkpoint.

## Canonical VM

```text
HOST=nucleo-a
VM=commander-win11
STATE=RUNNING
IP=192.168.122.177
W0_BASELINE=PASS
W0_DISK_SNAPSHOT=W0_CLEAN_WINDOWS11_BASELINE_20260926
SECONDARY_VM=DO_NOT_TOUCH
GAMES_2TB=DO_NOT_TOUCH
```

## Automation channel

The desktop is unlocked and the prior guest-unlock blocker is closed.

```text
QEMU_GUEST_AGENT_MSI=INSTALLED
QEMU_GUEST_AGENT_SERVICE=RUNNING
VIOSERIAL_DRIVER=w11/amd64/vioser.inf
VIOSERIAL_INSTALL=PASS
QGA_PING=PASS
LIBVIRT_AGENT_IP_READBACK=PASS
WINDOWS_AUTOMATION_CHANNEL=QGA_LIVE
```

## W1 stable Agent 0.3.7 repair

Fresh W1 execution found the public Windows installer did not parse under the
actual Windows PowerShell 5.1 runtime. The failure happened before pairing
consumption or Agent installation.

The two source causes were:

1. ambiguous PowerShell variable interpolation such as
   `"$Identity:(OI)(CI)F"`;
2. multiline startup conditions that began continuation lines with `-or`.

Repair authority:

```text
PR=#278
MERGE_SHA=f9d446ac13682dc47c03a3cff0dbc5603fb3a279
PROVENANCE_CI=SUCCESS
COMMANDER_SCALE_V2_CI=SUCCESS
WINDOWS_POWERSHELL_5_1_PARSE_ERRORS=0
FINAL_WINDOWS_INSTALLER_SHA256=74296f03b70f7b381fc87459ee77f0960cf9a11fc8ebc586ee4bd2a3efc3e166
PUBLIC_AGENT_0_3_7_SHA256=79f36ba30c579eec57f9eaf140b973a7a3d111661523f60389b565fcd6bca45e
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
```

DEV-only promotion used for the acceptance retest:

```text
DEV_VERSION=fd192855-f986-477a-b207-1402d96a1241
DEV_HEALTH=PASS
DEV_SERVED_WINDOWS_INSTALLER_SHA256=74296f03b70f7b381fc87459ee77f0960cf9a11fc8ebc586ee4bd2a3efc3e166
PROD_MUTATION=FALSE
```

## W1 preflight

The non-mutating preflight was run from the actual logged-in Windows user
session, not from the reduced SYSTEM/QGA environment.

```text
PLATFORM=WINDOWS
ARCHITECTURE=X64
COMMANDER_ENV=DEV
COMMANDER_HEALTH=TRUE
RELEASE_MANIFEST=TRUE
STABLE_AGENT_VERSION=0.3.7
PERSISTENCE=SCHEDULED_TASK
PERSISTENCE_READY=TRUE
MUTATION_PERFORMED=FALSE
```

## Current gate

```text
INSTALLER_PARSE=PASS
PAIRING_PROMPT=REACHED
PAIRING_CONSUMED=FALSE
PAIRING_SECRET_EXPOSED=FALSE
W1_SECURE_PAIRING_ENTRY=HUMAN_INPUT_REQUIRED
W1_TERMINAL=FALSE
```

The automation environment must not read, type or export the pairing secret.
After the operator supplies the one secure pairing entry inside the Windows VM,
#240 may continue with task/config custody, heartbeat, online/offline, selected
device behavior, RC acceptance and the remaining W2-W7 gates.

## Boundaries

```text
EVENT_V2_IMPLEMENTATION_MUTATION=FALSE
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
PROD_MUTATION=FALSE
PROD_CUTOVER=DENY
```

The separate Durable Object live-duration/cost gate remains blocked on a
dedicated Cloudflare Account Analytics Read token. Wrangler OAuth reuse remains
denied.
