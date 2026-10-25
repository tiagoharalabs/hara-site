// Offline provider boundary. Synthetic schema/responses are NOT Cloudflare
// measurements, native resource admission, or permission to start a campaign.
import test from 'node:test';
import assert from 'node:assert/strict';
import {CloudflareMeterReader,profileDigest,isProviderCapture} from '../src/cloudflare-meter-reader.mjs';
import {BILLING_METERS} from '../src/qa-resource-budget.mjs';

const NOW=Date.parse('2026-10-25T04:00:00Z');
const resources={account_id:'a'.repeat(32),resource_id:'b'.repeat(32)};
const profile={schema:'hara.commander.qa-meter-profile.v1',datasets:BILLING_METERS.map((meter,i)=>({
 meter,dataset:'dataset'+i,aggregation:'sum',field:'usage',filter_field:'resourceId',resource_key:'resource_id',
 sample_aggregation:'avg',sample_field:'sampleInterval',scale:1,
}))};
const schema={types:[{name:'Account',fields:profile.datasets.map(p=>({name:p.dataset,
 args:[{name:'filter',type:{name:'ResourceFilter'}},{name:'limit',type:{name:'Int'}}],
 type:{kind:'LIST',ofType:{name:'UsageGroup'}}}))},
 {name:'ResourceFilter',inputFields:['resourceId','datetime_geq','datetime_leq'].map(name=>({name}))},
 {name:'UsageGroup',fields:[{name:'sum',type:{name:'UsageSum'}},{name:'avg',type:{name:'UsageAvg'}}]},
 {name:'UsageSum',fields:[{name:'usage',type:{name:'Int'}}]},
 {name:'UsageAvg',fields:[{name:'sampleInterval',type:{name:'Float'}}]}]};
function boundary(overrides={}){
 const calls=[];
 return {calls,fetch:async(url,init)=>{
  calls.push({url,init});const request=JSON.parse(init.body);
  if(request.query.includes('__schema'))return Response.json({data:{__schema:schema}});
  const account=Object.fromEntries(profile.datasets.map((p,i)=>['m'+i,[{sum:{usage:i+10},avg:{sampleInterval:1}}]]));
  Object.assign(account,overrides.account||{});
  return Response.json(overrides.response||{data:{viewer:{accounts:[account]}}});
 }};
}
async function reader(io=boundary(),options={}){
 return {io,client:new CloudflareMeterReader({token:'SYNTHETIC_READ_TOKEN_NOT_A_CREDENTIAL',
  resources,profile,expectedProfileSha256:await profileDigest(profile),fetchImpl:io.fetch,now:()=>NOW,...options})};
}
const window={from_ms:NOW-120000,to_ms:NOW-1000};

test('discovered provider fields, pinned scope and bounded queries produce a provenance-marked capture',async()=>{
 const {client,io}=await reader();const capture=await client.capture(window);
 assert.equal(isProviderCapture(capture),true);
 assert.equal(capture.source,'CLOUDFLARE_GRAPHQL');
 assert.deepEqual(Object.keys(capture.meters).sort(),[...BILLING_METERS].sort());
 assert.equal(capture.meters.worker_requests,10);
 assert.equal(capture.captured_ms,NOW);assert.equal(capture.window.to_ms,window.to_ms);
 assert.equal(capture.native_admission,false);assert.equal(capture.complete_through_ms,null);
 assert.equal(io.calls.length,2);
 for(const call of io.calls){
  assert.equal(call.url,'https://api.cloudflare.com/client/v4/graphql');assert.equal(call.init.redirect,'error');
  assert.equal(call.init.headers.authorization,'Bearer SYNTHETIC_READ_TOKEN_NOT_A_CREDENTIAL');
 }
 const sent=JSON.parse(io.calls[1].init.body);
 assert.equal(sent.variables.accountTag,resources.account_id);
 assert.equal(sent.variables.f0.resourceId,resources.resource_id);
 assert.equal(sent.variables.f0.datetime_geq,new Date(window.from_ms).toISOString());
});
test('serialized JSON cannot counterfeit the in-process provider capture or an admission',async()=>{
 const {client}=await reader();const capture=await client.capture(window);
 assert.equal(isProviderCapture(JSON.parse(JSON.stringify(capture))),false);
 assert.equal(isProviderCapture({approved:true,source:'CLOUDFLARE_GRAPHQL'}),false);
 assert.equal(JSON.stringify(capture).includes('SYNTHETIC_READ_TOKEN'),false);
});
for(const [name,account] of [
 ['missing meter',{m3:[]}],['null meter',{m3:[{sum:{usage:null},avg:{sampleInterval:1}}]}],
 ['sampled aggregate',{m3:[{sum:{usage:10},avg:{sampleInterval:8}}]}],
 ['negative metric',{m3:[{sum:{usage:-1},avg:{sampleInterval:1}}]}],
 ['ambiguous scope',{m3:[{sum:{usage:10},avg:{sampleInterval:1}},{sum:{usage:11},avg:{sampleInterval:1}}]}],
])test(name+' is HOLD, never a zero or an exact measured total',async()=>{
 const {client}=await reader(boundary({account}));await assert.rejects(()=>client.capture(window),/HOLD_/);
});
test('a profile naming an undiscovered field never issues its metric query',async()=>{
 const bad=structuredClone(profile);bad.datasets[0].field='inventedCost';
 const {client,io}=await reader(boundary(),{profile:bad,expectedProfileSha256:await profileDigest(bad)});
 await assert.rejects(()=>client.capture(window),/HOLD_SCHEMA/);assert.equal(io.calls.length,1);
});
test('a changed profile or an approved file cannot replace the protected pin',async()=>{
 const bad={...profile,approved:true};
 const {client,io}=await reader(boundary(),{profile:bad});
 await assert.rejects(()=>client.capture(window),/HOLD_/);assert.equal(io.calls.length,0);
});
test('provider GraphQL errors, even alongside data, never produce a capture',async()=>{
 const {client}=await reader(boundary({response:{errors:[{message:'synthetic denied'}],data:{viewer:{accounts:[]}}}}));
 await assert.rejects(()=>client.capture(window),/HOLD_PROVIDER/);
});
test('missing native resources and future or reversed windows fail before provider I/O',async()=>{
 for(const change of [{from_ms:NOW,to_ms:NOW-1},{from_ms:NOW-1000,to_ms:NOW+1}]){
  const {client,io}=await reader();await assert.rejects(()=>client.capture(change),/HOLD_/);assert.equal(io.calls.length,0);
 }
 const {client,io}=await reader(boundary(),{resources:{account_id:resources.account_id}});
 await assert.rejects(()=>client.capture(window),/HOLD_/);assert.equal(io.calls.length,0);
});

test('non-null lists of non-null groups are discoverable without truncating provider type references',async()=>{
 const wrapped=structuredClone(schema);
 for(const field of wrapped.types[0].fields)field.type={kind:'NON_NULL',ofType:{kind:'LIST',ofType:{kind:'NON_NULL',ofType:{name:'UsageGroup',kind:'OBJECT'}}}};
 const io=boundary(),original=io.fetch;
 io.fetch=async(url,init)=>{
  const request=JSON.parse(init.body);
  if(request.query.includes('__schema')){
   assert.ok((request.query.match(/ofType/g)||[]).length>=8,'bounded discovery must include sufficient nested type references');
   return Response.json({data:{__schema:wrapped}});
  }
  return original(url,init);
 };
 const {client}=await reader(io);assert.equal((await client.capture(window)).native_admission,false);
});
