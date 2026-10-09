# H.A.R.A. Commander — signed beta package published 2026-10-09

## Exactly what was promoted

- Live: `https://commander.haralabs.com.br/`
- Linux: `https://commander.haralabs.com.br/install/linux.sh`
- Windows: `https://commander.haralabs.com.br/install/windows.ps1`
- MCP HTTPS: `https://commander.haralabs.com.br/api/mcp?profile=simple`
- Cloudflare PROD Worker version (100%):
  `51348588-5b38-4622-bed9-da99ab9a3ef9`
- Readback rollback Worker version (keep available):
  `afffe718-fe41-49e5-8728-c07c45382866`
- Signed public Agent release: **0.3.41**, NOT candidate 0.3.43.
- Reproducible signed 0.3.41 artifact provenance:
  Git `08500d5` for all four agent/installer files, signature, checksum
  index and release manifest. The source branch stays
  `local/commander-product-current`.
- Linux signed SHA-256:
  `e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730`
- Signed Linux installer SHA-256:
  `99b25c7671326b983ff1fa670ce0044f9a89674dcd1b2d78cf8ab4a6cccb828b`
- Signed Windows Agent SHA-256:
  `52bb1b3c537c31a357becc38c494ea8494bf310fc3e694d59b1a578509a56d44`
- Signed Windows installer SHA-256:
  `475d7afe4440fc760adfcb333e1922d5a9eb3d7bb49ca571c4c5741519bdc240`

The staging and production promotion used the canonical Worker versioned
process. An isolated staging build combined the newer tested Worker control
plane with **the exact signed 0.3.41 public release assets** from Git;
it did not publish or masquerade the unsigned 0.3.43 source.
The target version inherited all six existing PROD Worker secrets.
Migrations 0029 and 0030 were already applied previously.
Preflight, version deployment, trigger synchronization, Worker readback,
public asset exact readback and external SHA-256 comparison all PASS.

## First customer machine test

On `nucleo-a`, the officially published `install/linux.sh update`
completed successfully with exact installer SHA-256 pinned beforehand.
The downloaded Agent manifest signature and payload integrity passed; the
systemd user service was restarted; startup attestation and
`hara-commander doctor` returned PASS with live Agent **0.3.41**.
The previous Agent executable was also retained as a local safety backup.
The installed stable `hara-commander mcp` then passed **33/33 local
functional canaries** (scratch test data under `/tmp`, cleaned afterward).
This proves signed installation/update and the local MCP tools work.

The authenticated H.A.R.A. Commander ChatGPT Baseline connector pinged
the Nucleo successfully after promotion but reported
`operational_authority=HARA_SERVICES`,
`execution_authority=HARA_COMMANDER_AGENT`, and
`runtime_authority_from_chatgpt=false`.
This is **not evidence of the direct OpenAI Secure MCP Tunnel path**.
The public customer MCP route and OAuth discovery exist and return
401 for anonymous tool access, as expected.

## The real 0.3.43 release blocker

The canonical source is 0.3.43 and includes the Linux tunnel manual /
automatic startup controls. Linux and Windows installer version markers
were aligned to **0.3.43** for the next signed release.
The unsigned candidate manifest builder successfully produced exact file
hashes. The canonical signing tool rejected the available private key:
`RELEASE_SIGNING_KEY_MISMATCH` because the key's RSA public modulus does
**not** match the trusted public JWK pinned in published installers.
This is a **real release trust-anchor mismatch**, not a test failure.

Do not copy or expose the private key into Git, disable signature
verification, publish an unsigned 0.3.43 binary, silently rotate
the signing key, or call the signed 0.3.41 release 0.3.43.
Restore the original matching private signing key under proper custody,
or conduct an **explicitly approved, documented key rotation** with a
backward-compatibility plan for already-installed customers.
The canonical tracked `release/agent-manifest.json` and `SHA256SUMS`
remain at the **cryptographically valid signed 0.3.41** bundle.
`build_release_manifest.py --check` against newer 0.3.43 sources is
therefore intentionally STALE until the next release is legitimately signed.

The 0.3.43 candidate source SHA-256:
`1bb1875ee7483d4518b46cf9ef8d31f3231f5c4b3d3d7f54b9b74de964bcc129`.
The unsigned release manifest SHA-256 calculated after aligning both
installers: `53ee66bfdd9a70f67ba1f4d68ba77920fca3fd4195708e846c6250719d005611`.
It must be regenerated after any source changes.

## What is available now and what is not

- **NOW:** Customer can use the signed 0.3.41 Linux/Windows installer
  from the official web URL and test local `hara-commander mcp`.
- **NOW:** HARA Identity, existing Cloudflare MCP/Gateway and previous
  OUTBOUND_RELAY tenant/Agent path; OAuth discovery is available.
- **NOT YET:** Updated Agent 0.3.43 as a signed public release, OpenAI
  Secure MCP Tunnel per-customer runtime credential/profile, real direct
  OpenAI -> local MCP E2E, and paid Stripe checkout.
- **NOT YET:** Stripe PROD secret, webhook signing secret and Standard
  Price ID; billing preflight reports `FIRST_CHECKOUT_READY=FALSE`.
- Keep existing PROD Worker rollback as a **versioned Worker rollback**.
  Never roll back the D1 database to an old bookmark just to revert code.

Next gate is to repair the signing-key custody, sign 0.3.43, deploy
with the same versioned readback, then test the customer tunnel. Billing
is a separate activation milestone.
