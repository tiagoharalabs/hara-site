// Offline integration of the exact Worker completion/projection functions.
// Line protocol on stdin/stdout only. No HTTP listener, no tokens, no network.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import readline from 'node:readline';
import { DatabaseSync } from 'node:sqlite';
import { webcrypto } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const root=path.dirname(fileURLToPath(import.meta.url));
const app=path.join(process.env.HARA_PEER_SOURCE || path.join(root,'source'),'apps/commander');
const source=fs.readFileSync(path.join(app,'src/worker.js'),'utf8');
const simple=fs.readFileSync(path.join(app,'src/customer-mcp-simple.mjs'),'utf8');
const approval=await import(pathToFileURL(path.join(app,'src/approval-async-relay.mjs')).href);
const storage=await import(pathToFileURL(path.join(app,'src/approval-relay-storage.mjs')).href);
const tools=await import(pathToFileURL(path.join(app,'src/device-tool-contract.mjs')).href);
globalThis.fetch=async()=>{throw Error('PEER_NETWORK_FORBIDDEN');};
const extract=(text,name)=>{
 const m=new RegExp('(?:async )?function '+name+'\\(').exec(text);assert(m,name);
 const end=text.indexOf('\n}',m.index);assert(end>m.index);return text.slice(m.index,end+2);
};
let clock=Date.parse('2026-10-20T20:00:00Z');
const now=(s=0)=>new Date(clock+s*1000).toISOString();
const db=new DatabaseSync(':memory:');
for(const name of fs.readdirSync(path.join(app,'migrations')).filter(x=>x.endsWith('.sql')).sort()){
 db.exec(fs.readFileSync(path.join(app,'migrations',name),'utf8'));
}
const tenant='R6-TENANT',subject='R6-SUBJECT',deviceId='R6-DEVICE';
db.prepare("INSERT INTO tenants VALUES (?,?,'ACTIVE','DEV',?)").run(tenant,'Disposable QA',now());
db.prepare("INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES (?,?,?,?,'ACTIVE','OWNER',?)").run(subject,tenant,'https://peer.invalid','qa',now());
db.prepare("INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc) VALUES ('R6-PAIR','R6-HASH',?,?,?,?)").run(tenant,subject,now(),now(600));
db.prepare("INSERT INTO commander_devices (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,agent_version,tunnel_mode,credential_hash,state,created_at_utc,approval_mode) VALUES (?,'R6-PAIR',?,?,'R6 QA','LINUX','0.3.54','EVENT_V2','R6-QA-HASH','ACTIVE',?,'PERSISTENT_TRUSTED')").run(deviceId,tenant,subject,now());
const wrap=(sql,args=[])=>({async first(){return db.prepare(sql).get(...args)||null;},async all(){return {results:db.prepare(sql).all(...args)};},async run(){return {meta:{changes:Number(db.prepare(sql).run(...args).changes)}};}});
const env={PRODUCT_DB:{prepare(sql){return {bind(...args){return wrap(sql,args);}};}}};
const device={device_id:deviceId,tenant_id:tenant,platform:'LINUX',agent_version:'0.3.54'};
const runtime=vm.createContext({TextEncoder,crypto:webcrypto,console,Date,
 nowIso:()=>now(),resolveDeviceCredential:async()=>device,
 CALL_ROW_FIELDS:storage.CALL_ROW_FIELDS,settleCallUsage:storage.settleCallUsage,
 safeCallResultMetadata:approval.safeCallResultMetadata,
 deviceCallStoredContentMatches:async(a,b)=>a===b,reconcileAgentVersion:async()=>{},
 deviceFunctionForTool:tools.deviceFunctionForTool,isDeviceMutationTool:tools.isDeviceMutationTool,isDeviceProcessTool:tools.isDeviceProcessTool});
vm.runInContext(['cleanId','boundedJson','completeDeviceCall','trimPublicText','projectCustomerToolResult'].map(n=>extract(source,n)).join('\n')+'\n'+extract(simple,'publicToolResult')+'\nglobalThis.complete=completeDeviceCall;globalThis.project=projectCustomerToolResult;globalThis.wrap=publicToolResult;',runtime);
async function handle(req){
 if(req.action==='seed'){
  const ttl=Number(req.ttl_seconds??50);assert(ttl>0&&ttl<3600);
  db.prepare("INSERT INTO commander_device_calls (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,created_at_utc,expires_at_utc,claimed_at_utc,usage_mode,usage_units,usage_period_key,approval_timeout_seconds,execution_budget_ms) VALUES (?,?,?,?,?,?,'{}','EXECUTING',?,?,?,'UNMETERED',0,NULL,0,1000)")
   .run(req.call_id,req.call_id,tenant,subject,deviceId,req.tool_id||'hara.files.write',now(),now(ttl),now());
  return {ok:true,clock:now()};
 }
 if(req.action==='advance'){clock+=Number(req.seconds)*1000;return {ok:true,clock:now()};}
 if(req.action==='complete'){
  try{return {ok:true,response:await runtime.complete(env,{},req.body)};}
  catch(e){return {ok:false,error:e.message,call:db.prepare('SELECT state,result_json,call_result_metadata_json FROM commander_device_calls WHERE call_id=?').get(req.body.call_id)};}
 }
 if(req.action==='project'){
  const value=JSON.parse(fs.readFileSync(req.fixture,'utf8'));
  const before=value.result.stdout;let agentParsed=false;try{JSON.parse(before);agentParsed=true;}catch{}
  const p=runtime.project(req.tool_id,value);const m=runtime.wrap(p);const after=p.result.stdout;
  let parsed=false,reason=null;try{JSON.parse(after);parsed=true;}catch(e){reason=e.message;}
  return {ok:true,agent_result_bytes:Buffer.byteLength(JSON.stringify(value)),agent_stdout_chars:before.length,
   before_json_valid:agentParsed,projected_stdout_chars:after.length,after_json_valid:parsed,
   parse_error:reason,projection_marker:after.endsWith('[HARA_COMMANDER_OUTPUT_TRUNCATED]'),
   outer_mcp_content_json_valid:!!JSON.parse(m.content[0].text),
   structured_content_stdout_matches_projection:m.structuredContent.result.stdout===after,
   outer_state:p.state,is_error:m.isError||false,
   explicit_content_truncation_flag:Object.hasOwn(p,'result_content_truncated'),
   receipt_preserved:p.bridge_receipt_sha256===value.bridge_receipt_sha256};
 }
 throw Error('UNKNOWN_PEER_ACTION');
}
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of lines){
 try{process.stdout.write(JSON.stringify(await handle(JSON.parse(line)))+'\n');}
 catch(e){process.stdout.write(JSON.stringify({harness_error:e.stack})+'\n');}
}
db.close();
