param([string]$AgentDirectory=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent'))
# Source-only .56 heartbeat integration. Protocol, watchdog, parser, error
# classification and progress functions are real. The socket/task wire I/O,
# monotonic clock and sleep boundary are deterministic fixtures. No network,
# native Agent dispatch, enrollment, key, VM, installer or production is used.
$ErrorActionPreference='Stop'
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
$agentPath=Join-Path $AgentDirectory 'windows.ps1'
$heartbeatPath=Join-Path $AgentDirectory 'event_v2_dev.ps1'
$script:wirePath=(Resolve-Path (Join-Path $AgentDirectory 'event_v2_wire.ps1')).Path
$sourceHashes=[ordered]@{}
foreach($path in @($agentPath,$heartbeatPath,$script:wirePath)){$sourceHashes[(Split-Path $path -Leaf)]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Case([string]$Name,[scriptblock]$Action){
 $script:caseCount++
 try{& $Action | Out-Null;$checks.Add('CASE_'+$Name)}catch{$failures.Add(@{case=$Name;error=$_.Exception.Message;stack=$_.ScriptStackTrace})}
}
function Parse-Source([string]$Path){
 $tokens=$null;$errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $Path),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) ('PARSE_'+(Split-Path $Path -Leaf))
 return $ast
}
$agentTree=Parse-Source $agentPath
$heartbeatTree=Parse-Source $heartbeatPath
$wireTree=Parse-Source $script:wirePath
$functions=@{}
foreach($tree in @($agentTree,$heartbeatTree)){
 foreach($node in $tree.EndBlock.Statements){
  if($node -is [Management.Automation.Language.FunctionDefinitionAst]){$functions[$node.Name]=$node;. ([scriptblock]::Create($node.Extent.Text))}
 }
}
Check ($functions.ContainsKey('Invoke-CommercialEventV2Heartbeat')) 'ACTUAL_0356_HEARTBEAT_DEFINITION'
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
public sealed class HaraHeartbeatResponseFixture {
 public HttpStatusCode StatusCode {get;private set;}
 public HaraHeartbeatResponseFixture(int code){StatusCode=(HttpStatusCode)code;}
}
public sealed class HaraHeartbeatHttpExceptionFixture : Exception {
 public HaraHeartbeatResponseFixture Response {get;private set;}
 public HaraHeartbeatHttpExceptionFixture(int code):base("SYNTHETIC_HANDSHAKE_HTTP_FAILURE"){Response=new HaraHeartbeatResponseFixture(code);}
}
public sealed class HaraHeartbeatFrameFixture {
 public double After;
 public string Text;
 public bool Close;
 public HaraHeartbeatFrameFixture(double after,string text,bool close){After=after;Text=text;Close=close;}
}
public static class HaraHeartbeatFactoryFixture {
 public static double Now;
 public static bool ExtraConnection;
 public static int Created;
 public static readonly Queue<HaraHeartbeatClientFixture> Clients=new Queue<HaraHeartbeatClientFixture>();
 public static void Reset(){Now=1000;ExtraConnection=false;Created=0;Clients.Clear();}
 public static HaraHeartbeatClientFixture Next(){
  if(Clients.Count==0){ExtraConnection=true;throw new InvalidOperationException("QA_UNEXPECTED_RECONNECT");}
  Created++;return Clients.Dequeue();
 }
 public static void Advance(double seconds){Now+=seconds;}
}
public sealed class HaraHeartbeatClientFixture {
 public WebSocketState State {get;private set;}
 public int ConnectStatus,Aborts,Disposals,Receives,ActiveReceives,MaxReceives,PrematureGetResult,ProbeSends,LivenessSends;
 public bool FailProbeSend;
 public double ConnectedAt,FirstAbortAt=-1;
 public readonly Queue<HaraHeartbeatFrameFixture> Frames=new Queue<HaraHeartbeatFrameFixture>();
 public void AddText(double after,string text){Frames.Enqueue(new HaraHeartbeatFrameFixture(after,text,false));}
 public void AddClose(double after){Frames.Enqueue(new HaraHeartbeatFrameFixture(after,null,true));}
 public Task ConnectAsync(Uri uri,CancellationToken cancellation){
  ConnectedAt=HaraHeartbeatFactoryFixture.Now;
  Console.Out.WriteLine("HARA_QA_WIRE=CONNECT");
  if(ConnectStatus!=0){
   var source=new TaskCompletionSource<int>();
   source.SetException(new WebSocketException(WebSocketError.NotAWebSocket,"SYNTHETIC_UPGRADE_REJECTED",new HaraHeartbeatHttpExceptionFixture(ConnectStatus)));
   return source.Task;
  }
  State=WebSocketState.Open;return Task.CompletedTask;
 }
 public Task SendAsync(ArraySegment<byte> bytes,WebSocketMessageType type,bool end,CancellationToken cancellation){
  string text=Encoding.UTF8.GetString(bytes.Array,bytes.Offset,bytes.Count);
  if(text=="HARA_EVENT_V2_PROBE_V1"){
   ProbeSends++;Console.Out.WriteLine("HARA_QA_WIRE=PROBE");
   if(FailProbeSend){var source=new TaskCompletionSource<int>();source.SetException(new InvalidOperationException("SYNTHETIC_PROBE_SEND_FAILURE"));return source.Task;}
  }else{LivenessSends++;Console.Out.WriteLine("HARA_QA_WIRE=OTHER_SEND");}
  return Task.CompletedTask;
 }
 public HaraHeartbeatReceiveTaskFixture ReceiveAsync(ArraySegment<byte> bytes,CancellationToken cancellation){
  Receives++;ActiveReceives++;MaxReceives=Math.Max(MaxReceives,ActiveReceives);
  return new HaraHeartbeatReceiveTaskFixture(this,bytes);
 }
 public void Abort(){Aborts++;if(FirstAbortAt<0)FirstAbortAt=HaraHeartbeatFactoryFixture.Now;State=WebSocketState.Aborted;ActiveReceives=0;}
 public void Dispose(){Disposals++;}
}
public sealed class HaraHeartbeatReceiveTaskFixture {
 readonly HaraHeartbeatClientFixture client;
 readonly ArraySegment<byte> buffer;
 bool ready,consumed;
 WebSocketReceiveResult result;
 public HaraHeartbeatReceiveTaskFixture(HaraHeartbeatClientFixture owner,ArraySegment<byte> bytes){client=owner;buffer=bytes;}
 public bool Wait(int milliseconds){
  if(ready)return true;
  HaraHeartbeatFactoryFixture.Advance(milliseconds/1000.0);
  if(HaraHeartbeatFactoryFixture.Now-client.ConnectedAt>26)throw new InvalidOperationException("QA_WATCHDOG_NO_BOUNDED_EXIT");
  if(client.Frames.Count==0 || HaraHeartbeatFactoryFixture.Now-client.ConnectedAt<client.Frames.Peek().After)return false;
  var frame=client.Frames.Dequeue();
  if(frame.Close)result=new WebSocketReceiveResult(0,WebSocketMessageType.Close,true,(WebSocketCloseStatus)4003,"SYNTHETIC_REVOKED");
  else{
   var data=Encoding.UTF8.GetBytes(frame.Text);Array.Copy(data,0,buffer.Array,buffer.Offset,data.Length);
   result=new WebSocketReceiveResult(data.Length,WebSocketMessageType.Text,true);
  }
  ready=true;return true;
 }
 public HaraHeartbeatReceiveTaskFixture GetAwaiter(){return this;}
 public WebSocketReceiveResult GetResult(){
  if(!ready){client.PrematureGetResult++;throw new InvalidOperationException("QA_GETRESULT_BEFORE_TASK_READY");}
  if(!consumed){client.ActiveReceives--;consumed=true;}
  return result;
 }
}
public sealed class HaraHeartbeatWakeFixture {
 public int Sets;
 public bool Set(){Sets++;Console.Out.WriteLine("HARA_QA_WIRE=WAKE");return true;}
}
'@
# Keep the function body unchanged except its module-import seam. The seam
# imports the real adjacent wire, then substitutes only the socket factory.
# Protocol/watchdog/parser implementations therefore execute unmodified.
$script:wireFixture={
 . $script:wirePath -ImportOnly
 function New-EventV2Client([string]$DeviceToken){
  if($DeviceToken -cne 'synthetic-0356-qa-token-not-a-real-credential'){throw 'QA_UNEXPECTED_CREDENTIAL'}
  return [HaraHeartbeatFactoryFixture]::Next()
 }
}
$heartbeat=$functions['Invoke-CommercialEventV2Heartbeat']
$imports=@($heartbeat.Body.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst] -and $n.InvocationOperator -eq [Management.Automation.Language.TokenKind]::Dot},$true))
Check ($imports.Count -eq 1 -and $imports[0].Extent.Text.Contains("'event_v2_wire.ps1'")) 'ONLY_ADJACENT_0356_WIRE_IMPORT_SEAM'
$relative=$imports[0].Extent.StartOffset-$heartbeat.Extent.StartOffset
$definition=$heartbeat.Extent.Text.Remove($relative,$imports[0].Extent.Text.Length).Insert($relative,'. $script:wireFixture')
. ([scriptblock]::Create($definition))
function Get-WindowsRelayNow {return [HaraHeartbeatFactoryFixture]::Now}
function Start-Sleep([int]$Milliseconds=0,[double]$Seconds=0){
 if([HaraHeartbeatFactoryFixture]::ExtraConnection){throw 'QA_FIXTURE_END_AFTER_UNEXPECTED_RECONNECT'}
 [HaraHeartbeatFactoryFixture]::Advance($Seconds+$Milliseconds/1000.0)
}
function Invoke-Scenario([HaraHeartbeatClientFixture[]]$Clients){
 [HaraHeartbeatFactoryFixture]::Reset()
 foreach($client in $Clients){[HaraHeartbeatFactoryFixture]::Clients.Enqueue($client)}
 $signal=[HaraHeartbeatWakeFixture]::new()
 $cfg=[pscustomobject]@{event_v2_dev_enabled=$true;environment='DEV';base_url='https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev'}
 $priorOut=[Console]::Out
 $capture=New-Object IO.StringWriter
 $script:WindowsRelayWorkerMode=$true
 $script:AgentVersion='0.3.56'
 $script:RuntimeStatus=Join-Path ([IO.Path]::GetTempPath()) ('hara-0356-heartbeat-fixture-'+[guid]::NewGuid().ToString('N')+'.json')
 $caught=$null
 try{
  [Console]::SetOut($capture)
  try{Invoke-CommercialEventV2Heartbeat $cfg 'synthetic-0356-qa-token-not-a-real-credential' $signal | Out-Null}catch{$caught=$_.Exception.Message}
 }finally{
  [Console]::SetOut($priorOut)
  foreach($path in @($script:RuntimeStatus,($script:RuntimeStatus+'.tmp'))){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}}
 }
 $lines=@($capture.ToString().Split([char]10) | ForEach-Object {$_.TrimEnd([char]13)} | Where-Object {$_})
 $capture.Dispose()
 $progress=@($lines | Where-Object {$_.StartsWith('HARA_RELAY_PROGRESS=')} | ForEach-Object {$_.Substring(20) | ConvertFrom-Json})
 return @{lines=$lines;progress=$progress;signal=$signal;created=[HaraHeartbeatFactoryFixture]::Created;unexpected=[HaraHeartbeatFactoryFixture]::ExtraConnection;caught=$caught}
}
Case 'initial-probe-ack-and-wake-use-real-wire-parser' {
 $client=[HaraHeartbeatClientFixture]::new()
 $client.AddText(1,'HARA_EVENT_V2_PROBE_ACK_V1')
 $client.AddText(1.5,'{"schema":"hara.commander-device-event.v2","type":"CALL_AVAILABLE","call_id":"synthetic-call"}')
 $client.AddClose(2)
 $run=Invoke-Scenario @($client)
 Check (-not $run.unexpected -and $null -eq $run.caught -and $run.created -eq 1) 'ONE_AUTHENTICATED_CONNECTION_NO_RETRY_AFTER_4003'
 Check ($client.ProbeSends -eq 1 -and $client.LivenessSends -eq 0) 'IMMEDIATE_INITIAL_PROBE_WITHOUT_DURABLE_HEARTBEAT'
 $joined=$run.lines -join "`n"
 Check ($joined.IndexOf('HARA_QA_WIRE=PROBE') -ge 0 -and $joined.IndexOf('HARA_QA_WIRE=PROBE') -lt $joined.IndexOf('"kind":"HEARTBEAT_CONFIRMED"')) 'UPGRADE_OR_PID_ALONE_IS_NOT_CONFIRMED_HEALTH'
 Check (@($run.progress | Where-Object kind -ceq 'HEARTBEAT_CONFIRMED').Count -eq 1 -and $run.signal.Sets -eq 2) 'ACK_AND_WAKE_ONLY_SIGNAL_EXECUTOR'
 Check (@($run.progress | Where-Object {$_.kind -ceq 'REVOKED' -and $_.code -ceq 'EVENT_V2_AUTHORIZATION_ENDED'}).Count -eq 1) 'CLOSE_4003_REVOKES_WITHOUT_RECONNECT'
 Check ($client.PrematureGetResult -eq 0 -and $client.MaxReceives -eq 1 -and $client.Disposals -eq 1) 'ONE_RECEIVE_AND_RESULT_ONLY_AFTER_TASK_SUCCESS'
}
Case 'missing-probe-ack-deadline-retries-without-false-health' {
 $stalled=[HaraHeartbeatClientFixture]::new()
 $terminal=[HaraHeartbeatClientFixture]::new();$terminal.AddClose(.5)
 $run=Invoke-Scenario @($stalled,$terminal)
 Check (-not $run.unexpected -and $run.created -eq 2) 'DEAD_CHANNEL_RECONNECTS_ONCE_IN_FIXTURE'
 Check (@($run.progress | Where-Object {$_.kind -ceq 'HEARTBEAT_RETRY' -and $_.code -ceq 'WINDOWS_EVENT_V2_PONG_TIMEOUT'}).Count -eq 1) 'MISSING_ACK_CLASSIFIED_PONG_TIMEOUT'
 Check ($stalled.FirstAbortAt-$stalled.ConnectedAt -ge 20 -and $stalled.FirstAbortAt-$stalled.ConnectedAt -le 20.5) 'DEFAULT_20_SECOND_PROBE_DEADLINE_UNIT_CLOCK'
 Check (@($run.progress | Where-Object kind -ceq 'HEARTBEAT_CONFIRMED').Count -eq 0 -and $run.signal.Sets -eq 0) 'MISSING_ACK_NEVER_CONFIRMS_OR_EXECUTES'
}
Case 'failed-probe-send-cannot-be-confirmed-by-received-ack' {
 $faulted=[HaraHeartbeatClientFixture]::new();$faulted.FailProbeSend=$true
 $faulted.AddText(.5,'HARA_EVENT_V2_PROBE_ACK_V1');$faulted.AddClose(1)
 $terminal=[HaraHeartbeatClientFixture]::new();$terminal.AddClose(.5)
 $run=Invoke-Scenario @($faulted,$terminal)
 Check (@($run.progress | Where-Object kind -ceq 'HEARTBEAT_CONFIRMED').Count -eq 0 -and $run.signal.Sets -eq 0) 'FAILED_PROBE_SEND_IS_NOT_SUCCESSFUL_HEALTH'
 Check ($faulted.Aborts -gt 0) 'FAILED_SEND_FENCED_BEFORE_RETRY'
}
foreach($status in @(401,403)){
 Case ('nested-upgrade-http-'+$status+'-must-revoke') {
  $client=[HaraHeartbeatClientFixture]::new();$client.ConnectStatus=$status
  $run=Invoke-Scenario @($client)
  Check (-not $run.unexpected -and $null -eq $run.caught -and $run.created -eq 1) 'AUTHENTICATION_REJECTION_STOPS_RECONNECT_LOOP'
  Check (@($run.progress | Where-Object {$_.kind -ceq 'REVOKED' -and $_.code -ceq ('HTTP_'+$status)}).Count -eq 1) 'NESTED_TYPED_HTTP_STATUS_PRESERVED'
  Check (@($run.progress | Where-Object {$_.kind -ceq 'HEARTBEAT_RETRY' -and $_.code -cne 'EVENT_V2_RECONNECT_WAIT'}).Count -eq 0) 'AUTH_DENIAL_IS_NOT_TRANSIENT_NETWORK_RETRY'
 }
}
Case 'source-path-tool-isolation-and-bounded-send-contract' {
 $body=$heartbeat.Body.Extent.Text
 Check ($body.Contains("'event_v2_wire.ps1'") -and -not $body.Contains('StableAgent') -and -not $body.Contains('Import-StableAgentFunctions')) 'SOURCE_ADJACENT_WIRE_NOT_ANOTHER_INSTALLED_AGENT'
 $commands=@($heartbeat.Body.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst]},$true) | ForEach-Object {$_.GetCommandName()})
 Check (@($commands | Where-Object {$_ -cin @('Invoke-Tool','Invoke-WindowsRelayCall','Invoke-DurableDrain','Send-EventV2TransientResult')}).Count -eq 0) 'HEARTBEAT_PROCESS_NEVER_EXECUTES_TOOLS'
 $wait=@($wireTree.EndBlock.Statements | Where-Object {$_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq 'Wait-EventV2Send'})
 Check ($wait.Count -eq 1 -and $wait[0].Extent.Text.Contains('$TimeoutMs=20000') -and $wait[0].Extent.Text.Contains('$TimeoutMs -gt 20000')) 'WIRE_SEND_WAIT_MAXIMUM_20_SECONDS'
}
@{state=$(if($failures.Count){'FAIL_COMMERCIAL_0356_HEARTBEAT_SOURCE_QA'}else{'PASS_COMMERCIAL_0356_HEARTBEAT_SOURCE_QA'});cases=$caseCount;checks=$checks.Count;failures=$failures.ToArray();source_sha256=$sourceHashes;actual_0356_progress_and_admission=$true;actual_adjacent_wire_protocol=$true;deterministic_socket_task_clock_fixture=$true;native_vm_acceptance=$false;native_wake_acl_acceptance=$false;network_used=$false;installed=$false} | ConvertTo-Json -Depth 7
if($failures.Count){exit 1}
