# Commander 0.3.57 — private QA candidate preparation

This directory prepares a new version for the validated connect-flow source. It
does not replace the signed 0.3.56 release, sign a bundle, install software, or
publish assets. The builder accepts only the fixed source bytes recorded in its
constants; callers cannot supply alternative hash pins or a different version.

## Inputs and transformation

`build_private_0357.py` requires these absolute paths:

- `--source056`: the original source directory containing `agent/linux.py` and
  `agent/windows.ps1` from the signed 0.3.56 four-file release.
- `--connect-source`: the connect-flow source directory containing the frozen
  Linux and Windows candidate installers and standalone controllers.
- `--public-jwk`: the existing public v2 key file, SHA-256
  `4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b`.
- `--output`: a new private directory outside the source trees and Git checkouts.
  Its parent must already exist and satisfy the ownership/permission checks.

The complete inputs are read and checked before creating the output. Every input
must be a bounded regular file at its pinned hash; symlinks and changed files are
refused. Output creation uses exclusive files, directories mode 0700 and files
mode 0600, followed by byte/hash readback and fsync. An existing output is refused.
An unexpected write failure leaves the new private directory for inspection; the
builder does not delete or overwrite it on a retry.

The two Agents change only their single version declaration from `0.3.56` to
`0.3.57`. The Linux installer changes exactly eight version literals, and the
Windows installer exactly five. Both transformations are checked as reversible
byte substitutions of equal length. Both embedded controllers remain byte for
byte unchanged; their frozen hashes and unique embedding are checked separately.
Pair-existing and re-enrollment capability markers remain present.

The output contains the four artifacts, an **unsigned**
`release/agent-manifest.json`, the public key, `release/SHA256SUMS`, and
`BUILD-REPORT.json`. The wire channel remains `stable` for compatibility, while
the build report explicitly records private QA scope, no signature, no native
acceptance, no installation and no production mutation.

## Signing boundary

The prior `sign_private_commander_0356_v2.py` pins remain unchanged. That signer
must reject the new artifact hashes. The new
`sign_private_commander_0357_v2.py` pins the exact four output hashes and exact
manifest bytes from the build reported by the root operator on physical
Sentinela B. It retains the same trusted v2 public key and produces a new private
output directory. The build report is evidence to review and pin; it is not a
caller-controlled replacement for signature verification or release admission.

The pinned manifest SHA-256 is
`d1a9361f5edec6c926d6febc7990e9b0c00df28f5131c6ffe1146ebe348554d0`.
`SIGNER-SOURCE-REVIEW.json` records the exact source provenance. Only the module
docstring version, release version, manifest hash and four artifact pins changed
from the original signer; the remaining Python AST was compared and is unchanged.
Preparing this script did not read a private key or execute signing.

The existing signing implementation validates private-key ownership and mode,
rejects symlinks, disables dumps before reading key bytes, checks public-key
matching, and verifies the resulting signature. These checks must be retained in
the new version. Private key material must remain at the authorized signing host;
it must not be copied into this repository, build reports, or chat.

## Native validation and distribution

The root operator has reported the frozen Windows source passing native parsing,
23 controller fixtures and 14 isolated transaction fixtures. The Linux source has
24 isolated fixture results. Those results are source evidence and do not by
themselves certify the new 0.3.57 bundle.

A private native update requires an exact signed 0.3.57 distribution, validation
of its physical payload bytes, the existing 0.3.56 preimages, and authenticated
runtime evidence after the update under the actual QA user. Configuration,
approval mode, ownership, and the existing device enrollment must be preserved.
Direct execution of a verified update is distinct from proving automatic latest
release discovery through the product controller.

The Windows controller permits an explicit versioned HTTPS QA distribution while
retaining the actual Commander API origin; device credentials must not be sent
to the distribution host. Its current-Agent check also needs the signed immutable
release for the installed version. The Linux controller restricts discovery to
the configured origin. The Linux installer's explicit supported release-URL
override can exercise a verified native update separately; that does not prove
the same-origin automatic discovery path.

Fresh pairing tests require a legitimately issued code from the intended account.
An existing pairing must not be deleted, moved to another origin, or replaced
merely to manufacture that test. Native new pairing, native upgrade and rollback,
and public discovery/publication status must each retain their actual result.

Publishing a coherent latest manifest, immutable release and matching web
bootstrap is a separate operation. Neither the private build nor its signature
fixes the public mixed-version distribution by itself.
