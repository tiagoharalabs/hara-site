# Native dynamic assertions run against the actual imported adapter/transport functions.
function ExpectError([scriptblock]$Action,[string]$Code) {
 $seen=$null
 try { & $Action|Out-Null } catch { $seen=[string]$_.Exception.Message }
 if($seen-ne $Code){throw ('EXPECTED_'+$Code+'_GOT_'+$seen)}
}
Check 'stable_source_version_binding' {if($AgentVersion-ne'0.3.51'){throw 'AGENT_VERSION_BINDING'}}
Check 'liveness_fnv_repeatability_and_bound' {
 foreach($device in @('a','unicode-lab','long-'+('x'*128),'windows-event-v2-selftest')){
  $cfg=[pscustomobject]@{device_id=$device}
  $a=Get-DurableLivenessSeconds $cfg;$b=Get-DurableLivenessSeconds $cfg
  if($a-ne$b-or$a-lt20700-or$a-gt22500){throw 'LIVENESS_HASH_BOUND'}
 }
}
Check 'reconnect_negative_denied' {ExpectError {Get-ReconnectDelaySeconds -1} 'WINDOWS_EVENT_V2_RECONNECT_ATTEMPT_INVALID'}
Check 'origin_http_denied' {ExpectError {ConvertTo-EventV2Uri 'http://lab.invalid'} 'WINDOWS_EVENT_V2_HTTPS_REQUIRED'}
Check 'origin_query_denied' {ExpectError {ConvertTo-EventV2Uri 'https://lab.invalid?a=b'} 'WINDOWS_EVENT_V2_ORIGIN_INVALID'}
Check 'origin_fragment_denied' {ExpectError {ConvertTo-EventV2Uri 'https://lab.invalid#x'} 'WINDOWS_EVENT_V2_ORIGIN_INVALID'}
Check 'blank_token_denied' {ExpectError {New-EventV2Client ''} 'WINDOWS_EVENT_V2_DEVICE_TOKEN_INVALID'}
Check 'short_token_denied' {ExpectError {New-EventV2Client 'short'} 'WINDOWS_EVENT_V2_DEVICE_TOKEN_INVALID'}
Check 'native_client_keepalive' {$c=New-EventV2Client ('x'*64);try{if($c.Options.KeepAliveInterval.TotalSeconds-ne60){throw 'KEEPALIVE'}}finally{$c.Dispose()}}
$wake=@{schema='hara.commander-device-event.v2';type='CALL_AVAILABLE';call_id='HARA-CALL-lab'}
Check 'wake_exact_schema' {$o=Parse-EventV2Wake ($wake|ConvertTo-Json -Compress);if($o.call_id-ne'HARA-CALL-lab'){throw 'WAKE_ID'}}
Check 'wake_content_denied' {$o=$wake.Clone();$o.payload=@{command='lab'};ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Compress)} 'WINDOWS_EVENT_V2_EVENT_INVALID'}
Check 'wake_invalid_id_denied' {$o=$wake.Clone();$o.call_id='lab/invalid';ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Compress)} 'WINDOWS_EVENT_V2_CALL_ID_INVALID'}
Check 'wrong_schema_denied' {$o=$wake.Clone();$o.schema='v1';ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Compress)} 'WINDOWS_EVENT_V2_SCHEMA_DENIED'}
Check 'unknown_type_denied' {$o=$wake.Clone();$o.type='UNKNOWN';ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Compress)} 'WINDOWS_EVENT_V2_EVENT_TYPE_DENIED'}
Check 'invalid_json_denied' {ExpectError {Parse-EventV2Wake '{'} 'WINDOWS_EVENT_V2_EVENT_INVALID'}
$call=[pscustomobject]@{schema='hara.commander-device-event.v2';type='CALL_TRANSIENT';call_id='HARA-TRANSIENT-lab';request_id='LAB-REQ-1';tool_id='hara.health';execution_mode='EXECUTE_OR_REPLAY';payload=[pscustomobject]@{}}
Check 'transient_native_parse' {$p=Parse-EventV2Wake ($call|ConvertTo-Json -Depth 5 -Compress);if($p.request_id-ne'LAB-REQ-1'){throw 'TRANSIENT_ID'}}
Check 'transient_execution_mode_denied' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.execution_mode='EXECUTE_ALWAYS';ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Depth 5 -Compress)} 'WINDOWS_EVENT_V2_TRANSIENT_EXECUTION_MODE_INVALID'}
Check 'transient_payload_string_denied' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.payload='x';ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Depth 5 -Compress)} 'WINDOWS_EVENT_V2_TRANSIENT_PAYLOAD_INVALID'}
Check 'transient_payload_array_denied' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.payload=@('x');ExpectError {Parse-EventV2Wake ($o|ConvertTo-Json -Depth 5 -Compress)} 'WINDOWS_EVENT_V2_TRANSIENT_PAYLOAD_INVALID'}
Check 'transient_oversized_denied' {ExpectError {Parse-EventV2Wake ('x'*163841)} 'WINDOWS_EVENT_V2_MESSAGE_SIZE_INVALID'}
Check 'result_oversized_denied' {$c=[pscustomobject]@{State=[Net.WebSockets.WebSocketState]::Open};ExpectError {Send-EventV2TransientResult $c ([Threading.CancellationToken]::None) @{data=('x'*327681)}} 'WINDOWS_EVENT_V2_TRANSIENT_RESULT_TOO_LARGE'}
$cfg=[pscustomobject]@{device_id='windows-native-lab';architecture='x64'}
Check 'native_transient_health' {$r=Invoke-TransientCall $cfg $call;if($r.state-ne'COMPLETED'-or$r.result.state-ne'PASS'-or$r.result.result.device.agent_version-ne'0.3.51'){throw 'TRANSIENT_HEALTH'}}
Check 'native_transient_replay' {$r=Invoke-TransientCall $cfg $call;if($r.learning_signal.outcome-ne'REPLAYED'){throw 'TRANSIENT_REPLAY'}}
Check 'native_payload_conflict' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.payload=[pscustomobject]@{x='lab'};$r=Invoke-TransientCall $cfg $o;if($r.error_code-ne'IDEMPOTENCY_CONFLICT'){throw 'PAYLOAD_CONFLICT'}}
Check 'native_tool_conflict' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.tool_id='hara.functions.list';$r=Invoke-TransientCall $cfg $o;if($r.error_code-ne'IDEMPOTENCY_CONFLICT'){throw 'TOOL_CONFLICT'}}
Check 'native_replay_only_hit' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.execution_mode='REPLAY_ONLY';$r=Invoke-TransientCall $cfg $o;if($r.learning_signal.outcome-ne'REPLAYED'){throw 'REPLAY_ONLY_HIT'}}
Check 'native_replay_only_miss' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.request_id='LAB-MISS';$o.execution_mode='REPLAY_ONLY';$r=Invoke-TransientCall $cfg $o;if($r.error_code-ne'TRANSIENT_REPLAY_MISS'){throw 'REPLAY_ONLY_MISS'};if(Test-Path(Get-TransientLedgerPath $o)){throw 'REPLAY_MISS_PERSISTED'}}
Check 'native_unknown_tool_denied' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.request_id='LAB-TOOL-UNKNOWN';$o.tool_id='shell.run';$r=Invoke-TransientCall $cfg $o;if($r.state-ne'FAILED'-or$r.error_code-ne'TOOL_ID_INVALID'){throw 'ARBITRARY_TOOL_ALLOWED'}}
Check 'native_device_info_function' {$o=$call|ConvertTo-Json -Depth 5|ConvertFrom-Json;$o.request_id='LAB-DEVICEINFO';$o.tool_id='hara.functions.invoke';$o.payload=[pscustomobject]@{function_id='device.info';arguments=[pscustomobject]@{argv=@()}};$r=Invoke-TransientCall $cfg $o;if($r.state-ne'COMPLETED'-or$r.result.result.function_id-ne'device.info'){throw 'DEVICE_INFO_FUNCTION'}}
Check 'learning_signal_metadata_only' {$r=Invoke-TransientCall $cfg $call;$names=@($r.learning_signal.Keys|Sort-Object);if(($names-join',')-ne'agent_version,customer_content_collected,latency_bucket,outcome,platform,privileged_attempt,result_bytes_bucket,schema,tool_family,tool_id,transport_mode'){throw 'LEARNING_KEYS'};if($r.learning_signal.customer_content_collected-or$r.learning_signal.privileged_attempt){throw 'LEARNING_POLICY'}}
Check 'ledger_payload_values_absent' {$path=Get-TransientLedgerPath $call;$e=Get-Content -Raw -LiteralPath $path|ConvertFrom-Json;if($e.PSObject.Properties.Name-contains'payload'){throw 'LEDGER_PAYLOAD_PRESENT'};if($e.payload_sha256-notmatch'^[a-f0-9]{64}$'){throw 'LEDGER_PAYLOAD_HASH'}}
Check 'ledger_retention_batch' {foreach($i in 1..40){$f=Join-Path $TransientLedgerDir ('expired-'+$i+'.json');[IO.File]::WriteAllText($f,'{}');(Get-Item -LiteralPath $f).LastWriteTimeUtc=[DateTime]::UtcNow.AddHours(-25)};$n=Invoke-TransientLedgerCleanup;if($n-ne32){throw ('CLEANUP_BATCH_'+$n)};$fresh=Get-TransientLedgerPath $call;if(-not(Test-Path $fresh)){throw 'FRESH_LEDGER_REMOVED'}}
