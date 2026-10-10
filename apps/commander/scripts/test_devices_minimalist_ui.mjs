import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Self-contained DOM simulation of the actual production renderDevices source.
// No npm/browser/network; mocks only element construction and in-page counters.
const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const app=path.resolve(scriptDir,"../public");
const source=fs.readFileSync(path.join(app,"app.js"),"utf8");
const html=fs.readFileSync(path.join(app,"index.html"),"utf8");
const css=fs.readFileSync(path.join(app,"styles.css"),"utf8");

function functionSource(name,next) {
  const a=source.indexOf("  function "+name+"(");
  const b=source.indexOf("  function "+next+"(",a+5);
  assert.ok(a>=0 && b>a,"FUNCTION_BOUNDARY_"+name);
  return source.slice(a,b);
}
function elementClass(node,name){return String(node.className||"").split(/\s+/).includes(name)}
class Node {
  constructor(tag){
    this.tagName=String(tag).toUpperCase();
    this.children=[];
    this._text="";
    this.className="";
    this.dataset={};
    this.attributes={};
    this.hidden=false;
    this.classList={
      toggle:(name,yes)=>{
        const classes=new Set(this.className.split(/\s+/).filter(Boolean));
        const enabled=yes===undefined?!classes.has(name):Boolean(yes);
        if(enabled)classes.add(name);else classes.delete(name);
        this.className=[...classes].join(" ");
        return enabled;
      },
      add:(name)=>{
        const classes=new Set(this.className.split(/\s+/).filter(Boolean));
        classes.add(name);
        this.className=[...classes].join(" ");
      },
    };
  }
  set textContent(x){this._text=String(x);this.children=[]}
  get textContent(){return this._text+this.children.map(child=>child?.textContent||"").join("")}
  append(...items){
    for(const item of items) this.children.push(typeof item==="string"?new TextNode(item):item);
  }
  appendChild(item){this.append(item);return item}
  replaceChildren(...items){this.children=[];this._text="";this.append(...items)}
  setAttribute(k,v){this.attributes[k]=String(v)}
}
class TextNode{
  constructor(value){this.textContent=String(value)}
}
const ids=new Map();
const document={
  createElement:(tag)=>new Node(tag),
  createTextNode:(text)=>new TextNode(text),
  querySelectorAll:()=>[],
  getElementById:(id)=>{if(!ids.has(id))ids.set(id,new Node("div"));return ids.get(id);},
};
const context=vm.createContext({
  document,
  Intl,
  Date,
  Number,
  String,
  Math,
});
const definitions=[
  'var deviceTab="active";',
  'var deviceSectionTab="devices";',
  'var devicesCache=null;',
  'const number=(n)=>String(n);',
  'const setText=(id,text)=>{document.getElementById(id).textContent=text};',
  'const setState=()=>{};',
  functionSource("formatDeviceSeen","formatDeviceSeenCompact"),
  functionSource("formatDeviceSeenCompact","setDeviceSectionTab"),
  functionSource("setDeviceSectionTab","setDeviceTab"),
  functionSource("deviceApprovalLabel","deviceReadiness"),
  functionSource("deviceReadiness","deviceDiagnosticCommand"),
  functionSource("deviceDiagnosticCommand","renderDevices"),
  functionSource("renderDevices","handlePortalAuthFailure"),
  ].join("\n");
vm.runInContext(definitions,context,{timeout:2500});

const fiveMinutesAgo=new Date(Date.now()-5*60*1000).toISOString();
const yesterday=new Date(Date.now()-24*60*60*1000).toISOString();
const payload={
  devices:[
    {state:"ACTIVE",online:true,device_name:"services",device_id:"D1",
     platform:"LINUX",architecture:"x86_64",agent_version:"0.3.44",
     tunnel_mode:"OUTBOUND_RELAY",approval_mode:"PERSISTENT_TRUSTED",
     last_seen_at_utc:fiveMinutesAgo},
    {state:"ACTIVE",online:true,device_name:"nucleo-a",device_id:"D2",
     platform:"LINUX",architecture:"x86_64",agent_version:"0.3.44",
     tunnel_mode:"OUTBOUND_RELAY",approval_mode:"ASK_EVERY_ACTION",
     last_seen_at_utc:fiveMinutesAgo},
    {state:"ACTIVE",online:false,device_name:"ninja-blue",device_id:"D3",
     platform:"LINUX",architecture:"x86_64",agent_version:"0.3.41",
     tunnel_mode:"LOCAL_TUNNEL",authorization_active:true,
     approval_mode:"PERSISTENT_TRUSTED",last_seen_at_utc:yesterday},
    {state:"REVOKED",online:false,device_name:"former-win",device_id:"D4",
     platform:"WINDOWS",architecture:"x64",agent_version:"0.3.13",
     last_seen_at_utc:yesterday},
  ],
};
context.payload=payload;
vm.runInContext("renderDevices(payload)",context,{timeout:2500});

function descendants(node){
  return [node,...(node.children||[]).flatMap(child=>descendants(child))];
}
function byClass(node,cls){return descendants(node).filter(n=>elementClass(n,cls))}
function row(name){
  return byClass(document.getElementById("deviceList"),"device-row")
    .find(el=>el.textContent.includes(name));
}
const list=document.getElementById("deviceList");
assert.equal(byClass(list,"device-row").length,3,"ACTIVE_ROW_COUNT");
assert.equal(document.getElementById("deviceStatusSummary").textContent,"2 online · 1 offline");
assert.equal(document.getElementById("deviceActiveCount").textContent,"3");
assert.equal(document.getElementById("deviceHistoryCount").textContent,"1");
assert.equal(document.getElementById("dashboardConnections").textContent,"1 pronto");
console.log("DEVICE_MINIMALIST_TRUE_ONLINE_AND_READY_COUNTS=PASS");

for(const name of ["services","nucleo-a","ninja-blue"]){
  const target=row(name);
  assert.ok(target,"ROW_MISSING_"+name);
  const body=byClass(target,"device-copy")[0];
  assert.ok(!body.textContent.includes("Agent"));
  assert.ok(!body.textContent.includes("x86_64"));
  assert.ok(!body.textContent.includes("Sempre permitido"));
  assert.equal(byClass(target,"device-overflow").length,1);
  const more=byClass(target,"device-overflow")[0];
  assert.ok(more.tagName==="DETAILS");
  const trigger=byClass(target,"device-overflow-toggle")[0];
  assert.equal(trigger.tagName,"SUMMARY");
  assert.ok(trigger.attributes["aria-label"].includes(name));
  assert.equal(byClass(target,"device-primary-action").length,1);
  assert.equal(byClass(target,"device-revoke-action").length,1);
  assert.ok(byClass(target,"device-facts")[0].textContent.includes("Agent"));
}
assert.equal(byClass(row("ninja-blue"),"device-state")[0].textContent,"Offline",
  "AUTHORIZATION_MUST_NOT_MASK_DISCONNECTION");
assert.equal(byClass(row("services"),"device-state")[0].textContent,"Pronto");
assert.equal(byClass(row("nucleo-a"),"device-state")[0].textContent,"Atenção");
console.log("DEVICE_MINIMALIST_ROW_DISCLOSURES_AND_ACCURATE_STATES=PASS");

vm.runInContext('deviceTab="history";renderDevices(payload)',context,{timeout:2500});
assert.equal(byClass(document.getElementById("deviceList"),"device-row").length,1);
assert.ok(row("former-win"));
assert.equal(byClass(row("former-win"),"device-revoke-action").length,0);
assert.equal(byClass(row("former-win"),"device-primary-action").length,0);
console.log("DEVICE_MINIMALIST_HISTORY_AND_SAFETY=PASS");

vm.runInContext('setDeviceSectionTab("connect")',context,{timeout:2500});
assert.equal(vm.runInContext('deviceSectionTab',context),'connect');
vm.runInContext('setDeviceSectionTab("commands")',context,{timeout:2500});
assert.equal(vm.runInContext('deviceSectionTab',context),'commands');
vm.runInContext('setDeviceSectionTab("devices")',context,{timeout:2500});
assert.equal(vm.runInContext('deviceSectionTab',context),'devices');
console.log("DEVICE_MINIMALIST_THREE_TABS_NAVIGATION=PASS");

assert.match(html,/data-device-section-tab="commands"/);
assert.match(html,/data-device-section-panel="commands"/);
assert.match(html,/id="deviceStatusSummary"/);
assert.doesNotMatch(html,/<details class="devices-help" id="devicesHelp"/);
assert.match(css,/\[data-view="devices"\] \.device-overflow-panel/);
assert.match(css,/html\[data-theme="dark"\] \[data-view="devices"\]/);
assert.match(css,/--gold:/);
console.log("DEVICE_MINIMALIST_EXISTING_COLOR_THEME_AND_GUIDE_DISCLOSURE=PASS");
console.log("DEVICE_MINIMALIST_NO_BACKEND_MUTATION=TRUE");
