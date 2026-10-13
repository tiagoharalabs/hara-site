# Windows expired read — read-only diagnosis

The call `HARA-CALL-8fc82367-c9b8-4f99-a16b-ad89d29cfc5c` was created at 23:14:37.581Z, claimed at 23:14:39.662Z, expired at 23:15:27.581Z and reconciled as `DEVICE_CALL_EXPIRED` at 23:17:03.872Z on 2026-10-12. This was a read-only call; its 50-second TTL is separate from the 15-minute approval deadline used for eligible Windows mutating calls.

Owner-side diagnostic via the H.A.R.A. Commander direct integration found zero console events and zero owner-local receipts for this request. It parsed the full available console tail without truncation or malformed rows and examined all 184 receipt files. The surrounding 23:14–23:16Z window contains successful unrelated calls. No transport error is present in that window.

QGA under SYSTEM was denied access to the owner console events by the existing ACL. The diagnostic switched to the owner through the product; no ACL was changed. SYSTEM inability to read these files is not an Agent failure.

Source checks: `apps/commander/public/agent/windows.ps1` (SHA-256 `4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a`) writes `RECEIVED` before tool execution and creates the receipt before posting `/api/device/calls/complete`. A standalone completion-post failure in the normal worker therefore does not explain both missing earlier console events and a missing local receipt.

`apps/commander/src/worker.js`, function `claimNextDeviceCall`, records claim time and device state but no consumer process or transport identity. A successful server claim alone does not establish which local process received it. `apps/commander/experimental/event_v2_windows_agent.ps1`, functions `Get-NextDurableCall` and `Invoke-DurableDrain`, can consume the same durable endpoint and does not write normal console events. Runtime flags and historical process times must establish whether such a consumer was present before attributing this call to it.

Causal status: **UNPROVEN**. Plausible alternatives include loss of the claim response, a different consumer, or failure before local logging. The original command was not retried. No installed Agent, Windows task, session, runtime state or signature bundle was changed.

Process review supplied by `win49_cutover_review`: extra guest processes 7572 and 2912 in the 23:43:16Z snapshot were started at 23:43:14Z and 23:43:15Z. They postdate the expired claim and cannot explain it. They were not established as EventV2 runtime workers; diagnostic command lines may themselves match source-name filters.
