// Approval waiting is a call lifecycle; it is not a managed process yet.
import { isDeviceMutationTool, isDeviceProcessMutationTool } from "./device-tool-contract.mjs";

export const LOCAL_APPROVAL_WINDOW_SECONDS = 900;
export const APPROVAL_TRANSPORT_GRACE_SECONDS = 60;
export const ASYNC_APPROVAL_RESERVATION_TTL_SECONDS = 1800;
export const CALL_RESULT_METADATA_SCHEMA = "hara.commander-call-result-metadata.v1";
export const TERMINAL_CALL_STATES = Object.freeze(["COMPLETED","FAILED","CANCELLED","EXPIRED"]);

export function asyncApprovalDevice(device) {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(String(device?.agent_version || ""));
  return String(device?.platform || "").toUpperCase() === "WINDOWS"
    && String(device?.approval_mode || "").toUpperCase() === "ASK_EVERY_ACTION"
    && Boolean(match && (Number(match[1]) > 0 || Number(match[2]) > 3 ||
      (Number(match[2]) === 3 && Number(match[3]) >= 49)));
}
export function asyncApprovalTool(toolId) {
  return isDeviceMutationTool(toolId) || isDeviceProcessMutationTool(toolId);
}
export function asyncApprovalProfile(device, toolId, payload = {}) {
  if (!asyncApprovalDevice(device) || !asyncApprovalTool(toolId)) {
    return {approval_timeout_seconds:0,execution_budget_ms:0};
  }
  const cap = toolId === "hara.process.run" ? 10000 :
    ["hara.process.start","hara.process.interact"].includes(toolId) ? 3000 : 10000;
  const requested = Number(payload.timeout_ms ?? cap);
  const execution = Number.isFinite(requested) ? Math.max(0,Math.min(cap,Math.trunc(requested))) : cap;
  return {approval_timeout_seconds:LOCAL_APPROVAL_WINDOW_SECONDS,execution_budget_ms:execution};
}
export function claimedApprovalExpiresAt(profile, claimedAtUtc) {
  if (Number(profile?.approval_timeout_seconds) !== LOCAL_APPROVAL_WINDOW_SECONDS) {
    throw new Error("CALL_APPROVAL_PROFILE_INVALID");
  }
  const claimed = Date.parse(String(claimedAtUtc));
  const execution = Number(profile.execution_budget_ms);
  if (!Number.isFinite(claimed) || !Number.isInteger(execution) || execution < 0 || execution > 10000) {
    throw new Error("CALL_APPROVAL_PROFILE_INVALID");
  }
  return new Date(claimed + LOCAL_APPROVAL_WINDOW_SECONDS*1000 + execution +
    APPROVAL_TRANSPORT_GRACE_SECONDS*1000).toISOString();
}
export function isApprovalCallHandle(value) {
  return /^HARA-CALL-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value || ""));
}
export function pendingApprovalResult(call, computer, product = null) {
  return {
    state:"PENDING",accepted:true,operational_authority:"HARA_COMMANDER",
    execution_authority:null,runtime_authority_from_chatgpt:false,
    mutation_performed:null,customer_services_relay:false,computer,
    result:{
      call_id:call.call_id,session_id:call.call_id,request_id:call.request_id,
      tool_id:call.tool_id,call_state:String(call.state || "PENDING"),
      approval_timeout_seconds:Number(call.approval_timeout_seconds || 0),
      claimed_at_utc:call.claimed_at_utc || null,
      expires_at_utc:call.expires_at_utc,
      execution_outcome:"UNKNOWN",automatic_retry_allowed:false,
      next_action:"READ_EXISTING_CALL_STATUS",
      recommended_tool:"read_process_output",
      recommended_arguments:{computer,session_id:call.call_id},
    },
    ...(product ? {product} : {}),
  };
}
const authority = (v) => ["HARA_COMMANDER","HARA_SERVICES","HARA_COMMANDER_AGENT","LOCAL_OPERATOR_SESSION"].includes(v) ? v : null;
const code = (v) => typeof v === "string" && /^[A-Z][A-Z0-9_]{0,119}$/.test(v) ? v : null;
const identifier = (v) => typeof v === "string" && /^[A-Za-z0-9_.-]{1,120}$/.test(v) ? v : null;
export function safeCallResultMetadata(result, call) {
  const raw = result && typeof result === "object" ? result : {};
  const detail = raw.result && typeof raw.result === "object" ? raw.result : {};
  const receipt=String(raw.bridge_receipt_sha256 || "").trim().toLowerCase();
  return {
    schema:CALL_RESULT_METADATA_SCHEMA,call_id:call.call_id,request_id:call.request_id,
    tool_id:call.tool_id,call_state:call.state,
    state:["PASS","DENIED","FAILED","CANCELLED","EXPIRED","UNKNOWN","ERROR","TIMEOUT"].includes(raw.state) ? raw.state : "UNKNOWN",
    operational_authority:authority(raw.operational_authority),
    execution_authority:authority(raw.execution_authority),
    runtime_authority_from_chatgpt:false,
    mutation_performed:typeof raw.mutation_performed === "boolean" ? raw.mutation_performed : null,
    customer_services_relay:typeof raw.customer_services_relay === "boolean" ? raw.customer_services_relay : null,
    bridge_receipt_sha256:/^[0-9a-f]{64}$/.test(receipt) ? receipt : null,
    result:{
      function_id:["process.run","process.start","process.output","process.interact","process.terminate","filesystem.read","filesystem.write","filesystem.search","filesystem.list","device.info"].includes(detail.function_id) ? detail.function_id : null,
      risk_class:["READ_ONLY","MUTATING","PROCESS_MUTATING","FILESYSTEM_MUTATION","PROCESS_EXECUTION","WRITE","EXECUTE"].includes(detail.risk_class) ? detail.risk_class : null,
      process_exit_code:Number.isInteger(detail.process_exit_code) ? detail.process_exit_code : null,
      domain_success_inferred:typeof detail.domain_success_inferred === "boolean" ? detail.domain_success_inferred : false,
      content_redacted:true,
    },
    error_code:code(call.error_code),
  };
}
export function replayCallResultMetadata(metadata, call) {
  if (!metadata || metadata.schema !== CALL_RESULT_METADATA_SCHEMA ||
      metadata.call_id !== call.call_id || metadata.request_id !== call.request_id ||
      metadata.tool_id !== call.tool_id || metadata.call_state !== call.state) {
    return {
      state:"RESULT_METADATA_UNAVAILABLE",replayed:true,content_redacted:true,
      execution_outcome:"UNKNOWN",automatic_retry_allowed:false,
      mutation_performed:null,runtime_authority_from_chatgpt:false,
      result:{call_id:call.call_id,request_id:call.request_id,tool_id:call.tool_id,
        call_state:call.state,error_code:call.error_code || null,content_redacted:true},
    };
  }
  const safe=safeCallResultMetadata(metadata,call);
  return {...safe,replayed:true,content_redacted:true};
}
