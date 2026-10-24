// Authorized Services QA executor, not a Worker deployment or release admission.
// Uses native Wrangler against the exact dedicated QA D1 and the real HTTPS sink.
// No credential values, caller-supplied SQL or destinations leave this process.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const execute=promisify(execFile);
const root='/tmp/hara-cmd163-hosted-qa-20261024';
const canary='hara-commander-r163-canary-dev-20261024';
const databaseId='e769835e-0748-4f41-b868-c7c76b627fe9';
const origin='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
const digest=value=>createHash('sha256').update(value).digest('hex');
const stable=value=>JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))));

async function main(){
 const [campaign,node,wrangler,expectedModuleSha]=process.argv.slice(2);
 assert.equal(path.dirname(campaign),root);assert.ok(path.basename(campaign).startsWith('codex-r163-integration-'));
 assert.equal(fs.lstatSync(campaign).isSymbolicLink(),false);
 assert.equal(fs.statSync(campaign).mode&0o077,0);
 assert.equal(node,'/home/sartorius/.nvm/versions/node/v24.15.0/bin/node');
 assert.equal(wrangler,'/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules/wrangler/bin/wrangler.js');
 const original=JSON.parse(fs.readFileSync(path.join(campaign,'preflight-public.json'),'utf8'));
 const checkOriginal=()=>{
  for(const [name,sha] of Object.entries(original.original_evidence))assert.equal(digest(fs.readFileSync(path.join(root,name))),sha);
 };
 checkOriginal();
 const configPath=path.join(root,'main.config.jsonc'),config=JSON.parse(fs.readFileSync(configPath,'utf8'));
 assert.equal(digest(fs.readFileSync(configPath)),original.configs['main.config.jsonc'].sha256);
 assert.equal(config.name,'hara-commander-r163-canary-20261024');assert.equal(config.vars.ENVIRONMENT,'DEV');
 assert.equal(config.routes,undefined);assert.equal(config.d1_databases.length,1);
 assert.equal(config.d1_databases[0].database_id,databaseId);
 assert.equal(config.d1_databases[0].database_name,canary);
 const modulePath=path.join(campaign,'recovery-delivery.mjs');
 assert.equal(digest(fs.readFileSync(modulePath)),expectedModuleSha);
 const {dispatchRecoveryDeliveries}=await import(pathToFileURL(modulePath));
 const agent=JSON.parse(fs.readFileSync(path.join(campaign,'hosted-agent-evidence.json'),'utf8'));
 assert.equal(agent.state,'PASS');assert.equal(agent.events.length,4);
 const ids=agent.events.map(x=>x.server_event_id);
 assert.ok(ids.every(id=>/^HARA-REC-[0-9a-f]{48}$/.test(id)));
 let queryNumber=0,rowsRead=0,rowsWritten=0,d1DurationMs=0;
 const nativeEnv={...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG_PATH:path.join(campaign,'wrangler-delivery.log')};
 const literal=value=>{
  if(value===null)return 'NULL';
  if(typeof value==='number'&&Number.isSafeInteger(value))return String(value);
  assert.equal(typeof value,'string');return "'"+value.replaceAll("'","''")+"'";
 };
 async function query(sql,args=[]){
  let index=0;const bound=sql.replaceAll('?',()=>literal(args[index++]));assert.equal(index,args.length);
  const sqlPath=path.join(campaign,'query-'+String(++queryNumber).padStart(3,'0')+'.sql');
  fs.writeFileSync(sqlPath,bound,{flag:'wx',mode:0o600});
  // --file invokes D1 bulk import, whose result omits SELECT/RETURNING rows.
  // Use the query API via --command; SQL contains only persisted metadata.
  const {stdout}=await execute(node,[wrangler,'d1','execute',canary,'--remote','--config',configPath,'--json','--command',bound],
   {cwd:campaign,env:nativeEnv,timeout:30000,maxBuffer:2*1024*1024});
  const values=JSON.parse(stdout);assert.equal(values.length,1);const value=values[0];assert.equal(value.success,true);
  rowsRead+=Number(value.meta?.rows_read||0);rowsWritten+=Number(value.meta?.rows_written||0);d1DurationMs+=Number(value.meta?.duration||0);
  fs.writeFileSync(sqlPath+'.result.json',stdout,{flag:'wx',mode:0o600});
  return value;
 }
 const db={prepare:sql=>({bind:(...args)=>({
  first:async()=>(await query(sql,args)).results?.[0]??null,
  all:async()=>({results:(await query(sql,args)).results||[]}),
  run:async()=>({meta:(await query(sql,args)).meta||{}}),
 })})};
 function secret(name){
  const p=path.join(root,name),s=fs.lstatSync(p);
  assert.ok(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o077)===0);
  return fs.readFileSync(p,'utf8').trim();
 }
 const target={tenant_id:'HARA-TENANT-REVIEW163',id:'qa-review-163',kind:'QA_RECIPIENT_V1',origin,
  writePath:'/notify',readPath:'/receipt/',writeSecret:'QA_WRITE',readSecret:'QA_READ'};
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:db,COMMANDER_RECOVERY_ALERTS_ENABLED:'true',
  COMMANDER_RECOVERY_DELIVERY_ENABLED:'true',COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS:JSON.stringify([origin]),
  COMMANDER_RECOVERY_DELIVERY_TARGETS:JSON.stringify([target]),QA_WRITE:secret('sink-write.token'),QA_READ:secret('sink-read.token')};
 const readReceipt=async(event,authorized=true)=>fetch(origin+'/receipt/'+event.event_id,{
  headers:authorized?{authorization:'Bearer '+env.QA_READ}:{},redirect:'error',signal:AbortSignal.timeout(5000)});
 for(const {event} of agent.events){
  const before=await readReceipt(event);assert.equal(before.status,404);await before.body?.cancel();
 }
 const unauthenticated=await readReceipt(agent.events[0].event,false);assert.equal(unauthenticated.status,401);await unauthenticated.body?.cancel();
 const scopedFetch=async(url,init)=>{
  const u=new URL(url);assert.equal(u.origin,origin);assert.equal(init.redirect,'error');
  if(init.method==='POST')assert.ok(agent.events.some(x=>x.event.event_id===JSON.parse(init.body).event_id));
  else assert.ok(agent.events.some(x=>u.pathname==='/receipt/'+x.event.event_id));
  return fetch(url,init);
 };
 const ticks=[];let delivered=0;
 for(let n=0;n<8&&delivered<ids.length;n++){
  const result=await dispatchRecoveryDeliveries(env,{fetchImpl:scopedFetch,eventIds:ids});
  ticks.push(result);assert.equal(result.held,0);delivered+=result.delivered;
 }
 assert.equal(delivered,4);
 let replayCalls=0;
 const replay=await dispatchRecoveryDeliveries(env,{eventIds:ids,fetchImpl:async()=>{replayCalls++;throw Error('MUST_NOT_REPLAY');}});
 assert.equal(replay.attempted,0);assert.equal(replayCalls,0);
 const selected=await query(`SELECT o.*,r.client_event_id,r.portal_ack_at_utc FROM recovery_delivery_outbox o
  JOIN commander_device_recovery_events r ON r.event_id=o.event_id WHERE o.binding_id=? AND o.event_id IN (?,?,?,?)`,[target.id,...ids]);
 assert.equal(selected.results.length,4);
 const receipts=[];
 for(const {event,server_event_id} of agent.events){
  const response=await readReceipt(event);assert.equal(response.status,200);const receipt=await response.json();
  const row=selected.results.find(r=>r.event_id===server_event_id);
  assert.equal(receipt.state,'QA_RECIPIENT_PERSISTED');assert.equal(receipt.event_id,event.event_id);
  assert.equal(receipt.fingerprint,digest(stable(event)));assert.equal(row.state,'DELIVERED');
  assert.equal(row.receipt_ref,receipt.receipt_ref);assert.equal(row.receipt_sha256,digest(stable(receipt)));
  assert.equal(row.portal_ack_at_utc,null,'delivery cannot fabricate a human ACK');
  receipts.push({server_event_id,client_event_id:event.event_id,receipt,receipt_sha256:row.receipt_sha256});
 }
 checkOriginal();
 const evidence={schema:'hara.commander.r163.hosted-integrated-delivery.v1',state:'PASS',campaign,
  native_executor:'SERVICES_AUTHORIZED',worker_source_deployed:false,worker_prod_modified:false,
  native_qa_d1:databaseId,canary_origin:agent.origin,recipient_origin:origin,module_sha256:expectedModuleSha,
  agent_source_sha256:agent.source_sha256,real_d1_and_https:true,persisted_is_not_delivery:true,
  independent_authenticated_receipt_readback:true,delivery_is_not_human_ack:true,commercial_delivery_enabled:false,
  original_evidence_preserved:true,scoped_new_events_only:true,queryNumber,rowsRead,rowsWritten,d1DurationMs,ticks,receipts};
 fs.writeFileSync(path.join(campaign,'hosted-delivery-evidence.json'),JSON.stringify(evidence,null,2)+'\n',{flag:'wx',mode:0o600});
 console.log(JSON.stringify({state:'PASS_HOSTED_AGENT_D1_HTTPS_RECIPIENT_READBACK',events:receipts.length,campaign,
  evidence_sha256:digest(fs.readFileSync(path.join(campaign,'hosted-delivery-evidence.json'))),rowsRead,rowsWritten,d1DurationMs}));
}
main().catch(error=>{console.error(JSON.stringify({state:'FAIL_HOSTED_DELIVERY_PROBE',error_type:error.constructor.name,
 code:typeof error.code==='string'?error.code:null}));process.exitCode=1;});
