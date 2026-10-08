# H.A.R.A. Commander — Canonical Functions Hardening

Date: 2026-10-08
Branch: `local/commander-canonical-functions-hardening-20261008`
Base: `eff1b2d1e75ddd82c99ede363750951b711bd625`
State: **LINUX / LOCAL_TUNNEL SOURCE QUALIFICATION PASS**

## Goal

Improve the canonical H.A.R.A. Commander function contract without increasing the
Simple MCP surface above 24 tools.

The hardening targets correctness, safety, continuation semantics, concurrency,
truthful audit metadata and better function discovery.

## Findings and fixes

### 1. Symlink leaf mutation risk

The prior Linux implementation used `Path.resolve(strict=True)` in several
filesystem paths. A symlink leaf could therefore be resolved to its target
before a mutation.

This was dangerous for operations such as edit/delete and also made
`filesystem.info` misreport a symlink as the target file.

Fixed:

- `filesystem.info` now uses leaf lstat semantics and reports:
  - `type=symlink`
  - `is_symlink`
  - `symlink_target`
  - `resolved_path` when resolvable.
- write/edit/delete/copy/rollback/create-directory reject a symlink leaf.
- move preserves the symlink itself instead of moving its target.
- read-only read/hash may follow a symlink but report that fact.
- mutating reads use `O_NOFOLLOW` where applicable.

### 2. TOCTOU / concurrent file change

Added optional `expected_sha256` to:

- write_file / hara.files.write
- edit_block / hara.files.edit
- delete_file / hara.files.delete

The precondition is carried through:

Simple MCP -> Full MCP -> device-tool-contract -> Agent.

Wrong SHA returns a structured non-retryable conflict and performs no mutation.

Preimage metadata now also binds device, inode, size and mtime_ns. The Agent
revalidates the target against the preimage immediately before mutation.

### 3. Unsafe path shape drift

Local functions previously accepted path strings containing control characters
that cloud `pathArg` rejected.

Linux canonical functions now reject:

- empty paths;
- paths longer than 4096 chars;
- C0 control characters;
- DEL.

Process `cwd` uses the same guard.

### 4. Continuation / pagination

`filesystem.read` now returns:

- `eof`
- `has_more`
- `next_offset`
- `content_truncated`
- `continuation_safe`
- `oversized_line`

Reads stop at a safe complete-line boundary before the 64 KiB response budget.
A single oversized logical line is explicitly marked and never advertises an
unsafe `next_offset`.

`filesystem.list` now accepts `offset` and returns `has_more/next_offset`.

`filesystem.search` now accepts `offset`, sorts traversal deterministically
and returns `has_more/next_offset/scan_truncated`.

`process.list` now returns both returned and available counts plus a truncated
flag.

### 5. Truthful local authority

The Agent previously emitted stale relay-oriented metadata during LOCAL_MCP.

Fixed:

- device.info reports the actual product transport mode;
- LOCAL_MCP receipts record `transport_mode=LOCAL_MCP`;
- local result/receipt authority is `HARA_COMMANDER_LOCAL`;
- local health reports H.A.R.A. Services as bypassed/not in data plane.

### 6. Canonical function discovery

`functions.describe` now returns a real `CONTRACT` for all 13 canonical
read-only functions:

- argv shape;
- bounds;
- result hints;
- continuation semantics;
- symlink semantics.

`functions.list` rows include canonical domain and risk class.

### 7. MCP semantic alignment

- Copy descriptions now say regular file, matching runtime behavior.
- Edit and move destructive hints are aligned across Full and Simple MCP.
- FILE_PRECONDITION_FAILED and SYMLINK_MUTATION_DENIED are structured
  operational outcomes rather than opaque tool failures.

## Dynamic proof

PASS:

- symlink info semantics;
- write/edit/delete/copy symlink leaf denied;
- symlink target unchanged;
- symlink move preserves link;
- O_NOFOLLOW symlink denial;
- stale preimage / TOCTOU revalidation denial;
- SHA precondition success and failure/no-mutation;
- path-control-character denial;
- process cwd path guard;
- safe read pagination and EOF;
- oversized-line no-unsafe-continuation;
- deterministic list pagination;
- deterministic search pagination;
- process-list bounded metadata;
- truthful LOCAL_MCP result authority;
- truthful LOCAL_MCP receipt authority;
- enriched function describe/catalog.

Real `nucleo-a` local MCP canary:

`COMMANDER_LOCAL_MCP_FULL_CANARY_33_OF_33=PASS`

Existing contract, Full MCP, Simple MCP, edge and static validators remain PASS.

Official readiness:

`COMMANDER_PREPROD_CANONICAL_FUNCTIONS=PASS`

The next readiness gate stops fail-closed at:

`RELEASE_SHA256_DRIFT:agent/linux.py`

This is expected because the source candidate remains 0.3.43 while the published
signed manifest remains 0.3.41.

## Remaining next wave

1. Windows canonical parity:
   - reparse-point/symlink semantics;
   - optional SHA preconditions;
   - pagination/continuation result parity.
   This must be implemented using Windows semantics rather than copying POSIX.

2. Process contract hardening:
   - normalize memory fields across Linux/Windows;
   - enrich managed-session output contract;
   - audit lifecycle/resource bounds.

3. Read-only root symlink transparency:
   - diff/search/list/workspace can expose requested vs resolved root explicitly.

4. Move rollback semantics:
   - current move is correctly marked destructive;
   - there is no generic directory-move rollback artifact yet.

No PROD promotion was performed.

State markers:

`COMMANDER_CANONICAL_FUNCTIONS_LINUX_HARDENING=PASS`

`COMMANDER_CANONICAL_FUNCTIONS_SYMLINK_SAFETY=PASS`

`COMMANDER_CANONICAL_FUNCTIONS_SHA_PRECONDITION=PASS`

`COMMANDER_CANONICAL_FUNCTIONS_CONTINUATION=PASS`

`COMMANDER_CANONICAL_FUNCTIONS_LOCAL_MCP_33_OF_33=PASS`

`COMMANDER_CANONICAL_FUNCTIONS_PROD=PENDING_SIGNED_RELEASE`
