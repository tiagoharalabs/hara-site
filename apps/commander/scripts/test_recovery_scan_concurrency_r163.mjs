import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
const m=await import('../src/recovery-scan-leases.mjs').catch(error=>({error}));
const subject=()=>{assert.ifError(m.error);return m;};
function fixture(t){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 db.exec('CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,revoked_at_utc TEXT);'+
 "INSERT INTO tenants VALUES('A'),('B');INSERT INTO commander_devices VALUES('D','A','ACTIVE',NULL)");
 db.exec(readFileSync(new URL('../migrations/0039_recovery_device_leases.sql',import.meta.url),'utf8'));
 const env={PRODUCT_DB:{prepare:sql=>({bind:(...args)=>({first:async()=>db.prepare(sql).get(...args)??null,
  run:async()=>({meta:{changes:db.prepare(sql).run(...args).changes}})})})}};
 return {db,env,device:{device_id:'D',tenant_id:'A'}};
}
for(const concurrency of [1,2,4])test('bounded fanout actually overlaps at '+concurrency,async()=>{
 let active=0,peak=0;const seen=[];
 const result=await subject().boundedRecoveryMap(Array.from({length:12},(_,i)=>i),concurrency,async i=>{
  active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,2));seen.push(i);active--;return i*2;
 });
 assert.equal(peak,concurrency);assert.equal(active,0);assert.deepEqual(result,Array.from({length:12},(_,i)=>i*2));
 assert.equal(new Set(seen).size,12);
});
for(const n of [0,-1,3,8,Infinity,'4'])test('unadmitted concurrency rejected '+n,async()=>{
 await assert.rejects(()=>subject().boundedRecoveryMap([1],n,async()=>{}),/RECOVERY_SCAN_CONCURRENCY_INVALID/);
});
test('failed task drains active work before rejecting',async()=>{
 let active=0;await assert.rejects(()=>subject().boundedRecoveryMap([1,2,3,4],2,async n=>{
  active++;try{await new Promise(r=>setTimeout(r,n===1?1:10));if(n===1)throw Error('FAIL');}finally{active--;}
 }),/FAIL/);assert.equal(active,0);
});
test('exclusive enrollment lease, crash expiry and old-token release fence',async t=>{
 const {env,device}=fixture(t),s=subject();
 const first=await s.claimRecoveryDeviceLease(env,device,1000);
 assert.ok(first?.lease_token);assert.equal(await s.claimRecoveryDeviceLease(env,device,1001),null);
 const second=await s.claimRecoveryDeviceLease(env,device,31001);
 assert.ok(second);assert.notEqual(first.lease_token,second.lease_token);
 assert.equal(await s.releaseRecoveryDeviceLease(env,first),false);
 assert.equal(await s.releaseRecoveryDeviceLease(env,second),true);
 assert.ok(await s.claimRecoveryDeviceLease(env,device,31002));
});
test('foreign tenant and revoked enrollment cannot claim',async t=>{
 const {env,device,db}=fixture(t),s=subject();
 assert.equal(await s.claimRecoveryDeviceLease(env,{...device,tenant_id:'B'},1000),null);
 db.exec("UPDATE commander_devices SET revoked_at_utc='2026-10-24T00:00:00Z'");
 assert.equal(await s.claimRecoveryDeviceLease(env,device,1000),null);
});
test('partition stable, bounded and enrollment scoped',()=>{
 const s=subject(),ids=new Set();for(let i=0;i<100;i++)ids.add(s.recoveryPartition('D'+i));
 assert.ok(ids.size>1);assert.ok([...ids].every(i=>Number.isInteger(i)&&i>=0&&i<16));
 assert.equal(s.recoveryPartition('D1'),s.recoveryPartition('D1'));
});
