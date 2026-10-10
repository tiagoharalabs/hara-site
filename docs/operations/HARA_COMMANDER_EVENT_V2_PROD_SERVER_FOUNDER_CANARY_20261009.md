# H.A.R.A. Commander — PROD Event V2 server canary activated (2026-10-09 BRT)

## Executive status

**PROD SERVER EVENT_V2 CANARY = ACTIVE AND VERIFIED.**
**FOUNDER COMMERCIAL AGENT EVENT_V2 CUTOVER = NOT YET.**
**THE EXISTING COMMERCIALLY AUTHENTICATED CUSTOMER MCP REMAINS PASS.**

The business is already operational for the Founder's own account through the public ChatGPT H.A.R.A. Commander MCP with HARA Identity OAuth and the Cloudflare Worker. Device execution receipts were correlated to production D1 in `docs/operations/HARA_COMMANDER_COMMERCIAL_MCP_REAL_E2E_20261009.md`.

This release enables only the **server-side Durable Object WebSocket Hibernation API** behind a single authorized Founder device ID. It deliberately does not change the installed, trusted `0.3.41` Agent or the existing `OUTBOUND_RELAY` request/poll transport on any device. **Do not claim that the Cloudflare idle request rate has already decreased.**

## Cloudflare promotion and guard

- **Worker:** `hara-commander`, `commander.haralabs.com.br`.
- **Prior Worker version / rollback candidate:** `51348588-5b38-4622-bed9-da99ab9a3ef9`.
- **New version at 100%:** `215ab34e-78ad-4002-a4d6-7e26e3a71f94`.
- PROD `wrangler.jsonc`: new binding `DEVICE_CHANNEL -> DeviceChannel`, append-only migration **v3 `new_sqlite_classes:["DeviceChannel"]`**, variable `DEVICE_EVENT_V2_ENABLED=true`.
- **Only production allowlisted device:** `HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62` (`nucleo-a`); the Worker first validates the actual Agent bearer token, then checks `device.device_id` against `DEVICE_EVENT_V2_CANARY_DEVICE_ID`. Other authenticated customers are rejected by the Worker source with `DEVICE_EVENT_V2_CANARY_DENIED` HTTP 403 (source guard verified; cross-tenant authenticated live WebSocket not exercised here). An unauthenticated WebSocket Upgrade receives HTTP 401, no device token is exposed.
- `DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED` remains **absent in PROD**. Event V2 PROD continues using D1 durable call truth rather than DEV-only transient payload delivery.
- Existing Cloudflare D1 data was not reset or rolled back; migration v3 creates only the Durable Object namespace (no new D1 SQL migration).
- **Release assets remain cryptographically trusted:** the four existing published signed Agent 0.3.41 files were sourced byte-exactly from canonical commit `08500d5` into an isolated deployment stage. Signatures and four SHA-256 hashes were checked before and after deployment. No unsigned 0.3.43 Agent or installer was shipped.
- All **six Worker secret names** were preserved exactly; secret values were never fetched or printed.
- Prod deployment also uploaded three existing Git source UI assets (`index.html`, `styles.css`, `app.js`) where the prior deployed asset bundle differed. All were HTTP 200 at live readback; do not claim they remained byte-identical to the previous version. Any UX regression should use the safe Worker rollback path.

## Live post-deployment proof

- `wrangler deployments list --json`: `215ab34e-78ad-4002-a4d6-7e26e3a71f94` at **100%**.
- `/.well-known/oauth-protected-resource/api/mcp` = HTTP **200**; anonymous `/api/mcp?profile=simple` = **401**; anonymous `/api/device/channel` without upgrade = **426**; forged Upgrade with invalid bearer = **401**; unauthenticated portal dashboard = **401**.
- Public website and all three uploaded UI assets HTTP 200; the 4 signed Agent/installer paths have the same SHA-256 and size as before.
- ChatGPT plugin `H.A.R.A. Commander` `ping(nucleo-a)` PASS, `get_device_info(nucleo-a)` PASS and `get_usage_stats()` PASS after migration; SHA-256 receipts were present for the device calls.
- A new **post-deployment** commercial `ping` receipt from the signed Nucleo A Agent was cross-checked against exactly one production D1 `HARA-CUSTOMER-MCP-` call with `state=COMPLETED` and matching device ID: `AFTER_EVENT_V2_DEPLOY_COMMERCIAL_MCP_AGENT_D1_E2E=PASS`.
- PROD D1: `nucleo-a` still `agent_version=0.3.41`, `tunnel_mode=OUTBOUND_RELAY`, `state=ACTIVE`. The signed Agent is running, has not been swapped, and the customer's MCP still works.
- The DEV WebSocket canary previously completed `hara.health` twice (3829 ms and 2499 ms after controlled reconnect), with hibernation-capable `this.ctx.acceptWebSocket` and no idle HTTP polling, documented in `docs/operations/HARA_COMMANDER_EVENT_V2_HIBERNATION_DEV_PROOF_20261009.md`. This demonstrates Event V2 end-to-end **in DEV**, not signed-Agent parity in PROD. After verification, this isolated DEV test process was **stopped cleanly** and its status marked disconnected; the signed PROD Agent remained active.
- Static regression suite passed for Event V2 wiring/hibernation, websocket client, reconnect/shutdown, PROD static, cross-tenant source guard, transient DEV-only, local budget, quota TTL and billing. PROD dry run of signed 0.3.41 stage passed with Strict flag.

## Production safeguards and emergency rollback

The deployment had an immutable launch preflight: exact production Worker name, exact Founder canary device ID, ENVIRONMENT PROD, no transient RPC, migration v3, fixed signed Agent public files, complete signed manifest unchanged. The release stage builder is `apps/commander/scripts/build_prod_signed_event_v2_stage.py`.

Prepared runtime build path on Services:
`/tmp_hara/commander-eventv2-prod-stage-20261009-cf-v3/apps/commander`.

**First-line kill switch (fail-forward, retaining migration and signed assets):**

```sh
WRANGLER=/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules/.bin/wrangler
STAGE=/tmp_hara/commander-eventv2-prod-stage-20261009-cf-v3/apps/commander
"$WRANGLER" deploy --strict \
  --config "$STAGE/wrangler.event-v2-disabled.jsonc" \
  --message "Emergency disable Event V2; preserve v3 and signed 0.3.41"
```

This configuration sets `DEVICE_EVENT_V2_ENABLED=false` without deleting the `DeviceChannel` class migration or touching PROD D1. Confirm the Worker deployment and retest customer MCP after executing. Historic Worker version `51348588-5b38-4622-bed9-da99ab9a3ef9` is the fallback for Worker versioned rollback, but **new Durable Object migrations are atomic**, so prefer this forward kill switch; never restore old D1 backups to disable Event V2.

## Remaining gates before real request reduction

1. Resolve **signing-key custody** for 0.3.43: currently the available private signing key did not match the public RSA JWK pinned in existing installers. No signing private-key env var was configured in the operator shell. Do not bypass signature checks, fabricate the old key or silently rotate it. Use the correct matching key, or separately approve a formal trust-key rotation and migration plan.
2. Deliver Event V2 through a genuinely signed Agent package with an explicit Founder-only opt-in, one-loop-per-device and automatic fallback to the installed stable `OUTBOUND_RELAY` on failure. No silent changes to seven production hosts.
3. After signing, migrate only `nucleo-a`, verify OAuth → PROD MCP → EventV2 socket → Agent receipt → Cloudflare D1, reconnect, durable queue, quota/idempotency, and service rollback; only then expand to additional hosts.
4. Measure Cloudflare request counts and Durable Object billed duration (not just model predictions) before claiming lower cost. The existing 0.3.41 model estimated **10,086 idle infrastructure HTTP requests/day/device** and **70,602/day for seven**, not charged customer tool units.
5. Customer Free quota exhaustion, different-tenant denial and public distribution/Stripe checkout remain separate release gates.

## Handoff truth

**This turn delivered a successfully activated production hibernating WebSocket *server*, not the fully migrated production transport client.** The public customer-facing MCP, HARA OAuth, D1 call ledger, signed 0.3.41 Agent, seven-machine fleet and plan entitlements remain unchanged. No reduction in idle polling is claimed at this gate.
