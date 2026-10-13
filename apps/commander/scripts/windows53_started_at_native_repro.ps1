$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$File=Join-Path $Box 'private-053-rc-r2\agent\windows.ps1'
$Root=Join-Path $Box ('started-repro-'+[guid]::NewGuid().ToString('N'))
$RuntimeStatus=Join-Path $Root 'runtime-status.json';$AgentVersion='0.3.53'
New-Item -Path $Root -ItemType Directory|Out-Null
try{
 $t=$null;$e=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($File,[ref]$t,[ref]$e)
 foreach($name in @('Set-RuntimeStatus','Try-SetRuntimeStatus')){$f=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true));if($f.Count -ne 1){throw 'EXACT_FROZEN_FUNCTION_REQUIRED'};Invoke-Expression ($f[0].Extent.Text -replace '^function ','function script:')}
 Set-RuntimeStatus -StartedAt 'fixture-initial-start'
 $before=[string](Get-Content -Raw -LiteralPath $RuntimeStatus|ConvertFrom-Json).started_at_utc
 $null=Try-SetRuntimeStatus -HeartbeatAt 'fixture-heartbeat'
 $after=[string](Get-Content -Raw -LiteralPath $RuntimeStatus|ConvertFrom-Json).started_at_utc
 [ordered]@{schema='hara.windows53-runtime-started-repro.v1';state=if($before -ceq 'fixture-initial-start' -and $after -ceq ''){'PASS_DEFECT_REPRODUCED'}else{'FAIL_REPRO'};frozen_source_version='0.3.53';before_started_at=$before;after_started_at=$after;after_started_length=$after.Length;native_powershell=$PSVersionTable.PSVersion.ToString();fixture_only=$true;installed_status_modified=$false;main_modified=$false}|ConvertTo-Json -Compress
}finally{Remove-Item -LiteralPath $Root -Force -Recurse}
