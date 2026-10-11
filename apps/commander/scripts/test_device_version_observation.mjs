import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {observedAgentVersion, reconcileAgentVersion, VERSION_OBSERVATION_SQL} from '../src/device-version-observation.mjs';
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS '+name);}
const device={tenant_id:'tenant-a',device_id:'device-a',state:'ACTIVE',revoked_at_utc:null,agent_version:'0.3.41'};
const call={tool_id:'hara.device.info',state:'COMPLETED'};
function result(version='0.3.44',id='device-a',fn='device.info'){
 return {function_id:fn,process_exit_code:0,stdout:JSON.stringify({device_id:id,agent_version:version,hostname:'test-only'})};
}
function db(changes=1,success=true){const seen=[];return {seen,PRODUCT_DB:{prepare(sql){return {bind(...args){seen.push({sql,args});return {async run(){return {success,meta:{changes}};}};}};}}};}
await test('accepted authenticated info result',()=>assert.equal(observedAgentVersion(device,call,result()),'0.3.44'));
await test('accepted ping result',()=>assert.equal(observedAgentVersion(device,{...call,tool_id:'hara.ping'},result('0.3.44','device-a','device.ping')),'0.3.44'));
await test('wrong device denied',()=>assert.equal(observedAgentVersion(device,call,result('0.3.44','device-b')),null));
await test('wrong function denied',()=>assert.equal(observedAgentVersion(device,call,result('0.3.44','device-a','process.run')),null));
await test('arbitrary process output ignored',()=>assert.equal(observedAgentVersion(device,{...call,tool_id:'hara.process.run'},result()),null));
await test('failed call ignored',()=>assert.equal(observedAgentVersion(device,{...call,state:'FAILED'},result()),null));
await test('failed process ignored',()=>assert.equal(observedAgentVersion(device,call,{...result(),process_exit_code:1}),null));
await test('revoked device ignored',()=>assert.equal(observedAgentVersion({...device,revoked_at_utc:'2026-10-11T00:00:00Z'},call,result()),null));
await test('inactive device ignored',()=>assert.equal(observedAgentVersion({...device,state:'REVOKED'},call,result()),null));
await test('invalid JSON ignored',()=>assert.equal(observedAgentVersion(device,call,{...result(),stdout:'{'}),null));
await test('invalid versions ignored',()=>{for(const v of ['', 'latest','0.3.44\n','01.3.44','1.2',1,null,'1.2.3.4','1.2.3;DROP TABLE x'])assert.equal(observedAgentVersion(device,call,result(v)),null);});
await test('oversized output ignored',()=>assert.equal(observedAgentVersion(device,call,{...result(),stdout:' '.repeat(8193)}),null));
await test('10,000 matching observations issue no SQL',async()=>{const env=db();for(let i=0;i<10000;i++)assert.equal((await reconcileAgentVersion(env,{...device,agent_version:'0.3.44'},call,result())).state,'UNCHANGED');assert.equal(env.seen.length,0);});
await test('change uses one parameterized scoped CAS',async()=>{const env=db();assert.equal((await reconcileAgentVersion(env,device,call,result())).state,'UPDATED');assert.deepEqual(env.seen,[{sql:VERSION_OBSERVATION_SQL,args:['0.3.44','tenant-a','device-a','0.3.41']}]);});
await test('concurrent change not overwritten',async()=>assert.equal((await reconcileAgentVersion(db(0),device,call,result())).state,'CONCURRENT_CHANGE'));
await test('real rollback metadata allowed',async()=>{const env=db();await reconcileAgentVersion(env,{...device,agent_version:'0.3.44'},call,result('0.3.43'));assert.equal(env.seen[0].args[0],'0.3.43');});
await test('missing previous version supported',async()=>{const env=db();await reconcileAgentVersion(env,{...device,agent_version:null},call,result());assert.equal(env.seen[0].args[3],null);});
await test('storage failure is not success',async()=>assert.rejects(()=>reconcileAgentVersion(db(0,false),device,call,result()),/PERSIST_FAILED/));
await test('exact SQL on SQLite preserves other tenants and concurrent updates',()=>{
 const code=`import sqlite3,sys,json\np=json.load(sys.stdin)\nc=sqlite3.connect(':memory:')\nc.execute('CREATE TABLE commander_devices (tenant_id TEXT,device_id TEXT,state TEXT,revoked_at_utc TEXT,agent_version TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,PRIMARY KEY(tenant_id,device_id))')\nrows=[('tenant-a','device-a','ACTIVE',None,'0.3.41','EVENT_V2','original'),('tenant-b','device-a','ACTIVE',None,'0.3.41','EVENT_V2','original'),('tenant-a','revoked','ACTIVE','revoked','0.3.41','EVENT_V2','original')]\nc.executemany('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?)',rows)\nassert c.execute(p['sql'],('0.3.44','tenant-a','device-a','0.3.41')).rowcount==1\nassert c.execute(p['sql'],('0.3.42','tenant-a','device-a','0.3.41')).rowcount==0\nassert c.execute(p['sql'],('0.3.44','tenant-a','revoked','0.3.41')).rowcount==0\nassert c.execute('SELECT agent_version FROM commander_devices WHERE tenant_id=?',('tenant-b',)).fetchone()[0]=='0.3.41'\nassert c.execute('SELECT tunnel_mode,last_seen_at_utc FROM commander_devices WHERE tenant_id=? AND device_id=?',('tenant-a','device-a')).fetchone()==('EVENT_V2','original')\nprint('SQLITE_EXACT_SQL=PASS')`;
 const p=spawnSync('python3',['-c',code],{input:JSON.stringify({sql:VERSION_OBSERVATION_SQL}),encoding:'utf8'});
 assert.equal(p.status,0,p.stderr);console.log(p.stdout.trim());
});
await test('worker integration after accepted completion and fail-soft',()=>{
 const text=readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
 const fn=text.slice(text.indexOf('async function completeDeviceCall('),text.indexOf('async function deviceCallStatus('));
 assert.ok(text.includes('from "./device-version-observation.mjs"'));
 assert.ok(fn.indexOf('reconcileAgentVersion(env, device, row, body.result)')>fn.indexOf('throw new Error("DEVICE_CALL_NOT_EXECUTING")'));
 assert.ok(fn.includes('DEVICE_VERSION_OBSERVATION_DEGRADED'));
});
console.log(JSON.stringify({schema:'hara.device-version-observation-tests.v1',passed,failed:0,live_test:false}));
