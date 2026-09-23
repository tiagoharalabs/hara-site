# H.A.R.A. Commander — product direction current — 2026-09-22

## Product definition

H.A.R.A. Commander is a simple customer connectivity product.

The intended customer flow is:

1. create or enter a HARA account;
2. install HARA Commander Agent on a Linux or Windows computer;
3. pair that computer to the customer workspace with a short-lived one-time token;
4. keep an outbound-only authenticated Agent connection;
5. authorize ChatGPT, Codex or another supported MCP client;
6. route governed MCP calls to the selected connected computer;
7. return sanitized results and receipts.

Commander is not a fleet NOC, a Paradox observability console, a generic SSH/shell/file browser, or a per-customer Cloudflare Tunnel product.

## Current visual baseline

The visual direction is now approved enough to serve as the product baseline while implementation continues.

Light mode:
- white / blue-tinted glass header;
- thin HARA yellow line on both the top and bottom edges of the header;
- ice-blue page background;
- near-white blue-tinted cards;
- navy sidebar;
- HARA yellow reserved for CTA/accent emphasis;
- HARA blue used for interactive/supporting accents.

Dark mode:
- retain the current dark navy palette;
- preserve the same dual-line header grammar;
- use restrained blue/slate lines instead of yellow so the dark theme remains sober.

The dual-line header is a product signature and should remain consistent across Commander screens.

## Current production runtime

Production URL: https://commander.haralabs.com.br

Verified on 2026-09-22:
- production endpoint: HTTP 200;
- light header top yellow line: PASS;
- light header bottom yellow line: PASS;
- dark header dual blue/slate line: PASS;
- production CSS matches the canonical repository asset;
- Commander Worker health: ok=true;
- environment: PROD;
- storage mode: REMOTE_PROD.

## Current production login state

This section supersedes the historical 2026-09-22 login-readiness blocker.

Current factual state as of 2026-09-23:
- `/api/portal/auth-config` returns `configured=true`;
- provider is HARA Identity;
- client auth is BASIC;
- `/auth/login` returns HTTP 302 to the HARA Identity OIDC authorization endpoint;
- first real production OIDC login/onboarding previously completed successfully;
- account-switch now uses `prompt=select_account` with `max_age=0`;
- expired OIDC transactions are pruned before a new login transaction is created;
- D1 session readback now distinguishes expiry from explicit revocation.

The HARA Identity instance Login Policy fallback redirect has been aligned from the DEV Worker to `https://commander.haralabs.com.br/` through the supported ZITADEL Admin API. Independent backend validation reports `IDENTITY_LOGIN_DEFAULT_REDIRECT=PASS`, and after refreshing only the Login V2 container the public runtime gate now reports `HARA_IDENTITY_LOGIN_DEFAULT_REDIRECT_RUNTIME=PASS`. The remaining login gate is the fresh human browser callback/logout/account-switch retest.

Canonical evidence and remediation are in `docs/status/HARA_COMMANDER_LOGIN_FLOW_REVIEW_20260923.md`.

## Product implementation state

Already represented in the product package:
- HARA Identity / OIDC integration code;
- account/workspace UI;
- plan, entitlement and quota primitives;
- Linux and Windows Agent installers;
- short-lived one-time device pairing;
- device credential and heartbeat/presence;
- device revocation;
- outbound relay canary;
- governed/fail-closed boundary;
- production Worker, D1 and Durable Object isolation.

The product is still under active development. Visual approval does not mean functional closure.

## Next product gates

1. Re-prove a fresh human browser login/callback, logout / `Usar outra conta`, and preserve no-flash authenticated first-paint behavior.
2. Complete the first real production device pairing on `nucleo-a`.
3. Bind public MCP identity/workspace to the selected online customer computer.
4. Prove the governed tool surface end-to-end with ChatGPT/Codex.
5. Keep arbitrary shell, SSH and generic filesystem access absent.
6. Add billing only after ordinary authentication + MCP E2E is stable.

## HARA Labs institutional site direction

The main HARA Labs website should be updated in a separate front.

That future site update should:
- present Commander as a real HARA Labs product;
- reuse the now-approved Commander visual identity;
- explain the simple customer value proposition;
- link to the product without duplicating the Commander application UI;
- avoid presenting unfinished runtime gates as completed capabilities.

The institutional-site update is not a substitute for continued Commander product work.

## Decision

The Commander visual language is now sufficiently defined to inform the HARA Labs institutional site.

The product itself remains in active implementation and homologation.
