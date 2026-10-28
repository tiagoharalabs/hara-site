# Linux connection flow — source proposal

## Scope and status

`commander_connect.py` is an independent controller for the requested interaction:

1. Read the current user's device configuration without displaying credentials.
2. Validate an existing credential with the configured origin's authenticated heartbeat.
3. If paired, preserve the device and check the signed stable release. Install a newer verified release automatically.
4. If not paired, ask for the token generated after login on the same origin's portal, pair, validate, and update when necessary.
5. Start the per-user Agent and require current runtime plus authenticated connection evidence before reporting `CONNECTED`.

The controller defaults to `connect` and also accepts `conectar`. An explicit QA command can run it as:

```sh
python3 /path/to/commander_connect.py connect
```

The source-only installer candidate now embeds the exact frozen controller bytes and defaults to `connect`; `conectar` is an alias. It passes the explicit `connect` argument to the embedded Python program. Verified child installer invocations always specify `install`, `update`, `pair-existing`, or `re-enroll`, so they do not recursively invoke the default flow. The four-file manifest contract is preserved because the controller becomes part of `install/linux.sh` rather than an extra release asset.

The existing `hara-commander` Agent symlink is deliberately not replaced. A current QA deployment can provide a separate `hara-commander-connect` command or a **Conectar HARA Commander** Desktop shortcut. The embedded default is implemented in the unsigned source candidate; the shipped product's installer and Agent CLI remain unchanged until a new signed release is admitted.

## Release discovery and update rules

Discovery requests the configured origin's `/release/agent-manifest.json` and signature using the legitimate `HARA-Commander-Connect/1` user agent. The controller validates the pinned `commander-release-v2` key, exact manifest schema/file set, stable channel, product, and semantic version. The target is derived as the same origin's `/releases/<version>`. The immutable manifest must have identical bytes to the signed latest manifest; its signature is verified independently.

Both the matching Linux installer and Agent payload are checked against signed sizes and SHA-256 before an installer action or token prompt. The current Agent is checked against its own signed immutable release before it is started or updated. Requests retain normal TLS verification and deny redirects. Device credentials are sent only to the configured Commander origin and never to discovery endpoints, other origins, command-line arguments, or logs.

An older advertised channel cannot downgrade a newer installed Agent. A valid existing enrollment remains valid when release discovery or integrity checks fail: the controller reports `PAIRING_VALID_UPDATE_HOLD` and exits nonzero without stopping the running Agent, modifying its files, or requesting another token. If a mutating update fails, the controller rechecks the same configuration and authenticated credential before stating that pairing remains valid.

An explicit `--qa-release-url` is limited to a signed, versioned path on the same origin. It selects that particular QA release; it is not a substitute for a functioning latest-release channel.

## Installed but unpaired

The existing signed 0.3.56 installer rejects preexisting Agent directories when `device.env` is absent. It has no `pair-existing` action. The controller therefore requires this exact marker in the **signed and verified** release installer before invoking the new action:

```text
# HARA_COMMANDER_PAIR_EXISTING=1
```

An old installer without that capability produces `SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED` before asking for a token. Existing directories are not renamed or deleted to make a partial installation resemble a clean one.

`linux.source-only-candidate.sh` adds the corresponding action. It checks ownership, rejects symlinks and unexpected units, validates the Agent against its own signed release, reloads systemd and verifies the effective FragmentPath, DropInPaths, Type, and ExecStart. It then uses a controlled enrollment transaction. Existing Agent, unit, and CLI are preserved. On attach failure, only the newly created device configuration is removed; an existing rejected configuration is restored for re-enrollment failures.

If server-side revocation cannot be confirmed during rollback, a private 0600 `.pending-device-revoke-*.json` recovery record retains the newly issued credential. The operation remains failed/pending. This record is secret material and must never be copied into Git, evidence reports, or chat. Remote revocation is not claimed successful until the server confirms it.

## Validation

Local tests use ephemeral RSA signatures, synthetic HTTP responses, stubbed installer actions, and isolated temporary files. They do **not** claim native Ubuntu installation, real reviewer enrollment, or a public release.

### Native controller check reported by the root operator

On **28 October 2026 at 13:58 America/Sao_Paulo**, the root operator ran the exact frozen controller on the existing Ubuntu QA installation. Its development enrollment returned authenticated heartbeat HTTP 200. The installed Agent was **0.3.56**, while the signed stable channel offered **0.3.54**. The controller returned **`PAIRING_VALID_UPDATE_HOLD` / `AUTO_DOWNGRADE_REFUSED`**, preserving the configuration, Agent bytes, and original `hara-commander` CLI symlink. No new pairing token was requested and no downgrade occurred.

The QA helper was deployed at `/home/commanderqa/.local/share/hara-commander-connect-qa`, with the separate `hara-commander-connect` command and Desktop/application-menu launchers. This native check validates the existing-paired, older-channel path only. The unsigned installer candidate's new enrollment, embedded default, and update/rollback paths remain **not natively executed**.

### Reproduce the source candidate and local fixtures

From the Git repository root:

```sh
python3 apps/commander/release-candidates/commercial-connect-flow-source/linux/build_linux_candidate.py
```

The builder first checks the original local product-source layout and then the repository sibling `apps/commander/release-candidates/commercial-0.3.56-source/install/linux.sh`. Both layouts require the same pinned input hash. It does not choose another source after a hash mismatch.

From the candidate's `linux` directory:

```sh
python3 test_connect_flow.py
python3 test_pair_existing_rollback.py
python3 test_embedded_connect.py
bash -n linux.source-only-candidate.sh
```

The controller tests cover current paired no-op, automatic newer update, older channel refusal, connection failure, ambiguous 401, immutable/latest mismatch, payload corruption, unknown signing key, installed/unpaired capability gating, token-terminal gating, update after pairing, preservation of pairing after update failure, and preservation of credentials. Filesystem fixtures verify attach rollback, re-enroll rollback, and private pending-revocation recovery. Embedding fixtures compare the exact frozen controller bytes, exercise default and alias dispatch with a stub interpreter, preserve explicit install/update guards, and check explicit child-action delegation without recursion.

## Delivery limits

- The standalone `commander_connect.py` helper is not an asset covered by the current four-file release manifest. Its byte-identical content is now embedded in the proposed `install/linux.sh` candidate, ready to be covered by that installer's hash in a future signed release.
- `linux.source-only-candidate.sh` is unsigned and intentionally remains separate from the unchanged signed 0.3.56 installer.
- A production release must admit and version the embedded installer candidate, sign the new four-file release, and run native enrollment/update/rollback tests. The existing Agent CLI integration is separate; this change does not replace its symlink or imply that an installed old Agent already supports the new default.
- The pinned key is not silently replaced with a key advertised by the network. Future key rotation needs a trusted release/admission change.
- No public deployment, automatic migration from development to production, identity reset, or VM modification is performed by these local files.

The canonical signed source is `../../linux.sh` in the local product-source layout or `../../commercial-0.3.56-source/install/linux.sh` in the repository layout, SHA-256 `a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f`.
