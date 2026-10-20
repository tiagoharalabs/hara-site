import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const start=source.indexOf('async function productTransactionHistory(');
const end=source.indexOf('async function dashboardForSubject(',start);
assert.ok(start>=0&&end>start);
const run=vm.runInNewContext('('+source.slice(start,end).trim()+')',{Date});
let tests=0;
for(const values of [{calls_7d:15,calls_total:500},{calls_7d:0,calls_total:0},{calls_7d:'33',calls_total:'80000'}]) {
  let calls=0, sql='',bindings=[];
  const env={PRODUCT_DB:{prepare(query){calls++;sql=query;return{bind(...args){bindings=args;return{first:async()=>values};}};}}};
  const result=await run(env,'TENANT-A','SUBJECT-A');
  assert.equal(calls,1);assert.equal(bindings.length,14);
  assert.deepEqual([0,2,4,7,11].map(i=>bindings.slice(i,i+2)),
    Array(5).fill(null).map(()=>['TENANT-A','SUBJECT-A']));
  assert.equal(bindings[13],bindings[9].slice(0,10));
  assert.ok(sql.includes('commander_device_call_history_totals'));
  assert.ok(sql.includes('commander_device_call_history_hourly'));
  assert.equal(result.calls_7d,Number(values.calls_7d));assert.equal(result.calls_total,Number(values.calls_total));
  assert.equal(result.available,true);assert.equal(result.detail_level,'AGGREGATE_ONLY');tests++;
}
for(const stage of ['prepare','first']) {
  const env={PRODUCT_DB:{prepare(){if(stage==='prepare')throw new Error('synthetic');return{bind(){return{first:async()=>{throw new Error('synthetic');}};}};}}};
  const result=await run(env,'TENANT-A','SUBJECT-A');
  assert.equal(result.available,false);assert.equal(result.calls_total,null);assert.equal(result.calls_7d,null);tests++;
}
console.log(JSON.stringify({state:'PASS',tests,actual_worker_function:true,d1_round_trips_per_history_read:1,error_semantics:'UNAVAILABLE_NOT_ZERO',cloudflare_concurrency_certified:false},null,2));
