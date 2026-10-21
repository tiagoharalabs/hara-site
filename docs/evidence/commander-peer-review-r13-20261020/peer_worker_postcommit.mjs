#!/usr/bin/env node
// R13 independent direct Worker enrollment transaction test.
// SQL uses actual repository migrations and device-enrollment SQL.
// Inject exception AFTER the D1 batch commit, before the Worker can return
// the fresh device token. No HTTP server, provider, network, real tokens.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { DatabaseSync } from 'node:sqlite';
import { createHash, webcrypto } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const HERE=path.dirname(fileURLToPath(import.meta.url));
const ROOT=process.env.HARA_PEER_SOURCE||path.join(HERE,'source');
const APP=path.join(ROOT,'apps/commander');
const mod=await import(path.join(APP,'src/device-enrollment.mjs'));
const worker=fs.readFileSync(path.join(APP,'src/worker.js'),'utf8');
const start=worker.indexOf('async function enrollDevice(');
const end=worker.indexOf('\nasync function resolveDeviceCredential(',start);
assert(start>=0&&end>start);
const now='2026-10-20T23:30:00.000Z', tomorrow='2026-10-21T23:30:00.000Z';
const db=new DatabaseSync(':memory:');
const migrationFiles=fs.readdirSync(path.join(APP,'migrations')).filter(x=>x.endsWith('.sql')).sort();
for(const name of migrationFiles){db.exec(fs.readFileSync(path.join(APP,'migrations',name),'utf8'));}
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES ('QA_TENANT','QA only','ACTIVE','DEV',?)").run(now);
db.prepare("INSERT INTO users(subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES ('QA_OWNER','QA_TENANT','https://qa.invalid','qa','ACTIVE','OWNER',?)").run(now);
db.prepare("INSERT INTO users(subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES ('QA_OWNER_2','QA_TENANT','https://qa.invalid','qa-2','ACTIVE','OWNER',?)").run(now);
db.prepare("INSERT OR IGNORE INTO plans (plan_code,display_name,meter_id,period_kind,unit_limit,state,active_device_limit) VALUES ('FOUNDER_INTERNAL','QA Founder','HARA_COMMANDER_GOVERNED_INVOKE','NONE',NULL,'ACTIVE',NULL)").run();
db.prepare("INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc) VALUES ('QA_ENT','QA_TENANT','QA_OWNER','FOUNDER_INTERNAL','ACTIVE',?)").run(now);
const hash=s=>createHash('sha256').update(s).digest('hex');
const seedPair=(label,subject)=>db.prepare("INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc) VALUES (?,?,?,?,?,?)").run('PAIR_'+label,hash('QA_PAIR_'+label),'QA_TENANT',subject,now,tomorrow);
seedPair('FAIL_AFTER_COMMIT','QA_OWNER');
seedPair('POSITIVE','QA_OWNER_2');
let failSelection=true, selectionFaults=0;
const productDb={
 prepare(sql){return {bind(...args){return {
   async first(){return db.prepare(sql).get(...args)||null;},
   async run(){
     if(failSelection&&sql.includes('INSERT OR IGNORE INTO commander_device_selections')){
       selectionFaults++;
       throw new Error('QA_SELECTION_WRITE_UNAVAILABLE_AFTER_COMMIT');
     }
     const r=db.prepare(sql).run(...args);
     return {meta:{changes:Number(r.changes)}};
   }
 };}}},
 async batch(statements){
   db.exec('BEGIN IMMEDIATE');
   try{
     const results=[];
     for(const stmt of statements){results.push(await stmt.run());}
     db.exec('COMMIT');
     return results;
   }catch(e){db.exec('ROLLBACK');throw e;}
 }
};
let syntheticTokenSequence=0;
const context=vm.createContext({
  DEVICE_ENROLL_INSERT_SQL:mod.DEVICE_ENROLL_INSERT_SQL,
  DEVICE_ENROLL_CONSUME_SQL:mod.DEVICE_ENROLL_CONSUME_SQL,
  DEVICE_ENROLL_LIMIT_SQL:mod.DEVICE_ENROLL_LIMIT_SQL,
  cleanOpaque:v=>String(v),
  sha256:async v=>hash(String(v)),
  cleanDeviceName:v=>String(v),
  normalizeDevicePlatform:v=>String(v),
  cleanAgentValue:v=>String(v||''),
  normalizeApprovalMode:v=>String(v||'ASK_EVERY_ACTION'),
  crypto:webcrypto,
  randomToken:()=> 'QA_SYNTHETIC_DO_NOT_USE_AS_CREDENTIAL_'+String(++syntheticTokenSequence),
  nowIso:()=>now,
});
vm.runInContext(worker.slice(start,end)+'\nglobalThis.QA_ENROLL=enrollDevice;',context);
const enroll=(token)=>context.QA_ENROLL({PRODUCT_DB:productDb},
  {pairing_token:token,device_name:'QA_HOST',platform:'LINUX',architecture:'x86_64',agent_version:'0.3.43',approval_mode:'ASK_EVERY_ACTION'});
let firstError=null;
try{await enroll('QA_PAIR_FAIL_AFTER_COMMIT');}
catch(e){firstError=e.message;}
const orphan={
  worker_response_error:firstError,
  remote_active_devices:Number(db.prepare("SELECT COUNT(*) n FROM commander_devices WHERE tenant_id='QA_TENANT' AND state='ACTIVE' AND revoked_at_utc IS NULL").get().n),
  pairing_token_consumed:db.prepare("SELECT consumed_at_utc FROM device_pairing_tokens WHERE pairing_id='PAIR_FAIL_AFTER_COMMIT'").get().consumed_at_utc!==null,
  auto_revoked:false,
  selection_faults:selectionFaults,
  selection_rows:Number(db.prepare("SELECT COUNT(*) n FROM commander_device_selections").get().n),
  client_received_new_device_token:false,
};
let retryError=null;
try{await enroll('QA_PAIR_FAIL_AFTER_COMMIT');}
catch(e){retryError=e.message;}
orphan.retry_same_pairing_error=retryError;
failSelection=false;
let positive=null;
try{
 const r=await enroll('QA_PAIR_POSITIVE');
 positive={received_token:typeof r.device_token==='string'&&r.device_token.length>0, device_id_prefix:r.device_id.startsWith('HARA-DEVICE-'),state:r.state,selection_rows:Number(db.prepare("SELECT COUNT(*) n FROM commander_device_selections").get().n)};
}catch(e){positive={error:e.message};}
const reproduced=orphan.remote_active_devices===1&&orphan.pairing_token_consumed&&!!orphan.worker_response_error
 && retryError==='DEVICE_PAIRING_INVALID'&&positive?.received_token&&positive.selection_rows===1;
const report={
 schema:'hara.commander.peer-r13-server-postcommit-uncertainty.v1',
 observed_source:'exact enrollDevice function + actual device-enrollment SQL + 40 migrations',
 fixed_head:'1d8b183564f1d8498c0b71ae7e35e924787e8010',
 postcommit_fault_injected:'INSERT commander_device_selections',
 orphan,
 positive_control:positive,
 reproduced,
 network_requests:0, production_mutation:false,
 no_client_token_logged:true,
};
fs.writeFileSync(path.join(HERE,'r13-worker-postcommit-results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
db.close();
process.exitCode=reproduced?2:1;
