// Aggregate only the bounded recent call metadata already returned by the
// activity read. Values come from server timestamps, never from Agent clocks.
const STAGES = ["queue_ms", "execution_ms", "total_ms"];

function stageSummary(rows, field) {
  const values = rows.map((row) => row[field])
    .filter((value) => typeof value === "number" && Number.isFinite(value) && value >= 0)
    .sort((a, b) => a - b);
  const percentile = (rank) => values.length
    ? values[Math.ceil(values.length * rank / 100) - 1]
    : null;
  return {
    sample_size:values.length,
    missing_count:rows.length - values.length,
    avg:values.length ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)) : null,
    p50:percentile(50),
    p95:percentile(95),
    p99:percentile(99),
  };
}

function metrics(rows) {
  return Object.fromEntries(STAGES.map((stage) => [stage, stageSummary(rows, stage)]));
}

function groups(rows, keys) {
  const grouped = new Map();
  for (const row of rows) {
    const labels = keys.map((key) => String(row[key] || "UNKNOWN"));
    const identifier = JSON.stringify(labels);
    if (!grouped.has(identifier)) grouped.set(identifier, { labels, rows:[] });
    grouped.get(identifier).rows.push(row);
  }
  return [...grouped.values()]
    .sort((a, b) => b.rows.length - a.rows.length || JSON.stringify(a.labels).localeCompare(JSON.stringify(b.labels)))
    .slice(0, 6)
    .map((group) => ({
      ...Object.fromEntries(keys.map((key, index) => [key, group.labels[index]])),
      completed_rows:group.rows.length,
      metrics:metrics(group.rows),
    }));
}

export function summarizeRecentLatency(transactions, requestedLimit) {
  const rows = Array.isArray(transactions) ? transactions : [];
  const completed = rows.filter((row) => row?.state === "COMPLETED");
  return {
    source:"CLOUD_SERVER_TIMESTAMPS",
    scope:"RECENT_RETURNED_CALLS",
    percentile_method:"NEAREST_RANK",
    requested_limit:requestedLimit,
    returned_rows:rows.length,
    completed_rows:completed.length,
    metrics:metrics(completed),
    by_tool:groups(completed, ["tool_id"]),
    by_device:groups(completed, ["computer"]),
    by_transport:groups(completed, ["transport_mode"]),
    by_tool_device:groups(completed, ["tool_id", "computer", "transport_mode"]),
  };
}
