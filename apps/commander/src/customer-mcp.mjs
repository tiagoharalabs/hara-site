import {
  McpServer,
  createMcpHandler,
} from "@modelcontextprotocol/server";
import { z } from "zod";

export const CUSTOMER_MCP_TOOLS = Object.freeze([
  "hara.devices.list",
  "hara.capabilities",
  "hara.usage",
  "hara.activity",
  "hara.health",
  "hara.ping",
  "hara.device.info",
  "hara.system.uptime",
  "hara.system.resources",
  "hara.workspace.inspect",
  "hara.processes.list",
  "hara.files.info",
  "hara.files.hash",
  "hara.files.diff",
  "hara.files.search",
  "hara.files.list",
  "hara.files.read",
  "hara.files.read_many",
  "hara.files.create_directory",
  "hara.files.write",
  "hara.files.edit",
  "hara.files.move",
  "hara.files.copy",
  "hara.files.delete",
  "hara.files.preimages.list",
  "hara.files.rollback",
  "hara.process.sessions",
  "hara.process.run",
  "hara.process.start",
  "hara.process.output",
  "hara.process.interact",
  "hara.process.kill",
  "hara.functions.list",
  "hara.functions.describe",
  "hara.functions.invoke",
  "hara.receipts.get",
  "hara.calls.recent",
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

function operationalToolError(code, args = undefined) {
  const common = {
    runtime_authority_from_chatgpt: false,
    mutation_performed: false,
    customer_services_relay: false,
  };
  const build = (state, category, retryable, result = {}, extras = {}) => {
    const value = {
      state,
      ...common,
      blocker: { code, category, retryable, ...extras },
      result,
    };
    if (args?.computer) value.computer = String(args.computer).slice(0, 120);
    return publicToolResult(value);
  };

  if (code === "DEVICE_OFFLINE") {
    return build("UNAVAILABLE", "DEVICE_AVAILABILITY", true, { available: false, device_state: "OFFLINE" });
  }
  if (["DEVICE_BUSY", "CHANNEL_TRANSIENT_BUSY"].includes(code)) {
    return build("BUSY", "DEVICE_AVAILABILITY", true, { available: true, busy: true });
  }
  if (["DEVICE_CALL_TIMEOUT", "CHANNEL_TRANSIENT_TIMEOUT"].includes(code)) {
    return build("TIMEOUT", "DEVICE_EXECUTION", true, { completed: false });
  }
  if (["DEVICE_NOT_FOUND", "DEVICE_CALL_NOT_FOUND"].includes(code)) {
    return build("NOT_FOUND", "DEVICE_SELECTION", false, { exists: false });
  }
  if (code === "COMPUTER_NAME_AMBIGUOUS") {
    return build("NEEDS_INPUT", "DEVICE_SELECTION", false, { selection_required: true });
  }

  const filesystemNotFound = new Set([
    "FILENOTFOUNDERROR", "FILE_NOT_FOUND", "PARENT_DIRECTORY_NOT_FOUND", "FILESYSTEM_PARENT_NOT_FOUND",
    "PREIMAGE_NOT_FOUND", "RECEIPT_NOT_FOUND", "EDIT_MATCH_NOT_FOUND",
  ]);
  if (filesystemNotFound.has(code)) {
    const category = code === "PREIMAGE_NOT_FOUND" ? "ROLLBACK_STATE"
      : code === "RECEIPT_NOT_FOUND" ? "AUDIT_STATE"
      : code === "EDIT_MATCH_NOT_FOUND" ? "EDIT_MATCH"
      : "FILESYSTEM_STATE";
    const result = { exists: false };
    if (["PARENT_DIRECTORY_NOT_FOUND", "FILESYSTEM_PARENT_NOT_FOUND"].includes(code)) result.recommended_tool = "hara.files.create_directory";
    if (code === "PREIMAGE_NOT_FOUND") result.recommended_tool = "hara.files.preimages.list";
    return build("NOT_FOUND", category, false, result);
  }
  if (code === "PROCESS_SESSION_NOT_FOUND") {
    return build("NOT_FOUND", "PROCESS_STATE", false, {
      exists: false, recommended_tool: "hara.process.sessions",
    });
  }
  if (code === "PROCESS_SESSION_EXITED") {
    return build("TERMINAL", "PROCESS_STATE", false, { session_state: "EXITED" });
  }
  if (["DESTINATION_EXISTS", "PATH_EXISTS_NOT_DIRECTORY", "FILESYSTEM_PATH_EXISTS"].includes(code)) {
    return build("CONFLICT", "FILESYSTEM_STATE", false, { conflict: true });
  }
  if (code === "EDIT_MATCH_AMBIGUOUS") {
    return build("NEEDS_INPUT", "EDIT_MATCH", false, { selection_required: true });
  }
  if ([
    "PATH_NOT_FILE", "PATH_NOT_DIRECTORY", "FILESYSTEM_NOT_DIRECTORY", "SOURCE_NOT_FILE",
    "DELETE_TARGET_NOT_FILE", "ROLLBACK_TARGET_NOT_FILE", "PROCESS_CWD_INVALID",
  ].includes(code)) {
    return build("INVALID_TARGET", "FILESYSTEM_STATE", false, { valid_target: false });
  }
  if (code === "BINARY_FILE_DENIED") {
    return build("UNSUPPORTED_CONTENT", "FILESYSTEM_CONTENT", false, { text_required: true });
  }
  if ([
    "FILE_TOO_LARGE", "HASH_FILE_TOO_LARGE", "COPY_FILE_TOO_LARGE",
    "DELETE_FILE_TOO_LARGE", "PREIMAGE_FILE_TOO_LARGE", "WRITE_TOO_LARGE",
  ].includes(code)) {
    return build("LIMIT_EXCEEDED", "PAYLOAD_LIMIT", false, { within_limit: false });
  }
  return null;
}

function publicToolError(error, args = undefined) {
  const code = String(error?.message || "COMMANDER_MCP_TOOL_FAILED")
    .replace(/[^A-Z0-9_:-]/gi, "_")
    .slice(0, 160);

  const operational = operationalToolError(code, args);
  if (operational) return operational;

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
    annotations: {
      readOnlyHint,
      destructiveHint,
      idempotentHint,
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
      const headers = ctx?.http?.req?.headers;
      const transportRequestId =
        headers?.get?.("x-openai-request-id")
        || headers?.get?.("x-request-id")
        || headers?.get?.("traceparent")
        || headers?.get?.("cf-ray")
        || ctx?.sessionId
        || crypto.randomUUID();
      const value = await executeTool({
        tool_id: toolId,
        arguments: args || {},
        mcp_request_id: ctx?.mcpReq?.id ?? null,
        transport_request_id: transportRequestId,
        abort_signal: ctx?.mcpReq?.signal,
      });
      return publicToolResult(value);
    } catch (error) {
      return publicToolError(error, args);
    }
  };

  server.registerTool(
    "hara.devices.list",
    toolConfig({
      title: "List H.A.R.A. Computers",
      description: "List computers enrolled in the authenticated H.A.R.A. Commander tenant with online/offline state.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.devices.list"),
  );

  server.registerTool(
    "hara.capabilities",
    toolConfig({
      title: "H.A.R.A. Computer Capabilities",
      description: "Discover governed capabilities per enrolled computer, including Agent-version support, risk gates and local-approval requirements. Use this before attempting optional or mutating operations.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
      }).strict(),
    }),
    call("hara.capabilities"),
  );

  server.registerTool(
    "hara.usage",
    toolConfig({
      title: "H.A.R.A. Usage",
      description: "Read the authenticated product plan, grants and governed tool-call usage for the current billing period. Returns no customer payload content.",
      inputSchema: z.object({}).strict(),
    }),
    call("hara.usage"),
  );

  server.registerTool(
    "hara.activity",
    toolConfig({
      title: "H.A.R.A. Operational Activity",
      description: "Read metadata-only operational activity for the authenticated subject: transaction counts, success rate, queue/Agent/total latency, devices, transport and recent governed calls. Customer payload and result content are never returned.",
      inputSchema: z.object({
        window: z.enum(["24h","7d","30d"]).optional(),
        limit: z.number().int().min(1).max(100).optional(),
      }).strict(),
    }),
    call("hara.activity"),
  );

  server.registerTool(
    "hara.health",
    toolConfig({
      title: "H.A.R.A. Health",
      description:
        "Check one governed Commander computer and Agent health. Name the computer explicitly when more than one authorized computer is online.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
      }).strict(),
    }),
    call("hara.health"),
  );

  server.registerTool(
    "hara.ping",
    toolConfig({
      title: "Ping Computer",
      description: "Verify end-to-end connectivity to a governed H.A.R.A. Commander computer through its Agent.",
      inputSchema: z.object({ computer: z.string().min(1).max(120).optional() }).strict(),
    }),
    call("hara.ping"),
  );

  server.registerTool(
    "hara.device.info",
    toolConfig({
      title: "Get Computer Info",
      description: "Read basic non-sensitive information from a governed H.A.R.A. Commander computer.",
      inputSchema: z.object({ computer: z.string().min(1).max(120).optional() }).strict(),
    }),
    call("hara.device.info"),
  );

  server.registerTool(
    "hara.system.uptime",
    toolConfig({
      title: "Get System Uptime",
      description: "Read system uptime and load averages from a governed Linux computer.",
      inputSchema: z.object({ computer: z.string().min(1).max(120).optional() }).strict(),
    }),
    call("hara.system.uptime"),
  );

  server.registerTool(
    "hara.system.resources",
    toolConfig({
      title: "Get System Resources",
      description: "Read bounded CPU, memory, swap, load and root-disk capacity from a governed Linux computer without invoking a shell.",
      inputSchema: z.object({ computer: z.string().min(1).max(120).optional() }).strict(),
    }),
    call("hara.system.resources"),
  );

  server.registerTool(
    "hara.workspace.inspect",
    toolConfig({
      title: "Inspect Workspace",
      description: "Inspect one local project/workspace using bounded filesystem metadata and Git HEAD metadata only. No shell or external command is invoked.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        max_entries: z.number().int().min(1).max(200).optional(),
      }).strict(),
    }),
    call("hara.workspace.inspect"),
  );

  server.registerTool(
    "hara.processes.list",
    toolConfig({
      title: "List Processes",
      description: "List running processes using sanitized process metadata. Command lines and environment variables are not exposed.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        limit: z.number().int().min(1).max(200).optional(),
      }).strict(),
    }),
    call("hara.processes.list"),
  );

  server.registerTool(
    "hara.files.info",
    toolConfig({
      title: "Get File Info",
      description: "Read filesystem metadata for one path on a governed computer without reading file contents.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
      }).strict(),
    }),
    call("hara.files.info"),
  );

  server.registerTool(
    "hara.files.hash",
    toolConfig({
      title: "Hash File",
      description: "Compute SHA-256 and size for one regular file on a governed computer without changing it.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
      }).strict(),
    }),
    call("hara.files.hash"),
  );

  server.registerTool(
    "hara.files.diff",
    toolConfig({
      title: "Diff Text Files",
      description: "Produce a bounded unified diff between two text files on one governed computer. Binary and oversized files are refused.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        left: z.string().min(1).max(4096),
        right: z.string().min(1).max(4096),
        max_lines: z.number().int().min(1).max(400).optional(),
      }).strict(),
    }),
    call("hara.files.diff"),
  );

  server.registerTool(
    "hara.files.search",
    toolConfig({
      title: "Search Files",
      description: "Run a bounded read-only filename or text-content search on a governed computer without invoking a shell. Returns at most 100 matches and reports truncation.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        search_type: z.enum(["files", "content"]),
        pattern: z.string().min(1).max(256),
        max_results: z.number().int().min(1).max(100).optional(),
        include_hidden: z.boolean().optional(),
        ignore_case: z.boolean().optional(),
        file_glob: z.string().max(180).optional(),
      }).strict(),
    }),
    call("hara.files.search"),
  );

  server.registerTool(
    "hara.files.list",
    toolConfig({
      title: "List Directory",
      description: "List directory entries and metadata on a governed computer without reading file contents.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        limit: z.number().int().min(1).max(200).optional(),
        depth: z.number().int().min(1).max(5).optional(),
      }).strict(),
    }),
    call("hara.files.list"),
  );

  server.registerTool(
    "hara.files.read",
    toolConfig({
      title: "Read Text File",
      description: "Read a bounded range of a text file from a governed computer. Binary files and oversized reads are refused.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        offset: z.number().int().min(0).max(1000000).optional(),
        length: z.number().int().min(1).max(400).optional(),
      }).strict(),
    }),
    call("hara.files.read"),
  );

  server.registerTool(
    "hara.files.read_many",
    toolConfig({
      title: "Read Multiple Text Files",
      description: "Read the same bounded line range from up to 10 text files on one governed computer. Individual file failures are returned without aborting the whole batch.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        paths: z.array(z.string().min(1).max(4096)).min(1).max(10),
        offset: z.number().int().min(0).max(1000000).optional(),
        length: z.number().int().min(1).max(100).optional(),
      }).strict(),
    }),
    call("hara.files.read_many"),
  );

  server.registerTool(
    "hara.files.create_directory",
    toolConfig({
      title: "Create Directory",
      description: "Create a directory on a governed computer. Requires local human approval in the open H.A.R.A. Commander terminal before execution.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        parents: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
    }),
    call("hara.files.create_directory"),
  );

  server.registerTool(
    "hara.files.write",
    toolConfig({
      title: "Write Text File",
      description: "Write or append bounded UTF-8 text on a governed computer. Existing content receives a local preimage backup. Requires local terminal approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        content: z.string().max(65536),
        mode: z.enum(["rewrite","append"]).optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.write"),
  );

  server.registerTool(
    "hara.files.edit",
    toolConfig({
      title: "Edit Text File",
      description: "Replace exact text in a bounded UTF-8 file, with preimage backup and fail-closed match rules. Requires local terminal approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
        old_text: z.string().min(1).max(32768),
        new_text: z.string().max(32768),
        replace_all: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
    }),
    call("hara.files.edit"),
  );

  server.registerTool(
    "hara.files.move",
    toolConfig({
      title: "Move File or Directory",
      description: "Move one file or directory without overwriting an existing destination. Requires local terminal approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        source: z.string().min(1).max(4096),
        destination: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
    }),
    call("hara.files.move"),
  );

  server.registerTool(
    "hara.files.copy",
    toolConfig({
      title: "Copy File",
      description: "Copy one regular file to a new destination without overwriting. Requires local operator approval on the target computer.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        source: z.string().min(1).max(4096),
        destination: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false, destructiveHint: false, idempotentHint: false,
    }),
    call("hara.files.copy"),
  );

  server.registerTool(
    "hara.files.delete",
    toolConfig({
      title: "Delete File Reversibly",
      description: "Delete one regular file only after creating a verified local preimage for rollback. Directories are refused. Requires local operator approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        path: z.string().min(1).max(4096),
      }).strict(),
      readOnlyHint: false, destructiveHint: true, idempotentHint: false,
    }),
    call("hara.files.delete"),
  );

  server.registerTool(
    "hara.files.preimages.list",
    toolConfig({
      title: "List File Preimages",
      description: "List local rollback points created by governed H.A.R.A. file mutations. Returns metadata only, never preimage content.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        limit: z.number().int().min(1).max(100).optional(),
        path: z.string().min(1).max(4096).optional(),
      }).strict(),
    }),
    call("hara.files.preimages.list"),
  );

  server.registerTool(
    "hara.files.rollback",
    toolConfig({
      title: "Rollback File Preimage",
      description: "Restore one governed preimage to its original path after SHA verification. The current file is snapshotted first so rollback itself remains reversible. Requires local terminal approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        preimage_id: z.string().min(1).max(180),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
    }),
    call("hara.files.rollback"),
  );

  server.registerTool(
    "hara.process.sessions",
    toolConfig({
      title: "List Managed Process Sessions",
      description: "List process sessions started by H.A.R.A. Commander on the governed computer. Does not expose command text.",
      inputSchema: z.object({ computer: z.string().min(1).max(120).optional() }).strict(),
    }),
    call("hara.process.sessions"),
  );

  server.registerTool(
    "hara.process.run",
    toolConfig({
      title: "Run Governed Command",
      description: "Run one bounded shell command to completion. One-shot execution is capped at 10 seconds; for longer work use hara.process.start plus hara.process.output. Requests above 10 seconds return structured managed-session guidance instead of a schema error.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        command: z.string().min(1).max(4096),
        cwd: z.string().min(1).max(4096).optional(),
        timeout_ms: z.number().int().min(100).max(30000).optional(),
        max_lines: z.number().int().min(1).max(500).optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    }),
    async (args, ctx) => {
      if (Number(args?.timeout_ms || 0) > 10000) {
        const result = {
          state: "REQUIRES_MANAGED_SESSION",
          runtime_authority_from_chatgpt: false,
          mutation_performed: false,
          customer_services_relay: false,
          blocker: {
            code: "PROCESS_RUN_TIMEOUT_EXCEEDS_ONESHOT_LIMIT",
            category: "PROCESS_EXECUTION_MODE",
            retryable: true,
          },
          result: {
            requested_timeout_ms: Number(args.timeout_ms),
            one_shot_max_timeout_ms: 10000,
            recommended_tool: "hara.process.start",
            follow_up_tool: "hara.process.output",
          },
        };
        if (args?.computer) result.computer = String(args.computer).slice(0, 120);
        return publicToolResult(result);
      }
      return call("hara.process.run")(args, ctx);
    },
  );

  server.registerTool(
    "hara.process.start",
    toolConfig({
      title: "Start Process",
      description: "Start a shell command in a governed PTY session. Requires local human approval in the open H.A.R.A. Commander terminal. Command payload is redacted from durable transport after Agent claim.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        command: z.string().min(1).max(4096),
        cwd: z.string().min(1).max(4096).optional(),
        timeout_ms: z.number().int().min(0).max(3000).optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    }),
    call("hara.process.start"),
  );

  server.registerTool(
    "hara.process.output",
    toolConfig({
      title: "Read Process Output",
      description: "Read subsequent bounded output from a process session managed by H.A.R.A. Commander. Use after hara.process.interact when the immediate response contains only terminal echo.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        session_id: z.string().min(1).max(180),
        offset: z.number().int().min(0).max(1000000).optional(),
        length: z.number().int().min(1).max(500).optional(),
        timeout_ms: z.number().int().min(0).max(3000).optional(),
      }).strict(),
    }),
    call("hara.process.output"),
  );

  server.registerTool(
    "hara.process.interact",
    toolConfig({
      title: "Interact With Process",
      description: "Send bounded input to an existing H.A.R.A. Commander PTY process. The immediate response may contain only terminal echo; use hara.process.output for subsequent program output. Requires local human approval for every interaction.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        session_id: z.string().min(1).max(180),
        input: z.string().max(4096),
        timeout_ms: z.number().int().min(0).max(3000).optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
      openWorldHint: true,
    }),
    call("hara.process.interact"),
  );

  server.registerTool(
    "hara.process.kill",
    toolConfig({
      title: "Terminate Managed Process",
      description: "Terminate a process session started by H.A.R.A. Commander. Requires local human approval.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        session_id: z.string().min(1).max(180),
        force: z.boolean().optional(),
      }).strict(),
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: true,
    }),
    call("hara.process.kill"),
  );

  server.registerTool(
    "hara.functions.list",
    toolConfig({
      title: "List H.A.R.A. Functions",
      description:
        "List governed local function identifiers and states exposed by one Commander Agent. Name the computer explicitly when more than one authorized computer is online.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
      }).strict(),
    }),
    call("hara.functions.list"),
  );

  server.registerTool(
    "hara.functions.describe",
    toolConfig({
      title: "Describe H.A.R.A. Function",
      description:
        "Describe one exact governed local function on a named Commander computer using a minimized public projection.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
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
        "Invoke one exact admitted READ_ONLY local function on a named Commander computer. Arguments are passed without a shell.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
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
        "Read one audit receipt produced by a named Commander Agent by ID or SHA-256 using a minimized public projection.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        receipt_id_or_sha256: z.string().min(1).max(256),
      }).strict(),
    }),
    call("hara.receipts.get"),
  );

  server.registerTool(
    "hara.calls.recent",
    toolConfig({
      title: "Recent H.A.R.A. Calls",
      description: "Read persistent audit metadata for recent H.A.R.A. Commander calls made by the authenticated subject. Payload values and device results are not returned.",
      inputSchema: z.object({
        computer: z.string().min(1).max(120).optional(),
        tool: z.string().min(1).max(120).optional(),
        limit: z.number().int().min(1).max(100).optional(),
      }).strict(),
    }),
    call("hara.calls.recent"),
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
