# Separate diagnostic only: never replace a release or change product task/config.
# The exact installed .56 Agent executes only after joining this probe's Job Object.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeReceiptPath)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$sdSid='S-1-5-21-1207901905-1500652706-889822281-1005'
$sdDevice='HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12'
$sdOrigin='https://commander.haralabs.com.br'
$sdController='C:\Users\CommanderQA\Desktop\HARA Commander Conexao QA\Connect-Commander.ps1'
$sdControllerSha='2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da'
$sdAgentSha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
$sdResults='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results'
$sdContext=$null;$sdGuard=$null;$sdJob=$null;$sdPrivate=$null;$sdBefore=$null;$sdReceiptAdmitted=$false
$sdOutFile=$null;$sdErrFile=$null;$sdOutCopy=$null;$sdErrCopy=$null
$sdReport=[ordered]@{schema='hara.commander.windows-startup-diagnostic.v1';state='HOLD';stage='IDENTITY';started_utc=[DateTime]::UtcNow.ToString('o');device_id=$sdDevice;credential_origin=$sdOrigin;installed_files_replaced=$false;product_task_changed=$false;pairing_performed=$false;policy_changed=$false;raw_logs_exported=$false;product_runtime_certified=$false}
function Need-SD([bool]$Okay,[string]$Code){if(-not $Okay){throw $Code}}
function Safe-SD($Failure){
  $message=[string]$Failure.Exception.Message
  if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){return $message}
  return 'STARTUP_DIAGNOSTIC_FAILED'
}
function Policy-SD {
  $value=[ordered]@{}
  foreach($scope in @('MachinePolicy','UserPolicy','Process','CurrentUser','LocalMachine')){$value[$scope]=[string](Get-ExecutionPolicy -Scope $scope)}
  $value.effective=[string](Get-ExecutionPolicy)
  return ($value|ConvertTo-Json -Compress)
}
function Metadata-SD([string]$Path){
  Assert-CCNoReparse $Path
  if(-not(Test-Path -LiteralPath $Path)){return [pscustomobject]@{present=$false}}
  $item=Get-Item -LiteralPath $Path -Force
  $acl=Get-Acl -LiteralPath $Path
  $out=[ordered]@{present=$true;directory=[bool]$item.PSIsContainer;owner_sid=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;group_sid=$acl.GetGroup([Security.Principal.SecurityIdentifier]).Value;protected=$acl.AreAccessRulesProtected;attributes=[string]$item.Attributes;last_write_utc=$item.LastWriteTimeUtc.ToString('o');access=@()}
  foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
    $out.access+=@{sid=$rule.IdentityReference.Value;rights=[string]$rule.FileSystemRights;type=[string]$rule.AccessControlType;inherited=$rule.IsInherited;inheritance=[string]$rule.InheritanceFlags;propagation=[string]$rule.PropagationFlags}
  }
  if(-not $item.PSIsContainer){
    $out.bytes=$item.Length
    $out.zone_id=$null
    $streams=@(Get-Item -LiteralPath $Path -Stream '*' -ErrorAction SilentlyContinue)
    if(@($streams|Where-Object {$_.Stream -ceq 'Zone.Identifier'}).Count){
      $zone=Get-Content -LiteralPath $Path -Stream 'Zone.Identifier' -ErrorAction Stop
      foreach($line in $zone){if($line -cmatch '^ZoneId=([0-4])$'){$out.zone_id=[int]$Matches[1]}}
      $zone=$null
    }
  }
  return [pscustomobject]$out
}
function Runtime-SD {
  $out=[ordered]@{metadata=(Metadata-SD $sdContext.RuntimePath)}
  if($out.metadata.present){
    Need-SD ($out.metadata.bytes -le 262144) 'RUNTIME_METADATA_TOO_LARGE'
    try{
      $runtime=Get-Content -LiteralPath $sdContext.RuntimePath -Raw|ConvertFrom-Json
      foreach($name in @('agent_version','started_at_utc','last_successful_heartbeat_at_utc','updated_at_utc','last_runtime_error_at_utc')){$out[$name]=[string]$runtime.$name}
      if([string]$runtime.last_runtime_error_code -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$out.last_runtime_error_code=[string]$runtime.last_runtime_error_code}
    }catch{$out.parse_failed=$true}
  }
  return [pscustomobject]$out
}
function Processes-SD {
  $out=@()
  $all=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -OperationTimeoutSec 5)
  foreach($row in $all){
    # Inspect only matches; command lines themselves never leave this process.
    if(-not ([string]$row.CommandLine).Contains($sdContext.AgentPath)){continue}
    $owner=Invoke-CimMethod -InputObject $row -MethodName GetOwnerSid -OperationTimeoutSec 5
    $out+=@{pid=[int]$row.ProcessId;parent_pid=[int]$row.ParentProcessId;created_utc=$row.CreationDate.ToUniversalTime().ToString('o');session_id=[int]$row.SessionId;owner_sid=[string]$owner.Sid;executable=[string]$row.ExecutablePath;matches_product_path=$true}
  }
  return $out
}
function Task-SD {
  $task=Get-CCTask $sdContext
  Need-SD ([bool]$task) 'PRODUCT_TASK_MISSING'
  $info=Get-ScheduledTaskInfo -TaskName $sdContext.TaskName -TaskPath '\'
  return [pscustomobject]@{state=[string]$task.State;last_result=[long]$info.LastTaskResult;last_run_utc=$info.LastRunTime.ToUniversalTime().ToString('o');missed_runs=[int]$info.NumberOfMissedRuns}
}
function Events-SD {
  $out=[ordered]@{state='AVAILABLE';rows=@()}
  try{
    $events=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational';StartTime=(Get-Date).AddMinutes(-45)} -MaxEvents 150 -ErrorAction Stop)
    foreach($event in $events){
      $xml=[xml]$event.ToXml();$fields=@{}
      foreach($node in $xml.Event.EventData.Data){$fields[[string]$node.Name]=[string]$node.InnerText}
      if([string]$fields['TaskName'] -cne ('\'+$sdContext.TaskName)){continue}
      $row=[ordered]@{event_id=$event.Id;at_utc=$event.TimeCreated.ToUniversalTime().ToString('o')}
      foreach($key in @('ResultCode','ErrorValue','ProcessID','EnginePID')){if([string]$fields[$key] -cmatch '^(?:[0-9]{1,20}|0x[0-9a-fA-F]{1,16})$'){$row[$key]=[string]$fields[$key]}}
      $out.rows+=@([pscustomobject]$row)
    }
  }catch{$out.state='UNAVAILABLE';$out.error_type=$_.Exception.GetType().FullName}
  return [pscustomobject]$out
}
function SafeLog-SD([string]$Path){
  $item=Get-Item -LiteralPath $Path
  $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
  try{$bytes=New-Object byte[] 65536;$count=$stream.Read($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
  $raw=[Text.Encoding]::UTF8.GetString($bytes,0,$count)
  $out=[ordered]@{bytes=$item.Length;inspected_prefix_bytes=$count;codes=@();error_ids=@();categories=@();locations=@()}
  foreach($match in [regex]::Matches($raw,'(?m)^\s*([A-Z][A-Z0-9_]{2,100})\s*$')){$out.codes+=@($match.Groups[1].Value)}
  foreach($match in [regex]::Matches($raw,'FullyQualifiedErrorId\s*:\s*([A-Za-z][A-Za-z0-9_.-]{0,120})')){$out.error_ids+=@($match.Groups[1].Value)}
  foreach($match in [regex]::Matches($raw,'CategoryInfo\s*:\s*([A-Za-z][A-Za-z0-9]{0,60})')){$out.categories+=@($match.Groups[1].Value)}
  foreach($match in [regex]::Matches($raw,':([0-9]{1,6}) char:([0-9]{1,6})')){$out.locations+=@(@{line=[int]$match.Groups[1].Value;column=[int]$match.Groups[2].Value})}
  $raw=$null;$bytes=$null
  return [pscustomobject]$out
}

try{
  Need-SD ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ceq $sdSid -and $env:USERPROFILE -ceq 'C:\Users\CommanderQA') 'EXPECTED_QA_IDENTITY_REQUIRED'
  $NativeReceiptPath=[IO.Path]::GetFullPath($NativeReceiptPath)
  Need-SD ([IO.Path]::GetDirectoryName($NativeReceiptPath) -ieq $sdResults -and [IO.Path]::GetFileName($NativeReceiptPath) -cmatch '^[A-Za-z0-9_.-]+\.json$') 'DIAGNOSTIC_RECEIPT_PATH_REFUSED'
  Need-SD (-not(Test-Path -LiteralPath $NativeReceiptPath)) 'DIAGNOSTIC_RECEIPT_ALREADY_EXISTS'
  Need-SD ((Get-FileHash -LiteralPath $sdController -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $sdControllerSha) 'FROZEN_CONTROLLER_HASH_MISMATCH'
  . $sdController
  Assert-CCNoReparse $sdResults
  Need-SD (Test-Path -LiteralPath $sdResults -PathType Container) 'DIAGNOSTIC_RESULTS_DIRECTORY_REQUIRED'
  $sdReceiptAdmitted=$true
  $sdContext=New-CCContext $sdOrigin '' 'ASK_EVERY_ACTION'
  $sdGuard=Enter-CCGuard $sdContext
  $sdPrivate=New-CCPrivateStage $sdContext
  $sdReport.private_log_directory=$sdPrivate
  $sdPolicy=Policy-SD
  Need-SD ((Get-ExecutionPolicy) -ceq 'RemoteSigned' -and (Get-ExecutionPolicy -Scope Process) -ceq 'Undefined') 'EXPECTED_POLICY_REQUIRED'
  $sdBefore=Get-CCInstalledState $sdContext
  Need-SD ($sdBefore.DeviceId -ceq $sdDevice -and $sdBefore.Origin -ceq $sdOrigin -and $sdBefore.Version -ceq '0.3.56' -and $sdBefore.AgentSha -ceq $sdAgentSha) 'EXPECTED_ORIGINAL_BINDING_AND_AGENT_REQUIRED'
  Need-SD ((Test-CCCredential $sdBefore) -ceq 'VALID') 'EXISTING_BINDING_INVALID'
  $sdConfigSha=Get-CCFileSha $sdContext.ConfigPath
  $sdTaskXml=Export-ScheduledTask -TaskName $sdContext.TaskName -TaskPath '\'
  $sdReport.before=[ordered]@{task=(Task-SD);runtime=(Runtime-SD);agent=(Metadata-SD $sdContext.AgentPath);config=(Metadata-SD $sdContext.ConfigPath);product_root=(Metadata-SD $sdContext.Root);processes=@(Processes-SD);task_events=(Events-SD);authenticated_binding=$true}
  Need-SD ($sdReport.before.task.state -cne 'Running' -and @($sdReport.before.processes).Count -eq 0) 'LIVE_PRODUCT_AGENT_REFUSES_DIAGNOSTIC_START'
  $sdReport.stage='CONTAINED_EXACT_AGENT_STARTUP'

  # Reuses the native Job Object model in the pinned Agent. A stdin gate ensures
  # no Agent instruction runs until this child is assigned to its private job.
  Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
public sealed class HaraStartupDiagnosticJob : IDisposable {
  [StructLayout(LayoutKind.Sequential)] struct BasicLimits {public long ProcessTime,JobTime;public uint Flags;public UIntPtr MinWorkingSet,MaxWorkingSet;public uint ActiveLimit;public UIntPtr Affinity;public uint Priority,Scheduling;}
  [StructLayout(LayoutKind.Sequential)] struct Counters {public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes;}
  [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {public BasicLimits Basic;public Counters Io;public UIntPtr ProcessMemory,JobMemory,PeakProcessMemory,PeakJobMemory;}
  [StructLayout(LayoutKind.Sequential)] struct Accounting {public long UserTime,KernelTime,PeriodUserTime,PeriodKernelTime;public uint PageFaults,TotalProcesses,ActiveProcesses,TerminatedProcesses;}
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes,string name);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int info,IntPtr value,uint length);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int info,IntPtr value,uint length,IntPtr resultLength);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint exitCode);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  IntPtr job=IntPtr.Zero;readonly string nonce;public readonly Process Child;
  public HaraStartupDiagnosticJob(string shell,string agent) {
    if(agent.IndexOfAny(new char[]{'\'', '"','\r','\n','\0'})>=0) throw new InvalidOperationException("DIAGNOSTIC_PATH_INVALID");
    nonce=Guid.NewGuid().ToString("N");job=CreateJobObject(IntPtr.Zero,null);
    if(job==IntPtr.Zero) throw new InvalidOperationException("DIAGNOSTIC_JOB_CREATE_FAILED");
    try {
      ExtendedLimits limits=new ExtendedLimits();limits.Basic.Flags=0x2000;
      int size=Marshal.SizeOf(typeof(ExtendedLimits));IntPtr buffer=Marshal.AllocHGlobal(size);
      try{Marshal.StructureToPtr(limits,buffer,false);if(!SetInformationJobObject(job,9,buffer,(uint)size))throw new InvalidOperationException("DIAGNOSTIC_JOB_LIMIT_FAILED");}finally{Marshal.FreeHGlobal(buffer);}
      Child=new Process();Child.StartInfo.FileName=shell;
      Child.StartInfo.Arguments="-NoLogo -NoProfile -NonInteractive -Command \"& { $gate=[Console]::ReadLine(); if ($gate -cne '"+nonce+"') { exit 63 }; & '"+agent+"' }\"";
      Child.StartInfo.UseShellExecute=false;Child.StartInfo.CreateNoWindow=true;
      Child.StartInfo.RedirectStandardInput=true;Child.StartInfo.RedirectStandardOutput=true;Child.StartInfo.RedirectStandardError=true;
      if(!Child.Start())throw new InvalidOperationException("DIAGNOSTIC_CHILD_NOT_STARTED");
      if(!AssignProcessToJobObject(job,Child.Handle))throw new InvalidOperationException("DIAGNOSTIC_JOB_ASSIGN_FAILED");
    } catch {
      if(Child!=null){try{if(!Child.HasExited)Child.Kill();Child.WaitForExit(1000);}catch{}}
      if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}throw;
    }
  }
  public void Begin(){Child.StandardInput.WriteLine(nonce);Child.StandardInput.Flush();Child.StandardInput.Close();}
  public uint ActiveProcesses {
    get{int size=Marshal.SizeOf(typeof(Accounting));IntPtr buffer=Marshal.AllocHGlobal(size);
      try{if(job==IntPtr.Zero || !QueryInformationJobObject(job,1,buffer,(uint)size,IntPtr.Zero))throw new InvalidOperationException("DIAGNOSTIC_JOB_ACCOUNTING_FAILED");return ((Accounting)Marshal.PtrToStructure(buffer,typeof(Accounting))).ActiveProcesses;}
      finally{Marshal.FreeHGlobal(buffer);}}
  }
  public bool Stop(){if(job!=IntPtr.Zero && !TerminateJobObject(job,1))return false;Child.WaitForExit(1500);return ActiveProcesses==0;}
  public void Dispose(){if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}if(Child!=null)Child.Dispose();GC.SuppressFinalize(this);}
  ~HaraStartupDiagnosticJob(){if(job!=IntPtr.Zero)CloseHandle(job);}
}
'@
  $sdOutPath=Join-Path $sdPrivate 'startup-stdout.private.bin'
  $sdErrPath=Join-Path $sdPrivate 'startup-stderr.private.bin'
  $sdOutFile=New-Object IO.FileStream($sdOutPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  $sdErrFile=New-Object IO.FileStream($sdErrPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  Need-SD ((Get-CCFileSha $sdContext.AgentPath) -ceq $sdAgentSha -and (Get-CCFileSha $sdContext.ConfigPath) -ceq $sdConfigSha -and (Export-ScheduledTask -TaskName $sdContext.TaskName -TaskPath '\') -ceq $sdTaskXml -and (Task-SD).state -cne 'Running' -and @(Processes-SD).Count -eq 0) 'PREPROBE_PRODUCT_STATE_CHANGED'
  $sdJob=New-Object HaraStartupDiagnosticJob($sdContext.PowerShellExe,$sdContext.AgentPath)
  $sdReport.child=[ordered]@{pid=$sdJob.Child.Id;started_utc=$sdJob.Child.StartTime.ToUniversalTime().ToString('o');job_assigned_before_agent_dispatch=$true;observation_limit_ms=10000;explicit_product_task_restart=$false}
  $sdOutCopy=$sdJob.Child.StandardOutput.BaseStream.CopyToAsync($sdOutFile)
  $sdErrCopy=$sdJob.Child.StandardError.BaseStream.CopyToAsync($sdErrFile)
  $sdJob.Begin()
  $sdExited=$sdJob.Child.WaitForExit(10000)
  $sdReport.child.exited_naturally=$sdExited
  $sdReport.child.active_job_processes_at_observation=$sdJob.ActiveProcesses
  if($sdExited){$sdReport.child.exit_code=$sdJob.Child.ExitCode}
  $sdReport.child.diagnostic_job_terminated=($sdJob.ActiveProcesses -gt 0)
  if($sdReport.child.diagnostic_job_terminated){Need-SD ($sdJob.Stop()) 'DIAGNOSTIC_JOB_STOP_UNCONFIRMED'}
  Need-SD ($sdJob.ActiveProcesses -eq 0) 'DIAGNOSTIC_CHILDREN_NOT_QUIESCENT'
  $sdReport.child.job_quiescent=$true
  Need-SD ($sdOutCopy.Wait(2000) -and $sdErrCopy.Wait(2000)) 'DIAGNOSTIC_PRIVATE_LOG_CAPTURE_INCOMPLETE'
  $sdOutFile.Flush($true);$sdErrFile.Flush($true)
  $sdReport.child.stdout=(SafeLog-SD $sdOutPath);$sdReport.child.stderr=(SafeLog-SD $sdErrPath)
  $sdReport.after=[ordered]@{task=(Task-SD);runtime=(Runtime-SD);processes=@(Processes-SD);agent_preserved=((Get-CCFileSha $sdContext.AgentPath) -ceq $sdAgentSha);config_preserved=((Get-CCFileSha $sdContext.ConfigPath) -ceq $sdConfigSha);task_definition_preserved=((Export-ScheduledTask -TaskName $sdContext.TaskName -TaskPath '\') -ceq $sdTaskXml);policy_preserved=((Policy-SD) -ceq $sdPolicy)}
  Need-SD ($sdReport.after.agent_preserved -and $sdReport.after.config_preserved -and $sdReport.after.task_definition_preserved -and $sdReport.after.policy_preserved -and @($sdReport.after.processes).Count -eq 0) 'DIAGNOSTIC_PRESERVATION_UNCONFIRMED'
  $sdReport.state='DIAGNOSTIC_COMPLETE';$sdReport.stage='COMPLETE'
}catch{
  $sdReport.error_code=Safe-SD $_;$sdReport.error_type=$_.Exception.GetType().FullName
  if($sdPrivate){try{[IO.File]::WriteAllText((Join-Path $sdPrivate 'diagnostic-error.private.txt'),($_|Out-String),[Text.Encoding]::UTF8)}catch{}}
}finally{
  if($sdJob){
    try{if($sdJob.ActiveProcesses -gt 0){$sdReport.finally_job_cleanup_confirmed=$sdJob.Stop()}}catch{$sdReport.finally_job_cleanup_confirmed=$false}
    $sdJob.Dispose()
  }
  if($sdOutFile){$sdOutFile.Dispose()};if($sdErrFile){$sdErrFile.Dispose()}
  if($sdGuard){$sdGuard.ReleaseMutex();$sdGuard.Dispose()}
  $sdBefore=$null;$sdReport.finished_utc=[DateTime]::UtcNow.ToString('o')
  $sdJson=$sdReport|ConvertTo-Json -Depth 12 -Compress
  if($sdReceiptAdmitted -and -not(Test-Path -LiteralPath $NativeReceiptPath)){
    $bytes=[Text.Encoding]::UTF8.GetBytes($sdJson)
    $file=New-Object IO.FileStream($NativeReceiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$file.Write($bytes,0,$bytes.Length);$file.Flush($true)}finally{$file.Dispose()}
  }
}
$sdJson
if($sdReport.state -ceq 'DIAGNOSTIC_COMPLETE'){exit 0}
exit 2
