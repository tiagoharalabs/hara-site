import {
  McpServer,
  createMcpHandler,
} from "@modelcontextprotocol/server";
import { z } from "zod";

export const CUSTOMER_MCP_SIMPLE_TOOLS = Object.freeze([
  "list_devices",
  "get_config",
  "get_usage_stats",
  "get_activity",
  "ping",
  "get_device_info",
  "read_file",
  "read_multiple_files",
  "write_file",
  "edit_block",
  "create_directory",
  "list_directory",
  "move_file",
  "copy_file",
  "delete_file",
  "search",
  "get_file_info",
  "list_processes",
  "start_process",
  "read_process_output",
  "interact_with_process",
  "kill_process",
  "list_sessions",
  "get_recent_tool_calls",
]);

const SECURITY_SCHEMES = Object.freeze([
  { type: "oauth2", scopes: ["openid"] },
]);

function publicToolResult(value) {
  const result = value && typeof value === "object" ? value : {};
  return {
    content: [{ type: "text", text: JSON.stringify(result) }],
    structuredContent: result,
  };
}

function publicToolError(error, args = undefined) {
  const code = String(error?.message || "COMMANDER_MCP_TOOL_FAILED")
    .replace(/[^A-Z0-9_:-]/gi, "_")
    .slice(0, 160);

  if (code === "DEVICE_OFFLINE") {
    const result = {
      state: "UNAVAILABLE",
      runtime_authority_from_chatgpt: false,
      mutation_performed: false,
      customer_services_relay: false,
      blocker: {
        code: "DEVICE_OFFLINE",
        category: "DEVICE_AVAILABILITY",
        retryable: true,
      },
      result: {
        available: false,
        device_state: "OFFLINE",
      },
    };
    if (args?.computer) result.computer = String(args.computer).slice(0, 120);
    return publicToolResult(result);
  }

  return {
    isError: true,
    content: [{
      type: "text",
      text: JSON.stringify({ ok: false, code: code || "COMMANDER_MCP_TOOL_FAILED" }),
    }],
  };
}

function toolConfig({
  title,
  description,
  inputSchema,
  openWorldHint = false,
  readOnlyHint = true,
  destructiveHint = false,
  idempotentHint = true,
}) {
  return {
    title,
    description,
    inputSchema,
    annotations: { readOnlyHint, destructiveHint, idempotentHint, openWorldHint },
    _meta: { securitySchemes: SECURITY_SCHEMES },
  };
}

function deviceArgs(args = {}) {
  return args.computer ? { computer: args.computer } : {};
}

export function createSimpleCustomerMcpServer({ executeTool }) {
  if (typeof executeTool !== "function") throw new Error("CUSTOMER_MCP_EXECUTOR_REQUIRED");

  const server = new McpServer({
    name: "H.A.R.A. Commander Simple",
    version: "1.0.0",
  });

  const call = (internalTool, mapArgs = (args) => args || {}) => async (args, ctx) => {
    try {
      const headers = ctx?.http?.req?.headers;
      const transportRequestId =
        headers?.get?.("x-openai-request-id")
        || headers?.get?.("x-request-id")
        || headers?.get?.("traceparent")
        || headers?.get?.("cf-ray")
        || ctx?.sessionId
        || crypto.randomUUID();
      const mapped = mapArgs(args || {});
      const toolId = typeof internalTool === "function" ? internalTool(args || {}) : internalTool;
      const value = await executeTool({
        tool_id: toolId,
        arguments: mapped,
        mcp_request_id: ctx?.mcpReq?.id ?? null,
        transport_request_id: transportRequestId,
        abort_signal: ctx?.mcpReq?.signal,
      });
      return publicToolResult(value);
    } catch (error) {
      return publicToolError(error, args);
    }
  };

  const computer = z.string().min(1).max(120).optional();

  server.registerTool(
    "list_devices",
    toolConfig({
      title: "List Devices",
      description: "List enrolled computers and their online/offline state.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.devices.list", () => ({})),
  );

  server.registerTool(
    "get_config",
    toolConfig({
      title: "Get Config",
      description: "Get the selected computer's available capabilities, approval mode, grants and version support.",
      inputSchema: z.object({ computer }).strict(),
    }),
    call("hara.capabilities", (args) => ({ ...deviceArgs(args) })),
  );

  server.registerTool(
    "get_usage_stats",
    toolConfig({
      title: "Get Usage Stats",
      description: "Get plan and usage counters. No customer content is returned.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.usage", () => ({})),
  );

  server.registerTool(
    "get_activity",
    toolConfig({
      title: "Get Activity",
      description: "Get privacy-safe operational activity and recent call metadata.",
      inputSchema: z.object({
        window: z.enum(["24h", "7d", "30d"]).optional(),
        limit: z.number().int().min(1).max(100).optional(),
      }).strict(),
    }),
    call("hara.activity", (args) => ({
      ...(args.window ? { window: args.window } : {}),
      ...(args.limit !== undefined ? { limit: args.limit } : {}),
    })),
  );

  server.registerTool(
    "ping",
    toolConfig({
      title: "Ping",
      description: "Check whether a computer is reachable through H.A.R.A. Commander.",
      inputSchema: z.object({ computer }).strict(),
    }),
    call("hara.ping", (args) => ({ ...deviceArgs(args) })),
  );

  server.registerTool(
    "get_device_info",
    toolConfig({
      title: "Get Device Info",
      description: "Get OS, architecture, Agent and device information.",
      inputSchema: z.object({ computer }).strict(),
    }),
    call("hara.device.info", (args) => ({ ...deviceArgs(args) })),
  );

  server.registerTool(
    "read_file",
    toolConfig({
      title: "Read File",
      description: "Read a text file with optional line offset and length.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        offset: z.number().int().min(0).optional(),
        length: z.number().int().min(1).max(5000).optional(),
      }).strict(),
    }),
    call("hara.files.read", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      ...(args.offset !== undefined ? { offset: args.offset } : {}),
      ...(args.length !== undefined ? { length: args.length } : {}),
    })),
  );

  server.registerTool(
    "read_multiple_files",
    toolConfig({
      title: "Read Multiple Files",
      description: "Read several text files in one request.",
      inputSchema: z.object({
        computer,
        paths: z.array(z.string().min(1).max(4096)).min(1).max(10),
        offset: z.number().int().min(0).optional(),
        length: z.number().int().min(1).max(5000).optional(),
      }).strict(),
    }),
    call("hara.files.read_many", (args) => ({
      ...deviceArgs(args),
      paths: args.paths,
      ...(args.offset !== undefined ? { offset: args.offset } : {}),
      ...(args.length !== undefined ? { length: args.length } : {}),
    })),
  );

  server.registerTool(
    "write_file",
    toolConfig({
      title: "Write File",
      description: "Write or append text to a file.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        content: z.string().max(1024 * 1024),
        mode: z.enum(["rewrite", "append"]).optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.write", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      content: args.content,
      mode: args.mode || "rewrite",
    })),
  );

  server.registerTool(
    "edit_block",
    toolConfig({
      title: "Edit Block",
      description: "Apply a focused text replacement to one file.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        old_string: z.string().min(1).max(1024 * 1024),
        new_string: z.string().max(1024 * 1024),
        replace_all: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.edit", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      old_text: args.old_string,
      new_text: args.new_string,
      replace_all: Boolean(args.replace_all),
    })),
  );

  server.registerTool(
    "create_directory",
    toolConfig({
      title: "Create Directory",
      description: "Create a directory.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        parents: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      idempotentHint: true,
    }),
    call("hara.files.create_directory", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      parents: args.parents !== false,
    })),
  );

  server.registerTool(
    "list_directory",
    toolConfig({
      title: "List Directory",
      description: "List files and directories with bounded recursive depth.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        depth: z.number().int().min(1).max(8).optional(),
        limit: z.number().int().min(1).max(1000).optional(),
      }).strict(),
    }),
    call("hara.files.list", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      ...(args.depth !== undefined ? { depth: args.depth } : {}),
      ...(args.limit !== undefined ? { limit: args.limit } : {}),
    })),
  );

  server.registerTool(
    "move_file",
    toolConfig({
      title: "Move File",
      description: "Move or rename a file or directory.",
      inputSchema: z.object({
        computer,
        source: z.string().min(1).max(4096),
        destination: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.move", (args) => ({
      ...deviceArgs(args),
      source: args.source,
      destination: args.destination,
    })),
  );

  server.registerTool(
    "copy_file",
    toolConfig({
      title: "Copy File",
      description: "Copy a file or directory.",
      inputSchema: z.object({
        computer,
        source: z.string().min(1).max(4096),
        destination: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false,
      idempotentHint: false,
    }),
    call("hara.files.copy", (args) => ({
      ...deviceArgs(args),
      source: args.source,
      destination: args.destination,
    })),
  );

  server.registerTool(
    "delete_file",
    toolConfig({
      title: "Delete File",
      description: "Delete a file using H.A.R.A. reversible preimage protection.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.delete", (args) => ({ ...deviceArgs(args), path: args.path })),
  );

  server.registerTool(
    "search",
    toolConfig({
      title: "Search",
      description: "Search file names or text content. Returns bounded results in one request.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
        pattern: z.string().min(1).max(4096),
        search_type: z.enum(["files", "content"]).optional(),
        max_results: z.number().int().min(1).max(500).optional(),
        include_hidden: z.boolean().optional(),
        ignore_case: z.boolean().optional(),
        file_glob: z.string().max(512).optional(),
      }).strict(),
    }),
    call("hara.files.search", (args) => ({
      ...deviceArgs(args),
      path: args.path,
      pattern: args.pattern,
      search_type: args.search_type || "files",
      ...(args.max_results !== undefined ? { max_results: args.max_results } : {}),
      ...(args.include_hidden !== undefined ? { include_hidden: args.include_hidden } : {}),
      ...(args.ignore_case !== undefined ? { ignore_case: args.ignore_case } : {}),
      ...(args.file_glob ? { file_glob: args.file_glob } : {}),
    })),
  );

  server.registerTool(
    "get_file_info",
    toolConfig({
      title: "Get File Info",
      description: "Get file metadata.",
      inputSchema: z.object({
        computer,
        path: z.string().min(1).max(4096),
      }).strict(),
    }),
    call("hara.files.info", (args) => ({ ...deviceArgs(args), path: args.path })),
  );

  server.registerTool(
    "list_processes",
    toolConfig({
      title: "List Processes",
      description: "List running processes.",
      inputSchema: z.object({
        computer,
        limit: z.number().int().min(1).max(500).optional(),
      }).strict(),
    }),
    call("hara.processes.list", (args) => ({
      ...deviceArgs(args),
      ...(args.limit !== undefined ? { limit: args.limit } : {}),
    })),
  );

  server.registerTool(
    "start_process",
    toolConfig({
      title: "Start Process",
      description: "Run a command. By default waits for bounded completion. Set interactive=true for a managed session; requests above 10 seconds are automatically routed to a managed session.",
      inputSchema: z.object({
        computer,
        command: z.string().min(1).max(4096),
        cwd: z.string().min(1).max(4096).optional(),
        timeout_ms: z.number().int().min(100).max(30000).optional(),
        max_lines: z.number().int().min(1).max(500).optional(),
        interactive: z.boolean().optional(),
      }).strict(),
      openWorldHint: true,
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
    }),
    call(
      (args) => (args.interactive || Number(args.timeout_ms || 0) > 10000) ? "hara.process.start" : "hara.process.run",
      (args) => {
        const managed = Boolean(args.interactive || Number(args.timeout_ms || 0) > 10000);
        return {
          ...deviceArgs(args),
          command: args.command,
          ...(args.cwd ? { cwd: args.cwd } : {}),
          timeout_ms: managed
            ? Math.min(Number(args.timeout_ms ?? 1000), 3000)
            : Number(args.timeout_ms ?? 3000),
          ...(!managed ? { max_lines: args.max_lines ?? 200 } : {}),
        };
      },
    ),
  );

  server.registerTool(
    "read_process_output",
    toolConfig({
      title: "Read Process Output",
      description: "Read output from a managed interactive process session.",
      inputSchema: z.object({
        computer,
        session_id: z.string().min(1).max(160),
        offset: z.number().int().min(0).optional(),
        length: z.number().int().min(1).max(500).optional(),
        timeout_ms: z.number().int().min(0).max(10000).optional(),
      }).strict(),
    }),
    call("hara.process.output", (args) => ({
      ...deviceArgs(args),
      session_id: args.session_id,
      ...(args.offset !== undefined ? { offset: args.offset } : {}),
      ...(args.length !== undefined ? { length: args.length } : {}),
      ...(args.timeout_ms !== undefined ? { timeout_ms: args.timeout_ms } : {}),
    })),
  );

  server.registerTool(
    "interact_with_process",
    toolConfig({
      title: "Interact With Process",
      description: "Send input to a managed interactive process session.",
      inputSchema: z.object({
        computer,
        session_id: z.string().min(1).max(160),
        input: z.string().max(1024 * 1024),
        timeout_ms: z.number().int().min(0).max(10000).optional(),
      }).strict(),
      openWorldHint: true,
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.process.interact", (args) => ({
      ...deviceArgs(args),
      session_id: args.session_id,
      input: args.input,
      ...(args.timeout_ms !== undefined ? { timeout_ms: args.timeout_ms } : {}),
    })),
  );

  server.registerTool(
    "kill_process",
    toolConfig({
      title: "Kill Process",
      description: "Terminate a managed process session.",
      inputSchema: z.object({
        computer,
        session_id: z.string().min(1).max(160),
        force: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.process.kill", (args) => ({
      ...deviceArgs(args),
      session_id: args.session_id,
      force: Boolean(args.force),
    })),
  );

  server.registerTool(
    "list_sessions",
    toolConfig({
      title: "List Sessions",
      description: "List managed process sessions.",
      inputSchema: z.object({ computer }).strict(),
    }),
    call("hara.process.sessions", (args) => ({ ...deviceArgs(args) })),
  );

  server.registerTool(
    "get_recent_tool_calls",
    toolConfig({
      title: "Get Recent Tool Calls",
      description: "Get privacy-safe recent call metadata. Arguments and outputs are not returned.",
      inputSchema: z.object({
        computer,
        tool: z.string().min(1).max(160).optional(),
        limit: z.number().int().min(1).max(100).optional(),
      }).strict(),
    }),
    call("hara.calls.recent", (args) => ({
      ...deviceArgs(args),
      ...(args.tool ? { tool: args.tool } : {}),
      ...(args.limit !== undefined ? { limit: args.limit } : {}),
    })),
  );

  return server;
}

export async function handleSimpleCustomerMcpRequest(
  request,
  { executeTool, authInfo = undefined, allowedHosts = undefined },
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
    () => createSimpleCustomerMcpServer({ executeTool }),
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
