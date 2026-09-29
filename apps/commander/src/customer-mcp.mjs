import {
  McpServer,
  createMcpHandler,
} from "@modelcontextprotocol/server";
import { z } from "zod";

export const CUSTOMER_MCP_TOOLS = Object.freeze([
  "hara.health",
  "hara.functions.list",
  "hara.functions.describe",
  "hara.functions.invoke",
  "hara.receipts.get",
]);

const SECURITY_SCHEMES = Object.freeze([
  { type: "oauth2", scopes: ["openid"] },
]);

function publicToolResult(value) {
  const result = value && typeof value === "object" ? value : {};
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result),
      },
    ],
    structuredContent: result,
  };
}

function publicToolError(error) {
  const code = String(error?.message || "COMMANDER_MCP_TOOL_FAILED")
    .replace(/[^A-Z0-9_:-]/gi, "_")
    .slice(0, 160);
  return {
    isError: true,
    content: [
      {
        type: "text",
        text: JSON.stringify({
          ok: false,
          code: code || "COMMANDER_MCP_TOOL_FAILED",
        }),
      },
    ],
  };
}

function toolConfig({
  title,
  description,
  inputSchema,
  openWorldHint = false,
}) {
  return {
    title,
    description,
    inputSchema,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint,
    },
    _meta: {
      securitySchemes: SECURITY_SCHEMES,
    },
  };
}

export function createCustomerMcpServer({ executeTool }) {
  if (typeof executeTool !== "function") {
    throw new Error("CUSTOMER_MCP_EXECUTOR_REQUIRED");
  }

  const server = new McpServer({
    name: "H.A.R.A. Commander",
    version: "1.0.0",
  });

  const call = (toolId) => async (args, ctx) => {
    try {
      const value = await executeTool({
        tool_id: toolId,
        arguments: args || {},
        mcp_request_id: ctx?.mcpReq?.id ?? null,
        abort_signal: ctx?.mcpReq?.signal,
      });
      return publicToolResult(value);
    } catch (error) {
      return publicToolError(error);
    }
  };

  server.registerTool(
    "hara.health",
    toolConfig({
      title: "H.A.R.A. Health",
      description:
        "Check the authenticated subject's selected Commander computer and Agent health through the governed customer product path.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.health"),
  );

  server.registerTool(
    "hara.functions.list",
    toolConfig({
      title: "List H.A.R.A. Functions",
      description:
        "List governed local function identifiers and states exposed by the selected Commander Agent. The published invoke boundary remains read-only.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.functions.list"),
  );

  server.registerTool(
    "hara.functions.describe",
    toolConfig({
      title: "Describe H.A.R.A. Function",
      description:
        "Describe one exact governed local function on the selected Commander computer using a minimized public projection.",
      inputSchema: z.object({
        function_id: z.string().min(1).max(180),
      }).strict(),
    }),
    call("hara.functions.describe"),
  );

  server.registerTool(
    "hara.functions.invoke",
    toolConfig({
      title: "Invoke Read-only H.A.R.A. Function",
      description:
        "Invoke one exact admitted READ_ONLY local function on the selected Commander computer. Arguments are passed without a shell.",
      inputSchema: z.object({
        function_id: z.string().min(1).max(180),
        argv: z.array(z.string().max(4096)).max(64).optional(),
      }).strict(),
      openWorldHint: true,
    }),
    call("hara.functions.invoke"),
  );

  server.registerTool(
    "hara.receipts.get",
    toolConfig({
      title: "Read H.A.R.A. Receipt",
      description:
        "Read one audit receipt produced by the selected Commander Agent by ID or SHA-256 using a minimized public projection.",
      inputSchema: z.object({
        receipt_id_or_sha256: z.string().min(1).max(256),
      }).strict(),
    }),
    call("hara.receipts.get"),
  );

  return server;
}

export async function handleCustomerMcpRequest(
  request,
  {
    executeTool,
    authInfo = undefined,
    allowedHosts = undefined,
  },
) {
  if (Array.isArray(allowedHosts) && allowedHosts.length > 0) {
    const hostname = new URL(request.url).hostname.toLowerCase();
    if (!allowedHosts.map((value) => String(value).toLowerCase()).includes(hostname)) {
      return Response.json(
        { ok: false, code: "MCP_HOST_DENIED" },
        { status: 421, headers: { "cache-control": "no-store" } },
      );
    }
  }

  const handler = createMcpHandler(
    () => createCustomerMcpServer({ executeTool }),
    {
      legacy: "stateless",
      responseMode: "json",
      maxRequestBodySize: 256 * 1024,
      onerror: () => undefined,
    },
  );
  try {
    return await handler.fetch(request, { authInfo });
  } finally {
    await handler.close().catch(() => undefined);
  }
}
