#!/usr/bin/env python3
"""Execute only fixed QA diagnostics as direct PowerShell commands via QGA."""
import base64, json, subprocess, sys, time
DOMAIN="hara-commander-win11-qa0384-20261115"
PS=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
COMMANDS={
 "policy": r'''$ErrorActionPreference='Stop'; Write-Output ('EXECUTION_POLICY='+(Get-ExecutionPolicy).ToString()); $s=Get-ExecutionPolicy -List;foreach($x in $s){Write-Output ('SCOPE_'+$x.Scope+'='+$x.ExecutionPolicy)}''',
 "hashes": r'''$ErrorActionPreference='Stop';$root='D:\';$m='b0350ec8dc9f2b995742cf07df91df8ad5aaa324a9948b16753f178cef2820fe';$s='e0bc91232b7cb9f5344a1cd000dcb7e9a6be1e6b6c634c911626414bee31fe15';$p='4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b';if((Get-FileHash 'D:\release\agent-manifest.json').Hash.ToLowerInvariant() -ne $m){throw 'MANIFEST_SHA'};if((Get-FileHash 'D:\release\agent-manifest.sig.json').Hash.ToLowerInvariant() -ne $s){throw 'SIGNATURE_SHA'};if((Get-FileHash 'D:\release\release-signing-public.jwk').Hash.ToLowerInvariant() -ne $p){throw 'PUBLIC_PIN'};$a=(Get-Content 'D:\release\agent-manifest.json' -Raw|ConvertFrom-Json);if($a.agent_version -ne '0.3.84' -or $a.files.Count -ne 4){throw 'VERSION'};foreach($f in @($a.files)){$v=Join-Path $root ([string]$f.path).Replace('/','\');if(-not (Test-Path $v)){throw 'MISSING_FILE'};if((Get-FileHash $v).Hash.ToLowerInvariant() -ne $f.sha256){throw 'ARTIFACT_SHA'};if((Get-Item $v).Length -ne [long]$f.bytes){throw 'BYTES'}};Write-Output 'WINDOWS_NATIVE_FOUR_SHA_AND_MANIFEST_PASS' ''',
 "rsa": r'''$ErrorActionPreference='Stop';$m=[IO.File]::ReadAllBytes('D:\release\agent-manifest.json');$p=(Get-Content 'D:\release\release-signing-public.jwk' -Raw|ConvertFrom-Json);$s=(Get-Content 'D:\release\agent-manifest.sig.json' -Raw|ConvertFrom-Json);function DecodeB64([string]$v){$v=$v.Replace('-','+').Replace('_','/');$v+=[string]::new('=',(4-($v.Length%4))%4);return [Convert]::FromBase64String($v)};$par=New-Object System.Security.Cryptography.RSAParameters;$par.Modulus=DecodeB64 ([string]$p.n);$par.Exponent=DecodeB64 ([string]$p.e);$r=New-Object System.Security.Cryptography.RSACryptoServiceProvider;$r.PersistKeyInCsp=$false;$r.ImportParameters($par);if($r.KeySize -ne 3072){throw 'RSA_BITS'};$sig=DecodeB64 ([string]$s.signature);$oid=[System.Security.Cryptography.CryptoConfig]::MapNameToOID('SHA256');if(-not $r.VerifyData($m,$oid,$sig)){throw 'RSA_VERIFY'};$changed=New-Object byte[] $m.Length;[Array]::Copy($m,$changed,$m.Length);$changed[0]=$changed[0] -bxor 1;if($r.VerifyData($changed,$oid,$sig)){throw 'NEGATIVE_RSA_FAILED'};Write-Output 'WINDOWS_NATIVE_RSA3072_POSITIVE_NEGATIVE_PASS' ''',
 "parser": r'''$ErrorActionPreference='Stop';foreach($f in @('D:\agent\windows.ps1','D:\install\windows.ps1')){$tok=$null;$perr=$null;[System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$tok,[ref]$perr)|Out-Null;if($perr.Count -ne 0){throw 'PARSER_FAILED'}};$agent=Get-Content 'D:\agent\windows.ps1' -Raw;$inst=Get-Content 'D:\install\windows.ps1' -Raw;if(-not $agent.Contains('$AgentVersion = "0.3.84"')){throw 'VERSION'};if(-not $inst.Contains('Assert-ReleaseManifestSignature')){throw 'INSTALLER_RSA_GUARD'};if($inst.Contains('New-ScheduledTaskTrigger -AtLogOn') -or $inst.Contains('New-ScheduledTaskTrigger -AtStartup')){throw 'AUTOSTART'};Write-Output 'WINDOWS_NATIVE_TWO_PARSERS_AND_MANUAL_START_PASS' ''',
 "swap": r'''$ErrorActionPreference='Stop';$base='D:\qa\agent-windows-0383.ps1';$new='D:\agent\windows.ps1';$oldsha='4e61b014125e180c54ad5d8c256679af80dd910255912b5086feb5946d89ca4e';$newsha='5b331dfbb9be9c36bb8b54194dea73a85e79789273965d288ab64b47b907aff0';if((Get-FileHash $base).Hash.ToLowerInvariant() -ne $oldsha){throw 'BASE_PIN'};$dir=Join-Path $env:TEMP ('hara-qa0384-'+[Guid]::NewGuid().ToString('N'));New-Item -Path $dir -ItemType Directory|Out-Null;try{$p=Join-Path $dir 'agent.ps1';$b=Join-Path $dir 'backup.ps1';Copy-Item -LiteralPath $base -Destination $p;Copy-Item -LiteralPath $p -Destination $b;Copy-Item -LiteralPath $new -Destination $p -Force;if((Get-FileHash $p).Hash.ToLowerInvariant() -ne $newsha){throw 'UPDATE_SHA'};Copy-Item -LiteralPath $b -Destination $p -Force;if((Get-FileHash $p).Hash.ToLowerInvariant() -ne $oldsha){throw 'ROLLBACK_SHA'};Write-Output 'WINDOWS_NATIVE_TEMP_FILE_UPDATE_AND_ROLLBACK_PASS'}finally{Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue}'''
}
def qga(obj):
 p=subprocess.run(["virsh","-c","qemu:///system","qemu-agent-command",DOMAIN,"--timeout","4",json.dumps(obj)],capture_output=True,text=True,timeout=7)
 if p.returncode:raise RuntimeError("QGA_CALL_ERROR")
 x=json.loads(p.stdout)
 if x.get("error"):raise RuntimeError("QGA_RESPONSE_ERROR")
 return x["return"]
def main():
 if len(sys.argv)!=2 or sys.argv[1] not in COMMANDS:raise SystemExit("VALID_CASE_REQUIRED")
 name=sys.argv[1]
 args=["-NoProfile","-NonInteractive","-Command",COMMANDS[name]]
 pid=qga({"execute":"guest-exec","arguments":{"path":PS,"arg":args,"capture-output":True}})["pid"]
 for _ in range(26):
  r=qga({"execute":"guest-exec-status","arguments":{"pid":pid}})
  if r.get("exited"):
   out=base64.b64decode(r.get("out-data","")).decode(errors="replace").strip()
   err=base64.b64decode(r.get("err-data","")).decode(errors="replace").strip()
   success=r.get("exitcode")==0 and (name=="policy" or "PASS" in out)
   print(json.dumps({"case":name,"state":"PASS" if success else "HOLD","exitcode":r.get("exitcode"),"stdout":out[-500:],"stderr_tail":err[-250:]}))
   raise SystemExit(0 if success else 2)
  time.sleep(0.25)
 print(json.dumps({"case":name,"state":"PENDING","guest_pid":pid}))
 raise SystemExit(3)
if __name__=="__main__":
 main()
