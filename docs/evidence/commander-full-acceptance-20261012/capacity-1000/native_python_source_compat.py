from pathlib import Path
import subprocess,json,hashlib,base64
from datetime import datetime,timezone
r=Path("/tmp_hara/commander-win50-utf8-20261012")
files=("public/agent/linux.py","experimental/event_v2_websocket.py","experimental/event_v2_agent_loop.py",
 "experimental/event_v2_customer_agent.py","experimental/event_v2_telemetry.py")
sources={rel:base64.b64encode((r/"apps/commander"/rel).read_bytes()).decode() for rel in files}
hashes={rel:hashlib.sha256((r/"apps/commander"/rel).read_bytes()).hexdigest() for rel in files}
template="""from pathlib import Path
import base64,hashlib,json,os,sys,tempfile,importlib.util,platform,ast
sources=PAYLOAD
expected=HASHES
base=Path.home()/"hara-capacity1000-compat"
base.mkdir(mode=0o700,exist_ok=False)
os.environ["XDG_CONFIG_HOME"]=str(base/"xdg-config")
os.environ["XDG_DATA_HOME"]=str(base/"xdg-data")
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
checks=[]
for rel,encoded in sources.items():
 raw=base64.b64decode(encoded,validate=True)
 assert hashlib.sha256(raw).hexdigest()==expected[rel]
 p=base/"source/apps/commander"/rel;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"wb") as f:f.write(raw)
 ast.parse(raw)
 checks.append({"source":rel,"sha256":expected[rel],"parsed":True})
sys.path.insert(0,str(base/"source/apps/commander/experimental"))
for item in checks:
 p=base/"source/apps/commander"/item["source"]
 name="own_capacity_compat_"+p.stem
 spec=importlib.util.spec_from_file_location(name,p)
 module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
 item["imported"]=True
print(json.dumps({"schema":"hara.commander-capacity-native-python-compat.v1","state":"PASS_PARSE_IMPORT_ONLY",
 "hostname":os.uname().nodename,"uid":os.getuid(),"home":str(Path.home()),"python":platform.python_version(),
 "scope":"ISOLATED_OWN_SOURCE_IMPORT_NO_AGENT_START","source_checks":checks,
 "agent_processes_launched":0,"cloud_requests":0,"installed_Agent_modified":False,
 "private_sandbox":str(base)},sort_keys=True))
"""
code=template.replace("PAYLOAD",repr(sources)).replace("HASHES",repr(hashes))
reports=[]
for alias in ("sentinela-b","ninja-blue"):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=8",alias,"python3","-B","-"],input=code,
    text=True,capture_output=True,timeout=45)
 if p.returncode:
  report={"alias":alias,"state":"FAIL_NATIVE_COMPAT_IMPORT","exit_code":p.returncode,
          "stderr_exception_classes":[l.rsplit(":",1)[0].split()[-1] for l in p.stderr.splitlines() if l.startswith(("ImportError:","ModuleNotFoundError:","SyntaxError:","AttributeError:","RuntimeError:"))],
          "raw_stderr_retained":False}
 else:
  report=json.loads(p.stdout);report["alias"]=alias
 reports.append(report)
out={"schema":"hara.commander-capacity-physical-python-compat-series.v1","at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
     "state":"PASS" if all(x["state"]=="PASS_PARSE_IMPORT_ONLY" for x in reports) else "FAIL",
     "reports":reports,"current_experimental_manager_controller_tested":False,
     "source_freeze_scope":"SIGNED54_LINUX_AGENT_PLUS_FOUR_EVENT_V2_MODULES","network_load_started":False}
path=r/"docs/evidence/commander-full-acceptance-20261012/capacity-1000/native-python-310-314-source-compat.json"
path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,sort_keys=True))
