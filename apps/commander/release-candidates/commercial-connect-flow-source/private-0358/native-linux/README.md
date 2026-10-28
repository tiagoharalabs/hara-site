# Native Ubuntu 0.3.57 → 0.3.58 QA

This is a separate, create-once update attempt based on the recorded successful 0.3.57 R2 installation. It never enrolls a device or prompts for a token. The root operator uses the pinned coordinator against `hara-review-linux`, UUID `d7a27a4a-41c3-4c14-a84e-187443566a3c`, and launches the user driver as `commanderqa` UID 2000.

The precondition is the exact 0.3.57 Agent `79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13`, its valid existing DEV binding and current runtime. The retained 0.3.56 rollback must match `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`; its bytes and metadata are rechecked before dispatch. After a successful update, the rollback must exactly match the former 0.3.57 Agent.

The candidate is fetched from `https://192.168.10.23:18445/releases/0.3.58` using normal TLS verification and the same pinned public QA certificate. Trust changes are confined to the driver/installer processes. The driver requires its 280-second preflight allowance before the fixed 18:50Z distribution deadline. It never terminates a running signed installer.

The new work directory is `/home/commanderqa/.local/share/hara-commander-connect-qa/upgrade-0358`. Existing config, unit, CLI, approval policy, device identity and API origin must remain unchanged. Success requires exact signed target bytes, a new running 0.3.58 runtime, fresh heartbeat and authenticated binding.

Only `result.json`, `progress.json` and `preimage.json` are sanitized evidence. Never export `config.before.private` or raw installer logs. Actual execution and its outcome must be recorded separately; preparing these scripts is not native acceptance.
