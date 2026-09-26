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
