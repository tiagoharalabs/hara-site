# H.A.R.A. Commander Scale V2 — Human 10k target

Owner: #167  
Device-scale sibling: #163

## Target

Commander must be able to grow to **10,000 registered human users** without requiring one Cloudflare Access seat per customer and without making device growth multiply human Identity load.

Engineering envelope:

```text
REGISTERED_HUMANS=10_000
PEAK_ACTIVE_HUMANS=2_000
PORTAL_REQUESTS_PER_ACTIVE_USER_PER_MINUTE=6
LOGIN_BURST_TARGET=100_PER_SECOND
DEVICE_TARGET=20_000
DEVICE_SCALE_OWNER=#163
```

This is a bounded product target, not a claim that all registered users are continuously active.

## Non-negotiable separation

Human identity:

```text
browser
  -> HARA Identity / ZITADEL
  -> OIDC Authorization Code + PKCE
  -> Commander portal session
```

Device identity:

```text
Agent
  -> device credential
  -> Event V2 / device API
```

A device MUST NOT perform human OIDC login. Cloudflare Access MUST NOT become the customer identity store or a per-customer seat requirement.

## Bottlenecks found in the current design

### 1. PRODUCT_DB authenticated-request hot path

`resolvePortalSession()` performs one indexed D1 read/join for every authenticated portal request. At the 10k envelope, the model intentionally assumes 2,000 active humans and 6 portal requests/minute, or roughly 200 session reads/s.

This remains acceptable as an initial architecture target, but it is now explicitly measured. If measured load approaches the single-database budget, the next step is a session-plane abstraction or read scaling; not ad-hoc query duplication.

### 2. Repeated session resolution on initial dashboard

Before the second #167 package, a normal authenticated dashboard entry performed separate `session`, `dashboard` and `devices` requests. Each path independently resolved the same portal session.

The optimized remote dashboard bootstrap now performs one authenticated request:

```text
GET /api/portal/bootstrap
  -> resolve session once
  -> dashboard data
  -> device list
```

The old split endpoints remain available for targeted refresh and as a browser fallback. Session expiry and revocation are still checked against D1 on the bootstrap request.

```text
initial dashboard session resolutions
before=3
after=1
reduction=66.7%
```

### 3. Non-authoritative session liveness writes

Before #167, each active session could update `last_seen_at_utc` every 5 minutes. This field does not control the fixed 8h session expiry and does not control revocation.

#167 changes the telemetry touch interval to 30 minutes:

```text
2,000 peak active users
old: ~6.67 last_seen writes/s
new: ~1.11 last_seen writes/s
reduction: ~83.3%
```

Expiry and revocation semantics are unchanged.

### 4. Passive browser request budget

The portal has no background network polling loop. Route changes can still cause repeated product/device reads, so #167 now applies short in-memory browser TTLs to passive navigation:

```text
dashboard/product TTL = 30s
devices TTL = 15s
passive dashboard cap = 2 refreshes/minute/browser
passive devices cap = 4 refreshes/minute/browser
combined passive cap = 6 refreshes/minute/browser
```

User-initiated device refreshes bypass the cache. Device selection/revocation also force a fresh device read after mutation.

These browser caches are presentation accelerators only. They do not authorize a command, reserve quota, validate a device credential or revoke a session. Server-side authority remains unchanged.

### 5. Retention cleanup in login hot path

Before #167, every login start ran:
- expired OIDC transaction cleanup;
- terminal portal-session cleanup.

At a synthetic 100 login/s burst, that could add up to 200 maintenance operations/s exactly when login traffic is highest.

#167 moves this best-effort hygiene to an hourly Worker scheduled event. Retention remains bounded in batches of 100; authorization never depended on cleanup succeeding.

### 6. OIDC discovery/JWKS origin amplification

Before #167:
- login start fetched OIDC discovery;
- callback fetched discovery again;
- ID-token verification fetched JWKS.

This scaled origin traffic roughly with login attempts.

#167 introduces a 5-minute in-isolate cache for public discovery/JWKS metadata. JWKS lookup force-refreshes once when an unknown `kid` is observed, so signing-key rotation does not wait for cache expiry.

The cache is an accelerator only; issuer, endpoint, algorithm, audience, nonce, expiry and signature checks remain authoritative.

### 7. TenantQuota hot-tenant boundary

Quota is currently one Durable Object per tenant. This scales horizontally across many tenants, but a single very large tenant can become a per-object hotspot.

Do not shard quota pre-emptively. Before a redesign, measure at least:

```text
10k humans / 10k tenants
10k humans / 1k tenants
10k humans / 100 tenants
10k humans / 1 tenant
```

If one-tenant saturation is demonstrated, introduce a governed quota-shard contract while preserving idempotency and total tenant quota authority.

### 8. PRODUCT_DB decomposition seam

The current D1 database contains product identity, sessions, devices and calls. For the 10k target, premature physical sharding is not required, but code and migrations must not assume that a single database is the permanent architecture.

Future decomposition, only when measured evidence requires it:

```text
PRODUCT CORE
  tenants / users / plans / entitlements / identity bindings

SESSION PLANE
  portal sessions / revocation / retention

DEVICE-CALL PLANE
  devices / pairing / calls

QUOTA PLANE
  Durable Objects, tenant authority
```

A future split must preserve exact tenant identity, session revocation, receipt binding and quota semantics.

## 10k cost envelope — pricing snapshot 2026-09-25

This is a planning upper bound for the **human portal only**, not a prediction of normal customer behavior and not inclusive of the #163 device plane.

Using the intentionally aggressive UI caps already enforced in source:

```text
peak active humans = 2,000
active window = 8h/day
passive product reads = max 2/min/browser
passive device reads = max 4/min/browser
combined dynamic portal requests = max 200/s
monthly dynamic portal requests at that continuous stress = 172.8M
```

Cloudflare Workers Standard currently includes 10M requests/month and charges $0.30 per additional million. Under this deliberately pessimistic human-portal stress envelope, request overage is approximately **$48.84/month**, or **$53.84 including the $5 Workers subscription**, before CPU charges. Real normal usage should be materially lower because the cap assumes every one of the 2,000 active users continually drives the UI at the TTL ceiling for eight hours every day.

Current source:
https://developers.cloudflare.com/workers/platform/pricing/

For D1, the current Workers Paid allowance is 25B rows read/month and 50M rows written/month. The exact billable rows must be taken from D1 analytics; the local model uses a conservative logical approximation:

```text
172.8M session resolutions/month
x 3 logical authority rows (session + user + tenant)
= 518.4M logical rows/month
= ~2.1% of the 25B included read allowance

10x read-scan safety multiplier
= 5.184B
= ~20.7% of included read allowance

session liveness writes + every registered user logging in daily
with 6 writes/login headroom
= ~2.76M modeled writes/month
= ~5.5% of the 50M included write allowance
```

Current source:
https://developers.cloudflare.com/d1/platform/pricing/

The repository model is `apps/commander/scripts/commander_human_10k_cost_model.py`. Pricing constants are a dated snapshot and MUST be refreshed before a commercial pricing decision.

## 10k indexed session proof

The Scale V2 CI creates a 10,000-session SQLite dataset using the canonical Commander schema and proves that the current session-resolution join starts from the primary-key/indexed `session_hash` lookup and then reaches indexed user/tenant primary keys.

This does not substitute for D1 production latency/load testing, but it prevents a schema regression from silently turning session resolution into a 10k-row scan.

## Hot-tenant quota boundary

The current consumer product auto-provision path creates a distinct tenant for each new production identity, so the normal 10k individual-user case naturally spreads quota coordination across many `TenantQuota` Durable Objects.

A future enterprise/team tenant is the adversarial case. The stress model assumes all 2,000 peak-active humans share one tenant and each can sustain one governed invoke per minute:

```text
quota status from product UI = ~66.7 req/s
reserve + terminal transition for invokes = ~66.7 req/s
single hot tenant total = ~133.3 req/s
```

Cloudflare documents a ~1,000 req/s soft limit for an individual Durable Object and roughly 200–500 req/s for complex operations. The 10k target therefore does **not** justify quota sharding now, but a large-team launch MUST load-test the real quota implementation before onboarding a tenant expected to approach this envelope.

Current sources:
https://developers.cloudflare.com/durable-objects/reference/faq/
https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/

### Sharding policy

Do not shard D1 or TenantQuota merely because 10,000 accounts exist.

A split requires measured evidence such as:
- sustained per-tenant quota traffic approaching the complex-operation envelope;
- overload responses;
- unacceptable p95/p99 latency;
- D1 rows-read/written analytics materially approaching the paid-plan allowance;
- database-size or query-latency evidence.

Until then, indexes, bounded client traffic, Event V2 and per-device/per-tenant Durable Object partitioning are cheaper and simpler than premature physical sharding.

## HARA Identity / Storage boundary

HARA Identity is self-hosted and remains independent from device count. The Storage host is the primary Identity host today. Scale pressure should be measured in human login bursts and PostgreSQL/ZITADEL latency, not in number of Agents.

The first HA step, if ever needed, is another stateless ZITADEL replica plus a governed database/backup plan; it is not migration to per-user Cloudflare Access.

## Cost rules

```text
CLOUDFLARE_ACCESS_CUSTOMER_SEATS=FALSE
DEVICE_OIDC_LOGIN=FALSE
IDLE_DEVICE_POLLING_EVENT_V2=FALSE
LOGIN_RETENTION_CLEANUP_HOT_PATH=FALSE
OIDC_PUBLIC_METADATA_FETCH_LOGIN_LINEAR=FALSE
PREMATURE_DB_SHARDING=FALSE
```

## Acceptance for the 10k target

- deterministic 1k/10k capacity model passes;
- 2k-active / 200-session-read/s stress envelope remains explicit and is now grounded by browser TTL caps;
- session telemetry writes reduced >=80% from the old 5-minute cadence;
- retention cleanup is absent from login hot path;
- public OIDC metadata fetches are bounded by short cache entries;
- JWKS key rotation gets one forced refresh on unknown `kid`;
- device growth remains separated from human login growth;
- #163 continues to own 20k-device transport scale;
- no PROD deployment is implied by source hardening.
