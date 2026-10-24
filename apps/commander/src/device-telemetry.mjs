// Exact, metadata-only schema for infrequent Event V2 liveness piggyback.
// Reject arbitrary tool IDs, arguments, command text, paths and customer data.
export const TELEMETRY_SCHEMA = "hara.commander-device-telemetry.v1";
export const TELEMETRY_WINDOW_DAYS = 7;
export const TELEMETRY_MAX_COUNTER = 1_000_000_000;
export const TELEMETRY_FIELDS = Object.freeze([
  "connections", "disconnects", "reconnects", "session_errors",
  "durable_calls", "transient_calls", "transient_failures",
  "liveness_attempts", "transport_pings", "connected_seconds",
]);

function fail() { throw new Error("CHANNEL_TELEMETRY_INVALID"); }

export function canonicalChannelTelemetry(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const expected = ["schema", "window_days", ...TELEMETRY_FIELDS].sort();
  const given = Object.keys(value).sort();
  if (given.length !== expected.length
    || given.some((key, i) => key !== expected[i])) fail();
  if (value.schema !== TELEMETRY_SCHEMA
    || value.window_days !== TELEMETRY_WINDOW_DAYS) fail();
  const normalized = { schema: TELEMETRY_SCHEMA, window_days: 7 };
  for (const field of TELEMETRY_FIELDS) {
    const count = value[field];
    if (!Number.isSafeInteger(count) || count < 0 || count > TELEMETRY_MAX_COUNTER) fail();
    normalized[field] = count;
  }
  return normalized;
}

export function telemetryRollupQuery(env, tenantId, deviceId, atUtc, telemetry) {
  // Tenant/device IDs are supplied by the authenticated socket attachment,
  // never by payload values.
  const normalized = canonicalChannelTelemetry(telemetry);
  const columns = ["tenant_id", "device_id", "received_at_utc", "window_days", ...TELEMETRY_FIELDS];
  const update = ["received_at_utc = excluded.received_at_utc",
    "window_days = excluded.window_days",
    ...TELEMETRY_FIELDS.map(field => field + " = excluded." + field)].join(", ");
  const sql = "INSERT INTO commander_device_telemetry_snapshot (" +
    columns.join(", ") + ") SELECT " + columns.map(() => "?").join(", ") +
    " FROM commander_devices d WHERE d.tenant_id = ? AND d.device_id = ?" +
    " AND d.state = 'ACTIVE' AND d.revoked_at_utc IS NULL" +
    " AND d.tunnel_mode = 'EVENT_V2'" +
    " ON CONFLICT(tenant_id, device_id) DO UPDATE SET " + update +
    " WHERE excluded.received_at_utc >= commander_device_telemetry_snapshot.received_at_utc";
  return env.PRODUCT_DB.prepare(sql).bind(
    tenantId, deviceId, atUtc, normalized.window_days,
    ...TELEMETRY_FIELDS.map(field => normalized[field]),
    tenantId, deviceId,
  );
}

// Read only on demand. Every row is selected through the authenticated tenant;
// no public endpoint can submit or override a tenant ID.
export const DEVICE_TELEMETRY_SELECT = [
  "SELECT d.device_id, d.device_name AS computer, d.platform,",
  "d.agent_version, d.tunnel_mode, d.last_seen_at_utc,",
  "t.received_at_utc AS last_reported_at_utc, t.window_days,",
  ...TELEMETRY_FIELDS.map(field => "t." + field),
  "FROM commander_devices d",
  "LEFT JOIN commander_device_telemetry_snapshot t",
  "ON t.tenant_id = d.tenant_id AND t.device_id = d.device_id",
  "WHERE d.tenant_id = ? AND d.state = 'ACTIVE' AND d.revoked_at_utc IS NULL",
].join(" ");

export async function readTenantDeviceTelemetry(env, tenantId, computer = null, limit = 50) {
  if (!env?.PRODUCT_DB) throw new Error("TELEMETRY_PRODUCT_DB_MISSING");
  if (typeof tenantId !== "string" || !tenantId || tenantId.length > 180)
    throw new Error("TELEMETRY_TENANT_REQUIRED");
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100)
    throw new Error("TELEMETRY_LIMIT_INVALID");
  if (computer !== null && (
    typeof computer !== "string" || !computer.trim() || computer.length > 120
  )) throw new Error("TELEMETRY_COMPUTER_INVALID");
  const byComputer = computer !== null
    ? " AND LOWER(d.device_name) = LOWER(?)" : "";
  const sql = DEVICE_TELEMETRY_SELECT + byComputer + " ORDER BY d.created_at_utc DESC LIMIT ?";
  const params = computer !== null
    ? [tenantId, computer, limit]
    : [tenantId, limit];
  const response = await env.PRODUCT_DB.prepare(sql).bind(...params).all();
  return {
    schema: "hara.commander-device-telemetry-report.v1",
    window_days: 7,
    count: (response.results || []).length,
    devices: (response.results || []).map(row => ({
      device_id: row.device_id,
      computer: row.computer,
      platform: row.platform,
      agent_version: row.agent_version,
      transport_mode: row.tunnel_mode,
      last_seen_at_utc: row.last_seen_at_utc,
      last_reported_at_utc: row.last_reported_at_utc ?? null,
      metrics: row.last_reported_at_utc
        ? Object.fromEntries(TELEMETRY_FIELDS.map(field => [field, row[field]]))
        : null,
    })),
  };
}
