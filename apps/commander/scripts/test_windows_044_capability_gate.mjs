import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const text=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
function segment(begin,end){
 const a=text.indexOf(begin),b=text.indexOf(end,a+begin.length);
 assert.ok(a>=0&&b>a,"SOURCE_SECTION_MISSING:"+begin);
 return text.slice(a,b);
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
 normalizeApprovalMode:(m,defaultValue)=>m||defaultValue,
 MCP_TOOL_GRANTS:{},
};
vm.createContext(context);
vm.runInContext(functions,context);

let checked=0;
function check(name,action){action();checked++;}
const base={platform:"WINDOWS",agent_version:"0.3.43",device_name:"WIN",device_id:"D",architecture:"x64",online:true,approval_mode:"ASK_EVERY_ACTION"};
const processTools=["hara.process.start","hara.process.output","hara.process.interact","hara.process.kill","hara.process.sessions"];
for(const tool of processTools){
 check("windows43_denies_"+tool,()=>assert.equal(context.agentPurposeToolReady(base,tool),false));
 check("windows44_enables_"+tool,()=>assert.equal(context.agentPurposeToolReady({...base,agent_version:"0.3.44"},tool),true));
}
for(const tool of ["hara.files.write","hara.files.create_directory","hara.process.run","hara.files.read","hara.ping"]){
 check("legacy_windows_starter_"+tool,()=>assert.equal(context.agentPurposeToolReady(base,tool),true));
}
for(const tool of ["hara.files.delete","hara.files.rollback","hara.files.copy","hara.files.move"]){
 check("windows44_does_not_claim_linux_only_"+tool,()=>assert.equal(context.agentPurposeToolReady({...base,agent_version:"0.3.44"},tool),false));
}
const caps=context.capabilitiesForDevice({...base,agent_version:"0.3.44"},["COMMANDER_READ_ONLY_INVOKE","COMMANDER_PROCESS_EXECUTION","COMMANDER_MUTATION_INVOKE"]);
for(const tool of processTools) check("windows44_advertises_"+tool,()=>assert.ok(Array.from(caps.tools).includes(tool)));
check("ask_every_action_retained",()=>assert.equal(caps.approval_mode,"ASK_EVERY_ACTION"));
check("ask_requires_local_approval",()=>assert.equal(caps.mutation_requires_local_approval,true));
check("session_is_not_claimed_authorized",()=>assert.equal(caps.local_session_authorizes_governed_mutations,false));
const capsNoProcess=context.capabilitiesForDevice({...base,agent_version:"0.3.44"},["COMMANDER_READ_ONLY_INVOKE"]);
for(const tool of ["hara.process.start","hara.process.interact","hara.process.kill"])
 check("process_grant_required_"+tool,()=>assert.ok(!Array.from(capsNoProcess.tools).includes(tool)));
check("sessions_list_available_without_process_grant",()=>assert.ok(Array.from(capsNoProcess.tools).includes("hara.process.sessions")));
check("output_read_available_without_process_grant",()=>assert.ok(Array.from(capsNoProcess.tools).includes("hara.process.output")));
const caps43=context.capabilitiesForDevice(base,["COMMANDER_PROCESS_EXECUTION"]);
for(const tool of processTools) check("no_false_capability_before_v44_"+tool,()=>assert.ok(!Array.from(caps43.tools).includes(tool)));
console.log(JSON.stringify({schema:"hara.commander-windows44-capability-gate.v1",checked,passed:checked,failed:0,scope:"ACTUAL_WORKER_FUNCTIONS_OFFLINE",production_mutations:false}));
