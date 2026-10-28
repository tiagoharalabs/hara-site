import hashlib,json,runpy
from pathlib import Path
BASE=Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028')
p=BASE/'windows_install_native_driver_r6.py'
assert hashlib.sha256(p.read_bytes()).hexdigest()=='e1d3eea70edb079e6cc8492edd3544db254d262e98eab2211bb1abdadf1f1e04'
m=runpy.run_path(str(p))
import libvirt
c=libvirt.open('qemu:///system');d=c.lookupByUUIDString('154e2853-3d1d-4d23-a43d-706f76ad7939')
assert d.name()=='hara-review-win11-restoretest-20261024' and d.isActive()
m['ps'].__globals__['DOM']=d
s=BASE/'connect-flow-20261028/private-0359/native-windows/Setup-Private0359TLS.ps1'
b=s.read_bytes();assert hashlib.sha256(b).hexdigest()=='47a3bc54f7eceae7c8ec5e037d2a65d11c93358f8c89d2d22641ce5a144a201b'
r=m['ps']('qa0359-admin-temporary-tls',b.decode())
print(json.dumps(r))
