export const DEVICE_FUNCTION_ID = "device.info";
export const DEVICE_FUNCTION_IDS = Object.freeze([
  "device.info",
  "device.ping",
  "system.uptime",
  "process.list",
  "filesystem.info",
  "filesystem.hash",
  "filesystem.diff",
  "filesystem.search",
  "filesystem.list",
  "filesystem.read",
  "filesystem.read_many",
]);
export const DEVICE_TOOL_FUNCTION_MAP = Object.freeze({
  "hara.device.info": "device.info",
  "hara.ping": "device.ping",
  "hara.system.uptime": "system.uptime",
  "hara.processes.list": "process.list",
  "hara.files.info": "filesystem.info",
  "hara.files.hash": "filesystem.hash",
  "hara.files.diff": "filesystem.diff",
  "hara.files.search": "filesystem.search",
  "hara.files.list": "filesystem.list",
  "hara.files.read": "filesystem.read",
  "hara.files.read_many": "filesystem.read_many",
});
export const DEVICE_MUTATION_TOOLS = Object.freeze([
  "hara.files.create_directory",
  "hara.files.write",
  "hara.files.edit",
  "hara.files.move",
  "hara.files.copy",
  "hara.files.delete",
  "hara.files.rollback",
]);
const DEVICE_MUTATION_TOOL_SET = new Set(DEVICE_MUTATION_TOOLS);
export function isDeviceMutationTool(value) { return DEVICE_MUTATION_TOOL_SET.has(String(value || "")); }
export const DEVICE_PROCESS_TOOLS = Object.freeze([
  "hara.process.sessions",
  "hara.process.start",
  "hara.process.output",
  "hara.process.interact",
  "hara.process.kill",
]);
export const DEVICE_PROCESS_MUTATION_TOOLS = Object.freeze([
  "hara.process.start",
  "hara.process.interact",
  "hara.process.kill",
]);
const DEVICE_PROCESS_TOOL_SET = new Set(DEVICE_PROCESS_TOOLS);
const DEVICE_PROCESS_MUTATION_TOOL_SET = new Set(DEVICE_PROCESS_MUTATION_TOOLS);
export function isDeviceProcessTool(value) { return DEVICE_PROCESS_TOOL_SET.has(String(value || "")); }
export function isDeviceProcessMutationTool(value) { return DEVICE_PROCESS_MUTATION_TOOL_SET.has(String(value || "")); }

const DEVICE_FUNCTION_SET = new Set(DEVICE_FUNCTION_IDS);

function fail(code) { throw new Error(code); }
function isObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function exactKeys(value, expected) {
  if (!isObject(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}
function onlyKeys(value, allowed, required = []) {
  if (!isObject(value)) return false;
  const keys = Object.keys(value);
  if (keys.some((key) => !allowed.includes(key))) return false;
  return required.every((key) => keys.includes(key));
}
function requireFunctionId(value) {
  const id = typeof value === "string" ? value.trim() : "";
  if (!DEVICE_FUNCTION_SET.has(id)) fail("DEVICE_CALL_FUNCTION_DENIED");
  return id;
}
export function isDeviceFunctionAllowed(value) {
  return typeof value === "string" && DEVICE_FUNCTION_SET.has(value.trim());
}
export function deviceFunctionForTool(toolId) {
  return DEVICE_TOOL_FUNCTION_MAP[String(toolId || "")] || null;
}
function intNumber(value, min, max, code="DEVICE_CALL_PAYLOAD_INVALID") {
  const n = typeof value === "number" ? value : Number(String(value ?? "").trim());
  if (!Number.isSafeInteger(n) || n < min || n > max) fail(code);
  return n;
}
function intArg(value, min, max, code="DEVICE_CALL_PAYLOAD_INVALID") {
  return String(intNumber(value, min, max, code));
}
function idArg(value) {
  const text=String(value ?? "").trim();
  if (!/^[A-Za-z0-9_.:-]{1,180}$/.test(text)) fail("DEVICE_CALL_PAYLOAD_INVALID");
  return text;
}
function textArg(value,max) {
  const text=String(value ?? "");
  if (!text || text.length > max || text.includes("\u0000")) fail("DEVICE_CALL_PAYLOAD_INVALID");
  return text;
}
function pathArg(value) {
  const text=String(value ?? "").trim();
  if (!text || text.length > 4096 || /[\u0000-\u001f\u007f]/.test(text)) fail("DEVICE_CALL_PAYLOAD_INVALID");
  return text;
}
function canonicalArgv(functionId, argv) {
  if (!Array.isArray(argv)) fail("DEVICE_CALL_PAYLOAD_INVALID");
  if (["device.info","device.ping","system.uptime"].includes(functionId)) {
    if (argv.length !== 0) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return [];
  }
  if (functionId === "process.list") {
    if (argv.length > 1) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return argv.length ? [intArg(argv[0],1,200)] : [];
  }
  if (functionId === "filesystem.info") {
    if (argv.length !== 1) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return [pathArg(argv[0])];
  }
  if (functionId === "filesystem.hash") {
    if (argv.length !== 1) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return [pathArg(argv[0])];
  }
  if (functionId === "filesystem.diff") {
    if (argv.length < 2 || argv.length > 3) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return [pathArg(argv[0]),pathArg(argv[1]),...(argv.length===3 ? [intArg(argv[2],1,400)] : [])];
  }
  if (functionId === "filesystem.search") {
    if (argv.length < 3 || argv.length > 7) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const type=String(argv[1] ?? "");
    if (!["files","content"].includes(type)) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const pattern=String(argv[2] ?? "");
    if (!pattern || pattern.length > 256 || /[\u0000-\u001f\u007f]/.test(pattern)) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const out=[pathArg(argv[0]),type,pattern];
    if (argv.length >= 4) out.push(intArg(argv[3],1,100));
    if (argv.length >= 5) out.push(String(argv[4]) === "1" ? "1" : "0");
    if (argv.length >= 6) out.push(String(argv[5]) === "1" ? "1" : "0");
    if (argv.length >= 7) {
      const glob=String(argv[6] ?? "");
      if (glob.length > 180 || /[\u0000-\u001f\u007f]/.test(glob)) fail("DEVICE_CALL_PAYLOAD_INVALID");
      out.push(glob);
    }
    return out;
  }
  if (functionId === "filesystem.list") {
    if (argv.length < 1 || argv.length > 3) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const out=[pathArg(argv[0])];
    if (argv.length >= 2) out.push(intArg(argv[1],1,200));
    if (argv.length >= 3) out.push(intArg(argv[2],1,5));
    return out;
  }
  if (functionId === "filesystem.read") {
    if (argv.length < 1 || argv.length > 3) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const out=[pathArg(argv[0])];
    if (argv.length >= 2) out.push(intArg(argv[1],0,1000000));
    if (argv.length >= 3) out.push(intArg(argv[2],1,400));
    return out;
  }
  if (functionId === "filesystem.read_many") {
    if (argv.length < 3 || argv.length > 12) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const out=[intArg(argv[0],0,1000000),intArg(argv[1],1,100)];
    for (const value of argv.slice(2)) out.push(pathArg(value));
    return out;
  }
  fail("DEVICE_CALL_FUNCTION_DENIED");
}

export function canonicalDeviceToolPayload(toolId, payload) {
  const body = payload ?? {};
  if (!isObject(body)) fail("DEVICE_CALL_PAYLOAD_INVALID");

  if (["hara.health","hara.ping","hara.device.info","hara.system.uptime","hara.functions.list"].includes(toolId)) {
    if (!exactKeys(body, [])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {};
  }
  if (toolId === "hara.processes.list") {
    if (!onlyKeys(body,["limit"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return body.limit === undefined ? {} : { limit: intNumber(body.limit,1,200) };
  }
  if (toolId === "hara.files.info") {
    if (!exactKeys(body,["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return { path: pathArg(body.path) };
  }
  if (toolId === "hara.files.hash") {
    if (!exactKeys(body,["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {path:pathArg(body.path)};
  }
  if (toolId === "hara.files.diff") {
    if (!onlyKeys(body,["left","right","max_lines"],["left","right"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {left:pathArg(body.left),right:pathArg(body.right),max_lines:body.max_lines===undefined ? 200 : intNumber(body.max_lines,1,400)};
  }
  if (toolId === "hara.files.search") {
    if (!onlyKeys(body,["path","search_type","pattern","max_results","include_hidden","ignore_case","file_glob"],["path","search_type","pattern"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const type=String(body.search_type || "");
    if (!["files","content"].includes(type)) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const pattern=String(body.pattern || "");
    if (!pattern || pattern.length > 256 || /[\u0000-\u001f\u007f]/.test(pattern)) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const glob=body.file_glob === undefined ? undefined : String(body.file_glob);
    if (glob !== undefined && (glob.length > 180 || /[\u0000-\u001f\u007f]/.test(glob))) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      path:pathArg(body.path), search_type:type, pattern,
      max_results:body.max_results === undefined ? 50 : intNumber(body.max_results,1,100),
      include_hidden:body.include_hidden === true, ignore_case:body.ignore_case !== false,
      ...(glob === undefined ? {} : {file_glob:glob}),
    };
  }
  if (toolId === "hara.files.list") {
    if (!onlyKeys(body,["path","limit","depth"],["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      path:pathArg(body.path),
      ...(body.limit === undefined ? {} : {limit:intNumber(body.limit,1,200)}),
      ...(body.depth === undefined ? {} : {depth:intNumber(body.depth,1,5)}),
    };
  }
  if (toolId === "hara.files.read") {
    if (!onlyKeys(body,["path","offset","length"],["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      path: pathArg(body.path),
      ...(body.offset === undefined ? {} : {offset:intNumber(body.offset,0,1000000)}),
      ...(body.length === undefined ? {} : {length:intNumber(body.length,1,400)}),
    };
  }
  if (toolId === "hara.files.read_many") {
    if (!onlyKeys(body,["paths","offset","length"],["paths"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    if (!Array.isArray(body.paths) || body.paths.length < 1 || body.paths.length > 10) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      paths:body.paths.map(pathArg),
      offset:body.offset === undefined ? 0 : intNumber(body.offset,0,1000000),
      length:body.length === undefined ? 100 : intNumber(body.length,1,100),
    };
  }
  if (toolId === "hara.files.preimages.list") {
    if (!onlyKeys(body,["limit","path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      limit:body.limit === undefined ? 50 : intNumber(body.limit,1,100),
      ...(body.path === undefined ? {} : {path:pathArg(body.path)}),
    };
  }
  if (toolId === "hara.files.rollback") {
    if (!exactKeys(body,["preimage_id"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {preimage_id:idArg(body.preimage_id)};
  }
  if (toolId === "hara.process.sessions") {
    if (!exactKeys(body,[])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {};
  }
  if (toolId === "hara.process.start") {
    if (!onlyKeys(body,["command","cwd","timeout_ms"],["command"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      command:textArg(body.command,4096),
      ...(body.cwd === undefined ? {} : {cwd:pathArg(body.cwd)}),
      timeout_ms:body.timeout_ms === undefined ? 1000 : intNumber(body.timeout_ms,0,3000),
    };
  }
  if (toolId === "hara.process.output") {
    if (!onlyKeys(body,["session_id","offset","length","timeout_ms"],["session_id"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {
      session_id:idArg(body.session_id),
      ...(body.offset === undefined ? {} : {offset:intNumber(body.offset,0,1000000)}),
      length:body.length === undefined ? 200 : intNumber(body.length,1,500),
      timeout_ms:body.timeout_ms === undefined ? 500 : intNumber(body.timeout_ms,0,3000),
    };
  }
  if (toolId === "hara.process.interact") {
    if (!onlyKeys(body,["session_id","input","timeout_ms"],["session_id","input"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const input=String(body.input ?? "");
    if (input.length > 4096 || input.includes("\u0000")) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {session_id:idArg(body.session_id),input,timeout_ms:body.timeout_ms === undefined ? 1000 : intNumber(body.timeout_ms,0,3000)};
  }
  if (toolId === "hara.process.kill") {
    if (!onlyKeys(body,["session_id","force"],["session_id"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {session_id:idArg(body.session_id),force:body.force === true};
  }
  if (toolId === "hara.files.create_directory") {
    if (!onlyKeys(body,["path","parents"],["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {path:pathArg(body.path),parents:body.parents !== false};
  }
  if (toolId === "hara.files.write") {
    if (!onlyKeys(body,["path","content","mode"],["path","content"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const content=String(body.content ?? "");
    if (content.length > 65536 || content.includes("\u0000")) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const mode=String(body.mode || "rewrite");
    if (!["rewrite","append"].includes(mode)) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {path:pathArg(body.path),content,mode};
  }
  if (toolId === "hara.files.edit") {
    if (!onlyKeys(body,["path","old_text","new_text","replace_all"],["path","old_text","new_text"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const oldText=String(body.old_text ?? ""), newText=String(body.new_text ?? "");
    if (!oldText || oldText.length > 32768 || newText.length > 32768 || oldText.includes("\u0000") || newText.includes("\u0000")) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {path:pathArg(body.path),old_text:oldText,new_text:newText,replace_all:body.replace_all === true};
  }
  if (toolId === "hara.files.move") {
    if (!onlyKeys(body,["source","destination"],["source","destination"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {source:pathArg(body.source),destination:pathArg(body.destination)};
  }
  if (toolId === "hara.files.copy") {
    if (!onlyKeys(body,["source","destination"],["source","destination"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {source:pathArg(body.source),destination:pathArg(body.destination)};
  }
  if (toolId === "hara.files.delete") {
    if (!exactKeys(body,["path"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {path:pathArg(body.path)};
  }
  if (toolId === "hara.functions.describe") {
    if (!exactKeys(body, ["function_id"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return { function_id: requireFunctionId(body.function_id) };
  }
  if (toolId === "hara.functions.invoke") {
    if (!exactKeys(body, ["function_id", "arguments"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const functionId = requireFunctionId(body.function_id);
    const args = body.arguments;
    if (!exactKeys(args, ["argv"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return { function_id: functionId, arguments: { argv: canonicalArgv(functionId, args.argv) } };
  }
  if (toolId === "hara.receipts.get") {
    if (!exactKeys(body, ["receipt_id_or_sha256"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    const receipt = String(body.receipt_id_or_sha256 || "").trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(receipt)) fail("DEVICE_CALL_RECEIPT_INVALID");
    return { receipt_id_or_sha256: receipt };
  }
  fail("DEVICE_CALL_TOOL_DENIED");
}
