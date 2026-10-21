# HARA Commander — R18 Worker code provenance gap (QA only)

Review commit head: `3a9131785cf74ed5303b7474b4c2cf2d5ebd61a6`.

**Negative test / no production changes.** `peer_worker_code_bound.py` exercises `stage()`, `require_signed_stage()`, and `upload_version()` with an official *historical* signed v4 bundle as a local fixture. Wrangler is patched with a harmless reader, not invoked. The test deliberately alters only `src/worker.js` in a disposable detached clone, while retaining the reviewed `public/` tree, then restores the source in `finally`. It reproduces a missing gate: static signed asset digest passes but a different Worker source is offered to the uploader. Exit **2 means negative reproduction**, not acceptance PASS.

To run safely, make a **disposable detached-head clone** at `/tmp/hara-commander-r18-worker-drift-*` of the observed source commit. From this evidence directory run:

```bash
HARA_PEER_QA_ROOT=/tmp/hara-commander-r18-worker-drift-20261021 python3 -B peer_worker_code_bound.py
```

The script explicitly refuses locations outside this QA namespace and refuses a checked-out branch. It requires the selected historical signed v4 fixture; v4 is **not** a production rollout recommendation. Python/cryptography installed. No private key, commercial enrollment, client data, or Cloudflare API call.

Result file: `r18-worker-source-gate-results.json`. The report `docs/operations/HARA_COMMANDER_PEER_REVIEW_R18_WORKER_PROVENANCE_20261021.md` specifies P0 gate, acceptance and distinction from R16's static-asset-only snapshot. The Codex tracked implementation remains untouched.
