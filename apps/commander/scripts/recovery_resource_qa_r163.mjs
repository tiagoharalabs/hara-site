// Dedicated DEV entry boundary. Protected native rows remain the authority;
// files here neither create them nor change the previous campaign caps.
import {ResourceBudget} from '../src/qa-resource-budget.mjs';
import {profileDigest} from '../src/cloudflare-meter-reader.mjs';

const QUEUE='hara-commander-r163-recovery-dev-20261024';
const DLQ='hara-commander-r163-recovery-dlq-dev-20261024';
const PRODUCT_PATHS=new Set(['/api/device/calls/next','/api/device/calls/complete',
  '/api/device/product-lease','/api/device/metering-sync','/api/device/offline','/api/device/revoke-self']);
const enabled=env=>env.R163_QA_BUDGET_V2_ENABLED==='true';
const failure=error=>Response.json({code:/^HOLD_[A-Z0-9_]{1,100}$/.test(error?.message)
  ?error.message:'HOLD_RESOURCE_INVOCATION'},{status:503,headers:{'cache-control':'no-store'}});

export async function resourceInvocation(env,kind,work,{budgetFactory=e=>new ResourceBudget(e)}={}){
  if(env.ENVIRONMENT!=='DEV'||env.R163_QA_ISOLATED!=='true')throw Error('HOLD_QA_RESOURCE_ISOLATION');
  let profile;
  try{profile=JSON.parse(env.R163_QA_OPERATION_BOUNDS_JSON);}catch{throw Error('HOLD_NATIVE_OPERATION_BOUNDS');}
  if(!profile||Object.keys(profile).sort().join(',')!=='operations,schema'
      ||profile.schema!=='hara.commander.r163.resource-bounds.v1'
      ||!/^[0-9a-f]{64}$/.test(env.R163_QA_OPERATION_BOUNDS_SHA256||'')
      ||await profileDigest(profile)!==env.R163_QA_OPERATION_BOUNDS_SHA256
      ||!profile.operations?.[kind])throw Error('HOLD_NATIVE_OPERATION_BOUNDS');
  return budgetFactory(env).run(kind,profile.operations[kind],work);
}

async function drain(pending,error){
  let cursor=0;
  while(cursor<pending.length){
    const end=pending.length;
    const outcomes=await Promise.allSettled(pending.slice(cursor,end));cursor=end;
    error??=outcomes.find(o=>o.status==='rejected')?.reason;
  }
  if(error)throw error;
}

export function wrapQaEntry(legacy,product,options={}){
  return {
    async fetch(request,env,ctx){
      if(!enabled(env))return legacy.fetch(request,env,ctx);
      const path=new URL(request.url).pathname;
      // The existing authenticated stop must remain usable even when no new
      // spend can be admitted. It cannot resume STOPPED or replenish counters.
      if(path==='/__qa/stop')return legacy.fetch(request,env,ctx);
      try{return await resourceInvocation(env,'WORKER_FETCH',async metered=>{
        if(path==='/__qa/start'||path==='/__qa/debit')throw Error('HOLD_NATIVE_START_AND_METER_REQUIRED');
        if(path==='/api/device/channel'){
          // Hibernating auto-responses bypass JS counters and provider WSS
          // usage is reported after close. No source flag or imported JSON
          // supplies an enforceable in-flight meter. Fail closed until the
          // native owner resolves that missing metering boundary.
          throw Error('HOLD_NATIVE_WEBSOCKET_METER');
        }
        const pending=[];
        const context={waitUntil:promise=>pending.push(Promise.resolve(promise))};
        let result,error;
        try{result=await (PRODUCT_PATHS.has(path)?product:legacy).fetch(request,metered,context);}
        catch(cause){error=cause;}
        // Background work shares the same metered environment and lifetime.
        // Never settle the grant while waitUntil work can still create effects.
        await drain(pending,error);return result;
      },options);}catch(error){return failure(error);}
    },
    async queue(batch,env,ctx){
      if(!enabled(env))return legacy.queue(batch,env,ctx);
      if(![QUEUE,DLQ].includes(batch.queue))throw Error('HOLD_QA_QUEUE_IDENTITY');
      return resourceInvocation(env,batch.queue===DLQ?'DLQ':'QUEUE',
        metered=>legacy.queue(batch,metered,ctx),options);
    },
    async scheduled(event,env,ctx){
      if(!enabled(env))return legacy.scheduled(event,env,ctx);
      return resourceInvocation(env,'WORKER_FETCH',async metered=>{
        const pending=[];
        let error;
        try{await legacy.scheduled(event,metered,{waitUntil:p=>pending.push(Promise.resolve(p))});}
        catch(cause){error=cause;}
        await drain(pending,error);
      },options);
    },
  };
}

function meteredContext(ctx,grant){
  const originals=new WeakMap(),wrapped=new WeakMap();
  const socket=raw=>{
    if(wrapped.has(raw))return wrapped.get(raw);
    const view=new Proxy(raw,{get(target,key){
      if(key==='send')return data=>{grant.consume({ws_messages_out:1});return target.send(data);};
      const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
    }});
    wrapped.set(raw,view);originals.set(view,raw);return view;
  };
  const storage=new Proxy(ctx.storage,{get(target,key){
    const value=Reflect.get(target,key,target);
    if(typeof value!=='function')return value;
    return (...args)=>{
      const n=Array.isArray(args[0])?Math.max(1,args[0].length):1;
      const counts=key==='get'||key==='getAlarm'?{do_storage_reads:n}:
        key==='setAlarm'?{do_storage_writes:1,do_alarms:1}:
        ['put','delete','deleteAlarm'].includes(key)?{do_storage_writes:n}:null;
      if(!counts)throw Error('HOLD_UNMETERED_DO_STORAGE_API');
      return grant.effect(counts,()=>value.apply(target,args));
    };
  }});
  const context=new Proxy(ctx,{get(target,key){
    if(key==='storage')return storage;
    if(key==='getWebSockets')return (...args)=>target.getWebSockets(...args).map(socket);
    if(key==='getWebSocketAutoResponseTimestamp')return value=>target.getWebSocketAutoResponseTimestamp(originals.get(value)||value);
    if(key==='acceptWebSocket')return ()=>{throw Error('HOLD_NATIVE_WEBSOCKET_METER');};
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }});
  return {context,socket};
}

export function wrapQaDeviceChannel(Core,options={}){
  return class QaDeviceChannel extends Core {
    async resourceCall(kind,method,args){
      if(!enabled(this.env))return Core.prototype[method].apply(this,args);
      try{return await resourceInvocation(this.env,kind,async(env,grant)=>{
        if(method==='fetch'&&new URL(args[0].url).pathname==='/connect')throw Error('HOLD_NATIVE_WEBSOCKET_METER');
        const view=Object.create(this);
        const metered=meteredContext(this.ctx,grant);
        view.env=env;view.ctx=metered.context;
        if(method.startsWith('webSocket'))args=[metered.socket(args[0]),...args.slice(1)];
        // Share the original fence and pending map; never replace actor env
        // while another invocation is awaiting I/O.
        if(typeof this.withPresence==='function')view.withPresence=this.withPresence.bind(this);
        if(method==='webSocketMessage')grant.consume({ws_messages_in:1});
        return Core.prototype[method].apply(view,args);
      },options);}catch(error){
        // Ending existing transport is still possible on a terminal budget
        // failure; no new alarm, lifecycle write or message is emitted here.
        for(const socket of this.ctx.getWebSockets())try{socket.close(1013,'QA_RESOURCE_HOLD');}catch{}
        throw error;
      }
    }
    fetch(request){return this.resourceCall('DO_FETCH','fetch',[request]);}
    alarm(){return this.resourceCall('DO_ALARM','alarm',[]);}
    webSocketMessage(...args){return this.resourceCall('DO_MESSAGE','webSocketMessage',args);}
    webSocketClose(...args){return this.resourceCall('DO_MESSAGE','webSocketClose',args);}
    webSocketError(...args){return this.resourceCall('DO_MESSAGE','webSocketError',args);}
  };
}
