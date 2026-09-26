# Commander Agent Event V2 productization contract

Owner: #163

This source defines the transition from the proven Agent 0.3.7 polling baseline
to a release-candidate transport selector without changing the stable public
release yet.

## Transport law

```text
STABLE_PUBLIC_AGENT=0.3.7
STABLE_DEFAULT_TRANSPORT=POLL_V1
RC_DEFAULT_TRANSPORT=POLL_V1
EVENT_V2=EXPLICIT_OPT_IN_ONLY
AUTO_TRANSPORT_SELECTION=DENY
UNKNOWN_TRANSPORT=DENY
PROD_CUTOVER=DENY
```

The release-candidate launcher is:

`apps/commander/candidate/linux_agent_rc.py`

It deliberately lives outside `apps/commander/public` and outside the stable
release manifest.

## Rollback

Event V2 rollback does not require reinstalling or re-pairing a device.

A candidate installation must retain the same device identity/credential and
switch the launcher back to:

```text
HARA_DEVICE_TRANSPORT_MODE=POLL_V1
```

The stable V1 heartbeat/poll loop remains the rollback authority until Event V2
release acceptance is terminal.

## Promotion gates

Before any public release manifest or installer selects Event V2:

1. DEV Event V2 canary remains PASS.
2. Normal DO wake remains PASS.
3. Five-tool / receipt / quota parity remains PASS.
4. Disconnect grace/reconnect-storm guards remain PASS.
5. Per-device active queue backpressure remains bounded.
6. Candidate launcher defaults to POLL_V1 with unknown modes denied.
7. Installer upgrade preserves device identity/token and rollback.
8. Windows transport has equivalent source/runtime proof or remains explicitly
   unsupported for the first Event V2 release.
9. PROD Worker/D1/Agent cutover requires a separate explicit gate.

## Customer privacy

The transport selector changes transport only. It does not widen the five-tool
surface and does not authorize customer-content telemetry.

```text
CUSTOMER_SERVICES_PROXY=FALSE
CUSTOMER_CONTENT_COLLECTION=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
FIVE_TOOL_SURFACE=UNCHANGED
ARBITRARY_SHELL=DENY
```


## Linux RC install and rollback

The first release-candidate productization lane is Linux only.

Source:

`apps/commander/candidate/install_linux_rc.sh`

The RC installer is deliberately separate from the public 0.3.7 installer and
release manifest.

```text
LINUX_RC=SOURCE_READY
WINDOWS_EVENT_V2_RC=HOLD
PUBLIC_INSTALLER_EVENT_V2=ABSENT
PUBLIC_MANIFEST_EVENT_V2=ABSENT
RC_INSTALL_AUTO_START=FALSE
RC_DEFAULT_TRANSPORT=POLL_V1
RC_EVENT_V2_ACTIVATION=EXPLICIT_ONLY
RC_REPAIRING=FALSE
RC_DEVICE_ENV_REWRITE=FALSE
RC_DUAL_AGENT=DENY
RC_FAILED_START_ROLLBACK=STABLE_0_3_7
```

The candidate reuses the already-enrolled `device.env`. It does not call the
pairing/enrollment endpoint and does not create a new device identity.

Installation only materializes the candidate source and an inactive user-systemd
unit. Event V2 activation is a separate explicit action.

Activation order:

1. validate existing device config;
2. write only the candidate transport selector;
3. stop the stable service;
4. start and attest the RC service;
5. deny any simultaneous stable+RC state;
6. on start/attestation failure, stop RC and restore stable 0.3.7.

A reboot during RC evaluation remains conservative because the candidate unit is
not enabled by source installation; the proven stable service remains the
persistent public baseline until a later release gate explicitly changes that
law.

### Windows boundary

Windows remains on the proven public baseline until an equivalent Event V2
transport, installer, rollback and live canary exist.

```text
WINDOWS_STABLE_BASELINE=PRESERVE
WINDOWS_EVENT_V2_CUTOVER=DENY
CROSS_PLATFORM_PARITY_CLAIM=FALSE
```
