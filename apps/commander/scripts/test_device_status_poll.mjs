import assert from "node:assert/strict";
import fs from "node:fs";
import {customerStatusWaitMs,CUSTOMER_STATUS_TIMEOUT_MS} from "../src/device-status-poll.mjs";

let checked=0;
function check(fn){fn();checked++;}
check(()=>assert.equal(CUSTOMER_STATUS_TIMEOUT_MS,45000));
for(const [elapsed,expected] of [
  [0,250],[500,250],[1499,250],[1500,500],[5000,1000],
  [15000,2000],[30000,3000],[44999,3000],
]) check(()=>assert.equal(customerStatusWaitMs(250,elapsed,45000),expected));
check(()=>assert.equal(customerStatusWaitMs(1000,0,45000),1000));
check(()=>assert.equal(customerStatusWaitMs(5000,0,45000),3000));
check(()=>assert.equal(customerStatusWaitMs(-1,0,45000),250));
check(()=>assert.equal(customerStatusWaitMs(NaN,0,45000),250));
check(()=>assert.equal(customerStatusWaitMs(0,30000,150),150));
check(()=>assert.equal(customerStatusWaitMs(250,44999,1),1));
for(const bad of [NaN,-1,Infinity]) check(()=>assert.throws(
  ()=>customerStatusWaitMs(250,bad,40000),/STATUS_POLL_ELAPSED_INVALID/));
for(const bad of [0,-1,NaN]) check(()=>assert.throws(
  ()=>customerStatusWaitMs(250,0,bad),/STATUS_POLL_DEADLINE/));
const oldReads=Math.ceil(CUSTOMER_STATUS_TIMEOUT_MS/250);
let elapsed=0,reads=0;
while(elapsed<CUSTOMER_STATUS_TIMEOUT_MS) {
 const wait=customerStatusWaitMs(250,elapsed,CUSTOMER_STATUS_TIMEOUT_MS-elapsed);
 check(()=>assert.ok(wait>=1 && wait<=3000));
 elapsed+=wait;
 reads++;
}
check(()=>assert.ok(reads<=40,"ADAPTIVE_POLL_COUNT_TOO_HIGH_"+reads));
check(()=>assert.ok(reads<oldReads/4,"INSUFFICIENT_POLL_REDUCTION_"+reads));
const source=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
check(()=>assert.ok(source.includes("customerStatusWaitMs(")));
check(()=>assert.ok(source.includes("const deadline = startedAt + CUSTOMER_STATUS_TIMEOUT_MS")));
check(()=>assert.ok(source.includes('throw new Error("DEVICE_CALL_TIMEOUT")')));
check(()=>assert.ok(source.includes("const now = Date.now();")));
console.log(JSON.stringify({
 schema:"hara.commander-adaptive-status-poll.v1",checked,passed:checked,failed:0,
 synthetic_old_fixed_250ms_reads:oldReads,
 synthetic_new_adaptive_reads:reads,
 synthetic_reduction_fraction:Number((1-reads/oldReads).toFixed(3)),
 workload:"one 45-second pending call with retry_after_ms=250 (synthetic only)",
 production_savings_measured:false
},null,2));
