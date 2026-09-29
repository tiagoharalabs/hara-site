function trimText(value, limit = 65536) {
  if (typeof value !== "string") return null;
  if (value.length <= limit) return value;
  return value.slice(0, limit) + "\n[HARA_COMMANDER_OUTPUT_TRUNCATED]";
}

function projectBlocker(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const out = {};
  if (typeof value.code === "string" && value.code) out.code = value.code;
  if (value.details && typeof value.details === "object" && typeof value.details.risk_class === "string") {
    out.details = { risk_class: value.details.risk_class };
  }
  return Object.keys(out).length ? out : null;
}

function projectHealth(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const key of [
    "services_bridge_state",
    "hara_services_state",
    "registered_function_count",
    "executable_function_count",
    "authority",
  ]) {
    if (key in value) out[key] = value[key];
  }
  return out;
}

function projectList(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const key of ["registered_function_count", "executable_function_count", "active_function_count"]) {
    if (Number.isInteger(value[key])) out[key] = value[key];
  }
  if (Array.isArray(value.domains)) {
    out.domains = value.domains.filter((x) => typeof x === "string");
  }
  if (Array.isArray(value.functions)) {
    out.functions = value.functions
      .filter((entry) => entry && typeof entry === "object" && typeof entry.function_id === "string")
      .map((entry) => {
        const item = { function_id: entry.function_id };
        if (typeof entry.state === "string") item.state = entry.state;
        return item;
      });
  }
  return out;
}

function projectDescribe(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const key of ["function_id", "state", "pending_domain_binding"]) {
    if (key in value) out[key] = value[key];
  }
  if (value.IDENTITY && typeof value.IDENTITY.domain === "string") out.domain = value.IDENTITY.domain;
  if (value.PURPOSE && typeof value.PURPOSE.description_pt_br === "string") {
    out.description = value.PURPOSE.description_pt_br;
  }
  let risk = value.EXECUTION_SEMANTICS?.risk_class;
  if (risk == null) risk = value.AUTHORITY?.risk_class;
  if (typeof risk === "string") out.risk_class = risk;
  let changeIntent = value.EXECUTION_SEMANTICS?.change_intent_required;
  if (changeIntent == null) changeIntent = value.AUTHORITY?.change_intent_required;
  if (typeof changeIntent === "boolean") out.change_intent_required = changeIntent;
  let failClosed = value.AUTHORITY?.fail_closed;
  if (failClosed == null) failClosed = value.FAILURE_ROLLBACK?.fail_closed;
  if (typeof failClosed === "boolean") out.fail_closed = failClosed;
  return out;
}

function projectInvoke(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const key of ["function_id", "risk_class", "process_exit_code", "domain_success_inferred"]) {
    if (key in value) out[key] = value[key];
  }
  const stdout = trimText(value.stdout);
  const stderr = trimText(value.stderr);
  if (stdout !== null) out.stdout = stdout;
  if (stderr) out.stderr = stderr;
  return out;
}

function projectReceipt(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  for (const key of [
    "tool_id",
    "function_id_if_any",
    "transport_mode",
    "operational_authority",
    "mutation_class",
    "state",
    "payload_values_persisted",
  ]) {
    if (key in value) out[key] = value[key];
  }
  return out;
}

function projectResult(toolId, value) {
  if (toolId === "hara.health") return projectHealth(value);
  if (toolId === "hara.functions.list") return projectList(value);
  if (toolId === "hara.functions.describe") return projectDescribe(value);
  if (toolId === "hara.functions.invoke") return projectInvoke(value);
  if (toolId === "hara.receipts.get") return projectReceipt(value);
  return {};
}

export function projectCustomerToolResponse(toolId, response) {
  const value = response && typeof response === "object" && !Array.isArray(response) ? response : {};
  const projected = {
    state: value.state ?? null,
    operational_authority: value.operational_authority ?? null,
    runtime_authority_from_chatgpt: value.runtime_authority_from_chatgpt ?? null,
    mutation_performed: value.mutation_performed ?? null,
    result: projectResult(toolId, value.result),
  };
  if (typeof value.bridge_receipt_sha256 === "string") {
    projected.bridge_receipt_sha256 = value.bridge_receipt_sha256;
  }
  const blocker = projectBlocker(value.blocker);
  if (blocker) projected.blocker = blocker;
  return projected;
}
