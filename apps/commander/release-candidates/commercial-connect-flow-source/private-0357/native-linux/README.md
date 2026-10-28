# Native Ubuntu QA — direct signed 0.3.56 → 0.3.57 update

`native_private_0357_upgrade.py` is a one-device QA driver. It must run as the existing `commanderqa` account, UID 2000, on `hara-review-linux`. The root operator must verify the VM UUID/name through QGA before invoking it. This directory contains source only; preparing it does not execute an upgrade.

## Fixed scope

- Existing device: `HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889`.
- Existing API origin: `https://hara-commander-dev-v2.tiago-sartori.workers.dev`.
- Existing policy: `PERSISTENT_TRUSTED`, `OUTBOUND_RELAY`.
- Existing Linux Agent SHA-256: `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`.
- Explicit private release: `https://192.168.10.23:18444/releases/0.3.57`.
- New Agent: 265,620 bytes, SHA-256 `79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13`.
- New installer: 72,524 bytes, SHA-256 `2b11dd4cb5219d64692d9df764544752c04f4cb2518742d5c54a3f631178cbed`.
- Manifest SHA-256: `d1a9361f5edec6c926d6febc7990e9b0c00df28f5131c6ffe1146ebe348554d0`.
- Signature file SHA-256: `5637d5861c49c170af55a8d86f8051df78785c39f4a17b06a41b5c8ed25ddef7`.

The existing frozen controller is imported only after its exact `a696a233…` source hash is checked. Its existing pinned v2 signature verifier validates the manifest. The controller's discovery or mutation entry points are not used.

## Required staging

Place the public QA certificate at:

`/home/commanderqa/.local/share/hara-commander-connect-qa/qa-release-0357.crt`

The admitted PEM SHA-256 is `c15308e100ba014d463b20cc56568e2183c4c50e2b2b672af38a0926d1c879c1`; the DER SHA-256 is `893aeec40a123d5fd74fd312fa1ed90e4c9881e10a562cdc126026c3d848f29e`. The root operator stages this public file as owner 2000, mode 0444. No private key is needed or accepted.

The driver creates this directory **once**, mode 0700:

`/home/commanderqa/.local/share/hara-commander-connect-qa/upgrade-0357`

Do not precreate that directory. A second invocation with the same work directory is refused; collect the first invocation's receipt instead of rerunning it blindly.

The private distribution closes at **15:40 Brasília on 28 October 2026 (18:40Z)**. The driver requires a full 280-second preflight allowance before that deadline. Its installer child runs in a new process group without a controlling terminal. Only the explicit `update` action is invoked. Once dispatched, the signed transaction is allowed to finish naturally: elapsed time beyond 180 seconds or private logs beyond 2 MiB are reported, never used to terminate the installer. Progress is written every 15 seconds; a fresh 90-second independent observation budget starts after the child exits.

## Trust and credentials

Artifact downloads use normal hostname/TLS verification with the exact public QA certificate added to this process's SSL context. The child receives a private CA bundle containing the ordinary Ubuntu roots and that certificate through `CURL_CA_BUNDLE` and `SSL_CERT_FILE`. No root certificate store or persistent environment setting is modified.

Authenticated heartbeat requests use the ordinary Ubuntu roots and the existing configured API origin. The artifact host never receives a device credential. Neither enrollment nor a pairing-token prompt is permitted.

## Evidence and failure behavior

Before updating, the driver preserves exact private preimages and records ownership/modes/hashes for the config, Agent, unit, and CLI. It verifies the effective systemd definition, current runtime, and authenticated binding. Signed manifest, signature, installer and Agent bytes are all pinned before execution. The preimages and public certificate are rechecked under the connection lock before the child starts. Immediately before dispatch, the effective systemd executable, definition, original main PID, running state, and fresh .56 runtime are rechecked under that same lock.

Success requires the exact .57 Agent, changed/fresh .57 runtime startup and heartbeat, authenticated binding, unchanged config bytes/policy, unchanged unit and CLI, unchanged frozen controller and system CA bundle, and the installer's exact old-Agent rollback file. The success state is `PASS_DIRECT_SIGNED_0357_UPDATE`.

The signed installer owns its update/rollback behavior. The driver does not perform a second file restore, credential reset, or service start/stop on failure. It never sends a termination signal to the signed installer. An unexpected monitoring error waits for the live transaction before releasing the connection lock; independent state attestation follows natural child exit. Output-size limits are enforced only after the transaction has finished, so they cannot interrupt swap, restart, or rollback. A target or original Agent may be reported connected in that attestation while the overall operation remains `HOLD`.

Only collect **`result.json`**, **`progress.json`**, and, if needed, **`preimage.json`** as sanitized evidence. `config.before.private` contains the existing credential and must never enter Git, chat, or evidence bundles. Raw installer stdout/stderr files are also private and must not be copied wholesale.

This verifies a direct update from an explicit private signed release. It does **not** certify automatic same-origin latest-release discovery, new reviewer pairing, production distribution, or public release readiness.
