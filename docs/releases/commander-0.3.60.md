# Commander 0.3.60

Published to the development and production portals on 2026-10-28.

- Authenticated workspace members, including reviewers, can clear the revoked-device history projection from **Devices → History**. Active devices, revocation records, calls, receipts, and audit records remain intact. The operation requires confirmation and checks the expected record count.
- Linux and Windows installations provide `hara commander pair` and `hara-commander pair` for pairing after access is revoked, without reinstalling the agent. Generate a fresh code in the installation's portal environment and enter it at the command prompt. On Windows, open a new terminal after updating so the new command is on PATH.
- The portal's Advanced instructions show the pairing command. Install commands use the portal's environment; existing installations retain their configured environment.
- Current download paths and immutable `/releases/0.3.60` paths contain matching agents, installers, signed manifests, and public verification keys. Immutable 0.3.59 files remain available to verify existing installations.

Validation passed: 88 history interface/API cases, 7 SQLite isolation checks, 33 Linux connection/pairing cases, 4 shipped Linux command checks, and 37 native Windows cases. Signed upgrades from 0.3.59 preserved existing enrollment and platform configuration. Public release files were checked in both environments. Existing successful enrollments were retained during validation; no user history was deleted.

This release covers history cleanup, pairing commands, and installer distribution. It does not certify unrelated features or complete product launch readiness.
