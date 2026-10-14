# H.A.R.A. Commander — Postdeploy QA, 2026-10-13/14

## Public platform snapshot

Product Commander listed 13 enrolled entries, eight ONLINE and five REVOKED; Linux 0.3.54, Windows 0.3.53. PROD health GET 200, auth login GET 302, unauthenticated MCP GET 401.

## OAuth / dynamic registration

Existing live DCR is GUARDED, not CLOSED. The previously default-closed check falsely failed current production. The source test now defaults to --expect guarded while preserving explicit --expect closed for deployments needing that policy. Guarded read-only preflight PASS: issuer, OIDC metadata, PKCE S256, protected resource, unauth MCP denied, invalid client registration HTTP 400 with invalid_client_metadata. Real client authorization/token exchange not proven.

## Real Windows MCP operations

On HARA_WIN11 0.3.53, Powershell process execution PASS, write to an isolated TEMP file PASS, readback PASS and metadata PASS. The generic files.delete wrapper returns AGENT_UPGRADE_REQUIRED: get_config confirms files.delete is not offered by Windows 0.3.53. Cleanup through HARA Commander process.run PowerShell PASSED and confirmed the temporary file absent. This is unsupported capability, not an unsafe deletion bypass or a demonstrated defect in the supported file API. Windows scheduled task 'HARA Commander Agent' is RUNNING with an AtLogon trigger, not proof of reboot availability before login.

## Commercial signed Linux distribution

Official PROD Linux installer SHA256 699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463 exactly matched signed stage; original signed release verify RSA-3072 PASS. New reproducible test_signed_commercial_autoreconnect_tamper.py (source-only) copies allowed signed artifacts to an isolated /tmp_hara directory and changes one byte range; verify rejects it with COMMERCIAL_SIGNED_V2_FILE_HASH_MISMATCH, original source unchanged, no private key read and no PROD write. PASSED.

## Honest release readiness

Existing commercial_readiness_gate.py reports FOUNDER_TECHNICAL=PASS but COMMERCIAL_BETA=HOLD (customer distribution acceptance + SECOND_TENANT_ISOLATION missing) and GENERAL_AVAILABILITY=HOLD (Windows live parity, authentic 1000-tenant 24h soak, Stripe payment/webhook entitlement, OpenAI public approval). These required evidence gates are intentionally not weakened. A signed current installer and eight connected Founder machines do not substitute for an isolated new customer enrollment.

## Linux lab VM custody

Dedicated Ubuntu 24.04 commander-linux-clean-20261012 booted and queried using existing qemu-guest-agent. VM already contains commanderqa profile, a Commander config and prior test artifacts; therefore not claimed CLEAN. No re-enrollment attempted, existing identity/files preserved, VM returned to SHUT OFF. A fresh isolated tenant/user and enrollment receipt are still needed for a physical clean commercial reboot canary.

## Production boundary

This branch changes ONLY offline regression scripts and evidence. No Cloudflare deployment, D1, product permission, signed release, Agent, STOP, game state, or payment configuration mutation. CSOTN episode 9643 remains a different controlled runtime domain.

## Next owner gates

1. New commercial account/tenant + distinct clean Linux user or VM, real pairing, install, reboot and no new pairing token on reconnect; logind linger permission/witness and revocation tests.

2. Windows 0.3.53 capability-accurate UI; separate Windows agent update for files.delete if feature is prioritized; require signed Windows package acceptance rather than invoking unsupported tool.

3. Real ChatGPT OAuth authorization and token exchange with independent user identity; cross-tenant isolation/revoke/quota; preserve fast fail-closed rate limits.

4. Paid customer Stripe test-mode checkout/webhook/cancel; scale soak measured instead of synthetic health bursts. No public-GA claim before completion.
