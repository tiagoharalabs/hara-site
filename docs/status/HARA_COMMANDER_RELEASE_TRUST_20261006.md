# H.A.R.A. Commander — Release trust anchor V1

Date: 2026-10-06
State: SOURCE/PREPROD PASS — DEV LIVE PENDING

## Boundary

This change adds an independent cryptographic trust anchor for the stable
release manifest and therefore for install/update artifact integrity.

It does not claim an independent out-of-band trust anchor for the first
bootstrap installer download itself. Initial bootstrap still relies on the
canonical HTTPS web origin until a separately distributed package/key channel
is introduced.

## Release signature

- schema: hara.commander-release-signature.v1
- algorithm: RS256
- key id: commander-release-v1
- signature target: exact bytes of release/agent-manifest.json
- public key: committed and pinned in Linux/Windows installers
- private key: local-only, mode 0600, ignored by Git

Published artifacts:
- release/agent-manifest.json
- release/agent-manifest.sig.json
- release/release-signing-public.jwk
- release/SHA256SUMS

## Linux

Install/update/preflight:
1. download manifest and detached signature;
2. verify manifest SHA-256 declared by signature metadata;
3. verify RS256 signature against pinned public key;
4. parse the verified manifest;
5. verify Agent SHA-256 and version;
6. run Agent self-test;
7. only then install/update.

Invalid or missing signature fails closed.

## Windows

The Windows installer:
- downloads manifest/signature to temporary files;
- verifies the exact manifest bytes using .NET RSA SHA-256 PKCS#1 v1.5;
- parses JSON only after signature verification;
- then verifies Agent SHA/version/self-test.

Invalid or missing signature fails closed.

## Source/preprod proof

PASS:
- release signature schema/algorithm/key id
- public key contains no private RSA fields
- manifest hash match
- real RS256 signature verification
- modified manifest tamper denied
- Linux key pin/fetch/verify/fail-closed/preflight attestation
- Windows key pin/fetch/verify/fail-closed/exact-byte verification
- private signing key not tracked
- private JWK source leak absent
- clean Linux install/update/re-enroll/uninstall with signed manifest
- runtime drift covers signature and public key
- full supply-chain validator
- full Commander preprod readiness

## Remaining maturity

RELEASE_MANIFEST_INDEPENDENT_TRUST_ANCHOR=CLOSED_PASS
INITIAL_BOOTSTRAP_TRUST=HTTPS_WEB_ORIGIN
OUT_OF_BAND_BOOTSTRAP_TRUST=PENDING_GA_MATURITY
