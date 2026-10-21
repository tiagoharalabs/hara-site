// Read-only audit of the Worker capability contract per installed/candidate Agent.
import fs from "node:fs";
import vm from "node:vm";
import {createHash} from "node:crypto";
const source=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
function segment(begin,end) {
 const a=source.indexOf(begin),b=source.indexOf(end,a+begin.length);
 if(a<0||b<a)throw Error("WORKER_CAPABILITY_SOURCE_CHANGED");
 return source.slice(a,b);
}
const extracted=
 segment("function agentPurposeToolReady(device, toolId) {","async function customerMcpWaitForCall(")+
 segment("function semverAtLeast(version, wantedPatch) {","function capabilityToolDetail(")+
 segment("function capabilityToolDetail(toolId, approvalMode = ","function capabilitiesForDevice(device, grants) {")+
 segment("function capabilitiesForDevice(device, grants) {","async function ");
const context={
 isDeviceProcessTool:()=>false,
 isDeviceMutationTool:()=>false,
 isDeviceProcessMutationTool:(id)=>["hara.process.start","hara.process.kill","hara.process.interact","hara.process.run"].includes(id),
 normalizeApprovalMode:(a,b)=>a||b,
 MCP_TOOL_GRANTS:{},
};
vm.createContext(context);
vm.runInContext(extracted,context);
const grants=["COMMANDER_READ_ONLY_INVOKE","COMMANDER_MUTATION_INVOKE","COMMANDER_PROCESS_EXECUTION"];
function make(platform,agent_version){
 const device={platform,agent_version,device_id:"QA_ONLY",online:true,approval_mode:"SESSION_TRUSTED"};
 return context.capabilitiesForDevice(device,grants);
}
const linux=make("LINUX","0.3.54");
const windows053=make("WINDOWS","0.3.53");
const windows055=make("WINDOWS","0.3.55");
const subtract=(a,b)=>a.filter(x=>!b.includes(x)).sort();
const record={
 schema:"hara.commander.release-capability-matrix.r20.v1",
 source_worker_sha256:createHash("sha256").update(source).digest("hex"),
 server_contract:"SOURCE_ONLY_NOT_RUNTIME_W11",
 linux_054:{count:linux.tools.length},
 windows_053:{count:windows053.tools.length},
 windows_055:{count:windows055.tools.length},
 common_linux_win055:linux.tools.filter(x=>windows055.tools.includes(x)).length,
 missing_on_win055:subtract(linux.tools,windows055.tools),
 only_on_win055:subtract(windows055.tools,linux.tools),
 new_win055_tools:subtract(windows055.tools,windows053.tools),
 release_parity_complete:linux.tools.length===windows055.tools.length&&subtract(linux.tools,windows055.tools).length===0,
 network_requests:0,customer_device_mutated:false,
};
if(record.linux_054.count!==31||record.windows_053.count!==19||record.windows_055.count!==22)
 throw Error("R20_UNEXPECTED_WORKER_CAPABILITY_CONTRACT");
console.log(JSON.stringify(record,null,2));
