import importlib.util,json
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM=b.CLONE
for name in ("windows_clean_minimal_lifecycle_054_r1.ps1","windows_clean_normal_start_054.ps1"):
 print(json.dumps(b.stage(b.CLONE,"/tmp_hara/commander-windows-clean-20261012-r1/"+name,b.CLEAN+chr(92)+name)))
code=r"""
$ErrorActionPreference='Stop'
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'QA_UUID_REQUIRED'}
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Cases=@()
foreach($Name in @('windows_clean_native_install_054_r1.ps1','windows_clean_minimal_lifecycle_054_r1.ps1','windows_clean_normal_start_054.ps1')){
 $T=$null;$E=$null;$A=[Management.Automation.Language.Parser]::ParseFile((Join-Path $Box $Name),[ref]$T,[ref]$E)
 if(@($E).Count -gt 0){throw 'NATIVE_PARENT_PARSE_FAILED'}
 $Children=@($A.FindAll({param($N) $N -is [Management.Automation.Language.StringConstantExpressionAst] -and [string]$N.StringConstantType -match 'HereString'},$true))
 foreach($Child in $Children){
  $T=$null;$E=$null;$Parsed=[Management.Automation.Language.Parser]::ParseInput([string]$Child.Value,[ref]$T,[ref]$E)
  if(@($E).Count -gt 0){throw 'NATIVE_CHILD_PARSE_FAILED'}
 }
 $Cases+=[ordered]@{file=$Name;parent_parse_pass=$true;child_script_count=$Children.Count;child_parse_pass=$true}
}
[ordered]@{state='PASS';schema='hara.windows-clean-native-54-harness-parser.v1';cases=$Cases;edition=$PSVersionTable.PSEdition;version=$PSVersionTable.PSVersion.ToString();source_executed=$false;profile_modified=$false}|ConvertTo-Json -Depth 4 -Compress
"""
rc,out,err=q.powershell(code,wait=25);assert rc==0 and not err,"NATIVE_HARNESS_PARSER_FAILED"
print(out.strip())
