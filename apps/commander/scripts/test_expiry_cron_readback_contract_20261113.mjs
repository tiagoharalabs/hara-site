import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {isCanonicalRedactedSha256,evaluateNativeExpiryReadback,MARKER} from './expiry_cron_readback_contract_20261113.mjs';
const cases=[];
function run(name,fn){fn();cases.push({name,state:'PASS'});}
const valid=MARKER+createHash('sha256').update('SYNTHETIC_TEST_ONLY').digest('base64url');
const receipts=[
  {step:1,receipt_state:'QA_HOSTED_REAL_DO_EXPIRY_HOLD_PASS',
    protected_units:1,consumed_units:1,redacted_count:1,expired_count:1},
  {step:2,receipt_state:'QA_HOSTED_REAL_DO_REPLAY_HOLD_PASS',
    protected_units:1,consumed_units:1,redacted_count:0,expired_count:0}
];
const call={state:'EXPIRED',payload_json:valid,
 reconciliation_required:true,execution_started:true,manual_reconciliation_required:true};
const baseline={receipts,call,providerCronSchedules:[],commercialVersionUnchanged:true};
const evaluate=changes=>evaluateNativeExpiryReadback({...baseline,...changes});
const altered=(scope,fn)=>{const x=JSON.parse(JSON.stringify(baseline));fn(x[scope]);return evaluateNativeExpiryReadback(x);};
run('original SHA256 base64url43 accepted',()=>assert.equal(isCanonicalRedactedSha256(valid),true));
run('hexadecimal SHA256 of length 64 rejected',()=>assert.equal(isCanonicalRedactedSha256(MARKER+'a'.repeat(64)),false));
run('base64url with padding rejected',()=>assert.equal(isCanonicalRedactedSha256(valid+'='),false));
run('truncated base64url rejected',()=>assert.equal(isCanonicalRedactedSha256(valid.slice(0,-1)),false));
run('extra marker rejected',()=>assert.equal(isCanonicalRedactedSha256(MARKER+valid),false));
run('noncanonical bottom bits rejected',()=>{
 const altered=valid.slice(0,-1)+'B';
 assert.equal(isCanonicalRedactedSha256(altered),false);
});
run('missing marker rejected',()=>assert.equal(isCanonicalRedactedSha256('x'.repeat(43)),false));
run('null rejected',()=>assert.equal(isCanonicalRedactedSha256(null),false));
run('two valid native receipts and protected quota pass scoped',()=>{
 const v=evaluate({});assert.equal(v.hosted_native_cron_accepted,true);
 assert.equal(v.commercial_cutover_authorized,false);
});
run('zero receipts is HOLD not false PASS',()=>assert.equal(evaluate({receipts:[]}).state,'HOLD_CRON_NOT_OBSERVED'));
run('one receipt is HOLD',()=>assert.equal(evaluate({receipts:[receipts[0]]}).state,'HOLD_SECOND_NATIVE_CRON_MISSING'));
run('three receipts is HOLD',()=>assert.equal(evaluate({receipts:[...receipts,receipts[0]]}).state,'HOLD_EXTRA_OR_DUPLICATE_RECEIPTS'));
run('cron still active is HOLD',()=>assert.equal(evaluate({providerCronSchedules:['* * * * *']}).state,'HOLD_CRON_DISABLE_NOT_CONFIRMED'));
run('production baseline drift is HOLD',()=>assert.equal(evaluate({commercialVersionUnchanged:false}).state,'HOLD_PRODUCTION_BASELINE_UNVERIFIED'));
run('call still executing is HOLD',()=>assert.equal(altered('call',x=>x.state='EXECUTING').state,'HOLD_EXPIRED_CONTENT_UNPROVEN'));
run('unredacted content is HOLD',()=>assert.equal(altered('call',x=>x.payload_json='QA_SYNTHETIC_RAW').state,'HOLD_EXPIRED_CONTENT_UNPROVEN'));
run('missing reconciliation metadata is HOLD',()=>assert.equal(altered('call',x=>x.reconciliation_required=false).state,'HOLD_RECONCILIATION_METADATA_UNPROVEN'));
run('missing execution started is HOLD',()=>assert.equal(altered('call',x=>x.execution_started=false).state,'HOLD_RECONCILIATION_METADATA_UNPROVEN'));
run('missing manual hold is HOLD',()=>assert.equal(altered('call',x=>x.manual_reconciliation_required=false).state,'HOLD_RECONCILIATION_METADATA_UNPROVEN'));
run('wrong receipt state is HOLD',()=>assert.equal(altered('receipts',x=>x[0].receipt_state='DONE').state,'HOLD_RECEIPT_STATE_OR_ORDER_INVALID'));
run('swapped receipt steps is HOLD',()=>assert.equal(altered('receipts',x=>x[1].step=1).state,'HOLD_RECEIPT_STATE_OR_ORDER_INVALID'));
run('quota consumed changed is HOLD',()=>assert.equal(altered('receipts',x=>x[1].consumed_units=0).state,'HOLD_QUOTA_PROTECTION_INCOMPLETE'));
run('protected quota missing is HOLD',()=>assert.equal(altered('receipts',x=>x[0].protected_units=0).state,'HOLD_QUOTA_PROTECTION_INCOMPLETE'));
run('duplicate scrub effect is HOLD',()=>assert.equal(altered('receipts',x=>x[1].redacted_count=1).state,'HOLD_EXPIRY_NOT_IDEMPOTENT'));
run('duplicate expiry effect is HOLD',()=>assert.equal(altered('receipts',x=>x[1].expired_count=1).state,'HOLD_EXPIRY_NOT_IDEMPOTENT'));
run('receipt array malformed is HOLD',()=>assert.equal(evaluate({receipts:null}).state,'HOLD_INVALID_RECEIPT_LIST'));
console.log(JSON.stringify({state:'EXACT_CRON_READBACK_BASE64URL_26_CASES_PASS',cases:cases.length,negative_cases:cases.length-2,case_names:cases.map(x=>x.name),cloudflare_called:false,production_mutated:false,commercial_cutover_authorized:false}));