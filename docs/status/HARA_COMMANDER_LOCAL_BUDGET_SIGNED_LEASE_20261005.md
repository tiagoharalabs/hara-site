# H.A.R.A. Commander — Local budget + signed product lease

Date: 2026-10-05

## Free local budget

The existing local-budget candidate was audited and exercised against DEV.

Live DEV canary:

- budget block issuance: PASS
- block size: 100 calls
- fresh tenant baseline: FRESH_TENANT_ZERO
- legacy Durable Object reads for fresh baseline: 0
- three governed calls consumed one local block: PASS
- local debits: 3
- cloud issued units: 3
- cloud reported units: 3
- cloud block count: 1
- cleanup: PASS

The cloud remains authoritative for the 10,000-call monthly ceiling. Local
SQLite only consumes units that the cloud allocated to that device.

## Signed entitlement/product lease

The previously unsigned product-lease cache was hardened.

Agent release gate:
- local budget requires Linux Agent 0.3.36 or newer
- older Agents fall back to CLOUD_QUOTA

Lease signature:
- algorithm: RS256
- key id: commander-lease-v1
- audience: hara-commander-agent
- private key: runtime secret only; never committed
- public key: pinned in the Agent

The signed claims bind:
- cloud issuer
- device
- tenant
- entitlement
- plan
- grants
- meter
- period kind
- usage mode
- issue time
- expiry

The Agent verifies the signature locally using Python standard library only.

Local budget reserve additionally requires:
- current signed lease
- lease usage mode LOCAL_BUDGET
- budget tenant/device/entitlement/plan/meter matching the signed lease
- matching budget id and units on request replay

SQLite modification cannot promote Free to Pro: the stored signed token is
revalidated and the signed payload must exactly match the stored lease JSON.

## Regression

PASS:
- local budget architecture validator
- local budget race/rollover/replay validator
- signed lease static contract
- real RSA keypair match
- valid signed token
- tampered JWT denied
- expired JWT denied
- local SQLite lease tamper denied
- E2E harness
- full source preprod readiness

## Deployment gate

The private signing key exists only as local protected material and is excluded
from Git.

Automated secret provisioning was intentionally blocked by the execution
channel's secret-safety controls.

Therefore:
- Agent 0.3.36 is NOT promoted yet
- signed-lease Worker is NOT promoted yet
- current PROD remains safe on the prior release
- local-budget 0.3.35/unsigned path is not promoted through this branch

Required human gate:
configure Cloudflare Worker secret PRODUCT_LEASE_PRIVATE_JWK in DEV using the
locally generated private JWK, without copying the secret into chat.

After that gate:
1. deploy signed-lease candidate to DEV
2. rerun fresh Free local-budget canary
3. prove served Agent 0.3.36 verifies the live signed lease
4. only then consider PROD promotion

## State

LOCAL_BUDGET_FREE_DEV_LIVE=CLOSED_PASS
SIGNED_PRODUCT_LEASE_SOURCE=CLOSED_PASS
SIGNED_PRODUCT_LEASE_TAMPER_GATES=CLOSED_PASS
SIGNED_PRODUCT_LEASE_DEV_LIVE=PENDING_SECRET_PROVISION
WINDOWS_LOCAL_STORE_PARITY=PENDING_SEPARATE_SLICE
