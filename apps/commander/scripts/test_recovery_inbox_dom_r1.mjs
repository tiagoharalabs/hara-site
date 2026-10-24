import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const src=fs.readFileSync(path.join(root,"public/recovery-alerts.js"),"utf8");
class Node {
  constructor(tag="div") {this.tag=tag;this.children=[];this.hidden=false;this.dataset={};
    this.handlers={};this.disabled=false;this.textContent="";this.attributes={};}
  setAttribute(k,v) {this.attributes[k]=v;}
  append(...nodes) {this.children.push(...nodes);}
  prepend(...nodes) {this.children.unshift(...nodes);}
  replaceChildren(...nodes) {this.children=nodes.flatMap(n=>n.tag==="#fragment"?n.children:[n]);}
  addEventListener(k,f) {this.handlers[k]=f;}
}
function environment(initialMode="normal") {
 let logged=true, fetches=0, observer=null, interval=null, mode=initialMode, events=[];
 const main=new Node("main");const auth={hidden:false};const body={
  classList:{contains:()=>logged},
 };
 const doc={
  hidden:false,body,
  getElementById:id=>id==="mainContent"?main:null,
  querySelector:q=>q==="[data-auth-session]"?auth:null,
  createElement:tag=>new Node(tag),
  createDocumentFragment:()=>new Node("#fragment"),
  addEventListener:()=>{},
 };
 const mockFetch=async(url,options)=>{
  fetches++;
  if (mode==="disabled") return {status:404,ok:false,json:async()=>({})};
  if (url.endsWith("/ack")) {
   assert.equal(options.method,"POST");
   assert.equal(options.credentials,"same-origin");
   const {event_id}=JSON.parse(options.body);
   events=events.map(e=>({...e,portal_ack_at_utc:e.event_id===event_id?"2026-10-24T12:00:00Z":null}));
   return {status:200,ok:true,json:async()=>({ack:"PORTAL_ACKNOWLEDGED",event_id})};
  }
  if (url==="/api/portal/recovery-events")return {status:200,ok:true,json:async()=>({
    schema:"hara.commander.recovery-inbox.v1",events
  })};
  throw new Error("unexpected fetch");
 };
 const c=vm.createContext({
  document:doc,window:{fetch:mockFetch},fetch:mockFetch,Promise,
  MutationObserver:class {constructor(cb){observer=cb;}observe(){}},
  setInterval:fn=>{interval=fn;return 1;},console,
 });
 vm.runInContext(src,c,{filename:"recovery-alerts.js"});
 const box=main.children[0], list=box.children[2];
 return {get fetches(){return fetches},box,list,auth,body,doc,
  changeUser:(value)=>{logged=value;auth.hidden=!value;observer();},
  poll:()=>interval(),
  mode:value=>{mode=value},
  setEvents:next=>{events=next},
 };
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
let count=0;
const ok=x=>{console.log("PASS "+x);count++};
const fixture={event_id:"HARA-REC-"+"a".repeat(48),device_id:"DEVICE-A",
 incident_id:"INC-00000",event_state:"STALLED",persisted_at_utc:"2026-10-24T12:00:00Z",
 portal_ack_at_utc:null};
{
 const e=environment();e.setEvents([fixture]);await e.poll();await flush();
 assert.equal(e.box.hidden,false);assert.equal(e.list.children.length,1);
 assert.ok(e.list.children[0].children[0].textContent.includes("Travamento detectado"));
 const button=e.list.children[0].children[1];
 assert.equal(button.textContent,"Reconhecer");
 await e.box.handlers.click({target:{closest:()=>button}});
 assert.equal(e.box.hidden,true);
 assert.equal(e.list.children.length,0);
 ok("portal_renders_text_and_explicit_ack");
 e.setEvents([fixture]);await e.poll();await flush();
 assert.equal(e.box.hidden,false);
 e.changeUser(false);assert.equal(e.box.hidden,true);assert.equal(e.list.children.length,0);
 ok("logout_clears_prior_tenant_alerts");
}
{
 const e=environment("disabled");
 await e.poll();await flush();
 const before=e.fetches;
 await e.poll();await flush();
 assert.equal(e.fetches,before);
 assert.equal(e.box.hidden,true);
 ok("disabled_backend_has_no_repeat_requests");
}
console.log("RECOVERY_INBOX_DOM_R1="+count+"_CHECKS_PASS");
