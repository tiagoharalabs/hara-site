# H.A.R.A. Commander — Stripe TEST activation with one command
**10/10/2026 | Canonical branch `local/commander-product-current`**

Status: **CODE READY + DEV WORKER DEPLOYED; test key and a real hosted test checkout not yet provided**. DEV version **`490c38bf-5ef0-4b55-a33a-2dc6d0c6ad6c` 100%**, readback confirmed, DEV health=200, billing without session=401, DEV Stripe secret names all absent. PROD remained **`29e556f3-86af-476d-ba01-a764c3acb6a0` 100%**, Stripe secrets PENDING and billing first-checkout ready FALSE. Do not confuse an offline integration test or Stripe object creation with proof of a customer payment.

## What was built

- `apps/commander/scripts/stripe_test_activation_wizard.py`: dedicated TEST-only bootstrap. It accepts the `sk_test_` key only via local private `getpass`, never through CLI arguments or this chat.
- The script checks it is operating against exactly `hara-commander-dev-v2` with `ENVIRONMENT=DEV`, `STORAGE_MODE=REMOTE_DEV`. It has **no production option**.
- Stripe test API: reuse an existing `lookup_key=hara_commander_standard_brl_8000_month_v1` or create `H.A.R.A. Commander Pro` and recurring **BRL 80/month**, fixed/licensed, with idempotency keys. Reject wrong price, cadence, currency, or Stripe live mode.
- Stripe webhook: use the DEV endpoint `https://hara-commander-dev-v2.tiago-sartori.workers.dev/api/billing/stripe/webhook`. If absent, create a snapshot endpoint pinned to `2024-06-20`, events `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `invoice.payment_failed`. If it already exists, require the operator to enter the signing secret `whsec_` locally because Stripe only returns it when the endpoint is created through the API.
- Stripe customer portal: create/reuse a TEST configuration that allows invoice history, payment method updates and cancellation at period end. `createBillingPortal` now passes optional `STRIPE_PORTAL_CONFIGURATION` to the Stripe API, so a non-default portal configuration is supported.
- Test Worker secrets, in order: `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD`, `STRIPE_PORTAL_CONFIGURATION`, **`STRIPE_SECRET_KEY` last**, and confirm names afterward. Wrangler `secret put` deploys a new DEV Worker version each time; this is deliberate, and the final API key is installed last. No secret is written into Git, JSON, logs or output.
- Safety: if Stripe secrets already exist on the DEV Worker, refuse to overwrite automatically; an operator must reconcile first. Only Stripe test key `sk_test_` is accepted. No real payment or subscription is created by the wizard itself.

## Minimal operator step — on the Services machine in an interactive terminal

```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 -B apps/commander/scripts/stripe_test_activation_wizard.py --check
python3 -B apps/commander/scripts/stripe_test_activation_wizard.py --apply
```

The operator enters one Stripe **test secret API key** when requested (hidden input). If the webhook already exists, it also asks for its separate `whsec_` signing secret. Never post these values in ChatGPT or a ticket, and never pass them as shell command arguments. **Do not enter `sk_live_`.** If only a live key exists, create/find a test key in Stripe's test environment first.

### SSH non-login shell recovery (10/10/2026)

The first operator invocation from `nucleo-a` via `ssh -t services '...python3 ... --apply'` failed **before any secret prompt** with `STRIPE_TEST_ACTIVATION=CLOUDFLARE_DEV_SECRET_LIST_UNAVAILABLE`. Investigation reproduced Wrangler exit 127: `/usr/bin/env: 'node': No such file or directory`. Non-login SSH did not source `~/.bashrc`/NVM, although the Node 24.15.0 executable was installed in the Services user's `~/.nvm/versions/node/v24.15.0/bin`.

The wizard now supplies a temporary, subprocess-only Wrangler PATH, finding an executable user-owned NVM Node version when `node` is unavailable in the SSH environment. It does **not** source shell profiles, change system PATH, or print authentication material. `secret list` and `secret put` use the same bounded environment.

**Real verification through Núcleo → SSH → Services:** `--check` returned exit 0 both with noninteractive SSH and forced TTY (`ssh -tt`), read the DEV secret names, and confirmed all four Stripe secrets are still MISSING. Offline regression `validate_stripe_test_wizard.py` covers absent-Node-in-PATH recovery. Neither test ran `--apply`; no Stripe API calls, Cloudflare secret writes, production deploy, or charges occurred.

Because the operator is already connected to the Services interactive shell, the next command is simply:

```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 -B apps/commander/scripts/stripe_test_activation_wizard.py --apply
```

Enter only a real `sk_test_` key through the private terminal input. The command is intentionally not run unattended without the operator's key.

The wizard writes only test objects to Stripe and only DEV secrets to Cloudflare. The user's actual DEV tenant must then complete a **Stripe test Checkout** through the Commander portal, followed by a real signed webhook delivery. There is no automatic live charge and no automatic promotion to production.

## Local/production protections

- `billing.mjs` rejects DEV billing configured with live API keys, and PROD billing configured with test API keys. Production and test webhook `livemode` must match the Worker environment.
- Late `checkout.session.completed` can no longer regress current ACTIVE/SUSPENDED/REVOKED state or override a newer active subscription. A delayed old subscription event cannot resurrect a canceled subscription or revoke a different newer subscription. Failed invoice from old/unmatched subscription is ignored. Invoice subscription ID is accepted from either legacy `invoice.subscription` or `invoice.parent.subscription_details.subscription`.
- Webhooks still verify Stripe HMAC signature and 300-second timestamp tolerance, reject unknown prices, deduplicate Stripe `evt_` IDs and keep customer content out of telemetry.
- **Residual gate:** a formal provider-event timestamp/state reconciliation for distinct out-of-order ACTIVE-versus-SUSPENDED updates *within the same subscription ID* remains pending; test the real Stripe event stream before production live payment activation.

## Tests and operation

```bash
node apps/commander/scripts/billing_v1_selftest.mjs
node apps/commander/scripts/billing_sqlite_webhook_e2e.mjs
PYTHONDONTWRITEBYTECODE=1 python3 -B apps/commander/scripts/validate_stripe_test_wizard.py
python3 apps/commander/scripts/validate_billing_v1.py
python3 apps/commander/scripts/billing_prod_activation_preflight.py --live
```

The SQLite test uses the real D1 schema in memory and exercises signature reject, wrong Stripe mode reject, subscription activation, trial expiry, duplicate event, late checkout, payment failure, payment recovery, cancellation, stale old subscription/invoice events and unknown price rejection. The wizard test uses fake Stripe API objects and fake secret writes; **it never calls Stripe or changes Cloudflare**.

Once a Stripe TEST key is supplied privately, the wizard can prepare the test objects and Cloudflare DEV bindings. After that, the operator must finish and inspect:
1. Test account / tenant's OWNER signs in to Commander DEV, clicks Pro checkout and completes a Stripe TEST payment.
2. Verify webhook event delivery (all required event types and 2xx responses), `billing_webhook_events` exactly once per event, `billing_connections` linked, paid entitlement ACTIVE and prior Trial EXPIRED.
3. Verify Customer Portal, Stripe cancellation, entitlement REVOKED, payment failure/SUSPENDED and recovery/ACTIVE in DEV using authentic test events.
4. Only after all tests, a separately governed production activation: Stripe LIVE product/price/webhook/account/tax setup, Cloudflare production secret provisioning, preflight, one explicit authorized real subscription and rollback plan.

**PROD billing remains OFF until separately approved and tested.** Do not configure `STRIPE_SECRET_KEY` on the production Worker during the test activation.
