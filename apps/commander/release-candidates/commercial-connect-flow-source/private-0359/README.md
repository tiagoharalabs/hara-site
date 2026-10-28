# Private QA candidate 0.3.59

This is a separate signed candidate following native 0.3.58 QA. The historical 0.3.57 and 0.3.58 source, signatures and failure receipts remain unchanged. Current operational results are recorded in the top-level [closeout checkpoint](../CLOSEOUT-20261028.md) and the sanitized evidence files; source preparation does not imply native acceptance.

## Narrow Windows correction

Native 0.3.58 QA restored the main Windows runtime after the access-only DACL fix, but the executor worker failed its health acceptance. The empty abandoned-claims array survived a direct call as `[]` and became `[null]` across the actual function boundary. The 0.3.59 producer initializes an explicit `[object[]]` array before selecting executor seeds. The downstream consumer validation is unchanged.

`source/DERIVATION-REPORT.json`, `source/windows-agent.patch`, and `source/windows-installer.patch` record the exact source transformation. The Windows Agent retains the 0.3.58 DACL correction. The installer differs from 0.3.58 only in version literals, retaining its task synchronization and transactional update behavior. Frozen connection controllers and pairing helpers remain embedded unchanged. Linux changes only version literals relative to the frozen Agent and connection-flow installer sources.

## Build and signature custody

`BUILD-REPORT.json` records the deterministic unsigned build. `SIGNATURE-REPORT.json` and `SIGNATURE-READBACK.json` record the subsequent real signature and independent verification of the manifest and four artifact bytes. The existing `commander-release-v2` key was used in its native custody environment; private key material is excluded from this directory and delivery.

Manifest SHA-256: `efe39839596883875358cfc27cd7ec62c0d38acc3c03708df56034a82d35d7b4`.

Signature-file SHA-256: `888f8674ae48e511eac9b4cc8ec1858110576af6970a6e6a7db19b585ef15ba3`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `agent/linux.py` | 265620 | `df8b2d09c5447f8d405200538a841e669a8f165e9043701d6c8efcbfe5a34d38` |
| `agent/windows.ps1` | 173345 | `d3a4173829186e2488c2b686f5ac3ecca62c896387f55dcdfdbcdd155253ae24` |
| `install/linux.sh` | 72524 | `80732c941725e06f317ef42e878a0498d30f28bf890dd07d9a0b6a90f0cd0581` |
| `install/windows.ps1` | 77495 | `2f734ab8066b46cb82fc4fc9fb25244472bc829c16043cfe5f2771ae4e6d04b4` |

## Native execution and bounded distribution

The Windows regression exercises the actual parameter-binding boundary and retains rejection of malformed null claims. Native update acceptance additionally requires the exact target Agent, preserved enrollment/configuration/policy/task definition, a fresh authenticated main runtime and all expected relay workers. Passing source or isolated regression checks alone does not certify those conditions.

The Linux driver admits only the existing 0.3.58 Agent and its recorded 0.3.57 rollback file. Success must preserve enrollment, configuration, unit, CLI and policy, establish a fresh authenticated 0.3.59 runtime, and retain an exact 0.3.58 rollback Agent. It exercises an explicit private signed update, not same-origin public latest-release discovery.

The distribution serves only the exact eight pinned files at `https://192.168.10.23:18446/releases/0.3.59` to the two fixed QA guest addresses through `virbr96`. The unit/tag is `hara-connect-qa-0359-20261028`; the hard deadline is **19:35 UTC on 28 October 2026**. Its server and control sources derive from the reviewed earlier distribution with unchanged custody and firewall cleanup guards. The certificate is unchanged; any renewed Windows trust is separately bounded and needs an independent cleanup receipt.

Only sanitized receipts are collected. Configuration preimages, pairing/device credentials, raw process logs, private TLS/signing keys, temporary transfer bundles and caches must remain outside Git. A scheduled expiry is not a successful cleanup result: the operator must verify absent listener/rules and the end of the temporary Windows trust separately.

## Release boundary

A signed private candidate does not promote the production catalog or authorize public release. Public discovery, fresh reviewer pairing, native worker health and actual distribution cleanup each retain their own outcome. Historical failures are not reclassified when a later candidate passes.
