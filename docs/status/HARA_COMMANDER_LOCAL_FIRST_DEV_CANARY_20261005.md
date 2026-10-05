# H.A.R.A. Commander — Local-first Activity DEV canary

Date: 2026-10-05
DEV Worker: fcd75f09-9078-4c19-875e-7b1f85a0ee80
Agent: 0.3.33
Migration: 0022_device_local_activity_snapshot.sql

## Source / regression

PASS:

- TenantQuota O(1) storage efficiency
- local Activity store validator
- portal Activity contract
- Agent release manifest
- migration replay 0001 -> 0022
- full source preprod readiness

## Isolated live canary

Host: nucleo-a
Environment: isolated DEV XDG root under /tmp_hara
PROD Agent service: preserved and active throughout canary

The canary used the normal DEV enrollment contract. Pairing/device tokens were
not printed.

Live local proof:

- Agent version 0.3.33
- Local MCP call PASS
- process.run local call PASS
- operations.sqlite3 created
- database mode 0600
- terminal events persisted locally
- process action_summary persisted locally
- local raw payload_json column ABSENT
- local raw result_json column ABSENT
- heartbeat status PASS

## Cloud snapshot proof

The existing heartbeat carried the aggregate snapshot. No additional per-call
cloud request was introduced.

First readback:

- snapshot size: 1,358 bytes
- 24h calls: 1
- 7d calls: 1
- detail_location: LOCAL_DEVICE
- customer_content_synced: false

After a local process.run:

- snapshot size: 1,493 bytes
- 24h calls: 2
- Agent version: 0.3.33

Structural JSON-tree inspection found:

- forbidden command/payload/result/arguments/stdout/stderr/action_summary/
  receipt-detail keys: 0

Therefore the local command/action detail remained on the customer machine
while only aggregate metadata reached D1.

## Rollout compatibility

The portal path is hybrid:

- devices with local snapshots are excluded from the legacy call-history scan;
- devices without snapshots continue through the cloud fallback;
- summaries are merged without double counting;
- when all active devices have snapshots, the cloud call-history scan is
  skipped completely.

This permits progressive fleet rollout without hiding activity from older
devices.

## Cleanup

PASS:

- DEV canary device deleted
- pairing fixture deleted
- isolated /tmp_hara secret/config root deleted
- PROD nucleo-a Agent service remained active

## Promotion recommendation

The local-first Activity slice is eligible for progressive PROD rollout:

1. apply additive migration 0022;
2. deploy Worker/assets;
3. update Linux devices one at a time to Agent 0.3.33;
4. verify activity_summary heartbeat per device;
5. observe snapshot coverage increase and legacy cloud scan shrink;
6. keep Windows on cloud fallback until Windows local-store parity is shipped.
