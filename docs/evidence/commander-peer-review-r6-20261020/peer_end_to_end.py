#!/usr/bin/env python3
"""Offline Agent -> exact Worker functions -> public MCP projection.
No listening sockets/provider traffic. Synthetic clock and in-memory D1.
Only QA files in an automatically removed HOME are mutated.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, importlib.util, json, os, select, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get('HARA_PEER_SOURCE',str(ROOT/'source')))
NODE=os.environ.get('HARA_PEER_NODE','/home/sartorius/.nvm/versions/node/v24.15.0/bin/node')
findings=[];network=[];actions=[];fixtures=[]
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj);return obj
with tempfile.TemporaryDirectory(prefix='commander-r6-offline-') as tmp:
 home=Path(tmp)
 for k,part in [('HOME','home'),('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config')]:
  os.environ[k]=str(home/part);(home/part).mkdir()
 node=subprocess.Popen([NODE,'--disable-warning=ExperimentalWarning',str(ROOT/'peer_worker_bridge.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,cwd=ROOT)
 def rpc(message):
  node.stdin.write(json.dumps(message,ensure_ascii=False)+'\n');node.stdin.flush()
  ready,_,_=select.select([node.stdout],[],[],4)
  if not ready:raise RuntimeError('WORKER_FIXTURE_RESPONSE_TIMEOUT')
  line=node.stdout.readline()
  if not line:raise RuntimeError('WORKER_FIXTURE_EXITED: '+node.stderr.read()[-2500:])
  response=json.loads(line)
  if 'harness_error' in response:raise RuntimeError(response['harness_error'])
  return response
 try:
  agent=load(SOURCE/'apps/commander/public/agent/linux.py','peer_r6_agent')
  loop=load(SOURCE/'apps/commander/experimental/event_v2_agent_loop.py','peer_r6_loop')
  assert str(agent.DATA_DIR).startswith(tmp),'XDG_ISOLATION'
  def no_network(*args,**kwargs):network.append('blocked');raise RuntimeError('PEER_REAL_NETWORK_FORBIDDEN')
  agent.urllib.request.urlopen=no_network
  agent.effective_approval_mode=lambda config=None:'PERSISTENT_TRUSTED'
  agent.request_local_approval=lambda call:{'state':'APPROVED','mode':'QA_ONLY','source':'OFFLINE_FIXTURE'}
  agent.append_console_event=lambda *args,**kw:None
  cfg={'HARA_DEVICE_ID':'R6-DEVICE','HARA_DEVICE_ARCH':'x86_64','HARA_COMMANDER_URL':'https://peer.invalid','HARA_DEVICE_TOKEN':'QA_NOT_A_CREDENTIAL'}
  original=agent.execute_tool
  executed=[]
  def execute(config,call):executed.append(call['call_id']);return original(config,call)
  agent.execute_tool=execute
  def body(call,state,result,error_code=None):
   d={'call_id':call['call_id'],'state':state,'result':result}
   if error_code:d['error_code']=error_code
   return d
  def deliver(config,call,state,result,error_code=None):
   reply=rpc({'action':'complete','body':body(call,state,result,error_code)})
   actions.append({'call_id':call['call_id'],'server_ok':reply['ok'],'error':reply.get('error'),'server_state':(reply.get('call') or {}).get('state')})
   if not reply['ok']:raise RuntimeError(reply['error'])
   return reply['response']
  # Positive control: server accepts but ACK is lost; replay after deadline
  # must retain success, not execute mutation again.
  accepted={'call_id':'R6-ACCEPTED-ACK-LOST','request_id':'R6-ACCEPTED-ACK-LOST','tool_id':'hara.files.write',
            'payload':{'path':str(home/'accepted.txt'),'content':'ONE_QA_MUTATION','mode':'rewrite'}}
  assert rpc({'action':'seed','call_id':accepted['call_id']})['ok']
  first=True
  def accept_then_drop(*args,**kw):
   global first
   reply=deliver(*args,**kw)
   if first:first=False;raise ConnectionResetError('QA_ACK_LOST_AFTER_ACCEPTANCE')
   return reply
  agent.complete=accept_then_drop;agent.execute_call(cfg,dict(accepted));assert agent.completion_outbox_pending()==1
  rpc({'action':'advance','seconds':51});agent.complete=deliver
  delivered=agent.flush_completion_outbox(cfg)
  assert delivered==1 and agent.completion_outbox_pending()==0
  assert executed.count(accepted['call_id'])==1
  positive={'server_accepted_before_disconnect':True,'retry_after_deadline_delivered':delivered,'execution_count':1,'pending_after_retry':0}
  # Negative integration: initial send fails BEFORE server acceptance.
  late={'call_id':'R6-LATE-NOT-ACCEPTED','request_id':'R6-LATE-NOT-ACCEPTED','tool_id':'hara.files.write',
        'payload':{'path':str(home/'late.txt'),'content':'ONE_QA_MUTATION_LATE','mode':'rewrite'}}
  rpc({'action':'seed','call_id':late['call_id']})
  agent.complete=lambda *args,**kwargs:(_ for _ in ()).throw(ConnectionResetError('QA_SEND_LOST_BEFORE_ACCEPTANCE'))
  agent.execute_call(cfg,dict(late));assert (home/'late.txt').read_text()=='ONE_QA_MUTATION_LATE'
  assert agent.completion_outbox_pending()==1
  rpc({'action':'advance','seconds':51});agent.complete=deliver
  attempts=[agent.flush_completion_outbox(cfg) for _ in range(3)]
  next_calls=[]
  def next_call(*args,**kwargs):next_calls.append(1);return None
  agent.post_json=next_call
  guard_error=None
  try:loop.drain_durable_calls(agent,cfg)
  except RuntimeError as e:guard_error=str(e)
  row=agent._completion_outbox_fetch(late['call_id'])
  late_actions=[x for x in actions if x['call_id']==late['call_id']]
  findings.append({'id':'R6-OUTBOX-LATE-01','reproduced':row['status']=='READY' and guard_error=='EVENT_V2_RESULT_DELIVERY_PENDING' and not next_calls,
   'local_mutation_done':True,'local_execution_count':executed.count(late['call_id']),
   'server_replies':late_actions,'replay_delivered_counts':attempts,
   'pending_count':agent.completion_outbox_pending(),'local_outbox_state':row['status'],
   'new_claim_attempts':len(next_calls),'guard_error':guard_error,
   'positive_control':positive,
   'scope':'real Agent outbox + exact completeDeviceCall/D1 SQL + real Event V2 drain guard; synthetic clock, mocked authenticated device and stdin subprocess bridge; no cloud outage induced'})
  # True read results bounded by the Agent, then projected and wrapped by
  # exact public Worker/MCP functions rather than just checking payload size.
  paths=[]
  for i in range(10):
   p=home/f'bulk-{i}.txt';p.write_text(''.join(f'ROW-{n:03d}-'+'x'*590+'\n' for n in range(100)));paths.append(str(p))
  projections=[]
  for count in (1,4,10):
   result=original(cfg,{'call_id':f'R6-BULK-{count}','request_id':f'R6-BULK-{count}','tool_id':'hara.files.read_many','payload':{'paths':paths[:count],'offset':0,'length':100}})
   fixture=home/f'projection-{count}.json';fixture.write_text(json.dumps(result,separators=(',',':'),ensure_ascii=False))
   outcome=rpc({'action':'project','fixture':str(fixture),'tool_id':'hara.files.read_many'})
   projections.append({'files':count,**outcome})
  assert projections[0]['before_json_valid'] and projections[0]['after_json_valid'],'POSITIVE_PROJECTION_CONTROL'
  assert all(x['agent_result_bytes']<256*1024 for x in projections),'AGENT_ENVELOPE_EXPECTED_IN_BUDGET'
  findings.append({'id':'R6-PROJECTION-02','reproduced':any(x['before_json_valid'] and not x['after_json_valid'] for x in projections),
    'cases':projections,'scope':'actual Agent file reads and exact Worker projectCustomerToolResult/trimPublicText/publicToolResult; SDK HTTP not invoked, outer MCP JSON remains valid',
    'recommendation':'Do not slice structured JSON stdout as arbitrary text. Coordinate envelope limits through final projection and retain valid per-file continuation; test client-visible structured result, not only Agent byte size.'})
 finally:
  if node.stdin:
   try:node.stdin.close()
   except BrokenPipeError:pass
  try:node.wait(timeout=2)
  except subprocess.TimeoutExpired:node.kill();node.wait(timeout=2)
  if node.returncode not in (0,None):
   print('BRIDGE_STDERR',node.stderr.read()[-1800:],file=sys.stderr)
report={'schema':'hara.commander-peer-e2e-r6.v1','observed_utc':datetime.now(timezone.utc).isoformat(),
 'source_head':None if os.environ.get('HARA_PEER_SOURCE') else '97a35d9bde706db66e4c3a5645cefce083dc08c6',
 'source_sha256':{str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'apps/commander/public/agent/linux.py',SOURCE/'apps/commander/src/worker.js',SOURCE/'apps/commander/src/customer-mcp-simple.mjs',SOURCE/'apps/commander/experimental/event_v2_agent_loop.py']},'findings':findings,'network_attempts':len(network),
 'production_mutation':False,'fixtures_cleaned':True}
(ROOT/'r6-results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,indent=2,ensure_ascii=False))
sys.exit(2 if any(x['reproduced'] for x in findings) else 0)
