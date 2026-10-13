# Windows Event V2 native and live DEV acceptance — 2026-10-12

Scope: experimental Event V2 adapter/transport and candidate RC installer. The installed Founder 0.3.51 Agent, task, consent window, configuration and public download were not modified.

## Native Windows PowerShell 5.1

The real commander-win11 VM ran the sources under PowerShell 5.1.26100.9444 and CLR 4.0.30319.42000. The fixture used a separate process-scoped LOCALAPPDATA, stable source copied from the private 0.3.51 candidate and separate receipt/ledger directories. QGA executes under SYSTEM; no Founder identity or token was loaded.

native-baseline-result.json reproduced four failures: candidate installer parsing, adapter self-test, exported stable functions and reconnect RNG. Follow-up isolated native execution also exposed the 32-bit FNV mask overflow in the durable liveness hash.

The final corrected source passed **46 of 46** native dynamic checks (native-transport-diagnostics-result.json; the earlier native-dynamic-result.json contains the first 41):

- Five source parsers, transport and adapter self-tests.
- Stable function export with original inline parameter declarations; stable 0.3.51 version binding.
- Native .NET Framework reconnect jitter and deterministic bounded liveness jitter.
- HTTPS/WSS, token, schema, identifier, payload type and frame-size controls.
- Real local transient receipt/ledger creation, replay, payload/tool conflict denial, replay miss and unknown-tool denial.
- device.info, metadata-only learning signal and bounded ledger retention cleanup.
- Bounded nested WebSocket/Socket exception enum classification, original error-code preservation and UNKNOWN fallback without private messages or paths.

These are native runtime checks and isolated local function tests. They are not Cloudflare or fleet-load tests.

## Real DEV Cloudflare path

live-enrollment-result.json, live-integrated-result.json and live-recovery-result.json prove:

1. Normal DEV /api/device/enroll with a separate QA pairing; DPAPI configuration in the private Windows fixture.
2. Actual ClientWebSocket connection to the DEV Worker from Windows PowerShell 5.1.
3. Durable CALL_AVAILABLE wake and completed hara.health call: 2486 ms.
4. Transient health, real device.info quota commit, and retry as REPLAY_ONLY/REPLAYED with the identical receipt.
5. Graceful shutdown, process restart using the same DPAPI identity, WebSocket reconnection and replay of the same persisted local receipt after restart.
6. Final graceful shutdown with exit 0 and connected=false.

The real committed receipt was 089c2c26abfc7b3b35eb956e522c48f816329230ca886260be6c369f82fb0db2. Cloud responses reported no persisted customer payload/result and no customer content in the learning signal.

The QA portal session was preseeded. Actual OAuth login and the OpenAI MCP client were not exercised here. Portal selection from Services returned HTTP 403 with no Worker error code twice; this observation is retained separately. The real calls selected the owned QA device explicitly through the normal internal DEV call API.

## Cleanup and remaining scope

The first QA Agent was stopped; normal /api/device/revoke-self returned REVOKED, and its private DPAPI fixture profile was removed (live-revoke-cleanup-result.json).

This proof establishes native and real DEV Event V2 execution of the adapter's current read-only contract. Full Windows tool parity is still false: the adapter exposes hara.health, discovery, device.info and receipts; it does not implement the full terminal/filesystem tool set present in the OUTBOUND_RELAY Agent. No public or signed release claim is changed by these tests. Public release remains separate from this experimental RC.

Two existing source contract validators passed. Their SOURCE_READY_UNPROVEN markers describe source-only validator scope and do not replace the native and live evidence in this directory.

## Independent one-unit Cloud Quota fixture

A second QA identity was enrolled and connected with a DEV_ONE_UNIT entitlement (CALENDAR_MONTH limit 1 and read-only grants). This is an explicit QA entitlement, not a claim that the public Free plan has a one-unit limit. The quota owner runs the cloud authorization/commit/release/concurrency proof; this Windows task made no metered calls before that owner started. Live enrollment/start/online evidence is retained under live-one-unit-*.json.

A spontaneous disconnection at 00:03:04Z recovered in the same Windows process at 00:03:11Z. The existing runtime reported METHODINVOCATIONEXCEPTION. No interruption was induced by the quota probe owner, and the cause is unknown. The new bounded transport_error_class metadata was then added and passed all 46 native controls; the running second fixture still uses the earlier source until the quota owner approves replacement. Long-duration stability is not closed by this short reconnection observation.

## Final .53 native proof and Cloud Quota boundary

The final Windows source is 0.3.53, SHA f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299. All **46 native controls** passed again with that source (native-053-acceptance-result.json).

The immutable full-platform .53 R2 bundle passed actual PowerShell 5.1 CryptoAPI RSA3072/RS256 signature verification, all four asset hashes, Windows Agent and installer parsing, and the Agent's own self-test with exit 0. The physical manifest SHA is d8f6d0165253b13a5efcade628564900f41dfbeacf4a062f61439486fb1ad395 (native-full053-r2-signature-selftest-result.json). No installed profile, global task or signing key was used by that native test.

The quota owner completed the real DEV_ONE_UNIT cloud test on a separate .53 Windows Agent: eight concurrent requests for the final unit yielded one ALLOW and seven denials; release and terminal replay were checked; actual device.info produced a receipt and COMMITTED usage, an identical retry did not charge twice, and an additional unit was denied. The native receipt is 5554d7a544d929ad16f3c008de546806b2b6d72268428dbd46f2200d1465b083, with STDOUT_SHA256_V1 binding. Source and receipt metadata are in live-one-unit-r3-native-source-and-receipt.json; the full cloud quota evidence belongs to the quota owner's sibling evidence directory.

The r3 enrollment template initially declared .51 while its actual stable source was already .53; the physical source version and hash were independently captured, and the evidence records both values. The reusable enrollment template now derives the version from the staged stable source.

The final r3 WSS remained connected from 00:15:40Z to graceful shutdown at 00:22:59Z. It terminated exit 0, revoke-self returned REVOKED and the private DPAPI profile was removed. This short observation does not establish a 24/72-hour soak or the cause of the earlier r2 transient disconnection.

## Release guards and offline gate

Historical .51 validators now read the immutable signed .51 source with SHA 4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a rather than the active .53 source. Historical signatures and the immutable public v1 manifest/assets at commit 08500d5 remain checked.

A new independent full .53 verifier validates the pinned public RSA authority, exact canonical manifest, signature, four assets, both Agent versions, installer version fields and reviewed source equivalence after only the official v2 key-pin rewrite. Thirteen unsigned tamper cases cover every payload, manifest changes, rebound digest without resigning, signature/key/algorithm changes, checksum tampering and symlink rejection; no signing operation occurs.

The original 115 offline tests were preserved. The integrated suite additionally includes .53 signature/tamper checks and the two sibling self-service checks. Old Linux fixture version expectations were advanced to .53; crypto, quota, rollback, manual-start and preservation checks remain intact.

Final integrated offline gate: **119/119 PASS**, 1000 attempts per stress scenario and 24 threads (prelaunch-offline-gate-053-119-final.json). Final QA cleanup has zero live fixture processes and no remaining r1/r2/r3 private profiles; no global task was created by this task.
