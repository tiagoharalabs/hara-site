import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

// Run production functions against an in-memory, read-only D1 fixture. No remote
// service, clock sleep, database credentials, or production state is involved.
const workerPath=process.argv[2] || new URL("../src/worker.js",import.meta.url);
const source=fs.readFileSync(workerPath,"utf8");
function declaration(name) {
  const start=source.search(new RegExp(`^(?:async )?function ${name}\\(`,"m"));
  assert.ok(start>=0,`missing production function: ${name}`);
  const rest=source.slice(start);
  const end=rest.search(/^}/m);
  assert.ok(end>=0,`missing function end: ${name}`);
  return rest.slice(0,end+1);
}
let snapshot="2026-10-12T18:00:50.000Z";
let snapshotReads=0;
let deviceReads=[];
let idReads=[];
const context=vm.createContext({
  Date,
  nowIso:()=>{ snapshotReads+=1; return snapshot; },
  listDevices:async (_env,scope)=>{
    deviceReads.push(scope);
    assert.equal(scope.tenant_id,"TENANT-A");
    return [{device_id:"D-1",device_name:"windows-a"}];
  },
  resolveNamedCustomerDevice:(devices,name)=>{
    assert.equal(name,"windows-a");
    return devices[0];
  },
  cleanId:(value,limit)=>{
    idReads.push({value,limit});
    return String(value).slice(0,limit);
  },
});
vm.runInContext(
  declaration("projectRecentCustomerCall")+"\n"+
  declaration("recentCustomerCalls"),context,
);
const plain=(value)=>JSON.parse(JSON.stringify(value));
let checked=0;
function check(name,fn){fn();checked+=1;}
async function checkAsync(name,fn){await fn();checked+=1;}
const row={
  call_id:"C-1",request_id:"R-1",device_id:"D-1",device_name:"windows-a",
  tenant_id:"TENANT-A",subject_id:"SUBJECT-A",tool_id:"hara.process.run",
  state:"PENDING",created_at_utc:"2026-10-12T18:00:00.000Z",
  claimed_at_utc:null,completed_at_utc:null,error_code:null,
  expires_at_utc:"2026-10-12T18:00:50.000Z",
  arguments_json:"PRIVATE-FIXTURE-ARGUMENTS",device_token:"PRIVATE-FIXTURE-TOKEN",
};
const project=(entry,now=snapshot)=>plain(context.projectRecentCustomerCall(entry,now));
for (const state of ["PENDING","EXECUTING"]) {
  for (const [label,now,expected,origin] of [
    ["ttl-50s-start","2026-10-12T18:00:00.000Z",state,null],
    ["one-ms-before","2026-10-12T18:00:49.999Z",state,null],
    ["exact-deadline","2026-10-12T18:00:50.000Z","EXPIRED","DEADLINE_PROJECTION"],
    ["one-ms-after","2026-10-12T18:00:50.001Z","EXPIRED","DEADLINE_PROJECTION"],
    ["hour-late","2026-10-12T19:00:50.000Z","EXPIRED","DEADLINE_PROJECTION"],
  ]) check(`${state}-${label}`,()=>{
    const entry={...row,state};
    const before=JSON.stringify(entry);
    const result=project(entry,now);
    assert.equal(result.state,expected);
    assert.equal(result.effective_state,expected);
    assert.equal(result.persisted_state,state);
    assert.equal(result.expiry_origin,origin);
    assert.equal(result.expires_at_utc,row.expires_at_utc);
    assert.equal(JSON.stringify(entry),before,"projection mutated its input");
  });
}
for (const state of ["COMPLETED","FAILED","CANCELLED","CANCELED","EXPIRED"]) {
  check(`terminal-${state}`,()=>{
    const entry={...row,state,completed_at_utc:"2026-10-12T18:00:20.000Z",error_code:"ORIGINAL-ERROR"};
    const result=project(entry,"2026-10-12T19:00:00.000Z");
    assert.equal(result.state,state);
    assert.equal(result.effective_state,state);
    assert.equal(result.persisted_state,state);
    assert.equal(result.expiry_origin,null);
    assert.equal(result.completed_at_utc,entry.completed_at_utc);
    assert.equal(result.error_code,entry.error_code);
  });
}
for (const deadline of [null,undefined,""," ","invalid-deadline"]) {
  for (const state of ["PENDING","EXECUTING"]) {
    check(`invalid-deadline-${state}-${String(deadline)}`,()=>{
      const result=project({...row,state,expires_at_utc:deadline});
      assert.equal(result.state,state,"invalid deadline must not invent expiry");
      assert.equal(result.effective_state,state);
      assert.equal(result.persisted_state,state);
      assert.equal(result.expiry_origin,null);
    });
  }
}
check("invalid-snapshot-does-not-invent-expiry",()=>{
  assert.throws(()=>project(row,"invalid-snapshot"),/DEVICE_CALL_STATUS_TIMESTAMP_INVALID/);
});
check("unknown-state-preserved",()=>{
  const result=project({...row,state:"FUTURE-STATE"});
  assert.equal(result.state,"FUTURE-STATE");
  assert.equal(result.expiry_origin,null);
});
check("public-record-does-not-leak-fixture-private-fields",()=>{
  const result=project(row);
  assert.equal(result.call_id,row.call_id);
  assert.equal(result.request_id,row.request_id);
  assert.equal(result.computer,row.device_name);
  assert.equal(result.tool_id,row.tool_id);
  assert.equal(result.created_at_utc,row.created_at_utc);
  assert.equal(result.claimed_at_utc,row.claimed_at_utc);
  assert.equal(result.completed_at_utc,null,"deadline is not proof of completion");
  assert.ok(!("arguments_json" in result));
  assert.ok(!("device_token" in result));
  assert.ok(!("tenant_id" in result));
  assert.ok(!("subject_id" in result));
});
function deepFreeze(value) {
  for (const child of Object.values(value)) {
    if (child && typeof child==="object") deepFreeze(child);
  }
  return Object.freeze(value);
}
for (const completedAt of [null,"2026-10-12T18:00:49.500Z"]) {
  check(`expired-executing-retains-original-outcome-metadata-${String(completedAt)}`,()=>{
    const frozen=deepFreeze({
      ...row,state:"EXECUTING",claimed_at_utc:"2026-10-12T18:00:40.000Z",
      completed_at_utc:completedAt,error_code:"ORIGINAL-ERROR",
      result_json:'{"stdout":"PRIVATE-PARTIAL-OUTPUT","execution_started":true}',
      receipt_json:'{"receipt_id":"PRIVATE-RECEIPT"}',
      result_sha256:"PRIVATE-RESULT-HASH",receipt_sha256:"PRIVATE-RECEIPT-HASH",
      private_metadata:{execution_started:true,receipts:["PRIVATE-RECEIPT"]},
    });
    const before=JSON.stringify(frozen);
    const result=project(frozen);
    assert.equal(result.state,"EXPIRED");
    assert.equal(result.persisted_state,"EXECUTING");
    assert.equal(result.claimed_at_utc,frozen.claimed_at_utc);
    assert.equal(result.completed_at_utc,completedAt);
    assert.equal(result.error_code,"ORIGINAL-ERROR");
    assert.equal(JSON.stringify(frozen),before,"expiry must not modify execution results or receipts");
    assert.ok(Object.isFrozen(frozen.private_metadata.receipts));
    for (const privateKey of ["result_json","receipt_json","result_sha256","receipt_sha256","private_metadata"]) {
      assert.ok(!(privateKey in result),`private outcome metadata leaked: ${privateKey}`);
    }
  });
}
const ledger=[
  {...row,call_id:"FOREIGN-TENANT",tenant_id:"TENANT-B"},
  {...row,call_id:"FOREIGN-SUBJECT",subject_id:"SUBJECT-B"},
  {...row,call_id:"KEEP-EXPIRED"},
  {...row,call_id:"KEEP-FUTURE",device_id:"D-2",device_name:"linux-a",tool_id:"hara.device.info",created_at_utc:"2026-10-12T17:59:59.000Z",expires_at_utc:"2026-10-12T18:01:00.000Z"},
  {...row,call_id:"KEEP-TERMINAL",state:"COMPLETED",created_at_utc:"2026-10-12T17:59:58.000Z",completed_at_utc:"2026-10-12T18:00:01.000Z"},
];
function database(rows=ledger) {
  const captures=[];
  let writes=0;
  const db={prepare(sql){
    assert.match(sql,/^\s*SELECT\b/i,"recent reads must be SELECT only");
    assert.match(sql,/\bc\.tenant_id\s*=\s*\?/);
    assert.match(sql,/\bc\.subject_id\s*=\s*\?/);
    assert.match(sql,/\bc\.expires_at_utc\b/);
    assert.match(sql,/ORDER BY\s+c\.created_at_utc\s+DESC/i);
    assert.match(sql,/LIMIT\s+\?/i);
    const capture={sql,binds:null,all:0};captures.push(capture);
    return {bind(...binds){
      capture.binds=binds;
      return {async all(){
        capture.all+=1;
        let cursor=2;
        const deviceId=/c\.device_id\s*=\s*\?/.test(sql)?binds[cursor++]:null;
        const toolId=/c\.tool_id\s*=\s*\?/.test(sql)?binds[cursor++]:null;
        const limit=binds[cursor];
        const results=rows.filter((item)=>item.tenant_id===binds[0]&&item.subject_id===binds[1]&&(!deviceId||item.device_id===deviceId)&&(!toolId||item.tool_id===toolId)).sort((a,b)=>b.created_at_utc.localeCompare(a.created_at_utc)).slice(0,limit);
        return {results};
      },run(){writes+=1;throw new Error("DB_WRITE_FORBIDDEN");}};
    }};
  }};
  return {env:{PRODUCT_DB:db},captures,get writes(){return writes;}};
}
const customer={tenant_id:"TENANT-A",subject_id:"SUBJECT-A"};
await checkAsync("real-list-isolated-single-select-with-transparent-projection",async ()=>{
  snapshotReads=0;deviceReads=[];idReads=[];
  const db=database();
  const before=JSON.stringify(ledger);
  const result=plain(await context.recentCustomerCalls(db.env,customer,{}));
  assert.equal(db.captures.length,1);
  assert.equal(db.captures[0].all,1);
  assert.deepEqual(plain(db.captures[0].binds),["TENANT-A","SUBJECT-A",50]);
  assert.deepEqual(result.map((item)=>item.call_id),["KEEP-EXPIRED","KEEP-FUTURE","KEEP-TERMINAL"]);
  assert.deepEqual(result.map((item)=>item.state),["EXPIRED","PENDING","COMPLETED"]);
  assert.equal(result[0].persisted_state,"PENDING");
  assert.equal(result[0].expiry_origin,"DEADLINE_PROJECTION");
  assert.equal(result[0].completed_at_utc,null);
  assert.equal(db.writes,0);
  assert.equal(JSON.stringify(ledger),before);
  assert.equal(snapshotReads,1,"one snapshot for the complete result batch");
  assert.equal(deviceReads.length,0);
  assert.equal(idReads.length,0);
});
await checkAsync("real-list-computer-tool-limit-filters-preserved",async ()=>{
  snapshotReads=0;deviceReads=[];idReads=[];
  const db=database();
  const result=plain(await context.recentCustomerCalls(db.env,customer,{computer:"windows-a",tool:" hara.process.run ",limit:1}));
  assert.equal(db.captures.length,1);
  assert.deepEqual(plain(db.captures[0].binds),["TENANT-A","SUBJECT-A","D-1","hara.process.run",1]);
  assert.equal(deviceReads.length,1);
  assert.deepEqual(plain(deviceReads[0]),{tenant_id:"TENANT-A"});
  assert.deepEqual(idReads,[{value:"hara.process.run",limit:120}]);
  assert.deepEqual(result.map((item)=>item.call_id),["KEEP-EXPIRED"]);
  assert.equal(result[0].state,"EXPIRED");
  assert.equal(snapshotReads,1);
  assert.equal(db.writes,0);
});
for (const [limit,expected] of [[-10,1],[1000,100]]) {
  await checkAsync(`real-list-limit-clamped-${limit}`,async ()=>{
    const db=database();
    await context.recentCustomerCalls(db.env,customer,{limit});
    assert.equal(db.captures[0].binds.at(-1),expected);
    assert.equal(db.captures.length,1);
    assert.equal(db.writes,0);
  });
}
await checkAsync("real-list-empty-results-is-still-one-read",async ()=>{
  const db=database([]);
  assert.deepEqual(plain(await context.recentCustomerCalls(db.env,customer,{})),[]);
  assert.equal(db.captures.length,1);
  assert.equal(db.writes,0);
});
await checkAsync("real-list-crosses-deadline-without-persisting-or-waiting",async ()=>{
  const db=database([row]);
  const before=JSON.stringify(row);
  snapshot="2026-10-12T18:00:49.999Z";
  const beforeDeadline=plain(await context.recentCustomerCalls(db.env,customer,{}));
  snapshot="2026-10-12T18:00:50.000Z";
  const atDeadline=plain(await context.recentCustomerCalls(db.env,customer,{}));
  assert.equal(beforeDeadline[0].state,"PENDING");
  assert.equal(atDeadline[0].state,"EXPIRED");
  assert.equal(beforeDeadline[0].persisted_state,"PENDING");
  assert.equal(atDeadline[0].persisted_state,"PENDING");
  assert.equal(JSON.stringify(row),before);
  assert.equal(db.captures.length,2,"one SELECT per explicit invocation");
  assert.equal(db.writes,0);
});
console.log(JSON.stringify({
  schema:"hara.commander-recent-call-expiry-projection-test.v1",
  checked,passed:checked,failed:0,
  workload:"synthetic 50-second deadlines; production projection/list functions with read-only D1 fixture",
  production_database_access:false,production_mutation:false,
},null,2));
