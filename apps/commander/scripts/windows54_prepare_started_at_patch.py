import pathlib,hashlib,json
source=pathlib.Path("/tmp_hara/commander-full-053-signed-stage-20261012-root-r2/apps/commander/public/agent/windows.ps1")
raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()=="f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299"
s=raw.decode("utf-8")
old='$lastHeartbeat=if ($null -ne $HeartbeatAt) {$HeartbeatAt} elseif ($existing) {[string]$existing.last_successful_heartbeat_at_utc} else {$null}'
new='$lastHeartbeat=if ($PSBoundParameters.ContainsKey("HeartbeatAt")) {$HeartbeatAt} elseif ($existing) {[string]$existing.last_successful_heartbeat_at_utc} else {$null}'
assert s.count(old)==1;s=s.replace(old,new)
old='$startedAt=if ($null -ne $StartedAt) {$StartedAt} elseif ($existing) {[string]$existing.started_at_utc} else {$null}'
new='$runtimeStartedAt=if ($PSBoundParameters.ContainsKey("StartedAt")) {$StartedAt} elseif ($existing) {[string]$existing.started_at_utc} else {$null}\n  $runtimeErrorCode=if ($PSBoundParameters.ContainsKey("ErrorCode")) {$ErrorCode} elseif ($existing) {[string]$existing.last_runtime_error_code} else {$null}\n  $runtimeErrorAt=if ($PSBoundParameters.ContainsKey("ErrorAt")) {$ErrorAt} elseif ($existing) {[string]$existing.last_runtime_error_at_utc} else {$null}'
assert s.count(old)==1;s=s.replace(old,new)
for old,new in [('started_at_utc=$startedAt','started_at_utc=$runtimeStartedAt'),('last_runtime_error_code=$ErrorCode','last_runtime_error_code=$runtimeErrorCode'),('last_runtime_error_at_utc=$ErrorAt','last_runtime_error_at_utc=$runtimeErrorAt'),('Set-RuntimeStatus -HeartbeatAt $HeartbeatAt -ErrorCode $ErrorCode -ErrorAt $ErrorAt -StartedAt $StartedAt','Set-RuntimeStatus @PSBoundParameters')]:
 assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new)
# Successful heartbeat explicitly clears both error fields; bare partial updates preserve omitted fields.
old='Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o"))'
new='Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o")) -ErrorCode "" -ErrorAt ""'
assert s.count(old)==2;s=s.replace(old,new)
target=pathlib.Path("/tmp_hara/commander-win54-started-at-fix-20261013-r1/agent/windows.ps1");target.parent.mkdir(parents=True,exist_ok=True)
assert not target.exists(),"ISOLATED_PATCH_PATH_COLLISION"
target.write_bytes(s.encode("utf-8"))
print(json.dumps({"path":str(target),"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"bytes":target.stat().st_size,"version_unchanged_53":True,"signed53_modified":False,"main_modified":False}))
