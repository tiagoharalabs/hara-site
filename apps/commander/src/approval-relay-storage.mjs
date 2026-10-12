import { safeCallResultMetadata, replayCallResultMetadata, pendingApprovalResult, CALL_RESULT_METADATA_SCHEMA, TERMINAL_CALL_STATES } from "./approval-async-relay.mjs";

export const CALL_ROW_FIELDS = "call_id,request_id,tenant_id,subject_id,device_id,tool_id,state,created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,payload_json,result_json,error_code,usage_mode,usage_units,usage_period_key,usage_budget_id,approval_timeout_seconds,execution_budget_ms,call_result_metadata_json";
export function parseCallMetadata(value) {
  try { const x=JSON.parse(String(value || "null"));return x&&typeof x==="object"?x:null; } catch {return null;}
}
export async function settleCallUsage(env,row,result=null) {
  let metadata=parseCallMetadata(row.call_result_metadata_json);
  if (metadata && (metadata.schema!==CALL_RESULT_METADATA_SCHEMA || metadata.call_id!==row.call_id || metadata.request_id!==row.request_id || metadata.tool_id!==row.tool_id || metadata.call_state!==row.state)) throw new Error("CALL_RESULT_METADATA_INVALID");
  if (metadata) metadata=safeCallResultMetadata(metadata,row);
  if (result) metadata=safeCallResultMetadata(result,row);
  if (!metadata) {
    if (row.state==="COMPLETED" || row.state==="FAILED" || row.claimed_at_utc) {
      throw new Error("CALL_RESULT_METADATA_UNAVAILABLE");
    }
    metadata=safeCallResultMetadata({state:row.state,mutation_performed:false},row);
  }
  const units=Number(row.usage_units || 0),mode=String(row.usage_mode || "CLOUD_QUOTA");
  let usage={mode,state:mode,units:mode==="UNMETERED"?0:units,
    period_key:row.usage_period_key || null,budget_id:row.usage_budget_id || null,cloud_quota_transaction:false};
  if (mode==="CLOUD_QUOTA" && units>0) {
    const receipt=row.state==="COMPLETED"&&metadata.state==="PASS"
      ? metadata.bridge_receipt_sha256 : null;
    if (row.state==="EXPIRED" && row.claimed_at_utc && !metadata.bridge_receipt_sha256) {
      throw new Error("CALL_EXECUTION_OUTCOME_UNKNOWN");
    }
    const q=env.TENANT_QUOTA.getByName(row.tenant_id);
    const settled=await q.settleDeviceCall(row.request_id,row.subject_id,row.usage_period_key,units,receipt);
    if (!settled.ok) throw new Error(String(settled.code || "CALL_USAGE_SETTLEMENT_FAILED"));
    usage={...usage,state:settled.state,units:settled.state==="COMMITTED"?units:0,cloud_quota_transaction:true};
  }
  metadata={...metadata,usage};
  const encoded=JSON.stringify(metadata);
  const saved=await env.PRODUCT_DB.prepare("UPDATE commander_device_calls SET call_result_metadata_json=? WHERE call_id=? AND tenant_id=? AND subject_id=? AND state=?")
    .bind(encoded,row.call_id,row.tenant_id,row.subject_id,row.state).run();
  if (!saved.meta?.changes) throw new Error("CALL_RESULT_METADATA_WRITE_CONFLICT");
  row.call_result_metadata_json=encoded;
  return metadata;
}
export async function readScopedCall(env,context,callId) {
  return env.PRODUCT_DB.prepare("SELECT "+CALL_ROW_FIELDS+" FROM commander_device_calls WHERE call_id=? AND tenant_id=? AND subject_id=? LIMIT 1")
    .bind(callId,context.tenant_id,context.subject_id).first();
}
export async function acceptedCallStatus(env,context,callId,{expectedDeviceId=null,nowUtc,newMarker,isRedacted}={}) {
  let row=await readScopedCall(env,context,callId);
  if (!row || (expectedDeviceId && row.device_id!==expectedDeviceId)) throw new Error("DEVICE_CALL_NOT_FOUND");
  if (["PENDING","EXECUTING"].includes(row.state) && String(row.expires_at_utc)<=nowUtc) {
    await env.PRODUCT_DB.prepare("UPDATE commander_device_calls SET state='EXPIRED',completed_at_utc=?,error_code='DEVICE_CALL_EXPIRED' WHERE call_id=? AND tenant_id=? AND subject_id=? AND state IN ('PENDING','EXECUTING') AND expires_at_utc<=?")
      .bind(nowUtc,row.call_id,row.tenant_id,row.subject_id,nowUtc).run();
    row=await readScopedCall(env,context,callId);
  }
  if (!TERMINAL_CALL_STATES.includes(row.state)) return {row,result:null,metadata:null,content_redacted:false};
  const raw=row.result_json && !isRedacted(row.result_json) ? String(row.result_json) : null;
  let result=raw?JSON.parse(raw):null,metadata=parseCallMetadata(row.call_result_metadata_json);
  if (raw || metadata || (!row.claimed_at_utc && ["EXPIRED","CANCELLED"].includes(row.state))) {
    metadata=await settleCallUsage(env,row,result);
  }
  if (raw) {
    const marker=await newMarker(raw);
    const changed=await env.PRODUCT_DB.prepare("UPDATE commander_device_calls SET result_json=? WHERE call_id=? AND tenant_id=? AND subject_id=? AND result_json=?")
      .bind(marker,row.call_id,row.tenant_id,row.subject_id,raw).run();
    if (!changed.meta?.changes) result=null;
  }
  return {row,result,metadata,content_redacted:!result};
}
export function publicAcceptedCallStatus(status,computer,project) {
  const {row,result,metadata}=status;
  if (!TERMINAL_CALL_STATES.includes(row.state)) {
    const mode=String(row.usage_mode || "CLOUD_QUOTA");
    return pendingApprovalResult(row,computer,{quota:{mode,state:mode==="CLOUD_QUOTA" ? "RESERVED" : mode,original_units:mode==="UNMETERED" ? 0 : Number(row.usage_units || 0),additional_usage_units:0,period_key:row.usage_period_key || null,cloud_quota_transaction:false}});
  }
  const original=result ? project(row.tool_id,result) : replayCallResultMetadata(metadata,row);
  return {...original,computer,call_id:row.call_id,original_tool_id:row.tool_id,
    content_redacted:status.content_redacted,
    retrieval:{operation:"CALL_STATUS_READ",read_only:true,new_call_enqueued:false,additional_usage_units:0},
    product:{quota:metadata?.usage || null}};
}
