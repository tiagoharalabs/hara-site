import sys,json,pathlib,hashlib,base64,time
sys.path.insert(0,"/usr/lib/python3/dist-packages")
import libvirt,libvirt_qemu
BASE=pathlib.Path("/var/lib/hara-qa/restore-linux-056-preparation-20261027/qa-desktop-access-20261028")
raw=(BASE/"desktop-bundle.json").read_bytes()
assert hashlib.sha256(raw).hexdigest()=="4a5ac4d23ef57a68e540e1a9225ecd46844aebc2f468fbecb6719cb5a34ee12e"
bundle=json.loads(raw)
FILES={}
for name,obj in bundle["files"].items():
 assert name in ["instalar-commander-0.3.56.ps1","LEIA-ME.txt","RESULTADO-DOS-TESTES.txt","ACESSO-QA.txt"]
 data=base64.b64decode(obj["data"],validate=True)
 assert len(data)==obj["bytes"] and hashlib.sha256(data).hexdigest()==obj["sha256"]
 FILES[name]=data
DEST=r"C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA"
AGENT="agent-windows-0.3.56.ps1"
AGENT_SHA="a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620"
c=libvirt.open("qemu:///system")
d=c.lookupByUUIDString("154e2853-3d1d-4d23-a43d-706f76ad7939")
assert d.name()=="hara-review-win11-restoretest-20261024" and d.isActive()
def call(name,args):
 out=json.loads(libvirt_qemu.qemuAgentCommand(d,json.dumps({"execute":name,"arguments":args}),10,0))
 assert "error" not in out,out
 return out["return"]
def run_ps(label,script):
 launch=BASE/(label+"-launch.json");complete=BASE/(label+"-complete.json")
 if not launch.exists():
  r=call("guest-exec",{"path":r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe","arg":["-NoLogo","-NoProfile","-NonInteractive","-EncodedCommand",base64.b64encode(script.encode("utf-16-le")).decode()],"capture-output":True})
  launch.write_text(json.dumps(r))
 pid=json.loads(launch.read_text())["pid"]
 for _ in range(12):
  if complete.exists():r=json.loads(complete.read_text())
  else:
   r=call("guest-exec-status",{"pid":pid})
   if r.get("exited"):complete.write_text(json.dumps(r))
  if r.get("exited"):
   out=base64.b64decode(r.get("out-data","")).decode("utf-8","replace")
   err=base64.b64decode(r.get("err-data","")).decode("utf-8","replace")
   result={"exit":r.get("exitcode"),"out":out,"err":err}
   (BASE/(label+"-decoded.json")).write_text(json.dumps(result))
   assert result["exit"]==0,result
   return json.loads(out.strip())
  time.sleep(.15)
 print(json.dumps({"state":"RUNNING","operation":label,"pid":pid}));sys.exit(0)
prepare=r"""
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$qa=Get-LocalUser 'CommanderQA';$sid=$qa.SID.Value
$p=Get-CimInstance Win32_UserProfile|Where-Object SID -eq $sid
if(-not $p.Loaded -or $p.LocalPath -ne 'C:\Users\CommanderQA'){throw 'QA_PROFILE_MISMATCH'}
$k=[Microsoft.Win32.Registry]::Users.OpenSubKey($sid+'\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
$desktop=([string]$k.GetValue('Desktop',$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)).Replace('%USERPROFILE%',$p.LocalPath)
if($desktop -ne 'C:\Users\CommanderQA\Desktop'){throw 'DESKTOP_MISMATCH'}
foreach($a in @($p.LocalPath,$desktop)){if((Get-Item -LiteralPath $a).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_PATH'}}
$dest=Join-Path $desktop 'HARA Commander 0.3.56 QA'
if(Test-Path -LiteralPath $dest){throw 'DESTINATION_ALREADY_EXISTS'}
New-Item -ItemType Directory -Path $dest | Out-Null
& icacls.exe $dest /inheritance:r /grant:r ("*"+$sid+":(OI)(CI)F") '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if($LASTEXITCODE -ne 0){throw 'PRIVATE_ACL_FAILED'}
& icacls.exe $dest /setowner ("*"+$sid) | Out-Null
if($LASTEXITCODE -ne 0){throw 'OWNER_FAILED'}
$src='C:\ProgramData\HARA-QA\native-0356-activeqa-20261027\source\agent-windows-0.3.56.ps1'
if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'){throw 'AGENT_PIN_FAILED'}
Copy-Item -LiteralPath $src -Destination (Join-Path $dest 'agent-windows-0.3.56.ps1')
foreach($n in @('instalar-commander-0.3.56.ps1','LEIA-ME.txt','RESULTADO-DOS-TESTES.txt','ACESSO-QA.txt')){New-Item -ItemType File -Path (Join-Path $dest $n)|Out-Null}
[ordered]@{state='DESKTOP_DIRECTORY_READY';desktop=$desktop;folder=$dest;owner=(Get-Acl -LiteralPath $dest).Owner;console=(Get-CimInstance Win32_ComputerSystem).UserName}|ConvertTo-Json -Compress
"""
prep=run_ps("desktop-prepare",prepare)
assert prep["state"]=="DESKTOP_DIRECTORY_READY"
if not (BASE/"desktop-transfer.json").exists():
 records=[]
 for name,data in FILES.items():
  h=call("guest-file-open",{"path":DEST+"\\"+name,"mode":"r+"})
  try:
   for pos in range(0,len(data),24576):
    part=data[pos:pos+24576]
    r=call("guest-file-write",{"handle":h,"buf-b64":base64.b64encode(part).decode()})
    assert r.get("count")==len(part),r
   call("guest-file-flush",{"handle":h})
  finally:call("guest-file-close",{"handle":h})
  records.append({"name":name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
 (BASE/"desktop-transfer.json").write_text(json.dumps(records))
expected=[{"name":n,"bytes":len(v),"sha256":hashlib.sha256(v).hexdigest()} for n,v in FILES.items()]
expected.append({"name":AGENT,"bytes":172687,"sha256":AGENT_SHA})
b64=base64.b64encode(json.dumps(expected).encode()).decode()
verify=r"""
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$dest='C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA'
$expected=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"""+b64+r"""'))|ConvertFrom-Json
$rows=@();$out=@()
foreach($x in $expected){
$f=Get-Item -LiteralPath (Join-Path $dest $x.name)
$sha=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if($sha -ne $x.sha256 -or $f.Length -ne $x.bytes){throw ('FILE_MISMATCH '+$x.name)}
$rows+=($sha+'  '+$x.name);$out+=@{name=$x.name;bytes=$f.Length;sha256=$sha}
}
[IO.File]::WriteAllLines((Join-Path $dest 'SHA256SUMS.txt'),[string[]]$rows,[Text.Encoding]::ASCII)
$acl=Get-Acl -LiteralPath $dest
[ordered]@{state='DESKTOP_FILES_VERIFIED';folder=$dest;owner=$acl.Owner;acl_protected=$acl.AreAccessRulesProtected;files=$out;checksum_file='SHA256SUMS.txt';installed=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\hara-commander-agent.ps1');paired=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json');password_changed=$false}|ConvertTo-Json -Depth 5 -Compress
"""
result=run_ps("desktop-verify",verify)
assert result["state"]=="DESKTOP_FILES_VERIFIED"
(BASE/"desktop-delivery-result.json").write_text(json.dumps(result))
print(json.dumps(result))
