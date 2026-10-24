import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const start=source.indexOf('async function productTransactionHistory(');
const end=source.indexOf('async function dashboardForSubject(',start);
assert.ok(start>=0&&end>start);
const fakePeriod={start:'2026-10-01T00:00:00.000Z',end:'2026-11-01T00:00:00.000Z'};
const run=vm.runInNewContext('('+source.slice(start,end).trim()+')',{Date,Number,
  commanderCurrentMonthUtc:()=>fakePeriod});
let tests=0;
for(const values of [{calls_period:15,calls_total:500},{calls_period:0,calls_total:0},{calls_period:'33',calls_total:'80000'}]){
  let calls=0,sql='',bindings=[];
  const env={PRODUCT_DB:{prepare(query){calls++;sql=query;return{bind(...args){bindings=args;return{first:async()=>values};}};}}};
  const result=await run(env,'TENANT-A','SUBJECT-A',true);
  assert.equal(calls,1);assert.equal(bindings.length,12);
  assert.equal(bindings[0],'TENANT-A');assert.equal(bindings[1],'SUBJECT-A');
  assert.equal(bindings[2],fakePeriod.start);assert.equal(bindings[3],fakePeriod.end);
  assert.equal(bindings[4],'TENANT-A');assert.equal(bindings[5],'SUBJECT-A');
  assert.equal(bindings[8],'TENANT-A');assert.equal(bindings[9],'SUBJECT-A');
  assert.equal(bindings[10],'TENANT-A');assert.equal(bindings[11],'SUBJECT-A');
  assert.ok(sql.includes('WITH relay AS'));
  assert.equal(result.calls_period,Number(values.calls_period));
  assert.equal(result.internal_lifetime_calls,Number(values.calls_total));
  assert.equal(result.available,true);
  assert.equal(result.detail_level,'AGGREGATE_ONLY');tests++;
}
for(const stage of ['prepare','first']){
  const env={PRODUCT_DB:{prepare(){if(stage==='prepare')throw new Error('synthetic');return{bind(){return{first:async()=>{throw new Error('synthetic');}};}};}}};
  const result=await run(env,'TENANT-A','SUBJECT-A',true);
  assert.equal(result.available,false);assert.equal(result.internal_lifetime_calls,null);
  assert.equal(result.calls_period,null);tests++;
}
const noLifetimeDb={
  PRODUCT_DB:{
    prepare(){
      return {
        bind(){
          return {first:async()=>({calls_period:8,calls_total:120})};
        }
      };
    }
  }
};
const noLifetime=await run(noLifetimeDb,'TENANT-A','SUBJECT-A');
assert.ok(!Object.hasOwn(noLifetime,'internal_lifetime_calls'));tests++;
console.log(JSON.stringify({state:'PASS',tests,actual_worker_function:true,d1_round_trips_per_history_read:1,error_semantics:'UNAVAILABLE_NOT_ZERO'},null,2));
