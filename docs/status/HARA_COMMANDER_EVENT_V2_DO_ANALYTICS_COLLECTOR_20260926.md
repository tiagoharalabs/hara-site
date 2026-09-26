# Commander Event V2 — Durable Objects analytics collector

Date: 2026-09-26
Owner: #163
Environment: DEV only

## Purpose

The collector closes the remaining observability gap around Durable Object
request volume, compute-related metrics and storage without copying or exposing
the existing Wrangler OAuth credential.

Cloudflare documents Durable Object metrics through the GraphQL Analytics API.
The relevant datasets are:

```text
durableObjectsInvocationsAdaptiveGroups
durableObjectsPeriodicGroups
durableObjectsStorageGroups
durableObjectsSubrequestsAdaptiveGroups
```

The collector introspects the live schema before constructing measurements.
## DEV scope

```text
ACCOUNT_ID=c8631a3ac0ac5a043af08903b8308227
DEVICE_CHANNEL_NAMESPACE=acc93b344b4a42218a4a3267f88e16ac
TENANT_QUOTA_NAMESPACE=5592b173171943ecb93d0f8182e44ef8
PROD_QUERY=DENY
```

Namespace IDs came from the deployed Worker version readback and are not
credentials.

The probe validates all account/namespace IDs as 32 hexadecimal characters and
refuses any account other than the known DEV account.

## Authentication boundary

Cloudflare recommends scoped API tokens for GraphQL Analytics. Required token
permission for this probe:

```text
Account / Account Analytics / Read
```

The token must be provided through an explicit file owned by the current user
with no group/other permissions. Symlinks are denied when the platform supports
`O_NOFOLLOW`.
The collector intentionally does not read:

```text
~/.config/.wrangler/
default.toml
CLOUDFLARE_API_TOKEN environment variables
Global API Key
```

The existing Wrangler OAuth credential therefore remains under Wrangler
custody.

## Privacy contract

Measurements request aggregate nodes only:

```text
count
sum
max
quantiles
```

No `dimensions` block is requested, and no customer prompt, payload, result,
path, command, stdout/stderr or receipt body is queried or emitted.

The collector filters each query to one of the two known DEV namespace IDs.
## Schema drift / time-window handling

Cloudflare GraphQL has a dynamic schema. The probe:

1. introspects the `Account` type;
2. requires all four Durable Object datasets;
3. introspects each dataset filter and result type;
4. selects only known aggregate metrics that exist;
5. fails closed when namespace or time filters are unavailable.

The output records the effective time-filter granularity:

```text
datetime
hour
date
```

This avoids presenting a date-level aggregate as if it were a precise
15-minute measurement.

## Current gate

```text
COLLECTOR_SOURCE=PASS
COLLECTOR_SELF_CHECK=PASS
TOKEN_OUTPUT=ABSENT
WRANGLER_OAUTH_REUSE=DENY
LIVE_GRAPHQL_MEASUREMENT=PENDING_EXPLICIT_READ_ONLY_TOKEN
PROD_CUTOVER=DENY
```
## Usage after credential provisioning

Example:

```text
python3 apps/commander/scripts/commander_do_analytics_probe.py \
  --discover \
  --token-file /path/to/cloudflare-analytics-read.token \
  --output /tmp_hara/commander-do-schema.json

python3 apps/commander/scripts/commander_do_analytics_probe.py \
  --measure \
  --minutes 15 \
  --token-file /path/to/cloudflare-analytics-read.token \
  --output /tmp_hara/commander-do-analytics.json
```

The probe itself never prints the token.

Official references:
- https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/
- https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/
- https://developers.cloudflare.com/analytics/graphql-api/getting-started/authentication/api-token-auth/
