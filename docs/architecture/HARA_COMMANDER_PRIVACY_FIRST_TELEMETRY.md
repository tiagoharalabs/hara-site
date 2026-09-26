# H.A.R.A. Commander — Privacy-first telemetry and cost budget

Owner: #167  
Device-scale sibling: #163

## Purpose

Collect enough evidence to decide when Commander needs optimization or scale-out without turning observability into a new cost center or a customer-surveillance system.

The target remains:

- 100 users: establish baseline;
- 1,000 users: validate trend and cost model;
- 10,000 registered humans / 2,000 peak active humans: engineering envelope;
- 20,000 devices: separate Event V2 envelope owned by #163.

## Existing H.A.R.A. collection plane

Reuse what already exists:

```text
COMMANDER / CLOUDFLARE
  -> built-in Worker/D1/DO metrics for total traffic/cost signals
  -> optional sampled, sanitized application telemetry only where native metrics are insufficient

STORAGE
  -> ZITADEL /debug/metrics
  -> PostgreSQL/node metrics
  -> hara-prometheus LTS

SERVICES
  -> hara-telemetry-collector
  -> hara-telemetry-projection-v3
  -> cost/capacity normalization

OBSERVER
  -> hara-otel-gateway
  -> diagnostic traces when explicitly enabled
```

No new telemetry SaaS is required for the first 10k-user target.

## Ownership

### Cloudflare / Commander edge

Use built-in platform metrics as the 100% source for:

- Worker request volume;
- Worker invocation errors;
- subrequests;
- D1 read/write/query activity;
- Durable Object activity;
- execution/resource pressure.

Do not duplicate these into custom per-request events.

### Commander application telemetry

Only emit custom telemetry for facts that native platform metrics cannot express, such as:

- login started / succeeded / failed by safe error class;
- session resolve latency bucket;
- quota reserve / commit / release result class;
- Event V2 connect / reconnect / fallback state;
- product route class.

Never emit:

- passwords;
- OAuth, device, session or pairing tokens;
- Authorization/Cookie headers;
- command payloads;
- customer file contents;
- precise location;
- browser fingerprint;
- e-mail/name in metric dimensions.

User/device identifiers must not become Prometheus labels.

### Services

`hara-telemetry-collector` is the canonical NOC collection/normalization point for external product metrics and local fleet telemetry.

It should poll aggregated provider metrics at bounded intervals rather than ingesting every customer request.

For the customer plane:

```text
HARA_SERVICES_INLINE_CUSTOMER_PROXY=FALSE
HARA_SERVICES_NOC_AGGREGATION=TRUE
CUSTOMER_CONTENT_TO_SERVICES=FALSE
```

Services receives health/capacity/cost facts, not routine customer payloads.

The HARA-owned internal MCP/OpenAI engineering path is a separate operator-controlled plane and may be monitored more deeply.

### Storage

Prometheus LTS stores low-cardinality operational time series.

ZITADEL already exposes a Prometheus-compatible `/debug/metrics` endpoint. Scrape it internally only.

### Observer

OTel is for diagnostics and sampled traces, not as the default high-volume billing ledger.

## Cost-aware sampling policy

Built-in provider metrics remain unsampled for total counts.

Optional custom success telemetry is budgeted at 0.25% by default.

With the human-scale planning envelope:

```text
10,000 registered humans
2,000 peak active
6 authenticated requests / active user / minute
~= 200 portal requests/s
~= 17.28M portal requests/day

0.25% custom success sample
~= 43,200 custom events/day
```

This leaves headroom below a 100k/day custom-event planning budget.

Errors and security events must use aggregate counters and bounded diagnostic sampling rather than unconditional high-volume logs.

## Rollout stages

### Stage A — 0 to 100 users

- built-in Worker/D1/DO metrics;
- ZITADEL/PostgreSQL/node metrics;
- no full per-request application logging;
- establish real cost/request and latency baselines.

### Stage B — 100 to 1,000 users

- enable bounded custom application sampling if needed;
- validate session/D1 trend;
- validate Storage login CPU/latency;
- compare real traffic with the capacity model.

### Stage C — 1,000 to 10,000 users

- keep native metrics as primary volume truth;
- use sampled app telemetry for latency/error classes;
- activate C/D Identity replica only if measured thresholds justify it;
- split database/session planes only if evidence shows saturation.

## Privacy rules

Telemetry collection must have a documented operational/security/capacity purpose, minimum necessary fields, bounded retention and a user-facing privacy description.

The default customer contract is content-blind:

```text
CUSTOMER_CONTENT_COLLECTION=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
CUSTOMER_OPERATIONAL_METADATA_ONLY=TRUE
CUSTOMER_TRAFFIC_INSPECTION_DEFAULT=FALSE
```

Use native Cloudflare aggregate metrics first. Application telemetry exists only
to fill operational gaps such as connection/reconnect, delivery latency,
error-class and quota/cost signals.

Operational telemetry and optional marketing analytics are separate systems and must not share an implicit legal/consent model.

## Scale decision

Do not buy hardware or a new managed identity service because registered-user count crossed a round number.

Scale decisions are driven by measured:

- p95/p99 portal latency;
- D1 overload/queue symptoms;
- query duration;
- login latency;
- Storage CPU/RAM/PostgreSQL connection pressure;
- Event V2 reconnect pressure;
- error rate;
- actual provider cost per active user.

```text
EXISTING_FLEET_BEFORE_NEW_SPEND=TRUE
CUSTOM_TELEMETRY_IS_SAMPLED=TRUE
CUSTOMER_CONTENT_IN_TELEMETRY=FALSE
CUSTOMER_ACCESS_SEAT_COST=FALSE
```


## NOC flow

```text
Cloudflare Workers / D1 / Durable Objects
        |
        | aggregate provider metrics
        v
HARA Services telemetry collector
        |
        +--> capacity
        +--> cost
        +--> error-rate
        +--> latency
        +--> reconnect pressure
        +--> alerting

Storage / ZITADEL / PostgreSQL
        |
        +--> Identity health metrics
        |
        v
HARA Services
```

The NOC must be capable of answering "is the service healthy and where is it
hot?" without needing to know "what did the customer ask or execute?".


## Learning plane — derived behavior, not customer content

Commander may improve from aggregate usage only when the signal is generated
from a strict allowlist and cannot become a covert content channel.

The first Event V2 transient source contract allows exactly:

```text
schema
tool_id
tool_family
outcome
latency_bucket
result_bytes_bucket
platform
agent_version
transport_mode
privileged_attempt
customer_content_collected
```

The Agent emits:

```text
privileged_attempt=false
customer_content_collected=false
```

and the DeviceChannel validates the exact field set before accepting the signal.

Explicitly forbidden in learning telemetry:

```text
prompt
arguments
argv
path
filename
command
stdout
stderr
raw result
raw payload
Authorization
Cookie
device token
customer identifiers as metric labels
```

This creates a product-learning flywheel from safe facts such as tool-family
adoption, success/error classes, latency buckets, result-size buckets, platform
and Agent version without learning what the customer asked, read or produced.

For the managed hosted MCP relay, request/result content still exists
transiently in process memory while being forwarded. Therefore:

```text
MANAGED_RELAY_CONTENT_IN_TRANSIT=TRUE
MANAGED_RELAY_CONTENT_DURABLE_COLLECTION=FALSE
CUSTOMER_CONTENT_IN_LEARNING_PLANE=FALSE
RAW_DIAGNOSTICS_DEFAULT=FALSE
RAW_DIAGNOSTICS_EXPLICIT_OPT_IN_REQUIRED=TRUE
```

A future private transport may remove H.A.R.A. Cloud from the content data path,
but that is a separate transport mode and must not be confused with the
privacy properties of the standard managed MCP relay.
