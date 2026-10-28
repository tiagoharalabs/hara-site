"""Root-owned QGA coordinator for the one authorized Ubuntu private .57 update."""
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
SOURCE_SHA = '16f3842d700bdacec399135e27ad79cee9d7da328085121e7ddd344c3d2bcc1e'
CERT_SHA = 'c15308e100ba014d463b20cc56568e2183c4c50e2b2b672af38a0926d1c879c1'
STAGE = '/run/hara-qa-private0357-20261028'
HELPER = '/home/commanderqa/.local/share/hara-commander-connect-qa'
FILE = HELPER + '/native_private_0357_upgrade.py'
RESULT = HELPER + '/upgrade-0357/result.json'
PROGRESS = HELPER + '/upgrade-0357/progress.json'

def guest(label, code, user=False):
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
                raise RuntimeError('QGA_PHASE_FAILED_' + label + '_exit_' + str(value.get('exitcode')) + '_stderr_bytes_' + str(len(err.encode())))
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
    source = (ROOT / 'native_private_0357_upgrade.py').read_bytes()
    cert = (BASE / 'distribution-r3/tls/qa-server.crt').read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA
    assert hashlib.sha256(cert).hexdigest() == CERT_SHA
    ast.parse(source)
    guest('source-folder', f"""
import json,os,stat
from pathlib import Path
assert os.getuid()==0
p=Path({STAGE!r});assert not os.path.lexists(p)
assert not p.parent.is_symlink() and p.parent.stat().st_uid==0
p.mkdir(mode=0o700)
print(json.dumps({{'state':'SOURCE_STAGE_CREATED'}}))
""")
    marker = ROOT / 'source-transferred.json'
    if not marker.exists():
        for name, data in [('driver.py', source), ('certificate.crt', cert)]:
            handle = m['call']('guest-file-open', {'path': STAGE + '/' + name, 'mode': 'w'})
            try:
                for offset in range(0, len(data), 16000):
                    part = data[offset:offset+16000]
                    result = m['call']('guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(part).decode()})
                    assert result['count'] == len(part)
                m['call']('guest-file-flush', {'handle': handle})
            finally:
                m['call']('guest-file-close', {'handle': handle})
        m['save'](marker, {'source_sha256': SOURCE_SHA, 'public_certificate_sha256': CERT_SHA})
    result = guest('source-verify', f"""
import ast,hashlib,json,os,stat
from pathlib import Path
assert os.getuid()==0
helper=Path({HELPER!r});assert helper.is_dir() and helper.stat().st_uid==2000
for parent in [helper,*helper.parents]:
    s=parent.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid in (0,2000) and not s.st_mode&0o022
for name,dest,sha,mode in [('driver.py',{FILE!r},{SOURCE_SHA!r},0o400),('certificate.crt',str(helper/'qa-release-0357.crt'),{CERT_SHA!r},0o444)]:
    src=Path({STAGE!r})/name;s=src.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1
    raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
    if name=='driver.py':ast.parse(raw)
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),2000,2000);os.fchmod(f.fileno(),mode)
    assert hashlib.sha256(Path(dest).read_bytes()).hexdigest()==sha
    src.unlink()
Path({STAGE!r}).rmdir()
print(json.dumps({{'state':'PRIVATE_UPGRADE_SOURCE_NATIVE_PARSED','source_sha256':{SOURCE_SHA!r},'public_certificate_sha256':{CERT_SHA!r},'installer_executed':False}}))
""")
elif action == 'run':
    # One QGA process, pinned and recorded before it can ever be polled again.
    # The child owns the connection lock and runs naturally to completion.
    result = guest('native-upgrade', f"""
import hashlib,os,runpy,pwd
from pathlib import Path
assert os.getuid()==2000 and pwd.getpwuid(2000).pw_name=='commanderqa'
p=Path({FILE!r});assert hashlib.sha256(p.read_bytes()).hexdigest()=={SOURCE_SHA!r}
os.environ['HOME']='/home/commanderqa'
os.environ['XDG_RUNTIME_DIR']='/run/user/2000'
os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path=/run/user/2000/bus'
runpy.run_path(str(p),run_name='__main__')
""", user=True)
else:
    index = 0
    while (ROOT / ('receipt-' + str(index) + '-decoded.json')).exists():
        previous = json.loads((ROOT / ('receipt-' + str(index) + '-decoded.json')).read_text())
        if previous.get('receipt_kind') == 'result':
            break
        index += 1
    result = guest('receipt-' + str(index), f"""
import json,os,stat
from pathlib import Path
assert os.getuid()==2000
for name in ['result','progress']:
    p=Path({HELPER!r})/'upgrade-0357'/(name+'.json')
    if p.exists():
        s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_uid==2000 and not s.st_mode&0o077 and s.st_size<65536
        r=json.loads(p.read_text());r['receipt_kind']=name;print(json.dumps(r));break
else:print(json.dumps({{'state':'RECEIPT_NOT_YET_AVAILABLE','receipt_kind':'none'}}))
""", user=True)
    if result.get('receipt_kind') == 'result':
        m['save'](ROOT / 'native-result.json', result)
if action == 'result':
    compact = {key: result.get(key) for key in ('state','stage','error_code','error_type','started_utc','finished_utc','receipt_kind','updater_started_utc','child_exit','installer_markers','dispatch_service_rechecked_under_lock') if key in result}
    for key in ('after','independent_failure_attestation'):
        if key in result:
            compact[key] = result[key]
    print(json.dumps(compact))
else:
    print(json.dumps(result))
