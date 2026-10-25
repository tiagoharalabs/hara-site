// Dedicated #163 DEV QA. This extends the existing r163_qa_budget authority;
// no production configuration creates or admits these companion rows.
export const BILLING_METERS=Object.freeze([
  'worker_requests','worker_cpu_us','do_requests','do_active_gb_us',
  'do_storage_reads','do_storage_writes','do_storage_byte_seconds',
  'd1_rows_read','d1_rows_written','queue_billable_ops','dlq_billable_ops',
]);
export const OPERATION_DIMENSIONS=Object.freeze([...BILLING_METERS,
  'do_alarms','ws_handshakes','ws_messages_in','ws_messages_out','reconnect_attempts','events']);
export const RESOURCE_BUDGET_SCHEMA=`
CREATE TABLE IF NOT EXISTS r163_qa_resource_budget(
 id INTEGER PRIMARY KEY CHECK(id=1) REFERENCES r163_qa_budget(id),
 admission_sha256 TEXT NOT NULL,source_sha256 TEXT NOT NULL,
 resource_sha256 TEXT NOT NULL,profile_sha256 TEXT NOT NULL,
 caps_json TEXT NOT NULL,charged_upper_json TEXT NOT NULL,
 provider_json TEXT NOT NULL,provider_captured_ms INTEGER NOT NULL,
 provider_complete_ms INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
 provider_baseline_json TEXT NOT NULL DEFAULT '{}',
 provider_highwater_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS r163_qa_resource_operations(
 operation_id TEXT PRIMARY KEY,nonce TEXT NOT NULL,kind TEXT NOT NULL,
 upper_json TEXT NOT NULL,created_ms INTEGER NOT NULL,debited INTEGER NOT NULL DEFAULT 0,
 observed_d1_json TEXT NOT NULL DEFAULT '{}',outcome TEXT NOT NULL DEFAULT 'RESERVED');`;

const KINDS=new Set(['WORKER_FETCH','DO_FETCH','DO_ALARM','DO_MESSAGE','QUEUE','DLQ','STATUS','PROVIDER_REFRESH']);
const PINS={admission_sha256:'R163_QA_ADMISSION_SHA256',source_sha256:'R163_QA_SOURCE_SHA256',
  resource_sha256:'R163_QA_RESOURCE_SHA256',profile_sha256:'R163_QA_METER_PROFILE_SHA256'};
const zero=()=>Object.fromEntries(OPERATION_DIMENSIONS.map(key=>[key,0]));
const integer=x=>Number.isSafeInteger(x)&&x>=0;
const deny=code=>{throw Error(code);};
function vector(value,keys,code){
  if(!value||typeof value!=='object'||Array.isArray(value)
      ||Object.keys(value).sort().join(',')!==[...keys].sort().join(',')
      ||keys.some(k=>!integer(value[k])))deny(code);
  return value;
}
function measured(result){
  if(result?.success===false||!result?.meta
      ||!integer(result.meta.rows_read)||!integer(result.meta.rows_written))deny('HOLD_D1_METER');
  return result;
}
function physical(kind,upper){
  if(upper.d1_rows_read<64||upper.d1_rows_written<16)deny('HOLD_CONTROL_ESCROW');
  const required=kind.startsWith('DO_')?'do_requests':kind==='QUEUE'?'queue_billable_ops':
    kind==='DLQ'?'dlq_billable_ops':'worker_requests';
  if(upper[required]<1||(kind==='DO_ALARM'&&upper.do_alarms<1))deny('HOLD_PHYSICAL_RESERVATION');
}

export class ResourceBudget {
  #env;#db;#now;#grants=new WeakMap();
  constructor(env,{now=Date.now}={}){this.#env=env;this.#db=env.PRODUCT_DB;this.#now=now;}
  #isolate(){
    if(this.#env.ENVIRONMENT!=='DEV'||this.#env.R163_QA_ISOLATED!=='true'
        ||this.#env.R163_QA_BUDGET_V2_ENABLED!=='true')deny('HOLD_QA_RESOURCE_ISOLATION');
  }
  async stop(reason='HOLD_QA_RESOURCE_STOP'){
    this.#isolate();
    const code=/^[A-Z][A-Z0-9_]{0,95}$/.test(reason)?reason:'HOLD_QA_RESOURCE_STOP';
    await this.#db.prepare("UPDATE r163_qa_budget SET state='STOPPED',anomaly=COALESCE(anomaly,?) WHERE id=1")
      .bind(code).run();
  }
  async #hold(error){
    try{await this.stop(error?.message);}catch{}
    throw error;
  }
  async #load(){
    this.#isolate();
    const now=this.#now();
    if(!integer(now))deny('HOLD_QA_CLOCK');
    const result=measured(await this.#db.prepare(
      'SELECT r.*,b.state,b.deadline_ms,b.rows_read,b.rows_written,b.reserved_read,b.reserved_write,'+
      'b.queue_ops_upper,b.events_reserved FROM r163_qa_resource_budget r JOIN r163_qa_budget b ON b.id=r.id WHERE r.id=1'
    ).bind().all());
    const row=result.results?.[0];
    if(!row)deny('HOLD_NATIVE_RESOURCE_ADMISSION');
    for(const [field,pin] of Object.entries(PINS)){
      if(!/^[0-9a-f]{64}$/.test(this.#env[pin]||'')||this.#env[pin]!==row[field])deny('HOLD_NATIVE_RESOURCE_PIN');
    }
    if(row.state!=='ACTIVE'||!integer(row.deadline_ms)||now>=row.deadline_ms)deny('HOLD_CAMPAIGN_PAUSED_OR_EXPIRED');
    const lag=this.#env.R163_QA_METER_MAX_LAG_MS??60000;
    if(!integer(lag)||lag<1||lag>900000)deny('HOLD_NATIVE_METER_LAG_BOUND');
    if(!integer(row.provider_captured_ms)||!integer(row.provider_complete_ms)
        ||row.provider_captured_ms>now||row.provider_complete_ms>row.provider_captured_ms
        ||now-row.provider_captured_ms>60000||now-row.provider_complete_ms>lag)deny('HOLD_PROVIDER_METER_WATERMARK');
    let caps,charged,provider,baseline,highwater;
    try{
      caps=vector(JSON.parse(row.caps_json),OPERATION_DIMENSIONS,'HOLD_RESOURCE_CAPS');
      charged=vector(JSON.parse(row.charged_upper_json),OPERATION_DIMENSIONS,'HOLD_RESOURCE_CHARGES');
      provider=vector(JSON.parse(row.provider_json),BILLING_METERS,'HOLD_PROVIDER_METERS');
      baseline=JSON.parse(row.provider_baseline_json);highwater=JSON.parse(row.provider_highwater_json);
      for(const value of [baseline,highwater]){
        if(!value||typeof value!=='object'||Array.isArray(value))deny('HOLD_PROVIDER_HISTORY');
        if(Object.keys(value).length)vector(value,BILLING_METERS,'HOLD_PROVIDER_HISTORY');
      }
    }catch(error){deny(error?.message?.startsWith('HOLD_')?error.message:'HOLD_RESOURCE_JSON');}
    for(const key of BILLING_METERS){
      if(highwater[key]!==undefined&&(!integer(highwater[key])||provider[key]<highwater[key]))deny('HOLD_PROVIDER_COUNTER_DECREASE');
      if(baseline[key]!==undefined&&(!integer(baseline[key])||provider[key]<baseline[key]))deny('HOLD_PROVIDER_BASELINE');
    }
    // Older campaign consumption remains covered when native owners add the
    // companion rows. The code never seeds a new zero history or resets it.
    for(const [key,total] of Object.entries({d1_rows_read:row.rows_read+row.reserved_read,
      d1_rows_written:row.rows_written+row.reserved_write,queue_billable_ops:row.queue_ops_upper,events:row.events_reserved})){
      if(!integer(total)||Math.max(provider[key]||0,charged[key])<total)deny('HOLD_HISTORICAL_USAGE_UNBOUND');
    }
    for(const key of OPERATION_DIMENSIONS){
      const actual=provider[key]??0,base=baseline[key]??actual;
      if(!integer(base+charged[key])||Math.max(actual,base+charged[key])>caps[key])deny('HOLD_RESOURCE_CAP');
    }
    return {row,caps,charged,provider,baseline,now,overhead:result.meta};
  }
  async reserve(kind,upper,{operationId=crypto.randomUUID()}={}){
    this.#isolate();
    try{
      if(!KINDS.has(kind)||typeof operationId!=='string'||!/^[A-Za-z0-9_.:-]{8,120}$/.test(operationId))deny('HOLD_RESOURCE_OPERATION');
      vector(upper,OPERATION_DIMENSIONS,'HOLD_RESOURCE_VECTOR');physical(kind,upper);
      const loaded=await this.#load(),nonce=crypto.randomUUID(),now=this.#now();
      const checks=OPERATION_DIMENSIONS.map(key=>{
        const native=BILLING_METERS.includes(key)?`COALESCE(json_extract(r.provider_json,'$.${key}'),0)`:'0';
        const base=BILLING_METERS.includes(key)?`COALESCE(json_extract(r.provider_baseline_json,'$.${key}'),${native})`:'0';
        return `MAX(${native},${base}+json_extract(r.charged_upper_json,'$.${key}')+?)<=json_extract(r.caps_json,'$.${key}')`;
      });
      const insert=this.#db.prepare(
        "INSERT INTO r163_qa_resource_operations(operation_id,nonce,kind,upper_json,created_ms) "+
        "SELECT ?,?,?,?,? FROM r163_qa_resource_budget r JOIN r163_qa_budget b ON b.id=r.id "+
        "WHERE r.id=1 AND b.state='ACTIVE' AND b.deadline_ms>? AND r.revision=? "+
        "AND NOT EXISTS(SELECT 1 FROM r163_qa_resource_operations WHERE operation_id=?) AND "+checks.join(' AND ')
      ).bind(operationId,nonce,kind,JSON.stringify(upper),now,now,loaded.row.revision,operationId,...OPERATION_DIMENSIONS.map(k=>upper[k]));
      const edits=OPERATION_DIMENSIONS.map(k=>`'$.${k}',json_extract(charged_upper_json,'$.${k}')+?`).join(',');
      const debit=this.#db.prepare(
        'UPDATE r163_qa_resource_budget SET charged_upper_json=json_set(charged_upper_json,'+edits+'),'+
        "provider_baseline_json=CASE WHEN provider_baseline_json='{}' THEN provider_json ELSE provider_baseline_json END,"+
        'provider_highwater_json=provider_json,revision=revision+1 WHERE id=1 AND EXISTS('+ 
        'SELECT 1 FROM r163_qa_resource_operations WHERE operation_id=? AND nonce=? AND debited=0)'
      ).bind(...OPERATION_DIMENSIONS.map(k=>upper[k]),operationId,nonce);
      const stamp=this.#db.prepare('UPDATE r163_qa_resource_operations SET debited=1 WHERE operation_id=? AND nonce=?')
        .bind(operationId,nonce);
      const results=await this.#db.batch([insert,debit,stamp]);
      if(!Array.isArray(results)||results.length!==3)deny('HOLD_RESOURCE_DEBIT_RECEIPT');
      results.forEach(measured);
      if(results[0].meta.changes!==1||results[1].meta.changes!==1)deny('HOLD_RESOURCE_CAP_OR_CONCURRENT_CLAIM');
      const grant=Object.freeze({operationId,kind});
      this.#grants.set(grant,{nonce,upper:{...upper},observed:{d1_rows_read:loaded.overhead.rows_read,
        d1_rows_written:loaded.overhead.rows_written},queue:0,fault:null,
        pins:Object.fromEntries(Object.keys(PINS).map(k=>[k,loaded.row[k]])),
        lastMs:loaded.now,deadline:loaded.row.deadline_ms});
      const state=this.#grants.get(grant);
      for(const result of results)this.#addD1(state,result);
      return grant;
    }catch(error){return this.#hold(error);}
  }
  #addD1(state,result){
    measured(result);
    state.observed.d1_rows_read+=result.meta.rows_read;
    state.observed.d1_rows_written+=result.meta.rows_written;
    if(['d1_rows_read','d1_rows_written'].some(k=>!integer(state.observed[k])||state.observed[k]>state.upper[k]))deny('HOLD_D1_RESOURCE_RESERVATION');
    return result;
  }
  async run(kind,upper,work,options){
    const grant=await this.reserve(kind,upper,options),state=this.#grants.get(grant);
    const checkpoint=()=>{
      const now=this.#now();
      if(!integer(now)||now<state.lastMs)deny('HOLD_QA_CLOCK_ROLLBACK');
      state.lastMs=now;
      if(now>=state.deadline)deny('HOLD_CAMPAIGN_PAUSED_OR_EXPIRED');
    };
    const checked=async action=>{
      if(state.closed)deny('HOLD_RESOURCE_GRANT_CLOSED');
      if(state.fault)throw state.fault;
      try{
        checkpoint();
        const loaded=await this.#load();
        this.#addD1(state,{success:true,meta:loaded.overhead});
        if(Object.entries(state.pins).some(([k,v])=>loaded.row[k]!==v))deny('HOLD_NATIVE_RESOURCE_PIN');
        if(state.fault)throw state.fault;
        checkpoint();const result=await action();checkpoint();return result;
      }catch(error){state.fault=error;return this.#hold(error);}
    };
    // Keep raw D1 statements private and preserve provider batch atomicity.
    // Statements from another grant/database cannot escape this boundary.
    const statements=new WeakMap();
    const wrap=statement=>{
      const wrapped={bind:(...args)=>wrap(statement.bind(...args)),
        all:()=>checked(async()=>this.#addD1(state,await statement.all())),
        run:()=>checked(async()=>this.#addD1(state,await statement.run())),
        first:column=>checked(async()=>{
          const row=this.#addD1(state,await statement.all()).results?.[0]??null;
          return column&&row?row[column]:row;
        })};
      statements.set(wrapped,statement);return wrapped;
    };
    const db={prepare:sql=>wrap(this.#db.prepare(sql)),batch:batch=>checked(async()=>{
      if(!Array.isArray(batch)||!batch.length||batch.some(s=>!statements.has(s)))deny('HOLD_FOREIGN_D1_STATEMENT');
      const results=await this.#db.batch(batch.map(s=>statements.get(s)));
      if(!Array.isArray(results)||results.length!==batch.length)deny('HOLD_D1_BATCH_RECEIPT');
      return results.map(result=>this.#addD1(state,result));
    })};
    const used=zero();
    const consume=counts=>{
      try{
        if(state.closed)deny('HOLD_RESOURCE_GRANT_CLOSED');
        if(state.fault)throw state.fault;
        checkpoint();
        if(!counts||typeof counts!=='object'||Array.isArray(counts)||!Object.keys(counts).length
            ||Object.entries(counts).some(([k,v])=>!OPERATION_DIMENSIONS.includes(k)||!integer(v)))deny('HOLD_RESOURCE_EFFECT_VECTOR');
        for(const [key,count] of Object.entries(counts)){
          if(!integer(used[key]+count)||used[key]+count>state.upper[key])deny('HOLD_RESOURCE_EFFECT_BOUND');
        }
        for(const [key,count] of Object.entries(counts))used[key]+=count;
      }catch(error){state.fault=error;throw error;}
    };
    const effects=Object.freeze({...grant,consume,
      effect:(counts,action)=>checked(async()=>{consume(counts);return action();})});
    const original=this.#env.RECOVERY_DELIVERY_QUEUE;
    const queue=original?{sendBatch:entries=>checked(async()=>{
      if(!Array.isArray(entries)||!entries.length)deny('HOLD_QUEUE_RESOURCE_VECTOR');
      const chunks=entries.reduce((sum,e)=>sum+Math.ceil((new TextEncoder().encode(JSON.stringify(e.body)).length+100)/64000),0);
      state.queue+=chunks*12;
      if(!integer(state.queue)||state.queue>state.upper.queue_billable_ops)deny('HOLD_QUEUE_RESOURCE_RESERVATION');
      return original.sendBatch(entries);
    })}:undefined;
    try{
      const result=await work({...this.#env,PRODUCT_DB:db,RECOVERY_DELIVERY_QUEUE:queue},effects);
      if(state.fault)throw state.fault;
      await checked(async()=>null);
      const receipt=await this.#db.prepare(
        "UPDATE r163_qa_resource_operations SET observed_d1_json=?,outcome='COMPLETE' WHERE operation_id=? AND nonce=?"
      ).bind(JSON.stringify(state.observed),grant.operationId,state.nonce).run();
      this.#addD1(state,receipt);
      return result;
    }catch(error){return this.#hold(error);}
    finally{state.closed=true;}
  }
}
