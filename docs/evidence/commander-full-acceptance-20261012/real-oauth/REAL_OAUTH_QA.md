# Real OAuth and organic QA2 acceptance

The normal QA2 chain passed: legitimate ZITADEL human login with OAuth2 authorization code + PKCE S256, normal portal callback and cookie, organic Trial tenant creation, normal portal pairing, signed Windows Agent 0.3.53, customer MCP discovery and read-only calls, minimized receipt readback and quota accounting.

QA2 IdP subject `394861028946477060` created tenant `HARA-TENANT-BNRKHV5P7_1SBJSL8FZ_HYYR` through the portal callback. No QA2 D1 seed was used. The DEV self-service acceptance route was explicitly enabled for the two disposable QA identities; production guards and global IdP policies were preserved. The separate QA1 subject `394859086664957956` used an explicitly seeded QA Trial binding and provides a separate bearer-authentication proof.

The single disposable public DCR client used genuine authorization-code exchange, PKCE, state and the QA users' verified password Session API checks. IAM maintenance credentials created and later clean up the disposable IdP resources; they were never used as human customer MCP bearer tokens. The portal's existing OAuth client was preserved.

The original QA2 portal cookie selected the one owned device `HARAQA5312` / `HARA-DEVICE-6644a8cb-8a82-4f0f-8828-879a1c5a3261`. Normal portal pairing enrolled the Windows clone. The signed native Agent session was ACTIVE with matching operator PID/start metadata before dispatch. Customer MCP with the genuine QA2 bearer returned PASS for `list_devices`, `ping`, `get_device_info` and `get_receipt`. The device-info receipt SHA256 is `63d763e83cbdad799d1d9a21a24c7f2f2bbc5adf842fde3a0f84eefcf0228c63`; receipt metadata identified `HARA_COMMANDER_AGENT`, `HARAQA5312`, `READ_ONLY_OR_NONE_V1`, PASS and `payload_values_persisted=false`. One Trial unit was committed; 9999 of 10000 remain.

Both QA identities completed normal MCP initialize, initialized notification and tools/list with 33 tools. Metadata-only replay kept quota unchanged. A supplied caller field did not override the bounded QA2 context observed. A process request targeting a nonexistent QA computer was refused with GRANT_MISSING before execution. No mutation or process request executed on the paired device. One authentic portal callback replay was rejected with OIDC_STATE_REPLAYED, without minting a new portal session.

Two local harness assumptions were corrected: Streamable HTTP requires Accept to include both JSON and SSE, and the minimized receipt contract returns computer at the outer level rather than device_id inside result. The physical product calls returned PASS; the final receipt/quota check used metadata-only reads and did not repeat the metered device-info call.

Evidence:
- `normal_signup_mcp_pairing_proof.json`: consolidated OAuth, normal signup, protocol, bounded grant/privacy checks, callback replay and pairing.
- `normal_signup_windows53_mcp_read_receipt_proof.json`: physical Agent read, receipt and quota proof.
- `oauth_callback_replay_proof.json`: normal callback replay rejection.
- `../client-quota/qa2-organic-signup-d1-readback.json`: independently owned read-only database confirmation.

The protocol was exercised through the normal HTTPS API and redirects/cookies, not a browser-rendered login interface. All passwords, PATs, login-session values, authorization codes, OAuth bearers, cookie values and pairing tokens stayed inside private executors or files. Public evidence contains no credential values. New private files were mode0600.

The .54R2 normal QA2 portal pairing/select and real Windows read/receipt/quota chain subsequently passed with one debit1→2. Normal uninstall portal readback confirmed the new device REVOKED/offline. Exact cleanup then removed both QA users, four registered sessions, both OAuth bearers, the disposable DCR client, private cookie/pairing/state files and the two exact QA DEV tenants. The real portal client, global policies, Linux soak fixtures and canary custody were preserved. See normal_signup_windows54_mcp_read_receipt_proof.json, qa2_windows54_uninstall_portal_readback.json, exact-qa-idp-cleanup-054.json and exact-qa-d1-cleanup-054.json. Earlier53evidence remains historical.
