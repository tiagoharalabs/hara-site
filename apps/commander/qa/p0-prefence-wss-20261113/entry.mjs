// Isolated Cloudflare QA: fence active forward DO before swapping code.
// No customer routes, queue, Cron, production Worker or product bindings.
import {DeviceChannel} from "./worker.mjs";
export {DeviceChannel};
const HOST="hara-commander-p0-prefence-wss-qa-20261113.tiago-sartori.workers.dev";
const SCOPE="ISOLATED_QA_PREFENCE_WSS_20261113";
const CHANNEL="QA43-TENANT:QA43-DEVICE";
const EPOCH="QA_PREFENCE_WSS_EPOCH_20261113";
const HEADERS={"cache-control":"no-store","x-content-type-options":"nosniff"};
const respond=(x,status=200)=>Response.json(x,{status,headers:HEADERS});
const reject=()=>new Response("Not found",{status:404,headers:HEADERS});
const hash=async key=>{
 const raw=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(key));
 return [...new Uint8Array(raw)].map(v=>v.toString(16).padStart(2,"0")).join("");
};
function doStub(env){
 if(!env.DEVICE_CHANNEL||typeof env.DEVICE_CHANNEL.getByName!=="function")throw Error("DO_BINDING_MISSING");
 return env.DEVICE_CHANNEL.getByName(CHANNEL);
}
function internalRequest(){
 return new Request("https://qa-prefence.invalid/connect",{
  headers:{"x-hara-channel-authenticated":"1",upgrade:"websocket",
           "x-hara-tenant-id":"QA43-TENANT","x-hara-device-id":"QA43-DEVICE"}});
}
export default {
 async fetch(request,env){
  const u=new URL(request.url);
  if(u.hostname!==HOST||u.protocol!=="https:"||env.QA_SCOPE!==SCOPE||
     !["FORWARD","CONTAINMENT"].includes(env.QA_MODE))return reject();
  if(Date.now()>Number(env.QA_EXPIRES_MS||0))return respond({code:"QA_EXPIRED"},410);
  const key=request.headers.get("x-hara-qa-key")||"";
  if(!/^[a-f0-9]{64}$/.test(key)||!/^[a-f0-9]{64}$/.test(env.QA_KEY_SHA256||"")||
     await hash(key)!==env.QA_KEY_SHA256)return reject();
  try{
   const stub=doStub(env);
   if(u.pathname==="/__qa/status"&&request.method==="GET")
     return respond({state:"QA_ONLY",mode:env.QA_MODE,version:env.QA_VERSION?.id||null});
   if(u.pathname==="/__qa/witness"&&request.method==="GET")
     return respond({mode:env.QA_MODE,
       ...(await stub.cutoverFenceWitness(u.searchParams.get("nonce")||""))});
   if(u.pathname==="/__qa/fence"&&request.method==="POST"){
     if(env.QA_MODE!=="FORWARD")return respond({code:"QA_NOT_FORWARD"},503);
     const raw=await request.text();
     if(raw.length>256)return respond({code:"QA_BODY_OVERSIZE"},400);
     const body=JSON.parse(raw);
     if(!body||Object.keys(body).length!==1||body.epoch!==EPOCH)
       return respond({code:"QA_EPOCH_INVALID"},400);
     return respond({mode:"FORWARD",...(await stub.enterCutoverFence(body.epoch))});
   }
   if(u.pathname==="/__qa/ws"&&request.method==="GET"){
     if(env.QA_MODE!=="FORWARD")return respond({code:"QA_CONTAINED"},503);
     if(request.headers.get("upgrade")?.toLowerCase()!=="websocket")
       return respond({code:"QA_WEBSOCKET_REQUIRED"},426);
     return stub.fetch(internalRequest());
   }
  }catch{
   return respond({code:"QA_OPERATION_FAILED"},503);
  }
  return reject();
 },
 scheduled(){},
 queue(){throw Error("QA_QUEUE_NOT_CONFIGURED");}
};