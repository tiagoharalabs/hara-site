// HARA Commander #163: isolated hosted DEV notification recipient, not commercial delivery.
// Persist-only QA sink with separate authenticated readback of real HTTPS receipt.
const states=new Set(["STALLED","RECOVERING","RECOVERED","DEGRADED"]);
const allowed=new Set(["schema","event_id","client_incident_key","transition_seq","worker","state","observed_at_utc","detector"]);
async function digest(value){
  const b=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));
  return Array.from(new Uint8Array(b),v=>v.toString(16).padStart(2,"0")).join("");
}
function json(value,status=200){
  return Response.json(value,{status,headers:{"cache-control":"no-store","x-content-type-options":"nosniff"}});
}
async function auth(request,hash){
  const h=request.headers.get("authorization")||"";
  if(!h.startsWith("Bearer ")||h.length>256)return false;
  const got=await digest(h.slice(7));
  if(!hash || got.length!==hash.length)return false;
  let x=0;for(let i=0;i<got.length;i++)x|=got.charCodeAt(i)^hash.charCodeAt(i);
  return x===0;
}
export default {
  async fetch(request,env){
    const u=new URL(request.url);
    if(u.pathname==="/health"&&request.method==="GET")return json({ok:true,mode:"HARA_REVIEW_163_ONLY"});
    if(u.pathname==="/notify"&&request.method==="POST"){
      if(!await auth(request,env.QA_SINK_WRITE_SHA256))return json({ok:false,code:"AUTH_REQUIRED"},401);
      const size=Number(request.headers.get("content-length")||"0");
      if(!Number.isFinite(size)||size>2048)return json({ok:false,code:"OVERSIZE"},413);
      const raw=await request.text();
      if(new TextEncoder().encode(raw).length>2048)return json({ok:false,code:"OVERSIZE"},413);
      let event;
      try{event=JSON.parse(raw);}catch{return json({ok:false,code:"INVALID_JSON"},400);}
      if(!event||typeof event!=="object"||Array.isArray(event)
        ||Object.keys(event).length!==allowed.size
        ||Object.keys(event).some(k=>!allowed.has(k))
        ||event.schema!=="hara.commander.recovery-alert.proposal.v1"
        ||!/^[0-9a-f]{32}$/.test(event.event_id||"")
        ||!/^[0-9a-f]{32}$/.test(event.client_incident_key||"")
        ||!Number.isSafeInteger(event.transition_seq)||event.transition_seq<1
        ||!["heartbeat","executor"].includes(event.worker)
        ||!states.has(event.state)
        ||!["LINUX_PROCESS_GUARDIAN","WINDOWS_JOB_GUARDIAN"].includes(event.detector)
        ||!Number.isFinite(Date.parse(event.observed_at_utc||""))) {
        return json({ok:false,code:"INVALID_EVENT"},400);
      }
      const fingerprint=await digest(JSON.stringify(
        Object.fromEntries(Object.entries(event).sort(([a],[b])=>a.localeCompare(b)))));
      const reference=await digest(event.event_id+"|"+fingerprint+"|qa-recipient-163");
      const now=new Date().toISOString();
      await env.QA_SINK_DB.prepare(
        "INSERT INTO qa_delivery_receipts(event_id,fingerprint,receipt_ref,stored_at_utc) "+
        "VALUES(?,?,?,?) ON CONFLICT(event_id) DO NOTHING"
      ).bind(event.event_id,fingerprint,reference,now).run();
      const row=await env.QA_SINK_DB.prepare(
        "SELECT event_id,fingerprint,receipt_ref,stored_at_utc "+
        "FROM qa_delivery_receipts WHERE event_id=?"
      ).bind(event.event_id).first();
      if(!row || row.fingerprint!==fingerprint)return json({ok:false,code:"IDEMPOTENCY_CONFLICT"},409);
      return json({schema:"hara.commander.review163.recipient-accepted.v1",
        state:"QA_RECIPIENT_PERSISTED",event_id:row.event_id,
        receipt_ref:row.receipt_ref,stored_at_utc:row.stored_at_utc,
        customer_notification_confirmed:false},202);
    }
    if(u.pathname.startsWith("/receipt/")&&request.method==="GET"){
      if(!await auth(request,env.QA_SINK_READ_SHA256))return json({ok:false,code:"AUTH_REQUIRED"},401);
      const id=u.pathname.slice("/receipt/".length);
      if(!/^[0-9a-f]{32}$/.test(id))return json({ok:false,code:"INVALID_EVENT"},400);
      const row=await env.QA_SINK_DB.prepare(
        "SELECT event_id,fingerprint,receipt_ref,stored_at_utc "+
        "FROM qa_delivery_receipts WHERE event_id=?"
      ).bind(id).first();
      return row?json({schema:"hara.commander.review163.recipient-readback.v1",
        state:"QA_RECIPIENT_PERSISTED",...row}):json({ok:false,code:"NOT_FOUND"},404);
    }
    return json({ok:false,code:"NOT_FOUND"},404);
  }
};
