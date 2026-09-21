# Commander DEV V2 — functional scenarios and remote bootstrap

Visual baseline: approved in hara-site#25 / PR #26.

## Functional state scenarios

The approved portal can exercise failure and edge states without changing
production data. Add `scenario` to the DEV URL:

- `?scenario=loading#dashboard`
- `?scenario=empty#dashboard`
- `?scenario=auth-expired#dashboard`
- `?scenario=entitlement-suspended#dashboard`
- `?scenario=quota-exhausted#usage`
- `?scenario=mcp-unavailable#dashboard`
- `?scenario=receipt-unavailable#usage`
- `?scenario=billing-disconnected#plans`
- `?scenario=degraded#dashboard`

The normal local Product API remains `http://127.0.0.1:9192`.

A specific DEV API can be selected with the `api=https://...` query parameter.
Only HTTPS endpoints, or localhost HTTP endpoints, are accepted.

## Remote DEV bootstrap

`apps/commander/scripts/bootstrap_remote_dev.py` is intentionally idempotent.

It:
1. requires an authenticated Wrangler session;
2. lists remote D1 databases;
3. reuses `hara-commander-product-dev` when it already exists;
4. creates it only when absent;
5. generates an account-specific config under ignored `.generated/`;
6. applies D1 migrations remotely;
7. loads synthetic DEV seed data only;
8. deploys `hara-commander-dev-v2` with a SQLite-backed Durable Object;
9. does not add a production custom domain.

The generated config is never committed because it contains the Cloudflare
resource UUID.

## Explicit boundaries

- production DNS mutation: false;
- production customer data: false;
- real billing: false;
- real password storage in H.A.R.A.: false;
- HARA Services operational authority: unchanged.
