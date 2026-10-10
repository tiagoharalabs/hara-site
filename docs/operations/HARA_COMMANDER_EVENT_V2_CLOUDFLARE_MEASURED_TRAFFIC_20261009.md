# H.A.R.A. Commander — measured Cloudflare Event V2 traffic improvement

Proof captured on 2026-10-09 (America/Sao_Paulo). Read-only Cloudflare GraphQL Analytics and Cloudflare D1 PROD. No authenticated customer payloads, device tokens, OAuth secrets or command text were collected.

## Current production state

- Official customer ChatGPT H.A.R.A. Commander MCP: responding; signed `nucleo-a` Agent v0.3.44 uses `EVENT_V2` and server-side Durable Object WebSocket hibernation.
- Authenticated WebSocket still requires a valid device token and PROD is restricted to Founder `nucleo-a`. Other production hosts remain on signed 0.3.41 `OUTBOUND_RELAY` / polling; no fleet-wide cutover has been authorized by test evidence yet.
- Source-level Event V2 loop uses no periodic HTTP `/api/device/calls/next` calls while idle, only a bounded initial queue reconciliation and per-event drain; RFC6455 protocol keepalives do not make HTTP queue requests.
- On this readback, local systemd v2 active/enabled, `NRestarts=0`, local guard showed repeated `EVENT_V2_GUARD_HEALTH=PASS`. Full host reboot was not performed.

## Primary measured comparison — workload-matched quiet windows

| Read-only source metric | Before Event V2 | After Event V2 | Net change |
|---|---:|---:|---:|
| Window UTC | 2026-10-10 00:20–01:00 | 2026-10-10 02:05–02:45 | Both 40 minutes |
| Window in São Paulo | 09/10 21:20–22:00 | 09/10 23:05–23:45 | Both same local date |
| Production D1 `commander_device_calls` created | 4 | 4 | **Same count** |
| Cloudflare zone HTTP requests to `/api/device/calls/next` | **1,756** | **1,392** | **−364 (−20.73%)** |
| Cloudflare `hara-commander` Worker requests | **2,066** | **1,658** | **−408 (−19.75%)** |
| Worker errors | 0 | 0 | No change |
| Worker subrequests | 12 | 19 | +7; different mix |
| HTTP adaptive `avg.sampleInterval` | 1 | 1 | **Neither queue count was sampled** |

**Do not claim that the entire 20.73% reduction is caused by the one Núcleo A switch.** These are authentic zone/Worker *aggregate* counters shared by other registered devices, web and OAuth requests; matched operation *count* does not guarantee identical timing, call types, network conditions or other devices' health. The combined evidence is consistent with the intended reduction in idle queue polling, but individual-device attribution still requires isolated telemetry or a controlled multi-hour comparison.

Cloudflare GraphQL query paths:
- Account scope `workersInvocationsAdaptive`, `scriptName="hara-commander"`; total `sum.requests`, `sum.errors` and `sum.subrequests`
- Zone scope `httpRequestsAdaptiveGroups`, exact `clientRequestPath="/api/device/calls/next"`; `count`, `avg.sampleInterval`
- D1 PROD read-only `SELECT COUNT(*)` in identical UTC windows (4/4) — **not billable customer-usage data**
- Cloudflare GraphQL API token obtained transiently via authenticated Wrangler on Services, handled in memory only and never written/printed.

Auditable script:
`apps/commander/scripts/commander_prod_cf_efficiency_probe.py`

Sanitized JSON evidence:
`docs/status/HARA_COMMANDER_CF_EVENT_V2_MATCHED_ACTIVITY_MEASUREMENT_20261009.json`

Canonical invocation from Services:

```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 apps/commander/scripts/commander_prod_cf_efficiency_probe.py --check
python3 apps/commander/scripts/commander_prod_cf_efficiency_probe.py \
  --before-start 2026-10-10T00:20:00Z \
  --after-start 2026-10-10T02:05:00Z --minutes 40
```

The probe is read-only, checks UTC windows and source path scope, requires non-overlapping complete windows, rejects invalid output paths, does not emit OAuth tokens and labels the result `attributable_to_nucleo_only=false`, `actual_billing_cost_verified=false`.

## Excluded comparison — workload confounding

The initially queried windows 01:10–01:50 UTC versus 02:05–02:45 UTC had **37 vs 4** commercial operations. Their `/api/device/calls/next` aggregate 2,484 vs 1,392 and Worker total 2,841 vs 1,658 must **not** be represented as a controlled Event V2 effect because traffic/workload differed substantially. We selected the quieter windows with equal operation counts instead.

## Economics and limits

1. A Cloudflare Worker invocation is not inherently a separately billed H.A.R.A. Labs governed tool call. `/api/device/calls/next` polls are Agent infrastructure traffic; they are not deducted from a customer's monthly tool quota.
2. Worker invocations, Durable Object requests/messages, billed duration and D1 operations can have different included plan allocations and billing rates. **No actual invoice or DO billed-duration reduction was measured** in this session.
3. Hibernation is eligible in `DeviceChannel` because the Worker uses `this.ctx.acceptWebSocket(server)` and attachment serialization; the Cloudflare documentation confirms duration charges do not accrue during hibernation. Actual duration per-object remains a separate telemetry gate.
4. The new 0.3.44 on a single Founder device does not mean the rest of the fleet has left `OUTBOUND_RELAY`. Before a public launch, qualify tenant Free 10,000 monthly quota at the actual edge boundary, independent customer pairing/denial, signed Windows Agent, a separate per-device signed Linux release and a controlled rollout.
5. Repeat with multiple equal quiet windows and a 24-hour observation once available, normalizing active-device counts and command mix. Do not extrapolate one pair of 40-minute samples into a definitive savings in BRL.

### References

- https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/
- https://developers.cloudflare.com/analytics/graphql-api/sampling/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/

**Measured gate:** `PROD_EVENT_V2_AGGREGATE_IDLE_TRAFFIC_REDUCTION=OBSERVED_20_73_PERCENT_FOR_MATCHED_40MIN_WINDOWS`; **not** `VERIFIED_CUSTOMER_INVOICE_SAVINGS`.
