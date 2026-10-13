$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$Url='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
$Result=[ordered]@{schema='hara.windows-clean-http-metadata.v1';clone_uuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba';network_up=@(Get-NetAdapter|Where-Object{$_.Status -eq 'Up'}).Count;http_status=$null;agent_version=$null;manifest_sha256=$null;error_type=$null}
try{
 $Response=Invoke-WebRequest -UseBasicParsing -Uri ($Url+'/release/agent-manifest.json') -TimeoutSec 20 -MaximumRedirection 0
 $Result.http_status=[int]$Response.StatusCode
 $Bytes=$Response.RawContentStream.ToArray();$Digest=[Security.Cryptography.SHA256]::Create()
 try{$Result.manifest_sha256=([BitConverter]::ToString($Digest.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$Digest.Dispose()}
 $Result.agent_version=[string]($Response.Content|ConvertFrom-Json).agent_version
}catch{$Result.error_type=$_.Exception.GetType().Name;if($_.Exception.Response){$Result.http_status=[int]$_.Exception.Response.StatusCode}}
$Result|ConvertTo-Json -Compress
