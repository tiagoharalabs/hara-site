# H.A.R.A. Commander — 10k Human User Capacity Contract

Parent: #174  
Device-scale sibling: #163

## Target

Design Commander so that 1,000 to 10,000 registered human users do not require premature hardware purchases or per-customer identity-seat spending.

This contract deliberately separates:

- registered humans;
- concurrently active browser sessions;
- human login events;
- devices and their own credentials.

Devices do not authenticate through human OIDC.

## Current hot path

The current portal session resolver hashes the session cookie and performs a PRODUCT_DB lookup joining portal_sessions, users and tenants for every authenticated request. Continuously active sessions may also update last_seen_at_utc every five minutes.

The first model therefore measures database-operation demand rather than claiming a provider capacity ceiling.

## Default planning scenario

The deterministic model defaults to:

- 1k / 5k / 10k registered users;
- 10% concurrently active;
- 6 authenticated portal requests per active user per minute.

At the 10k-user default scenario this yields:

- 1,000 active users;
- 100 authenticated requests/s;
- 100 session SELECTs/s with the current implementation;
- at most ~3.33 session-touch writes/s.

A deliberately severe 10k/100%-active/12-requests-per-minute scenario yields 2,000 authenticated requests/s and exposes why the session lookup must not remain an unexamined global hot path.

## Engineering rules

1. Do not convert customer identities into Cloudflare Access seats.
2. Keep HARA Identity self-hosted and independent from device credentials.
3. Do not add hardware until measured evidence shows the existing Storage identity plane is the limiting resource.
4. Preserve strong session revocation and logout semantics.
5. Prepare PRODUCT_DB boundaries so session, product metadata, device/call state and receipt history can scale independently.
6. Keep Event V2 reconnect behavior from recreating synchronized polling.
7. Measure single-tenant TenantQuota concentration separately from globally distributed load.
8. Keep high-cardinality user/device identifiers out of general Prometheus dimensions.

## Next source package

The next package should instrument and reduce the authenticated session hot path behind a default-off/non-PROD gate, with exact parity tests for logout, revocation, inactive users and inactive tenants.

No production runtime mutation is part of this document.
