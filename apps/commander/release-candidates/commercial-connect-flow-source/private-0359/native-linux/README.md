# Native Ubuntu 0.3.58 → 0.3.59 QA

The coordinator verifies the existing Ubuntu domain `hara-review-linux`, UUID `d7a27a4a-41c3-4c14-a84e-187443566a3c`, and runs the pinned user driver as `commanderqa`, UID 2000. Its actions are `stage`, `run` and `result`; staging and execution are separate, recorded operations.

The driver requires the exact current 0.3.58 Agent (`c63cf76c3953e029f650227ec25cc167a95f93f145ef3c41f0379d07cc1b007d`), a fresh runtime and its valid existing DEV enrollment. Before dispatch, the retained 0.3.57 rollback (`79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13`) must remain unchanged. The new signed 0.3.59 Agent must match `df8b2d09c5447f8d405200538a841e669a8f165e9043701d6c8efcbfe5a34d38`; successful installation must retain the exact former 0.3.58 Agent as rollback.

The explicit private release is `https://192.168.10.23:18446/releases/0.3.59`. The existing pinned public certificate is reused with normal TLS verification in a process-local CA bundle. No system trust change, new enrollment, token prompt, or migration of the DEV origin is permitted. The preflight requires 280 seconds before the 19:35Z distribution deadline on 28 October 2026. A running signed installer is monitored to natural completion and is never terminated by the driver.

The create-once work directory is `/home/commanderqa/.local/share/hara-commander-connect-qa/upgrade-0359`. Success requires preserved config, unit, CLI, policy and enrollment, exact signed target bytes, a fresh new runtime, authenticated heartbeat, and the expected rollback.

Only `result.json`, `progress.json` and `preimage.json` may enter the evidence bundle. `config.before.private` and raw installer logs stay private. Actual native outcome and cleanup are established by their separate receipts; source preparation alone is not acceptance.
