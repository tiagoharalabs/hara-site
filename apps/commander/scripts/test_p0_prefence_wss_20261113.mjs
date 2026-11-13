// Real WSS handshake/alarm trigger/fence close in isolated Cloudflare QA only.
import fs from "node:fs";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const WebSocket=require("/tmp_hara/commander-capability-suite-20261110/node_modules/ws");
const mode=process.argv[2];
if(!["before","hold","after"].includes(mode))throw Error("QA_MODE_REQUIRED");
const key=fs.readFileSync("/tmp_hara/commander-prefence-wss-qa-20261113/access.key","utf8");
if(!/^[a-f0-9]{64}$/.test(key))throw Error("QA_KEY_INVALID");
const ws=new WebSocket("wss://hara-commander-p0-prefence-wss-qa-20261113.tiago-sartori.workers.dev/__qa/ws",
 {headers:{"x-hara-qa-key":key,"User-Agent":"HARA-P0-Exact-Only/1.0"},
  handshakeTimeout:14000});
let done=false,ack=false;
const timer=setTimeout(()=>{
 if(!done){ws.terminate();finish("QA_WSS_TIMEOUT",{},true);}
},mode==="hold"?135000:30000);
function finish(state,fields={},failed=false){
 if(done)return;done=true;clearTimeout(timer);
 console.log(JSON.stringify({schema:"hara.p0.exact.qa.wss.v1",state,mode,...fields}));
 if(failed)process.exitCode=2;
 if(ws.readyState===WebSocket.OPEN)ws.close(1000,"QA_COMPLETE");
 if(mode!=="hold")setTimeout(()=>process.exit(process.exitCode||0),160).unref();
}
ws.once("unexpected-response",(_req,res)=>{
 res.resume();
 const ok=mode==="after"&&res.statusCode===503;
 finish(ok?"QA_WSS_NEW_HANDSHAKE_REFUSED_503":"QA_WSS_HTTP_UNEXPECTED",
 {http_status:res.statusCode},!ok);
});
ws.on("open",()=>{
 if(mode==="after"){finish("QA_WSS_AFTER_SHOULD_HAVE_BEEN_DENIED",{},true);return;}
 ws.send("HARA_EVENT_V2_PROBE_V1");
});
ws.on("message",data=>{
 if(String(data)!=="HARA_EVENT_V2_PROBE_ACK_V1"){
   finish("QA_WSS_PROBE_ACK_MISMATCH",{},true);return;
 }
 ack=true;
 if(mode==="before")finish("QA_WSS_REAL_CHANNEL_BEFORE_CLOSE_PASS",{probe_ack:true});
 if(mode==="hold")console.log(JSON.stringify({schema:"hara.p0.exact.qa.wss.v1",
    mode,state:"QA_WSS_CONNECTION_HELD_FOR_CUTOVER",probe_ack:true}));
});
ws.on("close",(code,reason)=>{
 if(done)return;
 if(mode==="hold"){
   const ok=ack&&code===1012;
   finish(ok?"QA_WSS_EXISTING_CONNECTION_FENCED_1012":"QA_WSS_CLOSE_UNEXPECTED",
     {close_code:code,close_reason:String(reason).slice(0,60),probe_ack:ack},!ok);
 }else finish("QA_WSS_CLOSED_BEFORE_EXPECTED_RESULT",{close_code:code},true);
});
ws.on("error",err=>{if(!done)finish("QA_WSS_CLIENT_ERROR",{error_code:err.code||"ERROR"},true);});