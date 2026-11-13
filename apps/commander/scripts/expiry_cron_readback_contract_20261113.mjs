// Pure QA-only verification of native expiry cron receipts. No provider calls.
export const MARKER='HARA_REDACTED_SHA256:';
const canonical=/^[A-Za-z0-9_-]{43}$/;
const expectedStates=[
  'QA_HOSTED_REAL_DO_EXPIRY_HOLD_PASS',
  'QA_HOSTED_REAL_DO_REPLAY_HOLD_PASS'
];
const hold=(reason,observed=0)=>({
  state:'HOLD_'+reason,received_receipts:observed,
  hosted_native_cron_accepted:false,commercial_cutover_authorized:false
});
export function isCanonicalRedactedSha256(value) {
  if(typeof value!=='string'||!value.startsWith(MARKER))return false;
  const token=value.slice(MARKER.length);
  // For a 32-byte SHA-256 hash, 43 unpadded Base64URL chars must end
  // with a value divisible by 4 (two unused low bits). A regexp alone is insufficient.
  if(!canonical.test(token))return false;
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const last=alphabet.indexOf(token[42]);
  if(last<0||last%4!==0)return false;
  return true;
}
export function evaluateNativeExpiryReadback({receipts,call,providerCronSchedules,commercialVersionUnchanged}={}) {
  if(!Array.isArray(providerCronSchedules)||providerCronSchedules.length!==0)
    return hold('CRON_DISABLE_NOT_CONFIRMED',Array.isArray(receipts)?receipts.length:0);
  if(commercialVersionUnchanged!==true)return hold('PRODUCTION_BASELINE_UNVERIFIED',Array.isArray(receipts)?receipts.length:0);
  if(!Array.isArray(receipts))return hold('INVALID_RECEIPT_LIST');
  if(receipts.length===0)return hold('CRON_NOT_OBSERVED',0);
  if(receipts.length===1)return hold('SECOND_NATIVE_CRON_MISSING',1);
  if(receipts.length!==2)return hold('EXTRA_OR_DUPLICATE_RECEIPTS',receipts.length);
  if(!call||!isCanonicalRedactedSha256(call.payload_json)||call.state!=='EXPIRED')
    return hold('EXPIRED_CONTENT_UNPROVEN',2);
  if(call.reconciliation_required!==true||call.execution_started!==true||
     call.manual_reconciliation_required!==true)
    return hold('RECONCILIATION_METADATA_UNPROVEN',2);
  const [first,second]=receipts;
  if(first.step!==1||second.step!==2||
     first.receipt_state!==expectedStates[0]||second.receipt_state!==expectedStates[1])
    return hold('RECEIPT_STATE_OR_ORDER_INVALID',2);
  for(const row of receipts){
    if(row.protected_units!==1||row.consumed_units!==1)
      return hold('QUOTA_PROTECTION_INCOMPLETE',2);
  }
  if(first.redacted_count!==1||second.redacted_count!==0||
     first.expired_count!==1||second.expired_count!==0)
    return hold('EXPIRY_NOT_IDEMPOTENT',2);
  return {
    state:'QA_HOSTED_REAL_QUOTA_NATIVE_CRON_TWO_RECEIPTS_SCOPED_PASS',
    received_receipts:2,
    sha256_marker_format:'BASE64URL_43_UNPADDED',
    hosted_native_cron_accepted:true,
    commercial_cutover_authorized:false,
    global_do_quiescence_proven:false
  };
}