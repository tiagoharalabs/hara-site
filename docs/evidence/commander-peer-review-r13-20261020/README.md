# HARA Commander R13 — independent QA

These are local negative reproductions, never PROD incidents. The first script runs the actual Linux installer in a disposable HOME/XDG, with a **localhost-only** signed-release mock, synthetic pairing token and four deliberately faulty enrollment responses. The second executes the actual Worker `enrollDevice()`, actual SQL and all 40 SQLite migrations, injecting one exception after the primary insert/consume transaction commits. No Cloudflare or real device tokens are accessed.

Observed base: `1d8b183564f1d8498c0b71ae7e35e924787e8010` with eight copies of the Codex WIP, hashes in snapshot.json. Frozen local QA source: `/tmp/hara-commander-r13-pre-enroll-rgqgez92/source` on the Núcleo. The Git review commit contains scripts/evidence, not a rewrite of Codex product files.

To run, copy both scripts to an isolated QA directory and provide `HARA_PEER_SOURCE` pointing to a frozen source directory that contains `apps/commander/scripts/test_linux_r11_pre_enroll.py`, `apps/commander/src`, and `apps/commander/migrations`.

```bash
HARA_PEER_SOURCE=/tmp/hara-commander-r13-pre-enroll-rgqgez92/source python3 -B peer_malformed_enrollment.py
HARA_PEER_SOURCE=/tmp/hara-commander-r13-pre-enroll-rgqgez92/source /home/sartorius/.nvm/versions/node/v24.15.0/bin/node --disable-warning=ExperimentalWarning peer_worker_postcommit.mjs
```

Python requires cryptography for ephemeral RSA fixture. Node 24 includes node:sqlite. **Exit 2 means the defect was reproduced, not PASS**. The ordinary R11 pre-enrollment test and offline release integrity gate passed (exit 0,0); live HTTPS release check correctly returns exit 2 HOLD.

Expected negative cases: incomplete or invalid 2xx response leaves an in-memory mock enrollment with no revoke; lost HTTP ACK after a mock server commit leads to consumed pairing and failed retry; a post-commit failure while writing a device-selection row in the real Worker leaves an ACTIVE device with consumed pairing and no credential delivered. Positive Worker success control passes with a separate pairing.

The report is `docs/operations/HARA_COMMANDER_PEER_REVIEW_R13_ENROLLMENT_20261020.md`. No customer contents, private keys, real secrets, remote enrollments, D1 migrations, production Agents or CodeX source files are included.
