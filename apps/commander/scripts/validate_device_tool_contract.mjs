#!/usr/bin/env node
import fs from "node:fs";
import {
  DEVICE_FUNCTION_ID,
  DEVICE_FUNCTION_IDS,
  DEVICE_TOOL_FUNCTION_MAP,
  deviceFunctionForTool,
  isDeviceFunctionAllowed,
  isDeviceMutationTool,
  isDeviceProcessTool,
  isDeviceProcessMutationTool,
  canonicalDeviceToolPayload,
} from "../src/device-tool-contract.mjs";
function need(ok, code) { if (!ok) throw new Error("COMMANDER_DEVICE_TOOL_CONTRACT_"+code+"=FAIL"); console.log("COMMANDER_DEVICE_TOOL_CONTRACT_"+code+"=PASS"); }
function expectError(label, expectedCode, fn) { try { fn(); } catch (e) { need(e instanceof Error && e.message===expectedCode,label); return; } throw new Error("COMMANDER_DEVICE_TOOL_CONTRACT_"+label+"=FAIL_ALLOWED"); }
need(DEVICE_FUNCTION_ID === "device.info", "PRIMARY_FUNCTION_ID");
for (const id of ["device.info","device.ping","system.uptime","system.resources","workspace.inspect","process.list","filesystem.info","filesystem.search","filesystem.list","filesystem.read","filesystem.read_many"]) need(DEVICE_FUNCTION_IDS.includes(id) && isDeviceFunctionAllowed(id), "ALLOW_"+id.replaceAll(".","_").toUpperCase());
need(JSON.stringify(canonicalDeviceToolPayload("hara.health",{}))==="{}","HEALTH_EMPTY_PAYLOAD");
need(JSON.stringify(canonicalDeviceToolPayload("hara.ping",{}))==="{}","PING_EMPTY_PAYLOAD");
need(JSON.stringify(canonicalDeviceToolPayload("hara.system.resources",{}))==="{}","SYSTEM_RESOURCES_EMPTY_PAYLOAD");
const workspacePayload=canonicalDeviceToolPayload("hara.workspace.inspect",{path:"/tmp/project",max_entries:40});
need(workspacePayload.path==="/tmp/project" && workspacePayload.max_entries===40,"WORKSPACE_INSPECT_CANONICAL");
need(deviceFunctionForTool("hara.system.resources")==="system.resources","SYSTEM_RESOURCES_MAPPING");
need(deviceFunctionForTool("hara.workspace.inspect")==="workspace.inspect","WORKSPACE_INSPECT_MAPPING");
need(isDeviceMutationTool("hara.files.write"),"MUTATION_TOOL_WRITE");
need(isDeviceMutationTool("hara.files.edit"),"MUTATION_TOOL_EDIT");
need(isDeviceMutationTool("hara.files.rollback"),"MUTATION_TOOL_ROLLBACK");
const preimagesPayload=canonicalDeviceToolPayload("hara.files.preimages.list",{limit:20,path:"/tmp/x"});
need(preimagesPayload.limit===20 && preimagesPayload.path==="/tmp/x","PREIMAGES_LIST_CANONICAL");
const rollbackPayload=canonicalDeviceToolPayload("hara.files.rollback",{preimage_id:"HARA-PREIMAGE-0123456789abcdef0123456789abcdef"});
need(rollbackPayload.preimage_id.startsWith("HARA-PREIMAGE-"),"ROLLBACK_CANONICAL");
need(isDeviceProcessTool("hara.process.output"),"PROCESS_TOOL_OUTPUT");
need(isDeviceProcessTool("hara.process.run"),"PROCESS_TOOL_RUN");
need(isDeviceProcessMutationTool("hara.process.run"),"PROCESS_TOOL_RUN_MUTATION");
need(isDeviceProcessMutationTool("hara.process.start"),"PROCESS_TOOL_START_MUTATION");
need(isDeviceProcessMutationTool("hara.process.interact"),"PROCESS_TOOL_INTERACT_MUTATION");
const prun=canonicalDeviceToolPayload("hara.process.run",{command:"printf hi",cwd:"/tmp",timeout_ms:500,max_lines:20});
need(prun.command==="printf hi" && prun.timeout_ms===500 && prun.max_lines===20,"PROCESS_RUN_CANONICAL");
const pstart=canonicalDeviceToolPayload("hara.process.start",{command:"printf hi",cwd:"/tmp",timeout_ms:500});
need(pstart.command==="printf hi" && pstart.timeout_ms===500,"PROCESS_START_CANONICAL");
const pout=canonicalDeviceToolPayload("hara.process.output",{session_id:"HARA-PROC-test",length:20,timeout_ms:100});
need(pout.session_id==="HARA-PROC-test" && pout.length===20,"PROCESS_OUTPUT_CANONICAL");
const pint=canonicalDeviceToolPayload("hara.process.interact",{session_id:"HARA-PROC-test",input:"echo hi",timeout_ms:100});
need(pint.input==="echo hi","PROCESS_INTERACT_CANONICAL");
const pkill=canonicalDeviceToolPayload("hara.process.kill",{session_id:"HARA-PROC-test",force:true});
need(pkill.force===true,"PROCESS_KILL_CANONICAL");
const writePayload=canonicalDeviceToolPayload("hara.files.write",{path:"/tmp/x",content:"abc",mode:"rewrite"});
need(writePayload.path==="/tmp/x" && writePayload.content==="abc" && writePayload.mode==="rewrite","MUTATION_WRITE_CANONICAL");
const editPayload=canonicalDeviceToolPayload("hara.files.edit",{path:"/tmp/x",old_text:"a",new_text:"b"});
need(editPayload.old_text==="a" && editPayload.new_text==="b","MUTATION_EDIT_CANONICAL");
const movePayload=canonicalDeviceToolPayload("hara.files.move",{source:"/tmp/a",destination:"/tmp/b"});
need(movePayload.source==="/tmp/a" && movePayload.destination==="/tmp/b","MUTATION_MOVE_CANONICAL");
need(deviceFunctionForTool("hara.processes.list")==="process.list","PURPOSE_TOOL_PROCESS_MAPPING");
need(DEVICE_TOOL_FUNCTION_MAP["hara.files.read"]==="filesystem.read","PURPOSE_TOOL_FILE_MAPPING");
need(canonicalDeviceToolPayload("hara.processes.list",{limit:7}).limit===7,"DIRECT_PROCESS_LIST_CANONICAL");
need(canonicalDeviceToolPayload("hara.files.info",{path:"/tmp/a"}).path==="/tmp/a","DIRECT_FILES_INFO_CANONICAL");
const directSearch=canonicalDeviceToolPayload("hara.files.search",{path:"/tmp",search_type:"content",pattern:"needle",max_results:10,include_hidden:false,ignore_case:true,file_glob:"*.txt"});
need(directSearch.search_type==="content" && directSearch.max_results===10 && directSearch.file_glob==="*.txt","DIRECT_FILES_SEARCH_CANONICAL");
const directList=canonicalDeviceToolPayload("hara.files.list",{path:"/tmp",limit:20,depth:3});
need(directList.limit===20 && directList.depth===3,"DIRECT_FILES_LIST_CANONICAL");
const readMany=canonicalDeviceToolPayload("hara.files.read_many",{paths:["/tmp/a","/tmp/b"],offset:0,length:20});
need(readMany.paths.length===2 && readMany.length===20,"DIRECT_FILES_READ_MANY_CANONICAL");
need(canonicalDeviceToolPayload("hara.files.read",{path:"/tmp/a",offset:0,length:10}).length===10,"DIRECT_FILES_READ_CANONICAL");
need(JSON.stringify(canonicalDeviceToolPayload("hara.functions.list",{}))==="{}","LIST_EMPTY_PAYLOAD");
need(canonicalDeviceToolPayload("hara.functions.describe",{function_id:"system.uptime"}).function_id==="system.uptime","DESCRIBE_CANONICAL");
need(canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"system.resources",arguments:{argv:[]}}).function_id==="system.resources","SYSTEM_RESOURCES_FUNCTION_CANONICAL");
need(canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"workspace.inspect",arguments:{argv:["/tmp/project","25"]}}).arguments.argv[1]==="25","WORKSPACE_INSPECT_FUNCTION_CANONICAL");
need(canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"process.list",arguments:{argv:["7"]}}).arguments.argv[0]==="7","PROCESS_LIST_CANONICAL");
need(canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"filesystem.list",arguments:{argv:["/tmp","20"]}}).arguments.argv[1]==="20","FILESYSTEM_LIST_CANONICAL");
need(canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"filesystem.read",arguments:{argv:["/tmp/a","0","10"]}}).arguments.argv[2]==="10","FILESYSTEM_READ_CANONICAL");
expectError("UNKNOWN_TOOL_DENIED","DEVICE_CALL_TOOL_DENIED",()=>canonicalDeviceToolPayload("shell.run",{}));
expectError("UNKNOWN_FUNCTION_DENIED","DEVICE_CALL_FUNCTION_DENIED",()=>canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"shell.run",arguments:{argv:[]}}));
expectError("PROCESS_LIMIT_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"process.list",arguments:{argv:["999"]}}));
expectError("SEARCH_TYPE_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.files.search",{path:"/tmp",search_type:"regex",pattern:"x"}));
expectError("FILESYSTEM_READ_LENGTH_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.functions.invoke",{function_id:"filesystem.read",arguments:{argv:["/tmp/a","0","999"]}}));
expectError("FILESYSTEM_LIST_DEPTH_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.files.list",{path:"/tmp",depth:9}));
expectError("FILESYSTEM_READ_MANY_COUNT_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.files.read_many",{paths:[]}));
expectError("MUTATION_WRITE_SIZE_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.files.write",{path:"/tmp/x",content:"x".repeat(70000)}));
expectError("MUTATION_EDIT_EMPTY_MATCH_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.files.edit",{path:"/tmp/x",old_text:"",new_text:"x"}));
expectError("PROCESS_RUN_TIMEOUT_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.process.run",{command:"true",timeout_ms:20000}));
expectError("PROCESS_COMMAND_SIZE_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.process.start",{command:"x".repeat(5000)}));
expectError("PROCESS_SESSION_ID_DENIED","DEVICE_CALL_PAYLOAD_INVALID",()=>canonicalDeviceToolPayload("hara.process.output",{session_id:"bad id"}));
need(canonicalDeviceToolPayload("hara.files.copy",{source:"/tmp/a",destination:"/tmp/b"}).source==="/tmp/a","MUTATION_COPY_CANONICAL");
need(canonicalDeviceToolPayload("hara.files.delete",{path:"/tmp/a"}).path==="/tmp/a","MUTATION_DELETE_CANONICAL");
const worker=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
need(worker.includes("canonicalDeviceToolPayload(toolId, body.payload)"),"WORKER_ENQUEUE_GUARD");
need(worker.includes("isDeviceFunctionAllowed(functionId)"),"WORKER_FUNCTION_ALLOWLIST_GUARD");
need(worker.includes('"COMMANDER_MUTATION_INVOKE"'),"WORKER_MUTATION_GRANT");
need(worker.includes('"COMMANDER_PROCESS_EXECUTION"'),"WORKER_PROCESS_EXECUTION_GRANT");
need(worker.includes("transport_request_id") && worker.includes("transportRequestId"),"WORKER_TRANSPORT_REQUEST_ID_BINDING");
need(worker.includes("customerCapabilities") && worker.includes("capabilitiesForDevice"),"WORKER_CAPABILITY_NEGOTIATION");
need(
  worker.includes("function resolveNamedCustomerDevice")
  && worker.includes("const active=matches.filter((d)=>!d.revoked_at_utc)")
  && worker.includes("if (active.length===1) return active[0]")
  && worker.includes("const online=active.filter((d)=>d.online)")
  && worker.includes("deviceId=resolveNamedCustomerDevice(devices,args.computer).device_id"),
  "WORKER_ACTIVE_DEVICE_NAME_RESOLUTION",
);
need(
  worker.includes("customerUsage")
  && worker.includes("productUsageForPolicy")
  && worker.includes('if (kind === "NONE") return unlimitedProductUsage();')
  && worker.includes("quota.status"),
  "WORKER_USAGE_SURFACE",
);
need(worker.includes("semverAtLeast(device.agent_version,24)") && worker.includes('tools.push("hara.system.resources","hara.workspace.inspect")'),"WORKER_CONTEXT_TOOLS_0_3_24");
need(worker.includes('platform === "WINDOWS"') && worker.includes('semverAtLeast(device.agent_version,32)') && worker.includes('"hara.files.write"') && worker.includes('"hara.process.run"'),"WORKER_WINDOWS_STARTER_0_3_32");
need(worker.includes('toolId === "hara.process.run" ? 25') && worker.includes('tools.push("hara.process.run")'),"WORKER_PROCESS_RUN_0_3_25");
need(worker.includes('tools.push("hara.files.hash","hara.files.diff")') && worker.includes('tools.push("hara.files.copy","hara.files.delete")'),"WORKER_CAPABILITIES_0_3_23_COMPLETE");
need(worker.includes("capabilityToolDetail") && worker.includes('risk_class:processExecution ? "PROCESS_EXECUTION"') && worker.includes('local_session_authorization_sufficient:mutable && mode === "SESSION_TRUSTED"'),"WORKER_CAPABILITY_RISK_METADATA");
need(worker.includes('capability_detail_schema:"hara.commander-capability-tool.v2"'),"WORKER_CAPABILITY_DETAIL_SCHEMA");
need(worker.includes("normalizeApprovalMode") && worker.includes("SESSION_TRUSTED") && worker.includes("ASK_EVERY_ACTION") && worker.includes("PERSISTENT_TRUSTED"),"WORKER_APPROVAL_MODE_ENUM");
need(worker.includes("approval_mode:approvalMode") && worker.includes("local_session_authorizes_governed_mutations") && worker.includes("persistent_device_authorizes_governed_mutations"),"WORKER_APPROVAL_MODE_CAPABILITY_PROJECTION");
need(worker.includes('"local_authorization_mode"') && worker.includes('"authorization_source"'),"WORKER_AUTHORIZATION_SOURCE_PROJECTION");
need(worker.includes('"tool:"+toolId'),"WORKER_MUTATION_PROCESS_METERING");
need(worker.includes('isDeviceMutationTool(toolId) || isDeviceProcessTool(toolId) || toolId === \"hara.files.preimages.list\"'),"WORKER_MUTATION_AGENT_VERSION_GUARD");
console.log("COMMANDER_DEVICE_TOOL_CONTRACT=PASS");
