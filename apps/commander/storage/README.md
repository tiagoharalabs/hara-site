# H.A.R.A. Commander Storage collector

The Customer Agent -> Cloudflare Worker/D1 path is independent of Storage.
Storage only **pulls** minimal metadata from D1 hourly. It neither handles
customer tools nor proxies customer MCP requests.

Source: `apps/commander/scripts/storage_collect_agent_telemetry.py`.
Storage target: `~/.local/bin/hara-commander-storage-collector.py`.
Local database: `~/.local/state/hara-commander-collector/agent-events.sqlite3`.
Authentication: a **read-only scoped Cloudflare API token**, loaded from mode
0600 `~/.config/hara-commander-collector/collector.env`; not Git or systemd
arguments. Cloudflare account/database identifiers are non-secret.

Install user service and timer to
`~/.config/systemd/user/hara-commander-telemetry-collector.{service,timer}`.
`loginctl show-user sartorius -p Linger` should be `yes` on Storage.
After token provisioning, `systemctl --user daemon-reload`, run
`python3 ~/.local/bin/hara-commander-storage-collector.py --self-test`
and a one-shot run, then
`systemctl --user enable --now hara-commander-telemetry-collector.timer`.

The timer MUST stay **disabled** until the exact scoped token has been
provisioned and live readback succeeds. No new API route or privileged
identity database credentials are required.

The collector performs only a fixed SQL SELECT via Cloudflare's D1 API
`/accounts/{account_id}/d1/database/{database_id}/query`. It stores
no command text, paths, stdout, file contents, or secrets. It advances a
transactional composite watermark `(received_at_utc,event_id)` and stores
idempotently by `event_id`. The only metadata copied is tenant/device
reference, event kind, times, duration, count and Agent version.

The rollout remains gated by canonical release-signing and real end-to-end
LOCAL_TUNNEL proof. The PROD database migrations 0029/0030 can be applied
independently; a migration alone does not make the Agent released.
