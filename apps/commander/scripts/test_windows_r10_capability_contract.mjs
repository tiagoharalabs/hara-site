import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
function segment(begin,end){
  const a=source.indexOf(begin),b=source.indexOf(end,a+begin.length);
  assert.ok(a>=0 && b>a,`SOURCE_SECTION_MISSING:${begin}`);
  return source.slice(a,b);
}
const functions=
  segment("function agentPurposeToolReady(device, toolId) {","async function customerMcpWaitForCall(")+
  segment("function semverAtLeast(version, wantedPatch) {","function capabilityToolDetail(")+
  segment("function capabilityToolDetail(toolId, approvalMode = ","function capabilitiesForDevice(device, grants) {")+
  segment("function capabilitiesForDevice(device, grants) {","async function ");
const context={
  isDeviceProcessTool:()=>false,
  isDeviceMutationTool:()=>false,
  isDeviceProcessMutationTool:(id)=>["hara.process.start","hara.process.kill","hara.process.interact","hara.process.run"].includes(id),
  normalizeApprovalMode:(mode,fallback)=>mode||fallback,
  MCP_TOOL_GRANTS:{},
};
vm.createContext(context);
vm.runInContext(functions,context);

let checks=0;
function check(name,fn){fn();checks++;}
const old={platform:"WINDOWS",agent_version:"0.3.53",device_name:"HARA_WIN11",device_id:"D",architecture:"x64",online:true,approval_mode:"SESSION_TRUSTED"};
const next={...old,agent_version:"0.3.55"};
for(const tool of ["hara.files.read_many","hara.files.search","hara.files.edit"]){
  check(`old_${tool}_typed_upgrade`,()=>assert.throws(()=>context.assertWindowsToolCompatibility(old,tool,{}),/AGENT_UPGRADE_REQUIRED/));
  check(`new_${tool}_direct`,()=>assert.equal(context.agentPurposeToolReady(next,tool),true));
}
check("old_list_offset_denied_before_dispatch",()=>assert.throws(()=>context.assertWindowsToolCompatibility(old,"hara.files.list",{offset:4}),/LIST_OFFSET_UNSUPPORTED/));
check("old_first_page_allowed",()=>assert.doesNotThrow(()=>context.assertWindowsToolCompatibility(old,"hara.files.list",{offset:0})));
check("new_list_offset_allowed",()=>assert.doesNotThrow(()=>context.assertWindowsToolCompatibility(next,"hara.files.list",{offset:4})));
const grants=["COMMANDER_READ_ONLY_INVOKE","COMMANDER_MUTATION_INVOKE","COMMANDER_PROCESS_EXECUTION"];
const oldCaps=context.capabilitiesForDevice(old,grants);
const nextCaps=context.capabilitiesForDevice(next,grants);
for(const tool of ["hara.files.read_many","hara.files.search","hara.files.edit"]){
  check(`old_${tool}_not_advertised`,()=>assert.ok(!oldCaps.tools.includes(tool)));
  check(`new_${tool}_advertised`,()=>assert.ok(nextCaps.tools.includes(tool)));
}
check("windows_command_input_declared",()=>assert.equal(oldCaps.process_input_mode,"POWERSHELL_COMMAND_LINES"));
check("windows_readhost_not_claimed",()=>assert.equal(oldCaps.interactive_stdin_supported,false));
check("old_list_offset_not_claimed",()=>assert.equal(oldCaps.list_offset_supported,false));
check("new_list_offset_claimed",()=>assert.equal(nextCaps.list_offset_supported,true));
console.log(JSON.stringify({schema:"hara.commander-windows-r10-capability-contract.v1",checks,passed:checks,failed:0,scope:"WORKER_SOURCE_OFFLINE"}));
