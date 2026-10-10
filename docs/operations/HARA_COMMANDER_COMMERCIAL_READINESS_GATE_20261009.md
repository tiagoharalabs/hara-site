# H.A.R.A. Commander — commercial launch-readiness check (2026-10-09, BRT)

## Verified in PROD without mutation

Ran `apps/commander/scripts/billing_prod_activation_preflight.py --live` against the actual production D1 and Worker secret **names only**. The live Worker/D1 storage and subscription bridge schema exist and match the contract.

- `COMMANDER_BILLING_PROD_SCHEMA=PASS`.
- Free catalog `TRIAL`: ACTIVE, `CALENDAR_MONTH`, **10,000 governed units/month** (legacy 100 units superseded). `TRIAL_LIVE_ALIGNED=TRUE`.
- Pro catalog `STANDARD`: ACTIVE, period kind `NONE`, unlimited units, approved nominal `BRL 80.00/month`. The price in the product documentation is **not evidence that Stripe checkout is live**.
- Optional `SCALE` plan: not active. Do not advertise it as available.
- Stripe `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and `STRIPE_PRICE_STANDARD`: **PENDING** in production Worker configuration. The optional `STRIPE_PRICE_SCALE` is also absent.
- `BILLING_CONNECTIONS=0`; `BILLING_WEBHOOK_EVENTS=0` at the time of the check.
- **`COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`**. Do not claim that customer payment acceptance has been proven.
- `PROD_MUTATION=FALSE`; no Stripe values, cards, customer payment details or confidential tokens were read or generated.

The first read-only preflight invocation failed transiently during a Wrangler D1 call, while a direct D1 schema/catalog query and a subsequent rerun succeeded. To make future operational checks trustworthy, `billing_prod_activation_preflight.py` now uses the **pinned locally installed Wrangler**, a two-attempt bounded read retry, sanitized failure codes, and fails closed on any command other than `secret list` or remote D1 `SELECT`. The changed script does **not** provision Stripe secrets or write to PROD.

## Separate transport and data-plane readiness

- ChatGPT `H_A_R_A__Commander` customer MCP is deployed and executes real signed Founder Agent 0.3.44 calls via authenticated `EVENT_V2` WebSocket on `nucleo-a`. Signed 0.3.41 fallback preserved; local watchdog and per-device allowlist validated.
- Fleet other than Founder is **not** on Event V2 yet. Windows signing, independent-customer installer security and actual Free quota exhaustion remain gates before scaling.
- Live Cloudflare matched 40-minute windows (four commercial operations each) show **−364 /api/device/calls/next HTTP requests (−20.73%)** and **−408 Worker requests (−19.75%)**, both aggregated across the zone/Worker, unsampled queue source `sampleInterval=1`. Not attributable solely to one device, and **not yet verified against actual billing**. See `HARA_COMMANDER_EVENT_V2_CLOUDFLARE_MEASURED_TRAFFIC_20261009.md`.

## Required for paid public checkout

1. Through the official Stripe account, create/verify the approved Standard subscription product and BRL price, and collect the **real** resulting Price ID. Check live/test separation and company business details.
2. Provision the Stripe production secret and webhook signing secret **directly in Cloudflare Worker secrets**, never in Git, shell history, reports or the ChatGPT transcript. Configure a verified live webhook endpoint. Provision `STRIPE_PRICE_STANDARD` as a secret or approved runtime configuration.
3. Use the existing product preflight until `COMMANDER_BILLING_FIRST_CHECKOUT_READY=TRUE`. Run an explicitly authorized small-value checkout test through the real application, verify webhook signature/idempotency, tenant entitlement upgrade, portal cancellation and downgrade handling. Do not activate customer billing solely from a passing source test.
4. In an isolated canary tenant, exercise Free limit edge cases under real `CLOUD_QUOTA` (last allowed unit, `QUOTA_EXCEEDED`, idempotent replay, concurrent reserve, fail/release) before enabling self-service signup at scale.
5. Extend Event V2 to subsequent devices one at a time, with separately signed per-device/OS releases, canary allowlists, support rollback, and measured Cloudflare Worker/DO costs.

**Commercial operating truth:** customer MCP functional for Founder; SaaS transport efficiency already observed in aggregate; **public paid subscription checkout remains not activated**.
