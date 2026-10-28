# Bounded private distribution — 0.3.57

These scripts are a single-use QA distribution for the current two VMs on
physical Sentinela B. They do not expose a Commander API or change the public
release channel. Their predecessors under `qa-reentry-20261028/distribution`
remain unchanged.

## Fixed scope

- Bind: `192.168.10.23:18444`.
- Allowed clients: Windows `192.168.252.113/32` and Ubuntu
  `192.168.252.130/32`, through `virbr96`.
- Unit and firewall comment: `hara-connect-qa-0357-20261028`.
- Paths: the exact eight pinned signed files under `/releases/0.3.57/`.
  No directory listing, redirect, upload, alternative release, or API is served.
- Assets: the fixed private-0357 `signed` directory on Sentinela B.
- TLS: the existing `distribution-r3/tls/qa-server.crt` and `.key`. Certificate
  PEM and DER hashes are pinned. The key is loaded only by the TLS implementation;
  its root ownership, 0600 mode, single-link regular-file status and bounded size
  are checked. Neither TLS file is written or exported.
- Lifetime: at most 2,700 seconds, additionally bounded by
  **2026-10-28 18:40:00 UTC**. An expired start is refused. Start intent is
  exclusive and prevents silent reuse or renewal.

The existing `.56` service on port `18443` and its tagged rules are outside this
script's ownership. Cleanup selects only the new tag and fixed port/source rules.

## Lifecycle and failure cleanup

Run the control script as native root on Sentinela B with the fixed operation
`start`, `status`, or `stop`. `start` submits the transient unit without blocking
and reports `CONNECT_QA_DISTRIBUTION_START_REQUESTED`; this is not a READY result.
Confirm the unit, two nft rules, two tagged UFW rules, listener and actual HTTPS
payload before reporting readiness.

The transient unit runs `configure` as ExecStartPre and `cleanup` as ExecStopPost.
`configure` checks the exact systemd cgroup and invocation ID, and cannot be used
as a standalone persistent firewall opener. Both VM rules are independently
removed on cleanup. Partial configuration errors invoke cleanup immediately;
ExecStopPost also runs when startup fails or the service exits. A failed start
request attempts to stop the unit and invokes cleanup even if that stop command
fails.

The server loads and hash-checks all eight assets into memory, binds the fixed
socket, drops supplementary groups and root to UID/GID 65534, and sets
`no_new_privileges`. It uses normal TLS 1.2 or newer. Source-address checks exist
at both firewall and HTTP/TLS-accept layers.

The server has monotonic and absolute expiry checks plus a SIGALRM deadline to
interrupt a client stalled in TLS/header I/O. systemd RuntimeMaxSec supplies an
additional bound. Process exit closes the listener; ExecStopPost removes the
temporary firewall rules. The cleanup receipt reports CLOSED only after both
tagged rule sets and the listener are absent. An uncertain cleanup reports HOLD.

## Source review status

Syntax and the fixed-distribution contract were checked locally. This includes
the eight-file inventory and SUMS hash, source addresses, matching server pin,
same deadline and max lifetime in both scripts, and absence of any port-18443
operation. No local validation started a server, touched a firewall, accessed a
private key, or proved native cleanup. Native start/readback/stop receipts belong
to the deployment operator and must retain their actual outcomes.

This endpoint contains `.57` only. A controller that needs an immutable `.56`
release to validate its installed preimage must obtain that from its appropriate
trusted existing distribution; this server does not silently substitute `.57`
bytes for a `.56` path. Direct execution of a verified private update and testing
the public automatic-discovery path remain distinct validations.
