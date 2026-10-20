#!/usr/bin/env node
// Exercise the production projection and simple MCP envelope with JSON stdout.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createHash } from "node:crypto";

const app=new URL("../",import.meta.url);
const worker=fs.readFileSync(new URL("src/worker.js",app),"utf8");
const simple=fs.readFileSync(new URL("src/customer-mcp-simple.mjs",app),"utf8");
const full=fs.readFileSync(new URL("src/customer-mcp.mjs",app),"utf8");
function extract(source,name){
  const start=source.indexOf(`function ${name}(`);
  assert(start>=0,`missing ${name}`);
  const end=source.indexOf("\n}",start);
  assert(end>start);
  return source.slice(start,end+2);
}
const runtime=vm.createContext({TextEncoder,
  deviceFunctionForTool:()=>true,isDeviceMutationTool:()=>false,isDeviceProcessTool:()=>false});
vm.runInContext([extract(worker,"trimPublicText"),extract(worker,"projectCustomerToolResult"),
  extract(simple,"publicToolResult")].join("\n")+
  "\nglobalThis.project=projectCustomerToolResult;globalThis.envelope=publicToolResult;globalThis.trim=trimPublicText;",runtime);
vm.runInContext(extract(full,"publicToolResult").replace("function publicToolResult(","function fullToolResult(")+
  "\nglobalThis.fullEnvelope=fullToolResult;",runtime);
if(process.argv.includes("--stdin")) {
  const input=JSON.parse(fs.readFileSync(0,"utf8"));
  const projected=runtime.project(input.tool_id,input.result);
  const envelopes=[runtime.envelope(projected),runtime.fullEnvelope(projected)];
  const original=String(input.result?.result?.stdout || "");
  const hash=(value)=>createHash("sha256").update(value).digest("hex");
  const checks=envelopes.map((envelope)=>{
    const stdout=envelope.structuredContent.result.stdout;
    const data=JSON.parse(stdout);
    assert.equal(JSON.parse(envelope.content[0].text).result.stdout,stdout);
    return {sha256:hash(stdout),original_sha256:hash(original),count:data.count,
      successful_count:data.successful_count,failed_count:data.failed_count,
      deferred_count:data.deferred_count,overall_status:data.overall_status,
      files:Array.isArray(data.files)?data.files.map(x=>({state:x.state,line_count:x.line_count,
        next_offset:x.next_offset,has_more:x.has_more,
        file_revision_hint:x.file_revision_hint,
        file_changed_during_read:x.file_changed_during_read,
        restart_offset:x.restart_offset})):null,isError:envelope.isError===true};
  });
  assert.deepEqual(checks[0],checks[1]);
  process.stdout.write(JSON.stringify(checks[0])+"\n");
  process.exit(0);
}
const project=(data,tool="hara.files.read_many")=>{
  const response={state:"PASS",operational_authority:"HARA_COMMANDER_AGENT",
    runtime_authority_from_chatgpt:false,mutation_performed:false,
    result:{function_id:"filesystem.read_many",risk_class:"READ_ONLY",process_exit_code:0,
      stdout:JSON.stringify(data),domain_success_inferred:false}};
  const projected=runtime.project(tool,response);
  const publicResult=runtime.envelope(projected);
  assert.equal(publicResult.isError,undefined);
  assert.equal(JSON.parse(publicResult.content[0].text).result.stdout,publicResult.structuredContent.result.stdout);
  try { return JSON.parse(publicResult.structuredContent.result.stdout); }
  catch { throw new Error("PUBLIC_JSON_STDOUT_INVALID"); }
};

for (const count of [1,4,10]) {
  const data={count,files:Array.from({length:count},(_,i)=>({path:`/fixture/${i}`,
    state:i===count-1&&count===10?"FAILED":"PASS",
    error_code:i===count-1&&count===10?"FILE_NOT_FOUND":null,
    offset:0,next_offset:100,has_more:true,text:"X".repeat(count===1?60000:Math.floor(95000/count))}))};
  const result=project(data);
  assert.equal(result.count,count);
  assert.equal(result.files.length,count);
  assert.deepEqual(result.files.map(x=>x.next_offset),Array(count).fill(100));
  if(count===10) assert.equal(result.files[9].state,"FAILED");
  console.log(`COMMANDER_PUBLIC_READ_MANY_${count}_JSON_AND_OFFSETS=PASS`);
}

for(const length of [65535,65536,65537]) {
  const result=project({text:"🍵\u0001"+"X".repeat(length),next_offset:7,has_more:true});
  assert.equal(result.text.length,length+3);
  assert.equal(result.next_offset,7);
  console.log(`COMMANDER_PUBLIC_JSON_${length}_CHARS_PARSEABLE=PASS`);
}

const large=project({session_id:"HARA-PROC-QA",next_offset:3,total_lines:9,
  text:"X".repeat(150000)},"hara.process.run");
assert.equal(large.state,"TRUNCATED");
assert.equal(large.continuation.session_id,"HARA-PROC-QA");
assert.equal(large.continuation.next_offset,3);
console.log("COMMANDER_PUBLIC_OVERSIZE_JSON_STRUCTURED_CONTINUATION=PASS");
const cjk=project({text:"界".repeat(60000),next_offset:9});
assert.equal(cjk.state,"TRUNCATED");
assert.equal(cjk.continuation.next_offset,9);
const plain=runtime.trim("界".repeat(70000));
assert(new TextEncoder().encode(plain).length < 66000);
assert(plain.endsWith("[HARA_COMMANDER_OUTPUT_TRUNCATED]"));
console.log("COMMANDER_PUBLIC_UTF8_BYTE_LIMIT_PRESERVES_VALID_OUTPUT=PASS");
