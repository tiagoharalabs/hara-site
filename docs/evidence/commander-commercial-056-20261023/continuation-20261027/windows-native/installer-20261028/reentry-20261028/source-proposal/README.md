# Pairing payload preflight — isolated source proposal

Status: **source-only draft; native regression NOT_RUN; no deployment or release approval.**

The canonical signed Windows `.56` installer was read, not edited. Its SHA-256
remains `2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401`.

## Defect and minimum change

The public `.49` installer consumes a pairing code before downloading the Agent.
The canonical `.56` installer checks signed manifest/version metadata before the
prompt, but also waits until after enrollment to validate actual Agent bytes.
Consequently, a valid manifest paired with wrong asset bytes consumes a code and
requires enrollment rollback. The independent QA R5 wrapper prevents this in its
private QA path; the public installer has not received that protection.

The proposed function `Assert-InstallPayloadPreflight` downloads the real Agent
into a unique temporary `.ps1`, checks the existing signed manifest, size, hash,
version, parser and self-test, and removes the temporary file. It is called both
by `Invoke-Preflight` and immediately before the install pairing prompt.
The existing release signature and integrity functions are unchanged. All code
from the pairing prompt through enrollment, DPAPI configuration, task creation,
independent final integrity check and rollback is unchanged byte-for-byte.

**Limit:** this intentionally small change retains the original independent
Agent download after enrollment. It prevents consuming a token for a mismatch
already present during preflight, but cannot prevent a later server asset change
or download failure. The existing rollback remains necessary. Atomic immutable
release deployment is still required; this proposal does not repair the public
mixed release by itself.

## Files

- `build_source_candidate.py`: requires the exact canonical source hash and
  generates the candidate, diff and source review receipt without changing it.
- `windows.source-only-candidate.ps1`: unsigned candidate derived from `.56`.
- `windows.source-only.patch`: review diff, with intended source path
  `public/install/windows.ps1`; apply only after matching the actual source base.
- `source-review.json`: successful source checks and explicit scope limitations.
- `Test-PairingPreflight.ps1`: native Windows PowerShell 5.1 regression harness,
  **not run in this environment**.

The harness uses an ephemeral fixture RSA key and locally stubbed HTTP functions.
It executes the real candidate install tail through the preflight gates with a
prompt sentinel. Nine cases cover wrong hash at equal size, wrong size, invalid
signature, syntax error, self-test failure, version mismatch, download failure,
valid payload reaching the prompt, and the expanded preflight report. It checks
zero enrollment calls, temporary file cleanup and absence of product files.
No real Identity login, enrollment, product task, credentials or installed-product
lifecycle are involved; a harness PASS would not certify actual pairing.

Native invocation, when a legitimate QA native test context is available:

```powershell
powershell.exe -NoLogo -NoProfile -File .\Test-PairingPreflight.ps1
```

No execution-policy override is included. The normal authorized QA execution
context must permit source test scripts.

## Release boundary

Do not overwrite an already signed `.56` artifact with this candidate, modify a
manifest hash to match it, or serve it under the existing immutable release URL.
Adoption belongs in mutable repository source, followed by normal versioning,
tests, rebuild, signature and release promotion. The public `.41` manifest / `.52`
Agent / `.49` installer discrepancy remains a separate operational defect.

Local checks completed: canonical input hash; unique patch anchors; unchanged
signature/manifest/integrity functions; unchanged enrollment/DPAPI/task/rollback
tail; output candidate generation. Native syntax and regression execution are
explicitly outstanding.
