# H.A.R.A. Commander — Linux OpenAI tunnel startup choice

Date: 2026-10-09
Canonical line: `local/commander-product-current`
Scope: customer product MCP, not HARA Services administrative MCP.

## User contract

On the Commander site's **Connect computer > Linux** onboarding flow:

- Checkbox **Iniciar o túnel OpenAI automaticamente** (opt-in; unchecked by default).
- Checked: the copied installer command carries
  `HARA_COMMANDER_TUNNEL_AUTOSTART=ON`. The installer persists this mode in
  the local mode-0600 `device.env`. After the user provides OpenAI tunnel
  configuration, the Agent configures a **systemd --user** unit with
  `enable --now`.
- Unchecked: the installer carries `...=OFF` (default, fail-closed).
  `hara-commander tunnel configure` creates a user unit but leaves it
  **disabled and stopped**. User starts/stops it explicitly:
  `hara-commander tunnel start` and `hara-commander tunnel stop`.
- Already installed? `hara-commander tunnel autostart on` enables/starts
  the configured user unit; `... autostart off` disables boot startup
  without stopping an active session (use `tunnel stop` to disconnect).
  `hara-commander tunnel status` reports the startup preference, service
  state and local signed-lease authority without disclosing credentials.
- If the tunnel is not configured, `tunnel start` refuses with an
  actionable `NEXT_COMMAND=hara-commander tunnel configure`; setting
  autostart ON before configuration only arms the preference.
- `hara-commander start` is intentionally **unchanged**: it opens the
  separate local operator approval session, and is not the tunnel service.
- The site checkbox is an **installer choice**, not a cloud-origin remote
  command. Changing a box on the site does not remotely modify an installed
  host. The UI exposes the exact local command for existing devices.
- The user systemd manager starts enabled units at login. Automatic boot
  startup without login requires Linux user *linger* (do not silently grant
  privilege or enable linger).
- An active tunnel is **not** execution authority. The signed local product
  lease remains a 6-hour gate; `AUTHORIZATION_EXPIRED` must fail closed.
  The credential/tunnel profile must be configured locally, not supplied
  in chat or embedded in command-line arguments.
- The existing Cloudflare Commander identity/control-plane and telemetry
  are unchanged. No new MCP endpoint, request-per-tool, HARA Services
  proxy, or remote-control bypass was introduced.

## Example new installation and use

From the Commander site, choose Linux + approval policy, then optionally
check automatic startup. Copy the generated installation command.

After installing:
1. `hara-commander tunnel configure` (local OpenAI tunnel ID and runtime key)
2. `hara-commander authorize` (device-bound one-time code from site)
3. Manual choice: `hara-commander tunnel start`
4. Verify: `hara-commander tunnel status` and `hara-commander doctor`

Existing devices can use `hara-commander tunnel autostart on|off` and the
normal status/start/stop commands once the signed version is installed.

## Qualification

- `python3 apps/commander/scripts/validate_linux_tunnel_start_modes.py`
  runs a Bash installer resolver matrix, isolated Python Agent/systemd
  simulations (never touches customer systemd or credentials), UI contract,
  lease-gate preservation, no credential output and local mode transitions.
- Existing local-tunnel control-plane, product UI, telemetry, cost/economics
  and syntax validators pass with the source patch.
- Candidate Agent 0.3.43 and its installer were staged with exact hashes
  on nucleo-a and services; local read-only `tunnel autostart` and
  `tunnel status` commands exercised with no profile.
- The installed Agents were not replaced: nucleo-a=0.3.41,
  services=0.3.40. Neither the customer OpenAI tunnel nor local
  execution lease is asserted active.
- The **signed release and PROD Worker migration** remain separate gates.
  The public signed manifest was behind the source candidate at last
  inspection. Do not deploy the updated Agent or public site
  before canonical signed-manifest, signature/readback, rollback and
  real customer product MCP E2E checks succeed.
