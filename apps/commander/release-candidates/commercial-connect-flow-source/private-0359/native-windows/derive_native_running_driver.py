from pathlib import Path
import hashlib,ast,json,difflib
root=Path('/workspace/scratch/6e896ab26c66/commander-qa-continuation/product-source/connect-flow-20261028')
source=root/'private-0358/native-windows/Invoke-Private0358RunningUpdate.ps1'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='1afa08b8d75a4ed04d043e1b7cdfc7a9d8577f0a68c0b83ad6ebd73cb26e6589'
old=source.read_text(); s=old
s=s.replace('# One controlled same-signed-.58 update with an already-running QA Agent.','# One controlled signed .58 to .59 update with an already-running QA Agent.')
s=s.replace('18445/releases/0.3.58','18446/releases/0.3.59')
s=s.replace("$nuTargetAgentSha='bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d'","$nuTargetAgentSha='d3a4173829186e2488c2b686f5ac3ecca62c896387f55dcdfdbcdd155253ae24'")
s=s.replace("$nuTargetInstallerSha='27c856bb2b8ce8a100d8b258c8de544d99eb076ae8a0c6494110b17574ccfbc2'","$nuTargetInstallerSha='2f734ab8066b46cb82fc4fc9fb25244472bc829c16043cfe5f2771ae4e6d04b4'")
s=s.replace("$nuManifestSha='0c48cf879e5a8e564bb6554299c940a6414da64baf3477861450c6ee18be88dd'","$nuManifestSha='efe39839596883875358cfc27cd7ec62c0d38acc3c03708df56034a82d35d7b4'\n$nuSignatureSha='888f8674ae48e511eac9b4cc8ec1858110576af6970a6e6a7db19b585ef15ba3'\n$nuDistributionDeadline=[DateTimeOffset]::Parse('2026-10-28T19:35:00Z')")
s=s.replace('windows-private-0358-running-update.v1','windows-private-0359-running-update.v1')
s=s.replace('EXPLICIT_SAME_SIGNED_VERSION_RUNNING_UPDATE','EXPLICIT_SIGNED_0358_TO_0359_RUNNING_UPDATE')
s=s.replace("$current.Version -ceq '0.3.58' -and $current.AgentSha -ceq $nuTargetAgentSha","$current.Version -ceq '0.3.59' -and $current.AgentSha -ceq $nuTargetAgentSha")
s=s.replace('VERIFIED_0358_AGENT_PARSE_FAILED','VERIFIED_0359_AGENT_PARSE_FAILED')
s=s.replace('function WorkerSnapshot-NU {','function WorkerSnapshot-NU([switch]$ObserveBefore) {')
oldgate="  Need-NU ($result.workers.Count -eq 3 -and $result.workers.ContainsKey('heartbeat') -and $result.workers.ContainsKey('executor') -and $result.workers.ContainsKey('alerts')) 'THREE_RELAY_WORKERS_REQUIRED'"
assert s.count(oldgate)==1
s=s.replace(oldgate,"  if($ObserveBefore){\n    Need-NU ($result.workers.Count -ge 2 -and $result.workers.Count -le 3 -and $result.workers.ContainsKey('heartbeat') -and $result.workers.ContainsKey('alerts')) 'EXPECTED_KNOWN_BEFORE_WORKER_STATE_REQUIRED'\n  }else{\n"+oldgate+"\n  }")
s=s.replace("  $counts=@([HaraWinSqlite]::QueryReadOnly($database,'SELECT state,count(*) AS n FROM recovery_events GROUP BY state',@()))", "  $counts=@([HaraWinSqlite]::QueryReadOnly($database,'SELECT state,count(*) AS n FROM recovery_events GROUP BY state',@()))\n  $blockedEvents=@([HaraWinSqlite]::QueryReadOnly($database,\"SELECT event_id,worker,health,at_utc,created_ms,attempts,next_ms,server_event_id FROM recovery_events WHERE state='BLOCKED_AUTH' ORDER BY ordinal DESC LIMIT 4\",@()))")
s=s.replace('access_blocked=($blocked.Count -gt 0);counts=$counts;new_health_events=', 'access_blocked=($blocked.Count -gt 0);counts=$counts;blocked_auth_events=$blockedEvents;new_health_events=')
s=s.replace("  Need-NU (-not $outbox.access_blocked -and -not $outbox.new_stalled_or_degraded) 'RECOVERY_OUTBOX_HEALTH_HOLD'\n",'')
s=s.replace("state='PASS_THREE_STABLE_WORKERS_AND_OUTBOX'", "state='THREE_STABLE_WORKERS_OBSERVED'")
s=s.replace("alerts_network_ack=$(if(@($outbox.counts|Where-Object {[string]$_.state -ceq 'PERSISTED' -and [long]$_.n -gt 0}).Count){'PERSISTED_EVENTS_OBSERVED'}else{'NO_PENDING_EVENT_REQUIRED'})", "alerts_network_ack='NOT_TESTED';historical_persisted_count=@($outbox.counts|Where-Object {[string]$_.state -ceq 'PERSISTED'})")
s=s.replace("  Checkpoint-NU 'PREIMAGE'", "  Need-NU ([DateTimeOffset]::UtcNow -lt $nuDistributionDeadline.AddMinutes(-4)) 'PRIVATE_DISTRIBUTION_WINDOW_TOO_SHORT'\n  Checkpoint-NU 'PREIMAGE'")
s=s.replace("    if($Uri -ceq ($nuRelease+'/release/agent-manifest.json')){Need-NU ((Get-CCSha $bytes) -ceq $nuManifestSha) 'EXPECTED_0358_MANIFEST_HASH_REQUIRED'}", "    if($Uri -ceq ($nuRelease+'/release/agent-manifest.json')){Need-NU ((Get-CCSha $bytes) -ceq $nuManifestSha) 'EXPECTED_0359_MANIFEST_HASH_REQUIRED'}\n    if($Uri -ceq ($nuRelease+'/release/agent-manifest.sig.json')){Need-NU ((Get-CCSha $bytes) -ceq $nuSignatureSha) 'EXPECTED_0359_SIGNATURE_HASH_REQUIRED'}")
s=s.replace("$release.Version -ceq '0.3.58'", "$release.Version -ceq '0.3.59'")
s=s.replace('$release.AgentBytes.Length -eq 173192', '$release.AgentBytes.Length -eq 173345')
s=s.replace('EXPECTED_SIGNED_0358_RELEASE_REQUIRED','EXPECTED_SIGNED_0359_RELEASE_REQUIRED')
s=s.replace("$State.Version -ceq '0.3.58' -and $script:NUUpdaterStarted", "$State.Version -ceq '0.3.59' -and $script:NUUpdaterStarted")
s=s.replace("$Release.Version -ceq '0.3.58'", "$Release.Version -ceq '0.3.59'")
s=s.replace("    $script:NUUpdateInvocations++", "    Need-NU ([DateTimeOffset]::UtcNow -lt $nuDistributionDeadline.AddMinutes(-3)) 'PRIVATE_DISTRIBUTION_WINDOW_TOO_SHORT'\n    $script:NUUpdateInvocations++")
s=s.replace('verified-update-0358.ps1','verified-update-0359.ps1').replace('STAGED_0358_', 'STAGED_0359_')
s=s.replace("  Checkpoint-NU 'SIGNED_SAME_VERSION_UPDATE_WHILE_RUNNING'", "  $nuReport.before.relay_snapshot=WorkerSnapshot-NU -ObserveBefore\n  $script:NURecoveryStarted=[DateTime]::UtcNow\n  $nuReport.before.outbox=RecoveryOutbox-NU $nuReleaseData.AgentBytes\n  Checkpoint-NU 'SIGNED_0358_TO_0359_UPDATE_WHILE_RUNNING'")
s=s.replace("$nuUpdated.Version -ceq '0.3.58'", "$nuUpdated.Version -ceq '0.3.59'")
s=s.replace("  $nuReport.relay_health=Confirm-NUWorkers $nuReleaseData.AgentBytes", "  $nuReport.relay_health=Confirm-NUWorkers $nuReleaseData.AgentBytes\n  Need-NU (-not $nuReport.relay_health.outbox.new_stalled_or_degraded) 'NEW_RELAY_HEALTH_FAILURE_AFTER_UPDATE'")
s=s.replace("  $nuReport.state='PASS_PRIVATE_SIGNED_0358_RUNNING_UPDATE';$nuReport.stage='COMPLETE'", "  $nuReport.running_update_acceptance='PASS_SIGNED_0358_TO_0359_RUNNING_UPDATE'\n  $nuReport.auth_outbox_gate=[ordered]@{access_blocked_before=$nuReport.before.outbox.access_blocked;access_blocked_after=$nuReport.relay_health.outbox.access_blocked;flag_changed_by_driver=$false;alerts_delivery_confirmed=$false;follow_up='ROOT_SERVER_AUTH_DIAGNOSTIC'}\n  if($nuReport.relay_health.outbox.access_blocked){\n    $nuReport.state='HOLD_RECOVERY_OUTBOX_AUTH';$nuReport.stage='COMPLETE_WITH_SEPARATE_AUTH_HOLD';$nuReport.error_code='RECOVERY_OUTBOX_AUTH_BLOCKED'\n  }else{\n    $nuReport.state='PASS_PRIVATE_SIGNED_0359_RUNNING_UPDATE';$nuReport.stage='COMPLETE'\n  }")
s=s.replace("if($nuReport.state -ceq 'PASS_PRIVATE_SIGNED_0358_RUNNING_UPDATE')", "if($nuReport.state -ceq 'PASS_PRIVATE_SIGNED_0359_RUNNING_UPDATE')")
# Do not release the controller guard while a signed updater remains alive even if the observer fails.
s=s.replace("      if($stdoutFile){$stdoutFile.Dispose()};if($stderrFile){$stderrFile.Dispose()}\n      $script:NUChild=$null;$process.Dispose()", "      if($script:NUChild){\n        while(-not $process.HasExited){[void]$process.WaitForExit(1000)}\n        if($stdoutCopy){[void]$stdoutCopy.Wait(5000)};if($stderrCopy){[void]$stderrCopy.Wait(5000)}\n      }\n      if($stdoutFile){$stdoutFile.Dispose()};if($stderrFile){$stderrFile.Dispose()}\n      $script:NUChild=$null;$process.Dispose()")
assert s != old
out=root/'private-0359/native-windows';out.mkdir(exist_ok=True)
p=out/'Invoke-Private0359RunningUpdate.ps1';p.write_text(s)
sha=hashlib.sha256(p.read_bytes()).hexdigest()
cs=(root/'private-0358/native-windows/native_running_update_driver.py').read_text()
assert hashlib.sha256(cs.encode()).hexdigest()=='e0dd35d229e558b4bfc6aa6b2e8318599230141c74dda9ce66d284b54ee3cd44'
cs=cs.replace('one authorized Windows QA .57 update','one authorized Windows QA .58 to .59 running update')
cs=cs.replace('0358','0359').replace('QA058','QA059')
cs=cs.replace('1afa08b8d75a4ed04d043e1b7cdfc7a9d8577f0a68c0b83ad6ebd73cb26e6589',sha)
# Signed transaction observers must not be auto-terminated by a task execution deadline.
cs=cs.replace('-ExecutionTimeLimit (New-TimeSpan -Minutes 30)', '-ExecutionTimeLimit ([TimeSpan]::Zero)')
cs=cs.replace("'actual_enrollment_acl','relay_health'", "'actual_enrollment_acl','relay_health','running_update_acceptance','auth_outbox_gate'")
cp=out/'native_running_update_driver.py';cp.write_text(cs)
ast.parse(cs)
compile(cs,str(cp),'exec')
for p in (p,cp):
 print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}))
(out/'running-update-driver.patch').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),s.splitlines(keepends=True),fromfile='frozen0358',tofile='0359')))
