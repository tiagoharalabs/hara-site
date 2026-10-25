// Read-only GraphQL adapter. It neither admits budgets nor invokes a Worker,
// queues work, deploys, or substitutes zero for unavailable provider usage.
import {BILLING_METERS} from './qa-resource-budget.mjs';

const ENDPOINT='https://api.cloudflare.com/client/v4/graphql';
const captures=new WeakSet();
const name=x=>typeof x==='string'&&/^[A-Za-z_][A-Za-z0-9_]*$/.test(x);
const hold=code=>{throw Error(code);};
const canonical=value=>JSON.stringify(sort(value));
function sort(value){
  if(Array.isArray(value))return value.map(sort);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,sort(value[k])]));
  return value;
}
export async function profileDigest(profile){
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(profile)));
  return Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
}
export const isProviderCapture=value=>Boolean(value&&captures.has(value));
function typeName(type){
  for(let depth=0;type&&depth<8;depth++,type=type.ofType)if(type.name)return type.name;
  return null;
}
// Match the bounded typeName traversal, including [Group!]! wrappers.
const TYPE_REF=Array.from({length:7}).reduce(body=>'name kind ofType { '+body+' }','name kind');
const SCHEMA_QUERY=`query R163ReadMetricSchema { __schema { types { name kind
 fields { name args { name type { ${TYPE_REF} } } type { ${TYPE_REF} } }
 inputFields { name } } } }`;


export class CloudflareMeterReader {
  #token;#resources;#profile;#pin;#fetch;#now;
  constructor({token,resources,profile,expectedProfileSha256,fetchImpl=fetch,now=Date.now}){
    this.#token=token;this.#resources=resources;this.#profile=profile;
    this.#pin=expectedProfileSha256;this.#fetch=fetchImpl;this.#now=now;
  }
  async #request(query,variables={}){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),10000);
    try{
      const response=await this.#fetch(ENDPOINT,{method:'POST',redirect:'error',signal:abort.signal,
        headers:{authorization:'Bearer '+this.#token,'content-type':'application/json'},
        body:JSON.stringify({query,variables})});
      if(!response.ok||!response.body)hold('HOLD_PROVIDER_RESPONSE');
      const reader=response.body.getReader(),chunks=[];let size=0;
      try{while(true){const {value,done}=await reader.read();if(done)break;
        size+=value.byteLength;if(size>4*1024*1024)hold('HOLD_PROVIDER_RESPONSE_SIZE');chunks.push(value);}}
      finally{await reader.cancel().catch(()=>{});}
      const bytes=new Uint8Array(size);let offset=0;
      for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
      let result;try{result=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));}
      catch{hold('HOLD_PROVIDER_JSON');}
      if(!result?.data||(Array.isArray(result.errors)&&result.errors.length)||result.errors&&!Array.isArray(result.errors))hold('HOLD_PROVIDER_GRAPHQL');
      return result.data;
    }catch(error){hold(error?.message?.startsWith('HOLD_')?error.message:'HOLD_PROVIDER_IO');}
    finally{clearTimeout(timer);}
  }
  async capture(window){
    const now=this.#now(),p=this.#profile,r=this.#resources;
    if(!Number.isSafeInteger(now)||!window||!Number.isSafeInteger(window.from_ms)||!Number.isSafeInteger(window.to_ms)
        ||window.from_ms<0||window.from_ms>=window.to_ms||window.to_ms>now)hold('HOLD_PROVIDER_WINDOW');
    if(typeof this.#token!=='string'||!this.#token||/[\r\n]/.test(this.#token))hold('HOLD_PROVIDER_TOKEN_REFERENCE');
    if(!/^[0-9a-f]{32}$/.test(r?.account_id||''))hold('HOLD_PROVIDER_RESOURCE_BINDING');
    if(!p||Object.keys(p).sort().join(',')!=='datasets,schema'
        ||p.schema!=='hara.commander.qa-meter-profile.v1'||!Array.isArray(p.datasets)
        ||p.datasets.length!==BILLING_METERS.length
        ||new Set(p.datasets.map(d=>d.meter)).size!==BILLING_METERS.length
        ||BILLING_METERS.some(k=>!p.datasets.some(d=>d.meter===k))
        ||!/^[0-9a-f]{64}$/.test(this.#pin||'')||await profileDigest(p)!==this.#pin)hold('HOLD_NATIVE_METER_PROFILE_PIN');
    for(const d of p.datasets){
      if(Object.keys(d).sort().join(',')!=='aggregation,dataset,field,filter_field,meter,resource_key,sample_aggregation,sample_field,scale'
          ||!['dataset','field','aggregation','filter_field','resource_key','sample_aggregation','sample_field'].every(k=>name(d[k]))
          ||!Number.isSafeInteger(d.scale)||d.scale<1||d.scale>1000000
          ||typeof r[d.resource_key]!=='string'||!/^[A-Za-z0-9_.:-]{1,180}$/.test(r[d.resource_key]))hold('HOLD_PROVIDER_RESOURCE_BINDING');
    }
    const discovered=await this.#request(SCHEMA_QUERY);
    if(!Array.isArray(discovered.__schema?.types))hold('HOLD_SCHEMA_DISCOVERY');
    const types=new Map(discovered.__schema.types.map(t=>[t.name,t]));
    const account=types.get('Account')||discovered.__schema.types.find(t=>p.datasets.every(d=>t.fields?.some(f=>f.name===d.dataset)));
    if(!account)hold('HOLD_SCHEMA_ACCOUNT');
    const declarations=['$accountTag:string!'],variables={accountTag:r.account_id},fields=[];
    for(let i=0;i<p.datasets.length;i++){
      const d=p.datasets[i],dataset=account.fields?.find(f=>f.name===d.dataset);
      const filterType=typeName(dataset?.args?.find(a=>a.name==='filter')?.type);
      const inputs=types.get(filterType)?.inputFields?.map(x=>x.name)||[];
      const group=types.get(typeName(dataset?.type));
      const aggregation=types.get(typeName(group?.fields?.find(f=>f.name===d.aggregation)?.type));
      const sampling=types.get(typeName(group?.fields?.find(f=>f.name===d.sample_aggregation)?.type));
      if(!name(filterType)||![d.filter_field,'datetime_geq','datetime_leq'].every(k=>inputs.includes(k))
          ||!aggregation?.fields?.some(f=>f.name===d.field)||!sampling?.fields?.some(f=>f.name===d.sample_field)
          ||!dataset.args?.some(a=>a.name==='limit'))hold('HOLD_SCHEMA_NATIVE_METER_UNAVAILABLE');
      declarations.push('$f'+i+':'+filterType+'!');
      variables['f'+i]={[d.filter_field]:r[d.resource_key],datetime_geq:new Date(window.from_ms).toISOString(),datetime_leq:new Date(window.to_ms).toISOString()};
      fields.push('m'+i+':'+d.dataset+'(limit:2,filter:$f'+i+'){'+d.aggregation+'{'+d.field+'} '+d.sample_aggregation+'{'+d.sample_field+'}}');
    }
    const data=await this.#request('query R163ReadUsage('+declarations.join(',')+'){viewer{accounts(filter:{accountTag:$accountTag}){'+fields.join(' ')+'}}}',variables);
    const accounts=data.viewer?.accounts;
    if(!Array.isArray(accounts)||accounts.length!==1)hold('HOLD_PROVIDER_ACCOUNT_SCOPE');
    const meters={};
    for(let i=0;i<p.datasets.length;i++){
      const d=p.datasets[i],rows=accounts[0]['m'+i];
      if(!Array.isArray(rows)||rows.length!==1)hold('HOLD_PROVIDER_MISSING_OR_AMBIGUOUS_METER');
      const raw=rows[0]?.[d.aggregation]?.[d.field],sample=rows[0]?.[d.sample_aggregation]?.[d.sample_field];
      if(typeof raw!=='number'||!Number.isFinite(raw)||raw<0||sample!==1
          ||!Number.isSafeInteger(raw*d.scale))hold('HOLD_PROVIDER_METER_QUALITY');
      meters[d.meter]=raw*d.scale;
    }
    const result=Object.freeze({source:'CLOUDFLARE_GRAPHQL',meters:Object.freeze(meters),
      captured_ms:now,window:Object.freeze({...window}),profile_sha256:this.#pin,
      // GraphQL query bounds are not a provider completeness watermark. In
      // particular WebSocket invocations may appear only after close. A
      // native independent readback must settle that gap; never invent one.
      complete_through_ms:null,websocket_close_readback_required:true,native_admission:false});
    captures.add(result);return result;
  }
}
