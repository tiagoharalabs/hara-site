# Commander 0.3.56 — commercial source proposal

This is adapted source for review, not an admitted or signed public release.
Exact source inputs are recorded in `origin.json`; source diffs and native QA
receipts are under `docs/evidence/commander-commercial-056-20261023/`.

Linux: canonical .54 plus the documented renewal/revocation and no-op effect
ports. Both platforms add enrollment-bound local sessions, separate local
state by origin/device/tenant/credential context, check receipt ownership and
foreign call metadata, and preserve explicit consent. No Founder manifest,
wrapper, device identifier, credential, allowlist or local state is carried.

History opens clean in the new local scope. `history [limit [before_id]]` reads
current scoped history; `history legacy [limit [before_id]]` exposes sanitized old SQLite/JSONL
only to the local operator and never imports it into a different enrollment.
Old sessions are deliberately not reusable authority. Old budgets/leases and
preimages are preserved in their previous locations and are not implicitly
adopted by a new enrollment.

Browser CORS alone cannot prove a tenant. Linux loopback details deny browser
Origin requests until a tenant-proof integration is reviewed; CLI history is
available. Direct Linux MCP requires a signed product lease AND a fresh cloud
access-check; unavailable/revoked identity fails closed. The backend access-check
contract must be admitted with the release. Windows remains OUTBOUND_RELAY;
this proposal does not claim native Windows LOCAL_TUNNEL feature parity.

Installers fetch from `/releases/0.3.56/` (or an explicitly supplied release URL)
while API/enrollment remain at the configured Commander origin. v1 URLs are
not overwritten. Windows no longer supplies ExecutionPolicy Bypass. Client
policy compatibility/Authenticode is an admission decision, not bypassed here.
Linux lifecycle rollback preserves stopped state and reports partial recovery
honestly; preexisting unrelated files are refused.

The generator's explicit `--draft` mode allows a complete unsigned review
bundle without declaring proposed source reviewed/admitted. The normal signed
release gate, production selection and independent manifest admission pin remain
closed. No signing or publication is performed by the draft path.

Closed-beta review corrections: Linux's full self-test now anchors its synthetic
workspace. Both update paths retain the exact preimage after success or failure;
Windows also compensates for swap/start exceptions, and rollback PASS requires
fresh startup attestation on both platforms. Source tests and the isolated
PowerShell lifecycle harness cover these changes without installing an Agent.
The controlled pre-execution stall probe still returns `HOLD_P0_322`: heartbeat
is coupled to execution. Windows 11 ACL/DPAPI/SQLite/Task Scheduler acceptance,
native release admission and the authorized signature remain required. The
wire-contract channel remains `stable`; private-beta scope grants no production
selection, signature or installation authority.
