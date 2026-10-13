#!/usr/bin/env python3
"""Real installed Linux MCP: session-scoped authorization, SHA writes and 120-line PTY."""
import argparse,hashlib,json,os,pty,re,select,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--expected-agent-sha256",required=True);p.add_argument("--expected-version",default="0.3.53")
a=p.parse_args();assert re.fullmatch("[0-9a-f]{64}",a.expected_agent_sha256)
Q=Path("/home/commanderqa");D=Q/".local/share/hara-commander";A=D/"hara-commander-agent";C=Q/".config/hara-commander/device.env";S=D/"operator-session.json"
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
assert hashlib.sha256(A.read_bytes()).hexdigest()==a.expected_agent_sha256
assert subprocess.check_output(["python3",str(A),"--version"],text=True).strip()==a.expected_version
values=dict(line.split("=",1) for line in C.read_text().splitlines() if "=" in line)
assert values["HARA_COMMANDER_URL"]=="https://hara-commander-dev-v2.tiago-sartori.workers.dev" and values["HARA_COMMANDER_APPROVAL_MODE"]=="ASK_EVERY_ACTION"
checks=[];receipts=[];owner=None;client=None
def run(args):
 p=subprocess.run(["python3",str(A),*args],capture_output=True,text=True,timeout=30)
 assert p.returncode==0,"QA_CLI_FAILED"
def note(name,ok,extra=None):
 if not ok:raise AssertionError(name)
 checks.append({"check":name,"state":"PASS",**(extra or {})})
class Client:
 def __init__(self):
  self.p=subprocess.Popen(["python3",str(A),"mcp"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
  self.next_id=0;self.call("initialize",{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"HARA-LinuxQA-53","version":"1"}})
 def call(self,method,params):
  self.next_id+=1;ident=self.next_id
  self.p.stdin.write(json.dumps({"jsonrpc":"2.0","id":ident,"method":method,"params":params},ensure_ascii=False)+"\n");self.p.stdin.flush()
  readable,_,_=select.select([self.p.stdout],[],[],45)
  if not readable:raise RuntimeError("LOCAL_MCP_RESPONSE_TIMEOUT")
  response=json.loads(self.p.stdout.readline());assert response.get("id")==ident
  assert "error" not in response,"MCP_PROTOCOL_ERROR"
  return response["result"]
 def tool(self,name,args=None):
  response=self.call("tools/call",{"name":name,"arguments":args or {}})
  result=response.get("structuredContent")
  if not isinstance(result,dict):raise RuntimeError("MCP_STRUCTURED_RESULT_MISSING")
  sha=result.get("bridge_receipt_sha256")
  if isinstance(sha,str) and re.fullmatch("[0-9a-f]{64}",sha):receipts.append(sha)
  return result
 def close(self):
  if self.p.stdin:self.p.stdin.close()
  try:self.p.wait(timeout=5)
  except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=5)
def data(result):
 note("MCP-operation-receipt-PASS",result.get("state")=="PASS")
 return json.loads(result["result"]["stdout"])
result={"schema":"hara.commander-linux-clean-native-mcp.v1","backend":"installed_product_MCP_LOCAL_STDIO_with_real_DEV_enrollment","systemctl_backend":"real","human_ASK_response_generated":False,"authorization":"explicit_QA_SESSION_TRUSTED_until_CLI_close","managed_max_lines_contract":"fixed_200; configurable max_lines is bounded-run only","checks":checks,"receipt_sha256":receipts}
try:
 run(["approval-mode","session"])
 pid,fd=pty.fork()
 if pid==0:os.execvpe("python3",["python3",str(A),"start"],os.environ.copy())
 owner=(pid,fd);until=time.monotonic()+15
 while time.monotonic()<until and not S.is_file():time.sleep(.1)
 session=json.loads(S.read_text())
 note("actual-CLI-bounded-QA-session",session.get("owner_pid")==pid and session.get("approval_mode")=="SESSION_TRUSTED")
 client=Client()
 folder=Q/"commander-qa/mcp-53";data(client.tool("create_directory",{"path":str(folder),"parents":True}))
 path=folder/"unicode.txt";first="Olá ação H.A.R.A. São Paulo — v53\n";second="Café açaí: execução confirmada.\n"
 sha1=hashlib.sha256(first.encode()).hexdigest();sha2=hashlib.sha256(second.encode()).hexdigest()
 write=client.tool("write_file",{"path":str(path),"content":first,"mode":"rewrite"})
 written=data(write)
 note("session-authorization-source",write["result"].get("authorization_source")=="LOCAL_OPERATOR_SESSION")
 read=data(client.tool("read_file",{"path":str(path),"offset":0,"length":30}))
 note("Unicode-write-read-exact",read.get("text")==first.rstrip("\n") and hashlib.sha256(path.read_bytes()).hexdigest()==sha1)
 data(client.tool("write_file",{"path":str(path),"content":second,"mode":"rewrite","expected_sha256":sha1}))
 stale=client.tool("write_file",{"path":str(path),"content":"MUST_NOT_REPLACE\n","mode":"rewrite","expected_sha256":sha1})
 note("stale-SHA-conflict-preserves-file",stale.get("state")=="CONFLICT" and hashlib.sha256(path.read_bytes()).hexdigest()==sha2)
 bounded_code="import sys;[print('QA-BOUND-%03d'%i,flush=True) for i in range(120)]"
 bounded=data(client.tool("start_process",{"command":"python3 -u -c "+shlex.quote(bounded_code),"cwd":str(folder),"interactive":False,"timeout_ms":3000,"max_lines":20}))
 note("bounded-run-line-cap-respected",len(bounded.get("text","").splitlines())==20 and bounded.get("total_lines")==120 and bounded.get("output_truncated") is True and bounded.get("exit_code")==0 and re.findall(r"QA-BOUND-([0-9]{3})",bounded.get("text",""))==[f"{i:03}" for i in range(20)])
 input_="Café HARA açaí";input_sha=hashlib.sha256(input_.encode()).hexdigest()
 code="import sys,hashlib;[print('QA-LINE-%03d'%i,flush=True) for i in range(120)];print('QA_READY',flush=True);v=sys.stdin.readline().rstrip('\\n');print('INPUT_SHA='+hashlib.sha256(v.encode()).hexdigest(),flush=True)"
 started=data(client.tool("start_process",{"command":"python3 -u -c "+shlex.quote(code),"cwd":str(folder),"interactive":True,"timeout_ms":1000}))
 sid=started["session_id"];text=started.get("text","")
 note("managed-default-output-line-cap-respected",len(text.splitlines())<=200)
 for _ in range(10):
  if "QA_READY" in text:break
  d=data(client.tool("read_process_output",{"session_id":sid,"length":200,"timeout_ms":1000}));text+=d.get("text","")
 echo=data(client.tool("interact_with_process",{"session_id":sid,"input":input_+"\n","timeout_ms":1000}));text+=echo.get("text","")
 exited=False
 for _ in range(15):
  d=data(client.tool("read_process_output",{"session_id":sid,"length":200,"timeout_ms":1000}));text+=d.get("text","")
  if d.get("state")=="EXITED":
   exited=d.get("exit_code")==0;break
 lines=re.findall(r"QA-LINE-([0-9]{3})",text)
 note("interactive-PTY-120-lines-complete",lines==[f"{i:03}" for i in range(120)] and exited,{"line_count":len(lines)})
 note("interactive-UTF8-input-roundtrip","INPUT_SHA="+input_sha in text)
 note("all-successful-MCP-operations-have-receipts",len(receipts)>=8 and len(set(receipts))==len(receipts))
 run(["stop"])
 note("close-session-revokes-scope",not S.exists())
 run(["approval-mode","ask"])
 result.update(state="PASS_NATIVE_LINUX_MCP_53",agent_version=a.expected_version)
except Exception as error:
 result.update(state="FAIL_NATIVE_LINUX_MCP_53",error_type=type(error).__name__,error_code=str(error) if isinstance(error,AssertionError) else "NATIVE_MCP_PHASE_FAILED")
finally:
 if client:
  try:client.close()
  except Exception:pass
 if owner:
  try:run(["stop"]);os.close(owner[1])
  except Exception:pass
 try:run(["approval-mode","ask"])
 except Exception:pass
print(json.dumps(result))
raise SystemExit(0 if result["state"].startswith("PASS") else 1)