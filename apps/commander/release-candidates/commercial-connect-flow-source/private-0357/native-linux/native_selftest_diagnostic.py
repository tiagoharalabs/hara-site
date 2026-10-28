"""Pinned, create-once Ubuntu diagnostic copy; never install the modified Agent."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

BASE = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028')
ROOT = BASE / 'connect-flow-20261028/private-0357/native-linux'
ORIGINAL = BASE / 'windows_install_native_driver_r6.py'
assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == 'e1d3eea70edb079e6cc8492edd3544db254d262e98eab2211bb1abdadf1f1e04'
m = runpy.run_path(str(ORIGINAL))
import libvirt
connection = libvirt.open('qemu:///system')
domain = connection.lookupByUUIDString('d7a27a4a-41c3-4c14-a84e-187443566a3c')
assert domain.name() == 'hara-review-linux' and domain.isActive()
m['call'].__globals__['DOM'] = domain
AGENT = ROOT.parent / 'signed/agent/linux.py'
AGENT_SHA = '79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13'
STAGE = '/run/hara-qa-private0357-selftest-20261028'
HELPER = '/home/commanderqa/.local/share/hara-commander-connect-qa'
WORK = HELPER + '/selftest-0357-diagnostic'
DIAG_FILE = WORK + '/linux-agent-diagnostic.py'
RESULT = WORK + '/result.json'
MARKER = 'HARA_QA_EXIT7_OBSERVATION='

raw = AGENT.read_bytes()
assert hashlib.sha256(raw).hexdigest() == AGENT_SHA
source = raw.decode('utf-8')
expected = ast.parse("assert failed_data['state'] == 'EXITED' and failed_data['exit_code'] == 7 and failed_proc['result']['process_exit_code'] == 7").body[0]
tree = ast.parse(source)
matches = [n for n in ast.walk(tree) if isinstance(n, ast.Assert) and ast.dump(n, include_attributes=False) == ast.dump(expected, include_attributes=False)]
assert len(matches) == 1 and matches[0].lineno == 3888
node = matches[0]
lines = source.splitlines(keepends=True)
indent = lines[node.lineno - 1][:node.col_offset]
# Only fixed enum/numeric values can enter this marker. Existing assertion stays.
marker_line = indent + 'print(' + repr(MARKER) + ' + json.dumps({"state": failed_data.get("state") if failed_data.get("state") in ("EXITED", "RUNNING", "TIMED_OUT", "STARTING", "FAILED") else "UNEXPECTED_STATE", "exit_code": failed_data.get("exit_code") if type(failed_data.get("exit_code")) in (int, type(None)) else "UNEXPECTED_TYPE", "process_exit_code": failed_proc["result"].get("process_exit_code") if type(failed_proc["result"].get("process_exit_code")) in (int, type(None)) else "UNEXPECTED_TYPE"}, sort_keys=True), flush=True)\n'
lines.insert(node.lineno - 1, marker_line)
diag = ''.join(lines).encode('utf-8')
diag_tree = ast.parse(diag)
assert sum(isinstance(n, ast.Assert) and ast.dump(n, include_attributes=False) == ast.dump(expected, include_attributes=False) for n in ast.walk(diag_tree)) == 1
# Removing the sole marker reproduces every original byte.
assert diag.replace(marker_line.encode('utf-8'), b'', 1) == raw
diag_sha = hashlib.sha256(diag).hexdigest()


def guest(label, code, user=False):
    label = 'selftest-diag-' + label
    launch = ROOT / (label + '-launch.json')
    complete = ROOT / (label + '-complete.json')
    decoded = ROOT / (label + '-decoded.json')
    if not launch.exists():
        args = ['-I', '-S', '-c', code]
        path = '/usr/bin/python3'
        if user:
            path = '/usr/sbin/runuser'
            args = ['-u', 'commanderqa', '--', '/usr/bin/python3', *args]
        m['save'](launch, m['call']('guest-exec', {'path': path, 'arg': args, 'capture-output': True}))
    pid = json.loads(launch.read_text())['pid']
    for _ in range(6):
        value = json.loads(complete.read_text()) if complete.exists() else m['call']('guest-exec-status', {'pid': pid})
        if value.get('exited'):
            if not complete.exists():
                m['save'](complete, value)
            out = base64.b64decode(value.get('out-data', '')).decode()
            err = base64.b64decode(value.get('err-data', '')).decode()
            if value.get('exitcode') != 0:
                raise RuntimeError('QGA_DIAG_PHASE_FAILED_' + label + '_exit_' + str(value.get('exitcode')) + '_stderr_bytes_' + str(len(err.encode())))
            result = json.loads(out)
            if not decoded.exists():
                m['save'](decoded, result)
            return result
        time.sleep(.15)
    print(json.dumps({'state': 'RUNNING', 'label': label, 'pid': pid}))
    raise SystemExit(0)


action = sys.argv[1]
assert action in ('stage', 'run', 'result')
if action == 'stage':
    guest('stage-folder', f"""
import json,os,stat
from pathlib import Path
assert os.getuid()==0
p=Path({STAGE!r});assert not os.path.lexists(p)
s=p.parent.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
p.mkdir(mode=0o700)
print(json.dumps({{'state':'DIAGNOSTIC_STAGE_CREATED'}}))
""")
    transferred = ROOT / 'selftest-diag-transferred.json'
    if not transferred.exists():
        handle = m['call']('guest-file-open', {'path': STAGE + '/diagnostic.py', 'mode': 'w'})
        try:
            for offset in range(0, len(diag), 16000):
                part = diag[offset:offset + 16000]
                result = m['call']('guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(part).decode()})
                assert result['count'] == len(part)
            m['call']('guest-file-flush', {'handle': handle})
        finally:
            m['call']('guest-file-close', {'handle': handle})
        m['save'](transferred, {'original_agent_sha256': AGENT_SHA, 'diagnostic_sha256': diag_sha})
    result = guest('stage-verify', f"""
import ast,hashlib,json,os,stat
from pathlib import Path
assert os.getuid()==0
helper=Path({HELPER!r})
for p in [helper,*helper.parents]:
    s=p.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid in (0,2000) and not s.st_mode&0o022
assert helper.stat().st_uid==2000
work=Path({WORK!r});assert not os.path.lexists(work)
work.mkdir(mode=0o700);os.chown(work,2000,2000)
src=Path({STAGE!r})/'diagnostic.py';s=src.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1
raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()=={diag_sha!r};ast.parse(raw)
fd=os.open({DIAG_FILE!r},os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
with os.fdopen(fd,'wb') as f:
    f.write(raw);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),2000,2000);os.fchmod(f.fileno(),0o400)
assert hashlib.sha256(Path({DIAG_FILE!r}).read_bytes()).hexdigest()=={diag_sha!r}
src.unlink();Path({STAGE!r}).rmdir()
print(json.dumps({{'state':'DIAGNOSTIC_COPY_NATIVE_PARSED','source_sha256':{AGENT_SHA!r},'diagnostic_sha256':{diag_sha!r},'original_assertion_preserved':True,'installed':False}}))
""")
elif action == 'run':
    result = guest('run', f"""
import datetime,hashlib,json,os,pwd,re,stat,subprocess,time
from pathlib import Path
assert os.getuid()==2000 and pwd.getpwuid(2000).pw_name=='commanderqa'
p=Path({DIAG_FILE!r});s=p.lstat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==2000 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o400
assert hashlib.sha256(p.read_bytes()).hexdigest()=={diag_sha!r}
work=Path({WORK!r});s=work.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==2000 and stat.S_IMODE(s.st_mode)==0o700
assert not os.path.lexists(work/'result.json')
env=os.environ.copy()
for key in ('BASH_ENV','ENV','PYTHONPATH','PYTHONHOME','LD_PRELOAD','LD_LIBRARY_PATH'):env.pop(key,None)
env.update({{'HOME':'/home/commanderqa','XDG_RUNTIME_DIR':'/run/user/2000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/2000/bus','PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','HARA_COMMANDER_URL':'https://hara-commander-dev-v2.tiago-sartori.workers.dev','HARA_COMMANDER_RELEASE_URL':'https://192.168.10.23:18444/releases/0.3.57','PYTHONDONTWRITEBYTECODE':'1'}})
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
stdout=work/'stdout.private.txt';stderr=work/'stderr.private.txt'
out_fd=os.open(stdout,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
try:err_fd=os.open(stderr,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
except Exception:os.close(out_fd);raise
try:
    # Run the preserved self-test to natural completion; no updater is invoked.
    child=subprocess.Popen(['/usr/bin/python3',str(p),'--self-test'],stdin=subprocess.DEVNULL,stdout=out_fd,stderr=err_fd,env=env,cwd=str(work),start_new_session=True)
    child.wait()
finally:os.close(out_fd);os.close(err_fd)
with stdout.open('rb') as f:out=f.read(262145)
with stderr.open('rb') as f:err=f.read(65537)
markers=[]
for line in out[:262144].decode('utf-8',errors='replace').splitlines():
    if line.startswith({MARKER!r}):
        obj=json.loads(line[len({MARKER!r}):]);assert set(obj)=={{'state','exit_code','process_exit_code'}}
        assert obj['state'] in ('EXITED','RUNNING','TIMED_OUT','STARTING','FAILED','UNEXPECTED_STATE')
        assert all(type(obj[k]) in (int,type(None)) or obj[k]=='UNEXPECTED_TYPE' for k in ('exit_code','process_exit_code'))
        markers.append(obj)
assert len(markers)<=1
error_lines=[int(n) for n in re.findall(r'File [^\\n]+, line (\\d+)',err[:65536].decode('utf-8',errors='replace'))]
error_type=''
for name in ('AssertionError','RuntimeError','ValueError','TypeError','OSError','PermissionError','TimeoutError'):
    if re.search(r'(?m)^'+name+r'(?::|$)',err[:65536].decode('utf-8',errors='replace')):error_type=name
result={{'schema':'hara.commander.linux-0357-selftest-diagnostic.v1','state':'DIAGNOSTIC_COMPLETED','started_utc':started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_agent_sha256':{AGENT_SHA!r},'diagnostic_sha256':{diag_sha!r},'original_assertion_preserved':True,'installation_performed':False,'system_configuration_changed_by_driver':False,'child_exit_code':child.returncode,'marker_count':len(markers),'markers':markers,'stdout_bytes':stdout.stat().st_size,'stderr_bytes':stderr.stat().st_size,'diagnostic_scan_truncated':len(out)>262144 or len(err)>65536,'error_type':error_type,'error_lines':error_lines}}
fd=os.open(work/'result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as f:json.dump(result,f,sort_keys=True);f.write('\\n');f.flush();os.fsync(f.fileno())
print(json.dumps(result))
""", user=True)
else:
    result = guest('result', f"""
import json,os,stat
from pathlib import Path
assert os.getuid()==2000
p=Path({RESULT!r});s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==2000 and s.st_nlink==1 and not s.st_mode&0o077 and s.st_size<16384
print(json.dumps(json.loads(p.read_text())))
""", user=True)
    m['save'](ROOT/'selftest-diagnostic-result.json',result)
print(json.dumps(result))
