// Dedicated #163 DEV SLO phase; reuses the existing delivery campaign and caps.
// The idle interval sends no campaign requests; all 121 seconds are real.
import fs from 'node:fs';import {execFileSync} from 'node:child_process';import {createHash} from 'node:crypto';
const p='/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_BETA_FECHADO_VM_R1_20261023/r163-queue-dev-20261024-44ba72c',s=JSON.parse(fs.readFileSync(p+'/private-state.json')),base='https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev',cfg=p+'/queue.config.jsonc';
const node='/home/sartorius/.nvm/versions/node/v24.15.0/bin/node',wr='/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules/wrangler/bin/wrangler.js',env={...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG:'log'},hash=x=>createHash('sha256').update(x).digest('hex');
async function ctl(k,b){const r=await fetch(base+'/__qa/'+k,{method:b===undefined?'GET':'POST',headers:{authorization:'Bearer '+s.control_token,'content-type':'application/json'},body:b===undefined?undefined:JSON.stringify(b),signal:AbortSignal.timeout(10000)});const o=await r.json();if(r.status!==200)throw Error(k+'_'+JSON.stringify(o));return o;}
function cli(a){return execFileSync(node,[wr,...a],{env,timeout:20000,encoding:'utf8'});}
function query(q){return JSON.parse(cli(['d1','execute','hara-commander-r163-canary-dev-20261024','--remote','--config',cfg,'--json','--command',q]))[0];}
const configuration=JSON.parse(fs.readFileSync(cfg));
if(configuration.name!=='hara-commander-r163-canary-20261024'||configuration.vars.ENVIRONMENT!=='DEV'||
 configuration.vars.R163_QA_AUTOMATIC_CRON!=='false'||configuration.routes!==undefined||
 configuration.d1_databases?.[0]?.database_id!=='e769835e-0748-4f41-b868-c7c76b627fe9'||
 configuration.queues?.consumers?.[0]?.max_concurrency!==4||s.tenant!=='HARA-R163-QUEUE-DEV-20261024')throw Error('HOLD_QA_SCOPE');
for(const file of [p,p+'/private-state.json'])if(fs.lstatSync(file).isSymbolicLink()||(fs.statSync(file).mode&0o077))throw Error('HOLD_PRIVATE_CUSTODY');
const queues=['hara-commander-r163-recovery-dev-20261024','hara-commander-r163-recovery-dlq-dev-20261024'];
let active=false;const out=JSON.parse(fs.readFileSync(p+'/campaign-evidence-attempt4.json'));
try{
 const initial=await ctl('status');if(initial.budget.state!=='PAUSED'||initial.budget.reserved_read||initial.budget.reserved_write)throw Error('HOLD_IDLE_PREIMAGE');
 if(1800000-initial.budget.active_ms_effective<75000)throw Error('HOLD_INSUFFICIENT_ACTIVE_TIME');
 for(const q of queues)cli(['queues','pause-delivery',q]);
 await ctl('start',{});active=true;
 let cursor=0;await Promise.all(Array.from({length:4},async()=>{while(cursor<50){const d=s.devices[cursor++],r=await fetch(base+'/api/device/heartbeat',{method:'POST',headers:{authorization:'Bearer '+d.token,'content-type':'application/json'},body:JSON.stringify({device_id:d.id,agent_version:'0.3.54',architecture:'x86_64',approval_mode:'PERSISTENT_TRUSTED'}),signal:AbortSignal.timeout(8000)});if(r.status!==200)throw Error('HEARTBEAT_'+r.status);await r.body?.cancel();}}));
 const anchors=query("SELECT device_id,last_seen_at_utc FROM commander_devices WHERE tenant_id='HARA-R163-QUEUE-DEV-20261024'");if(anchors.results.length!==50)throw Error('ANCHOR_COUNT');await ctl('debit',{reads:anchors.meta.rows_read,writes:0,events:0});
 await ctl('stop',{});active=false;const idle=await ctl('status');if(idle.budget.state!=='PAUSED'||idle.budget.reserved_read||idle.budget.reserved_write)throw Error('HOLD_IDLE_NOT_SETTLED');
 const oldest=Math.min(...anchors.results.map(r=>Date.parse(r.last_seen_at_utc))),last=Math.max(...anchors.results.map(r=>Date.parse(r.last_seen_at_utc)));
 out.idle_wait={queues_paused:true,automatic_cron:false,budget_state:'PAUSED',native_budget:idle.budget,real_heartbeat_anchors:anchors.results,wait_until_ms:last+121000,no_campaign_requests_during_wait:true};
 fs.writeFileSync(p+'/slo-idle-preimage.json',JSON.stringify(out.idle_wait,null,2)+'\n',{flag:'wx',mode:0o600});console.log(JSON.stringify({state:'REAL_HEARTBEAT_IDLE_WAIT',oldest,last,active_ms_effective:idle.budget.active_ms_effective,remaining_active_ms:1800000-idle.budget.active_ms_effective}));
 while(Date.now()<last+121000)await new Promise(r=>setTimeout(r,Math.min(5000,last+121000-Date.now())));
 await ctl('start',{});active=true;
 for(const q of queues.toReversed())cli(['queues','resume-delivery',q]);
 const before=(await ctl('status')).jobs.map(j=>j.message_id),started=Date.now(),plan=await ctl('produce',{});if(plan.scan_devices!==50)throw Error('SCAN_SCOPE_'+JSON.stringify(plan));let observed;
 while(Date.now()<oldest+178000){const o=await ctl('status'),jobs=o.jobs.filter(j=>j.kind==='SCAN'&&!before.includes(j.message_id));if(jobs.length===plan.jobs&&jobs.every(j=>j.outcome==='ACKNOWLEDGED')){observed=o;break;}await new Promise(r=>setTimeout(r,500));}
 if(!observed)throw Error('HOLD_NATIVE_SCAN_NOT_COMPLETED_WITHIN_SLO');
 const quote=x=>"'"+x.replaceAll("'","''")+"'";
 const result=query("SELECT device_id,heartbeat_anchor_at_utc,persisted_at_utc,event_id FROM commander_device_recovery_events WHERE tenant_id='HARA-R163-QUEUE-DEV-20261024' AND origin='SERVER' AND event_state='DEGRADED' AND heartbeat_anchor_at_utc IN ("+anchors.results.map(r=>quote(r.last_seen_at_utc)).join(',')+")");await ctl('debit',{reads:result.meta.rows_read,writes:0,events:0});if(result.results.length!==50)throw Error('HOLD_DETECTION_COUNT');
 const times=result.results.map(r=>(Date.parse(r.persisted_at_utc)-Date.parse(r.heartbeat_anchor_at_utc))/1000).sort((a,b)=>a-b);
 out.detection={devices:50,concurrency:4,actual_heartbeat_anchors:anchors.results,rows:result.results,intervals_scaled:false,max_persisted_delay_s:times.at(-1),p95_s:times[Math.ceil(times.length*.95)-1],p99_s:times[Math.ceil(times.length*.99)-1],readback_upper_delay_s:(observed.server_ms-oldest)/1000,processing_upper_ms:observed.server_ms-started};
 const poison={schema:'hara.commander.recovery-work.v1',kind:'SCAN',device_ids:['R163-QA-DLQ-FAULT']},fault=observed.jobs.find(j=>j.detail?.includes('R163-QA-DLQ-FAULT')&&j.attempts===3),receipt=observed.dlq.find(r=>r.body_sha256===hash(JSON.stringify(poison)));
 if(!fault||!receipt)throw Error('HOLD_NATIVE_DLQ_RECEIPT');out.dlq={state:'PASS_NATIVE_DLQ_READBACK',fault_attempts:3,source_message_id:fault.message_id,receipt};
 if(out.detection.readback_upper_delay_s>180||out.detection.processing_upper_ms>=45000)throw Error('HOLD_MEASURED_SLO');
 out.prior_controller_error=out.error;delete out.error;out.state='PASS_HOSTED_QUEUE_DLQ_AND_SLO';out.measurement_controller='native-idle-window-capture';out.slo_source_commit=s.source_commit;out.budget=(await ctl('status')).budget;
 fs.writeFileSync(p+'/campaign-evidence-pass.json',JSON.stringify(out,null,2)+'\n',{flag:'wx',mode:0o600});console.log(JSON.stringify({state:out.state,detection_s:out.detection.readback_upper_delay_s,processing_ms:out.detection.processing_upper_ms,evidence_sha256:hash(fs.readFileSync(p+'/campaign-evidence-pass.json'))}));
}catch(error){fs.writeFileSync(p+'/slo-idle-failure.json',JSON.stringify({state:'FAIL_STOPPED',message:error.message},null,2)+'\n',{mode:0o600});console.error(JSON.stringify({state:'FAIL_STOPPED',message:error.message}));process.exitCode=1;}
finally{for(const q of queues)try{cli(['queues','pause-delivery',q]);}catch{}if(active)try{await ctl('stop',{});}catch{}const final=await ctl('status');fs.writeFileSync(p+'/final-budget.json',JSON.stringify(final,null,2)+'\n',{mode:0o600});}
