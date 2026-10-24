param(
 [string]$TransportPath=(Join-Path $PSScriptRoot '../experimental/event_v2_windows_transport.ps1'),
 [string]$AdapterPath=(Join-Path $PSScriptRoot '../experimental/event_v2_windows_agent.ps1')
)
# Definitions-only Event V2 transport QA, with a fake .NET-shaped socket and a
# deterministic monotonic clock. No Agent dispatch, connection, credential,
# VM, deployment, hosted endpoint, or native Windows acceptance is involved.
$ErrorActionPreference='Stop'
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Case([string]$Name,[scriptblock]$Action){
 $script:caseCount++
 try{& $Action | Out-Null;$checks.Add('CASE_'+$Name)}catch{$failures.Add(@{case=$Name;error=$_.Exception.Message;stack=$_.ScriptStackTrace})}
}
function Denied([scriptblock]$Action,[string]$Code){
 $denied=$false
 try{& $Action | Out-Null}catch{$denied=$_.Exception.Message.Contains($Code)}
 Check $denied $Code
}
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $TransportPath),[ref]$tokens,[ref]$errors)
Check ($errors.Count -eq 0) 'TRANSPORT_PARSE'
. $TransportPath -ImportOnly
Check ($KeepAliveSeconds -eq 60) 'LEGACY_KEEPALIVE_DEFAULT_UNCHANGED'
$sourceSha=(Get-FileHash -LiteralPath $TransportPath -Algorithm SHA256).Hash.ToLowerInvariant()
$adapterSha=(Get-FileHash -LiteralPath $AdapterPath -Algorithm SHA256).Hash.ToLowerInvariant()
$required=@('New-EventV2Watchdog','Step-EventV2Watchdog','Confirm-EventV2Watchdog','Wait-EventV2Send','Wait-EventV2ProbeSend')
$missing=@($required | Where-Object {-not (Get-Command $_ -CommandType Function -ErrorAction SilentlyContinue)})
if($missing.Count){
 @{state='RED_WINDOWS_EVENT_V2_WATCHDOG_ABSENT';missing=$missing;checks=$checks.Count;transport_sha256=$sourceSha;adapter_sha256=$adapterSha;installed=$false;network_used=$false;windows_native=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)} | ConvertTo-Json -Depth 5
 exit 2
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
public sealed class HaraEventV2WatchdogSocketFixture {
 public WebSocketState State {get;set;}
 public readonly List<string> Sent=new List<string>();
 public int Aborts,ReceiveCalls,ConcurrentReceives,MaxConcurrentReceives,ActiveSends,MaxConcurrentSends;
 public bool HoldSends=false;
 public bool LastEndOfMessage;
 public WebSocketMessageType LastMessageType;
 public CancellationToken LastSendToken;
 readonly TaskCompletionSource<int> pendingSend=new TaskCompletionSource<int>();
 readonly TaskCompletionSource<WebSocketReceiveResult> pendingReceive=new TaskCompletionSource<WebSocketReceiveResult>();
 Timer releaseTimer;
 public Task PendingSend {get{return pendingSend.Task;}}
 public HaraEventV2WatchdogSocketFixture(){State=WebSocketState.Open;}
 public Task SendAsync(ArraySegment<byte> bytes,WebSocketMessageType type,bool end,CancellationToken token){
  if(token.IsCancellationRequested) return Task.FromCanceled(token);
  if(State!=WebSocketState.Open) throw new InvalidOperationException("QA_SOCKET_NOT_OPEN");
  if(ActiveSends!=0) throw new InvalidOperationException("QA_CONCURRENT_SEND_NOT_SUPPORTED");
  ActiveSends++;MaxConcurrentSends=Math.Max(MaxConcurrentSends,ActiveSends);
  Sent.Add(Encoding.UTF8.GetString(bytes.Array,bytes.Offset,bytes.Count));
  LastMessageType=type;LastEndOfMessage=end;LastSendToken=token;
  if(HoldSends) return pendingSend.Task;
  ActiveSends=0;return Task.CompletedTask;
 }
 public Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> bytes,CancellationToken token){
  ReceiveCalls++;ConcurrentReceives++;
  MaxConcurrentReceives=Math.Max(MaxConcurrentReceives,ConcurrentReceives);
  return pendingReceive.Task;
 }
 public void Abort(){
  Aborts++;State=WebSocketState.Aborted;
  ActiveSends=0;pendingSend.TrySetCanceled();pendingReceive.TrySetCanceled();ConcurrentReceives=0;
 }
 public void CompleteSendAfter(int milliseconds){
  releaseTimer=new Timer(delegate(object value){
   ActiveSends=0;HoldSends=false;pendingSend.TrySetResult(0);
  },null,milliseconds,Timeout.Infinite);
 }
 public static Task FaultedSend(){
  var source=new TaskCompletionSource<int>();
  source.SetException(new InvalidOperationException("SYNTHETIC_SEND_FAILURE"));return source.Task;
 }
}
'@
$none=[Threading.CancellationToken]::None
$probe='HARA_EVENT_V2_PROBE_V1'
$ack='HARA_EVENT_V2_PROBE_ACK_V1'
Case 'quiet-until-default-probe' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 foreach($n in @(0,1,30,59.999)){Step-EventV2Watchdog $s $c $none $n | Out-Null}
 Check ($c.Sent.Count -eq 0) 'NO_PROBE_BEFORE_60_SECONDS'
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 Check ($c.Sent.Count -eq 1 -and $c.Sent[0] -ceq $probe) 'EXACT_ONE_STATIC_HIBERNATION_PROBE'
 Check ($c.LastMessageType -eq [Net.WebSockets.WebSocketMessageType]::Text -and $c.LastEndOfMessage) 'PROBE_SINGLE_COMPLETE_TEXT_FRAME'
 Check (-not $c.Sent[0].Contains('LIVENESS') -and -not $c.Sent[0].Contains('device_id') -and -not $c.Sent[0].Contains('Bearer')) 'PROBE_METADATA_AND_DURABLE_WRITE_FREE'
}
Case 'missing-ack-aborts-at-80-default-seconds' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 Step-EventV2Watchdog $s $c $none 79.999 | Out-Null
 Check ($c.Aborts -eq 0 -and $c.Sent.Count -eq 1) 'WAIT_FULL_20_SECOND_ACK_WINDOW'
 Denied {Step-EventV2Watchdog $s $c $none 80} 'WINDOWS_EVENT_V2_PONG_TIMEOUT'
 Check ($c.Aborts -eq 1 -and $c.State -eq [Net.WebSockets.WebSocketState]::Aborted) 'ZOMBIE_SOCKET_ABORTED'
}
Case 'correlated-ack-keeps-connection-and-resumes-probes' {
 $s=New-EventV2Watchdog 100
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 Step-EventV2Watchdog $s $c $none 160 | Out-Null
 Check (Confirm-EventV2Watchdog $s $ack 161) 'PENDING_ACK_CONFIRMED'
 Check (-not (Confirm-EventV2Watchdog $s $ack 162)) 'DUPLICATE_ACK_NOT_NEW_CONFIRMATION'
 Step-EventV2Watchdog $s $c $none 219.999 | Out-Null
 Check ($c.Sent.Count -eq 1 -and $c.Aborts -eq 0) 'ACK_PREVENTS_FALSE_TIMEOUT_WITHOUT_HOT_PROBE'
 Step-EventV2Watchdog $s $c $none 221 | Out-Null
 Check ($c.Sent.Count -eq 2 -and $c.Sent[1] -ceq $probe) 'NEXT_PROBE_AFTER_CONFIRMED_RECOVERY'
}
Case 'unrelated-and-malformed-frames-do-not-prove-pong' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 foreach($text in @($probe,($ack+'x'),$ack.ToLowerInvariant(),'{"schema":"hara.commander-device-event.v2","type":"CALL_AVAILABLE","call_id":"synthetic"}')){
  Check (-not (Confirm-EventV2Watchdog $s $text 61)) 'ONLY_EXACT_PENDING_ACK_PROVES_PONG'
 }
 Denied {Step-EventV2Watchdog $s $c $none 80} 'WINDOWS_EVENT_V2_PONG_TIMEOUT'
 Check ($c.Aborts -eq 1) 'WAKE_TRAFFIC_DOES_NOT_MASK_MISSING_ACK'
}
Case 'late-ack-cannot-resurrect-expired-watchdog' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 Check (-not (Confirm-EventV2Watchdog $s $ack 80.001)) 'LATE_ACK_NOT_ACCEPTED'
 Denied {Step-EventV2Watchdog $s $c $none 80.001} 'WINDOWS_EVENT_V2_PONG_TIMEOUT'
}
Case 'reconnect-resets-confirmation-and-deadline' {
 $old=New-EventV2Watchdog 0
 $oldClient=[HaraEventV2WatchdogSocketFixture]::new()
 Step-EventV2Watchdog $old $oldClient $none 60 | Out-Null
 $fresh=New-EventV2Watchdog 70
 $freshClient=[HaraEventV2WatchdogSocketFixture]::new()
 Check (-not (Confirm-EventV2Watchdog $fresh $ack 71)) 'OLD_OR_UNSOLICITED_ACK_NOT_NEW_CONNECTION_LIVENESS'
 Step-EventV2Watchdog $fresh $freshClient $none 129.999 | Out-Null
 Check ($freshClient.Sent.Count -eq 0 -and $freshClient.Aborts -eq 0) 'RECONNECT_DOES_NOT_INHERIT_OLD_PENDING_DEADLINE'
 Step-EventV2Watchdog $fresh $freshClient $none 130 | Out-Null
 Check (Confirm-EventV2Watchdog $fresh $ack 131) 'FRESH_CONNECTION_REQUIRES_OWN_PROBE_ACK'
 Check ($oldClient.Aborts -eq 0) 'NEW_STATE_DOES_NOT_SIGNAL_OLD_SOCKET'
}
Case 'cancellation-prevents-further-probes' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 $cts=[Threading.CancellationTokenSource]::new()
 try{
  $cts.Cancel()
  try{Step-EventV2Watchdog $s $c $cts.Token 60 | Out-Null}catch [OperationCanceledException]{}
  Check ($c.Sent.Count -eq 0) 'NO_PROBE_AFTER_LOCAL_STOP_CANCELLATION'
 }finally{$cts.Dispose()}
}
Case 'closed-socket-has-no-new-send' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 $c.State=[Net.WebSockets.WebSocketState]::Closed
 try{Step-EventV2Watchdog $s $c $none 60 | Out-Null}catch{
  Check ($_.Exception.Message -notlike '*PONG_TIMEOUT*') 'CLOSED_SOCKET_NOT_MISREPORTED_AS_PENDING_PONG'
 }
 Check ($c.Sent.Count -eq 0 -and $c.Aborts -eq 0) 'CLOSED_SOCKET_NOT_REUSED_OR_RESURRECTED'
}
Case 'pending-send-and-receive-never-build-up' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 $c.HoldSends=$true
 $receive=Start-EventV2Receive $c $none
 $watch=[Diagnostics.Stopwatch]::StartNew()
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 $watch.Stop()
 Check ($watch.Elapsed.TotalSeconds -lt 1) 'PENDING_SEND_DOES_NOT_BLOCK_WATCHDOG_THREAD'
 foreach($n in 61..79){Step-EventV2Watchdog $s $c $none ([double]$n) | Out-Null}
 Check ($c.Sent.Count -eq 1) 'ONE_PROBE_SEND_IN_FLIGHT'
 Check ($c.ReceiveCalls -eq 1 -and $c.MaxConcurrentReceives -eq 1 -and -not $receive.Task.IsCompleted) 'WATCHDOG_REUSES_SINGLE_OUTSTANDING_RECEIVE'
 Denied {Step-EventV2Watchdog $s $c $none 80} 'WINDOWS_EVENT_V2_PONG_TIMEOUT'
 Check ($receive.Task.IsCompleted -and $c.Aborts -eq 1) 'TIMEOUT_ABORT_RELEASES_PENDING_RECEIVE'
}
Case 'bounded-send-completed-and-faulted-task' {
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 Wait-EventV2Send ([Threading.Tasks.Task]::CompletedTask) $c $none | Out-Null
 Check ($c.Aborts -eq 0) 'COMPLETED_SEND_NEEDS_NO_ABORT'
 Denied {Wait-EventV2Send ([HaraEventV2WatchdogSocketFixture]::FaultedSend()) $c $none 20} 'SYNTHETIC_SEND_FAILURE'
}
Case 'bounded-send-pending-times-out-and-aborts' {
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 $watch=[Diagnostics.Stopwatch]::StartNew()
 Denied {Wait-EventV2Send $c.PendingSend $c $none 20} 'WINDOWS_EVENT_V2_SEND_TIMEOUT'
 $watch.Stop()
 Check ($watch.Elapsed.TotalSeconds -lt 1 -and $c.Aborts -eq 1) 'SEND_TIMEOUT_ABORT_BOUNDED_UNDER_ONE_SECOND'
 Check ($c.PendingSend.IsCompleted) 'SEND_TIMEOUT_ABORT_RELEASES_PENDING_TASK'
}
Case 'bounded-send-timeout-cannot-be-extended-or-disabled' {
 foreach($timeoutMs in @(-1,0,20001,2147483647)){
  $c=[HaraEventV2WatchdogSocketFixture]::new()
  $denied=$false
  $watch=[Diagnostics.Stopwatch]::StartNew()
  try{Wait-EventV2Send ([Threading.Tasks.Task]::CompletedTask) $c $none $timeoutMs | Out-Null}catch{$denied=$true}
  $watch.Stop()
  Check ($denied -and $watch.Elapsed.TotalSeconds -lt 1) 'INVALID_SEND_TIMEOUT_FAILS_CLOSED'
 }
 foreach($timeoutMs in @(1,20000)){
  $c=[HaraEventV2WatchdogSocketFixture]::new()
  Wait-EventV2Send ([Threading.Tasks.Task]::CompletedTask) $c $none $timeoutMs | Out-Null
  Check ($c.Aborts -eq 0) 'VALID_SEND_TIMEOUT_RANGE_ACCEPTED'
 }
}
Case 'bounded-send-propagates-cancellation' {
 foreach($alreadyCanceled in @($true,$false)){
  $c=[HaraEventV2WatchdogSocketFixture]::new()
  $cts=[Threading.CancellationTokenSource]::new()
  try{
   if($alreadyCanceled){$cts.Cancel()}else{$cts.CancelAfter(20)}
   $seen=$false
   $watch=[Diagnostics.Stopwatch]::StartNew()
   try{Wait-EventV2Send $c.PendingSend $c $cts.Token 500 | Out-Null}catch{
    $seen=$_.Exception -is [OperationCanceledException] -or $_.Exception.InnerException -is [OperationCanceledException]
    Check (-not $_.Exception.Message.Contains('WINDOWS_EVENT_V2_SEND_TIMEOUT')) 'CANCEL_NOT_MISREPORTED_AS_SEND_TIMEOUT'
   }
   $watch.Stop()
   Check ($seen -and $watch.Elapsed.TotalSeconds -lt 1) 'SEND_WAIT_LOCAL_CANCELLATION_PROPAGATED'
  }finally{$cts.Dispose()}
 }
}
Case 'confirmed-pong-retains-pending-send-fence' {
 $s=New-EventV2Watchdog 0
 $c=[HaraEventV2WatchdogSocketFixture]::new()
 $c.HoldSends=$true
 Step-EventV2Watchdog $s $c $none 60 | Out-Null
 Confirm-EventV2Watchdog $s $ack 61 | Out-Null
 Check ($c.ActiveSends -eq 1) 'PONG_DOES_NOT_COMPLETE_CLIENT_SEND_TASK'
 $c.CompleteSendAfter(80)
 Wait-EventV2ProbeSend $s $c $none 61 | Out-Null
 Check ($c.PendingSend.IsCompleted) 'PROBE_SEND_FENCED_EVEN_AFTER_PONG_CONFIRMED'
 Send-EventV2Liveness $c $none | Out-Null
 Check ($c.Sent.Count -eq 2 -and $c.MaxConcurrentSends -eq 1 -and $c.Aborts -eq 0) 'LIVENESS_SEND_SERIALIZED_AFTER_PROBE_SEND'
 Check ($c.ReceiveCalls -eq 0) 'SEND_FENCE_DOES_NOT_CREATE_RECEIVE_TASK'
}
Case 'send-helpers-use-bounded-wait-at-real-boundary' {
 $script:realWait=(Get-Command Wait-EventV2Send -CommandType Function).ScriptBlock
 $script:waitCalls=0
 function Wait-EventV2Send($Task,$Client,[Threading.CancellationToken]$CancellationToken,[int]$TimeoutMs=20000){
  $script:waitCalls++
  Check ($TimeoutMs -ge 1 -and $TimeoutMs -le 20000) 'APPLICATION_SEND_USES_BOUNDED_POLICY'
  & $script:realWait $Task $Client $CancellationToken 20
 }
 try{
  foreach($kind in @('liveness','transient')){
   $c=[HaraEventV2WatchdogSocketFixture]::new()
   $c.HoldSends=$true
   $watch=[Diagnostics.Stopwatch]::StartNew()
   if($kind -ceq 'liveness'){
    Denied {Send-EventV2Liveness $c $none} 'WINDOWS_EVENT_V2_SEND_TIMEOUT'
   }else{
    Denied {Send-EventV2TransientResult $c $none @{schema='hara.commander-device-event.v2';type='TRANSIENT_RESULT';call_id='synthetic';request_id='synthetic';state='COMPLETED';result=@{}}} 'WINDOWS_EVENT_V2_SEND_TIMEOUT'
   }
   $watch.Stop()
   Check ($c.Aborts -eq 1 -and $watch.Elapsed.TotalSeconds -lt 1) ('BOUNDED_REAL_SEND_HELPER_'+$kind)
  }
  Check ($script:waitCalls -eq 2) 'BOTH_APPLICATION_SEND_HELPERS_USE_BOUNDED_WAIT'
 }finally{Set-Item -Path function:Wait-EventV2Send -Value $script:realWait}
}
Case 'ack-is-consumed-before-wake-dispatch' {
 $tokens=$null;$errors=$null
 $agentAst=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AdapterPath),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) 'ADAPTER_PARSE'
 $function=$agentAst.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Invoke-ConnectedSession'},$true)
 Check ($function.Count -eq 1) 'EXACT_CONNECTED_SESSION_DEFINITION'
 $body=$function[0].Body
 $commands=@($body.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst]},$true))
 $new=@($commands | Where-Object {$_.GetCommandName() -ceq 'New-EventV2Watchdog'})
 $step=@($commands | Where-Object {$_.GetCommandName() -ceq 'Step-EventV2Watchdog'})
 $confirm=@($commands | Where-Object {$_.GetCommandName() -ceq 'Confirm-EventV2Watchdog'})
 $parse=@($commands | Where-Object {$_.GetCommandName() -ceq 'Parse-EventV2Wake'})
 Check ($new.Count -eq 1 -and $step.Count -eq 1 -and $confirm.Count -eq 1) 'ONE_WATCHDOG_BOUND_TO_CONNECTED_SESSION'
 Check ($parse.Count -eq 1 -and $confirm[0].Extent.StartOffset -lt $parse[0].Extent.StartOffset) 'ACK_CLASSIFIED_BEFORE_WAKE_PARSER'
 $if=$confirm[0].Parent
 while($null -ne $if -and $if -isnot [Management.Automation.Language.IfStatementAst]){$if=$if.Parent}
 Check ($null -ne $if -and @($if.FindAll({param($n)$n -is [Management.Automation.Language.ContinueStatementAst]},$true)).Count -eq 1) 'ACCEPTED_ACK_SKIPS_TOOL_AND_DURABLE_DISPATCH'
 Check (@($commands | Where-Object {$_.GetCommandName() -ceq 'Start-EventV2Receive'}).Count -eq 2) 'SINGLE_INITIAL_RECEIVE_AND_REARM_ONLY_ON_COMPLETION'
 $text=$body.Extent.Text
 Check (-not $text.Contains('/api/device/heartbeat')) 'WATCHDOG_DOES_NOT_ADD_DURABLE_HTTP_HEARTBEAT'
 Check ($text.Contains('Get-DurableLivenessSeconds')) 'DURABLE_LIVENESS_REMAINS_SEPARATE'
 foreach($helperName in @('Send-EventV2Liveness','Send-EventV2TransientResult')){
  $sender=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $helperName},$true))
  $wait=@($sender[0].Body.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -ceq 'Wait-EventV2Send'},$true))
  Check ($wait.Count -eq 1) ('BOUNDED_SEND_AST_WIRING_'+$helperName)
 }
 $applicationSends=@($commands | Where-Object {$_.GetCommandName() -cin @('Send-EventV2Liveness','Send-EventV2TransientResult')})
 Check ($applicationSends.Count -eq 2) 'EXACT_CONNECTED_APPLICATION_SEND_SITES'
 foreach($send in $applicationSends){
  $scope=$send.Parent;$fenced=$false
  while($null -ne $scope -and $scope -isnot [Management.Automation.Language.FunctionDefinitionAst]){
   if($scope -is [Management.Automation.Language.StatementBlockAst]){
    $prior=@($scope.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -ceq 'Wait-EventV2ProbeSend'},$true) | Where-Object {
     $ancestor=$_.Parent
     while($null -ne $ancestor -and $ancestor -isnot [Management.Automation.Language.StatementBlockAst]){$ancestor=$ancestor.Parent}
     $ancestor -eq $scope -and $_.Extent.EndOffset -lt $send.Extent.StartOffset
    })
    if($prior.Count -gt 0){$fenced=$true;break}
   }
   $scope=$scope.Parent
  }
  Check $fenced ('PROBE_FENCE_BEFORE_'+$send.GetCommandName())
 }
}
@{state=$(if($failures.Count){'FAIL_WINDOWS_EVENT_V2_WATCHDOG'}else{'PASS_WINDOWS_EVENT_V2_WATCHDOG_SOURCE_QA'});checks=$checks.Count;cases=$caseCount;failures=$failures.ToArray();transport_sha256=$sourceSha;adapter_sha256=$adapterSha;windows_native=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT);native_vm_acceptance=$false;installed=$false;network_used=$false} | ConvertTo-Json -Depth 7
if($failures.Count){exit 1}
