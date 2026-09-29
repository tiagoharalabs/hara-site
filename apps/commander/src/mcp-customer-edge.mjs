const MCP_PROTOCOL_VERSION = "2025-06-18";

const TOOL_DEFINITIONS = Object.freeze([
  {
    name: "hara.health",
    title: "H.A.R.A. Health",
    description: "Check the authenticated subject's selected Commander computer and Agent health through the governed product path.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["openid"] }] },
  },
  {
    name: "hara.functions.list",
    title: "List H.A.R.A. Functions",
    description: "List governed local function identifiers and states exposed by the selected Commander Agent. The published invoke boundary remains read-only and may refuse mutation-capable functions.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["openid"] }] },
  },
  {
    name: "hara.functions.describe",
    title: "Describe H.A.R.A. Function",
    description: "Describe one exact governed local function on the selected Commander computer by function_id using a public minimized projection of its purpose, state and risk semantics.",
    inputSchema: {
      type: "object",
      properties: { function_id: { type: "string", minLength: 1, maxLength: 180 } },
      required: ["function_id"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["openid"] }] },
  },
  {
    name: "hara.functions.invoke",
    title: "Invoke Read-only H.A.R.A. Function",
    description: "Invoke one exact admitted READ_ONLY local function on the selected Commander computer through the governed product bridge. Arguments are passed without a shell.",
    inputSchema: {
      type: "object",
      properties: {
        function_id: { type: "string", minLength: 1, maxLength: 180 },
        argv: { type: "array", items: { type: "string" }, maxItems: 0 },
      },
      required: ["function_id"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["openid"] }] },
  },
  {
    name: "hara.receipts.get",
    title: "Read H.A.R.A. Receipt",
    description: "Read one audit receipt produced by the selected Commander Agent by SHA-256 using a public minimized projection without internal tracing metadata.",
    inputSchema: {
      type: "object",
      properties: {
        receipt_id_or_sha256: { type: "string", pattern: "^[0-9a-fA-F]{64}$" },
      },
      required: ["receipt_id_or_sha256"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: { securitySchemes: [{ type: "oauth2", scopes: ["openid"] }] },
  },
]);

const TOOL_NAMES = new Set(TOOL_DEFINITIONS.map((tool) => tool.name));

function jsonRpc(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function jsonRpcError(id, code, message) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

function response(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function cleanPublicError(error) {
  const code = String(error?.message || "INTERNAL_ERROR");
  return /^[A-Z][A-Z0-9_]{0,119}$/.test(code) ? code : "INTERNAL_ERROR";
}

function toolResult(value) {
  const structured = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    content: [{ type: "text", text: JSON.stringify(structured) }],
    structuredContent: structured,
    isError: false,
  };
}

function toolError(code) {
  return {
    content: [{ type: "text", text: JSON.stringify({ ok: false, code }) }],
    structuredContent: { ok: false, code },
    isError: true,
  };
}

export function customerMcpToolDefinitions() {
  return TOOL_DEFINITIONS.map((tool) => structuredClone(tool));
}

export function normalizeCustomerToolPayload(name, args) {
  const value = args && typeof args === "object" && !Array.isArray(args) ? args : {};
  if (name === "hara.health" || name === "hara.functions.list") return {};
  if (name === "hara.functions.describe") {
    return { function_id: String(value.function_id || "") };
  }
  if (name === "hara.functions.invoke") {
    return {
      function_id: String(value.function_id || ""),
      arguments: { argv: Array.isArray(value.argv) ? value.argv.map(String) : [] },
    };
  }
  if (name === "hara.receipts.get") {
    return { receipt_id_or_sha256: String(value.receipt_id_or_sha256 || "").toLowerCase() };
  }
  throw new Error("MCP_TOOL_NOT_FOUND");
}

export async function handleCustomerMcpProtocol(request, { callTool }) {
  if (request.method === "GET") {
    return new Response(null, {
      status: 405,
      headers: { allow: "POST", "cache-control": "no-store" },
    });
  }
  if (request.method !== "POST") {
    return response(jsonRpcError(null, -32600, "Invalid Request"), 405);
  }

  let body;
  try {
    body = await request.json();
  } catch (_error) {
    return response(jsonRpcError(null, -32700, "Parse error"), 400);
  }

  if (!body || body.jsonrpc !== "2.0" || typeof body.method !== "string") {
    return response(jsonRpcError(body?.id ?? null, -32600, "Invalid Request"), 400);
  }

  const id = body.id;
  const method = body.method;
  const params = body.params && typeof body.params === "object" ? body.params : {};

  if (method === "notifications/initialized" && id === undefined) {
    return new Response(null, { status: 202, headers: { "cache-control": "no-store" } });
  }

  if (method === "initialize") {
    return response(jsonRpc(id, {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "H.A.R.A. Commander", version: "1.0.0" },
      instructions: "Operate only on the authenticated user's selected Commander computer through the five governed read-only tools. No arbitrary shell or filesystem surface is available.",
    }));
  }

  if (method === "ping") return response(jsonRpc(id, {}));

  if (method === "tools/list") {
    return response(jsonRpc(id, { tools: customerMcpToolDefinitions() }));
  }

  if (method === "tools/call") {
    const name = String(params.name || "");
    if (!TOOL_NAMES.has(name)) {
      return response(jsonRpc(id, toolError("MCP_TOOL_NOT_FOUND")));
    }
    try {
      const payload = normalizeCustomerToolPayload(name, params.arguments);
      const result = await callTool(name, payload, { rpc_id: id });
      return response(jsonRpc(id, toolResult(result)));
    } catch (error) {
      return response(jsonRpc(id, toolError(cleanPublicError(error))));
    }
  }

  return response(jsonRpcError(id, -32601, "Method not found"));
}

export const CUSTOMER_MCP_PROTOCOL_VERSION = MCP_PROTOCOL_VERSION;
