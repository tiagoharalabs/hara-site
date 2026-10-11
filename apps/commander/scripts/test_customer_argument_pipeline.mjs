import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { canonicalDeviceToolPayload, deviceFunctionForTool } from '../src/device-tool-contract.mjs';
import { handleSimpleCustomerMcpRequest } from '../src/customer-mcp-simple.mjs';

// Use the actual MCP handler, Worker adapters and canonical contract. All
// requests remain in-process. No Cloudflare, device, shell or network is invoked.
let worker=fs.readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const originalWorkerSha256=createHash('sha256').update(worker).digest('hex');
const candidateMode=false;
assert.ok(!process.argv.includes('--candidate'),'TEST_REQUIRES_ACTUAL_PRODUCT_SOURCE');
function extract(start,end) {
 const a=worker.indexOf(start),b=worker.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a,'WORKER_FUNCTION_BOUNDARIES_REQUIRED');return worker.slice(a,b).trim();
}
const adapterSource=extract('function customerMcpDevicePayload(', 'function quotaFunctionIdForTool(');
const legacySource=extract('function legacyInvokePayload(', 'function agentPurposeToolReady(');
const adapter=vm.runInNewContext('('+adapterSource+')',{});
const legacy=vm.runInNewContext('('+legacySource+')',{deviceFunctionForTool});
const plain=x=>JSON.parse(JSON.stringify(x));
const path='/tmp/commander-pipeline-fixture.txt';
const sha='a7'.repeat(32);
const vectors=[
 {name:'write_file',tool:'hara.files.write',args:{path,content:'test',mode:'rewrite'}},
 {name:'edit_block',tool:'hara.files.edit',args:{path,old_string:'old',new_string:'new'},payload:{path,old_text:'old',new_text:'new',replace_all:false}},
 {name:'delete_file',tool:'hara.files.delete',args:{path}},
];
const results=[];
async function test(name,fn){try{await fn();results.push({name,state:'PASS'});}catch(e){results.push({name,state:'FAIL',error:e.code||e.name});}}
let requestId=0;
async function call(name,args,validate=true) {
 let captured=null;
 const request=new Request('https://commander.example.invalid/api/mcp?profile=simple',{
  method:'POST',headers:{'content-type':'application/json',accept:'application/json, text/event-stream'},
  body:JSON.stringify({jsonrpc:'2.0',id:++requestId,method:'tools/call',params:{name,arguments:args}}),
 });
 const response=await handleSimpleCustomerMcpRequest(request,{
  executeTool:async request=>{
   const first=adapter(request.tool_id,request.arguments);
   captured={tool:request.tool_id,projected:plain(first),canonical:validate?plain(canonicalDeviceToolPayload(request.tool_id,first)):null};
   return {state:'PASS',result:{ok:true}};
  },
  authInfo:{token:'test-only-not-a-credential',clientId:'PIPELINE_TEST',scopes:['openid']},
  allowedHosts:['commander.example.invalid'],
 });
 await response.text();
 return captured;
}
for(const v of vectors){
 await test(v.name+'_sha_reaches_canonical_payload',async()=>{
  const r=await call(v.name,{...v.args,expected_sha256:sha});assert.ok(r);assert.equal(r.projected.expected_sha256,sha);assert.equal(r.canonical.expected_sha256,sha);
 });
 await test(v.name+'_uppercase_sha_normalized_by_contract',async()=>{
  const r=await call(v.name,{...v.args,expected_sha256:sha.toUpperCase()});assert.ok(r);assert.equal(r.canonical.expected_sha256,sha);
 });
 await test(v.name+'_missing_sha_preserves_optional_behavior',async()=>{
  const r=await call(v.name,v.args);assert.ok(r);assert.equal(Object.hasOwn(r.canonical,'expected_sha256'),false);
 });
 await test(v.name+'_different_sha_remains_distinct_request_material',async()=>{
  const x=await call(v.name,{...v.args,expected_sha256:sha}),y=await call(v.name,{...v.args,expected_sha256:'b9'.repeat(32)});
  assert.notEqual(JSON.stringify(x.projected),JSON.stringify(y.projected));
 });
 await test(v.name+'_invalid_direct_values_are_not_silently_dropped',()=>{
  for(const value of ['',null,7,{},'bad'])assert.throws(()=>canonicalDeviceToolPayload(v.tool,adapter(v.tool,{...(v.payload||v.args),expected_sha256:value})));
 });
 await test(v.name+'_invalid_public_hash_rejected_before_executor',async()=>{
  assert.equal(await call(v.name,{...v.args,expected_sha256:'invalid'}),null);
 });
}
for(const [name,tool,base] of [
 ['search','hara.files.search',{path:'/tmp',pattern:'fixture',search_type:'files',max_results:10}],
 ['list_directory','hara.files.list',{path:'/tmp',limit:10,depth:2}],
]){
 for(const offset of [0,17,10000])await test(name+'_offset_'+offset+'_reaches_agent_payload',async()=>{
  const r=await call(name,{...base,offset});assert.ok(r);assert.equal(r.projected.offset,offset);assert.equal(r.canonical.offset,offset);
 });
 await test(name+'_consecutive_pages_are_not_identical',async()=>{
  const a=await call(name,{...base,offset:0}),b=await call(name,{...base,offset:10});
  assert.notEqual(JSON.stringify(a.canonical),JSON.stringify(b.canonical));
 });
 await test(name+'_out_of_range_offset_rejected',async()=>{
  for(const offset of [-1,10001,0.5])assert.equal(await call(name,{...base,offset}),null);
 });
 await test(name+'_routing_metadata_not_sent_to_agent',async()=>{
  const r=await call(name,{...base,computer:'fixture-machine',offset:17});assert.ok(r);assert.equal(Object.hasOwn(r.projected,'computer'),false);assert.equal(Object.hasOwn(r.canonical,'computer'),false);
 });
}
await test('legacy_search_preserves_offset_argument',()=>{
 const p=adapter('hara.files.search',{path:'/tmp',pattern:'x',search_type:'files',offset:37});
 const out=plain(legacy('hara.files.search',p));
 assert.equal(out.arguments.argv[7],'37');
 assert.deepEqual(plain(canonicalDeviceToolPayload('hara.functions.invoke',out)),out);
});
await test('legacy_list_fills_limit_depth_before_offset',()=>{
 const out=plain(legacy('hara.files.list',{path:'/tmp',offset:37}));
 assert.deepEqual(out.arguments.argv,['/tmp','100','1','37']);
 assert.deepEqual(plain(canonicalDeviceToolPayload('hara.functions.invoke',out)),out);
});
await test('legacy_list_without_offset_keeps_original_shape',()=>{
 assert.deepEqual(plain(legacy('hara.files.list',{path:'/tmp'})).arguments.argv,['/tmp']);
 assert.deepEqual(plain(legacy('hara.files.list',{path:'/tmp',depth:3})).arguments.argv,['/tmp','100','3']);
});
await test('legacy_search_without_offset_keeps_original_shape',()=>{
 const p=adapter('hara.files.search',{path:'/tmp',pattern:'x',search_type:'files'});
 assert.equal(plain(legacy('hara.files.search',p)).arguments.argv.length,7);
});
await test('write_content_and_empty_edit_replacement_are_unchanged',async()=>{
 const a=await call('write_file',{path,content:'a\nb\n',mode:'append',expected_sha256:sha});
 assert.equal(a.canonical.content,'a\nb\n');assert.equal(a.canonical.mode,'append');
 const b=await call('edit_block',{path,old_string:'remove',new_string:'',replace_all:true,expected_sha256:sha});
 assert.equal(b.canonical.new_text,'');assert.equal(b.canonical.replace_all,true);
});
await test('process_command_is_not_rewritten',()=>{
 const input={command:"printf 'fixture\\n'",cwd:'/tmp',timeout_ms:1000,max_lines:5};
 assert.deepEqual(plain(canonicalDeviceToolPayload('hara.process.run',adapter('hara.process.run',input))),input);
});
await test('process_output_pagination_is_unchanged',()=>{
 const input={session_id:'HARA-PROC-fixture',offset:23,length:11,timeout_ms:0};
 assert.deepEqual(plain(canonicalDeviceToolPayload('hara.process.output',adapter('hara.process.output',input))),input);
});
await test('received_preconditions_are_present_before_request_id_derivation',()=>{
 const start=worker.indexOf('const payload = customerMcpDevicePayload(toolId, args)');
 assert.ok(start>=0);const block=worker.slice(start,start+400);
 assert.ok(block.includes('customerMcpRequestId('));assert.ok(block.includes('{ device_id: targetDeviceId, payload }'));
});
console.log(JSON.stringify({schema:'hara.commander-argument-pipeline.v1',scope:'REAL_INPROCESS_MCP_AND_SOURCE_ADAPTERS_NO_NETWORK',candidate_mode:candidateMode,tests_actual_product_source:true,original_worker_sha256:originalWorkerSha256,source_worker_sha256:createHash('sha256').update(worker).digest('hex'),checked:results.length,passed:results.filter(x=>x.state==='PASS').length,failed:results.filter(x=>x.state==='FAIL').length,tests:results},null,2));
process.exitCode=results.some(x=>x.state!=='PASS')?1:0;
