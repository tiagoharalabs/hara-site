# H.A.R.A. Commander — Linux dual-origin bootstrap trust

Date: 2026-10-06
State: CLOSED_PASS (Linux)

## Goal

Reduce first-install trust concentration on the Commander web origin without
changing the already-closed signed Agent/update path.

## Design

The Linux verified bootstrap is distributed through an immutable GitHub commit.
It downloads the canonical Linux installer and release-signing public key from
two independent HTTPS origins:

- `https://commander.haralabs.com.br`
- `https://raw.githubusercontent.com/tiagoharalabs/hara-site/...`

It requires exact byte equality for both the installer and public release key
before the Commander-origin installer is allowed to execute.

Fail-closed conditions include:
- primary or GitHub fetch failure;
- non-HTTPS Commander URL;
- redirect;
- installer mismatch;
- release-key mismatch.

The GitHub comparison source is pinned to canonical commit:
`35d9a5e19e045ebbfdd128360dddbe6c72a569fe`.

## Immutable bootstrap verifier

Verifier source commit:
`29fbb42f402f1ef4de3cd7e6927abd48f638e66f`

Immutable raw path:
`https://raw.githubusercontent.com/tiagoharalabs/hara-site/29fbb42f402f1ef4de3cd7e6927abd48f638e66f/apps/commander/public/bootstrap/linux-dual-origin.sh`

Safe verification-only command:

```bash
curl -fsS --proto '=https' --tlsv1.2 --location --max-redirs 0 --max-time 30 \
  'https://raw.githubusercontent.com/tiagoharalabs/hara-site/29fbb42f402f1ef4de3cd7e6927abd48f638e66f/apps/commander/public/bootstrap/linux-dual-origin.sh' \
  | bash -s -- --verify-only
```

## Live proof

Immutable GitHub verifier execution on nucleo-a:
- exit 0;
- HARA_BOOTSTRAP_DUAL_ORIGIN=PASS;
- HARA_BOOTSTRAP_VERIFY_ONLY=PASS;
- installer SHA-256 `76a3a19e2d3a3b0ab63dc1198f559f4869a2f995de959382b5d2d44d92da0713`;
- release-key SHA-256 `ee4bbbca568b90c50551cd6797f921abdb988afe104e4644132154418723b7b4`.

Tamper simulation:
- deliberately different installer bytes between origins;
- verifier exited with code 20;
- `HARA_BOOTSTRAP_INSTALLER_ORIGIN_MISMATCH=TRUE`;
- installer was not executed.

Preprod:
- COMMANDER_PREPROD_BOOTSTRAP_DUAL_ORIGIN=PASS;
- COMMANDER_SOURCE_PREPROD_READY=PASS.

## Boundary

This closes an independent dual-origin bootstrap path for Linux.
It does not claim the same out-of-band bootstrap path for Windows yet.
The existing signed manifest / Agent update trust remains unchanged.

LINUX_DUAL_ORIGIN_BOOTSTRAP=CLOSED_PASS
LINUX_BOOTSTRAP_GITHUB_IMMUTABLE_VERIFIER=CLOSED_PASS
LINUX_BOOTSTRAP_LIVE_VERIFY_ONLY=CLOSED_PASS
LINUX_BOOTSTRAP_TAMPER_DENY=CLOSED_PASS
WINDOWS_DUAL_ORIGIN_BOOTSTRAP=PENDING_SEPARATE_SLICE
RELEASE_MANIFEST_INDEPENDENT_TRUST_ANCHOR=CLOSED_PASS
