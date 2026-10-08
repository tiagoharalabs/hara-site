$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$RuntimeStatus = Join-Path $Root "runtime-status.json"
$SessionPath = Join-Path $Root "operator-session.json"
$ConsoleEvents = Join-Path $Root "console-events.jsonl"
$OperationsDb = Join-Path $Root "operations.sqlite3"
$SessionMaxHours = 12
$AgentVersion = "0.3.42"
$SloProfile = "INTERNAL_BETA_V1"
$SloMinSuccessPercent = 99.0
$SloP50MaxMs = 1000
$SloP95MaxMs = 6000
$SloP99MaxMs = 12000
$SloMinLatencySamples = 20
$SloLatencySampleMax = 5000
$HeartbeatSeconds = 60
$CallPollHotSeconds = 2
$CallPollIdleSeconds = 10
$CallPollHotWindowSeconds = 120
$CallPollStartupHotSeconds = 30
$RateLimitBackoffInitialSeconds = 30
$RateLimitBackoffMaxSeconds = 300
$FunctionId = "device.info"

function Get-PlainText([Security.SecureString]$SecureValue) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-SafeErrorCode($ErrorRecord) {
  try {
    if ($ErrorRecord.Exception.Response -and $ErrorRecord.Exception.Response.StatusCode) {
      return "HTTP_" + [int]$ErrorRecord.Exception.Response.StatusCode
    }
  } catch {}
  $raw=[string]$ErrorRecord.Exception.Message
  if ($raw -match "^[A-Z][A-Z0-9_]{0,79}$") { return $raw }
  $name=[string]$ErrorRecord.Exception.GetType().Name
  $normalized=($name -replace "[^A-Za-z0-9_]", "_").ToUpperInvariant()
  if ($normalized -match "^[A-Z][A-Z0-9_]{0,79}$") { return $normalized }
  return "RUNTIME_ERROR"
}

function Test-OperationalErrorCode([string]$Code) {
  $operational=@(
    "DEVICE_OFFLINE","DEVICE_BUSY","CHANNEL_TRANSIENT_BUSY","DEVICE_CALL_TIMEOUT","CHANNEL_TRANSIENT_TIMEOUT",
    "DEVICE_NOT_FOUND","DEVICE_CALL_NOT_FOUND","COMPUTER_NAME_AMBIGUOUS",
    "FILENOTFOUNDERROR","FILE_NOT_FOUND","PARENT_DIRECTORY_NOT_FOUND","FILESYSTEM_PARENT_NOT_FOUND",
    "PREIMAGE_NOT_FOUND","RECEIPT_NOT_FOUND","EDIT_MATCH_NOT_FOUND","PROCESS_SESSION_NOT_FOUND","PROCESS_SESSION_EXITED",
    "DESTINATION_EXISTS","PATH_EXISTS_NOT_DIRECTORY","FILESYSTEM_PATH_EXISTS","FILEEXISTSERROR","EDIT_MATCH_AMBIGUOUS",
    "PATH_NOT_FILE","PATH_NOT_DIRECTORY","FILESYSTEM_NOT_DIRECTORY","SOURCE_NOT_FILE","DELETE_TARGET_NOT_FILE",
    "ROLLBACK_TARGET_NOT_FILE","PROCESS_CWD_INVALID","ISADIRECTORYERROR","NOTADIRECTORYERROR","BINARY_FILE_DENIED",
    "FILE_TOO_LARGE","HASH_FILE_TOO_LARGE","COPY_FILE_TOO_LARGE","DELETE_FILE_TOO_LARGE","PREIMAGE_FILE_TOO_LARGE","WRITE_TOO_LARGE"
  )
  return $operational -contains $Code
}

function Set-RuntimeStatus([string]$HeartbeatAt=$null,[string]$ErrorCode=$null,[string]$ErrorAt=$null,[string]$StartedAt=$null) {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $existing=$null
  if (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf) {
    try { $existing=Get-Content -Raw -LiteralPath $RuntimeStatus | ConvertFrom-Json } catch { $existing=$null }
  }
  $lastHeartbeat=if ($null -ne $HeartbeatAt) {$HeartbeatAt} elseif ($existing) {[string]$existing.last_successful_heartbeat_at_utc} else {$null}
  $startedAt=if ($null -ne $StartedAt) {$StartedAt} elseif ($existing) {[string]$existing.started_at_utc} else {$null}
  $payload=[ordered]@{
    schema="hara.commander-agent-runtime-status.v1"
    agent_version=$AgentVersion
    started_at_utc=$startedAt
    last_successful_heartbeat_at_utc=$lastHeartbeat
    last_runtime_error_code=$ErrorCode
    last_runtime_error_at_utc=$ErrorAt
    updated_at_utc=[DateTime]::UtcNow.ToString("o")
  }
  $tmp=$RuntimeStatus+".tmp"
  $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -Force -LiteralPath $tmp -Destination $RuntimeStatus
}

function Try-SetRuntimeStatus([string]$HeartbeatAt=$null,[string]$ErrorCode=$null,[string]$ErrorAt=$null,[string]$StartedAt=$null) {
  try {
    Set-RuntimeStatus -HeartbeatAt $HeartbeatAt -ErrorCode $ErrorCode -ErrorAt $ErrorAt -StartedAt $StartedAt
    return $true
  } catch {
    return $false
  }
}

function Get-OperatorProcess([int]$OwnerPid) {
  if ($OwnerPid -le 1) { return $null }
  try { return Get-Process -Id $OwnerPid -ErrorAction Stop }
  catch { return $null }
}

function Get-OperatorSession {
  if (-not (Test-Path -LiteralPath $SessionPath -PathType Leaf)) { return $null }
  try { $session=Get-Content -Raw -LiteralPath $SessionPath | ConvertFrom-Json } catch { return $null }
  if ([string]$session.schema -ne "hara.commander-operator-session.v1") { return $null }
  try { $started=[DateTime]::Parse([string]$session.started_at_utc).ToUniversalTime() } catch { return $null }
  if (([DateTime]::UtcNow-$started).TotalHours -gt $SessionMaxHours) { return $null }
  $proc=Get-OperatorProcess ([int]$session.owner_pid)
  if (-not $proc) { return $null }
  $marker=$proc.StartTime.ToUniversalTime().ToString("o")
  if ($marker -ne [string]$session.owner_started_at_utc) { return $null }
  return $session
}

function Test-OperatorSessionActive {
  return $null -ne (Get-OperatorSession)
}

function Initialize-WinSqlite {
  if ("HaraWinSqlite" -as [type]) { return }
  $source=@"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class HaraWinSqlite {
  const int OK=0, ROW=100, DONE=101;
  const int INTEGER=1, FLOAT=2, TEXT=3, NULL=5;
  static readonly IntPtr TRANSIENT=new IntPtr(-1);

  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_open16([MarshalAs(UnmanagedType.LPWStr)] string filename,out IntPtr db);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_close(IntPtr db);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern IntPtr sqlite3_errmsg16(IntPtr db);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_prepare16_v2(IntPtr db,[MarshalAs(UnmanagedType.LPWStr)] string sql,int n,out IntPtr stmt,IntPtr tail);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_bind_null(IntPtr stmt,int index);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_bind_text16(IntPtr stmt,int index,[MarshalAs(UnmanagedType.LPWStr)] string value,int n,IntPtr destructor);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_bind_int64(IntPtr stmt,int index,long value);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_bind_double(IntPtr stmt,int index,double value);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_step(IntPtr stmt);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_finalize(IntPtr stmt);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_column_count(IntPtr stmt);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern IntPtr sqlite3_column_name16(IntPtr stmt,int col);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_column_type(IntPtr stmt,int col);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern IntPtr sqlite3_column_text16(IntPtr stmt,int col);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern long sqlite3_column_int64(IntPtr stmt,int col);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern double sqlite3_column_double(IntPtr stmt,int col);

  static Exception Failure(IntPtr db,string where,int rc) {
    string message="";
    try { message=Marshal.PtrToStringUni(sqlite3_errmsg16(db)) ?? ""; } catch {}
    return new InvalidOperationException(where+":"+rc+":"+message);
  }
  static void Check(IntPtr db,int rc,string where) {
    if (rc!=OK) throw Failure(db,where,rc);
  }
  static void Bind(IntPtr db,IntPtr stmt,object[] values) {
    if (values==null) return;
    for (int i=0;i<values.Length;i++) {
      object value=values[i];
      int rc;
      if (value==null || value is DBNull) rc=sqlite3_bind_null(stmt,i+1);
      else if (
        value is byte || value is sbyte || value is short || value is ushort ||
        value is int || value is uint || value is long
      ) rc=sqlite3_bind_int64(stmt,i+1,Convert.ToInt64(value));
      else if (value is float || value is double || value is decimal)
        rc=sqlite3_bind_double(stmt,i+1,Convert.ToDouble(value));
      else rc=sqlite3_bind_text16(stmt,i+1,Convert.ToString(value),-1,TRANSIENT);
      Check(db,rc,"bind");
    }
  }

  public static void Execute(string path,string sql,object[] values) {
    IntPtr db=IntPtr.Zero,stmt=IntPtr.Zero;
    int open=sqlite3_open16(path,out db);
    if (open!=OK) throw Failure(db,"open",open);
    try {
      Check(db,sqlite3_prepare16_v2(db,sql,-1,out stmt,IntPtr.Zero),"prepare");
      Bind(db,stmt,values);
      int rc=sqlite3_step(stmt);
      if (rc!=DONE && rc!=ROW) throw Failure(db,"step",rc);
    } finally {
      if (stmt!=IntPtr.Zero) sqlite3_finalize(stmt);
      if (db!=IntPtr.Zero) sqlite3_close(db);
    }
  }

  public static List<Dictionary<string,object>> Query(string path,string sql,object[] values) {
    var rows=new List<Dictionary<string,object>>();
    IntPtr db=IntPtr.Zero,stmt=IntPtr.Zero;
    int open=sqlite3_open16(path,out db);
    if (open!=OK) throw Failure(db,"open",open);
    try {
      Check(db,sqlite3_prepare16_v2(db,sql,-1,out stmt,IntPtr.Zero),"prepare");
      Bind(db,stmt,values);
      int count=sqlite3_column_count(stmt);
      while (true) {
        int rc=sqlite3_step(stmt);
        if (rc==DONE) break;
        if (rc!=ROW) throw Failure(db,"step",rc);
        var row=new Dictionary<string,object>(StringComparer.OrdinalIgnoreCase);
        for (int col=0;col<count;col++) {
          string name=Marshal.PtrToStringUni(sqlite3_column_name16(stmt,col)) ?? ("c"+col);
          int type=sqlite3_column_type(stmt,col);
          object value=null;
          if (type==INTEGER) value=sqlite3_column_int64(stmt,col);
          else if (type==FLOAT) value=sqlite3_column_double(stmt,col);
          else if (type==TEXT) value=Marshal.PtrToStringUni(sqlite3_column_text16(stmt,col));
          row[name]=value;
        }
        rows.Add(row);
      }
      return rows;
    } finally {
      if (stmt!=IntPtr.Zero) sqlite3_finalize(stmt);
      if (db!=IntPtr.Zero) sqlite3_close(db);
    }
  }
}
"@
  Add-Type -TypeDefinition $source -Language CSharp
}

function Invoke-LocalDbExec([string]$Sql,[object[]]$Values=@()) {
  Initialize-WinSqlite
  [HaraWinSqlite]::Execute($script:OperationsDb,$Sql,$Values)
}

function Invoke-LocalDbQuery([string]$Sql,[object[]]$Values=@()) {
  Initialize-WinSqlite
  return [HaraWinSqlite]::Query($script:OperationsDb,$Sql,$Values)
}

function Set-LocalStoreAcl {
  if (-not (Test-Path -LiteralPath $script:OperationsDb -PathType Leaf)) { return }
  try {
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $script:OperationsDb /inheritance:r /grant:r ("*$sid" + ":(F)") "*S-1-5-18:(F)" | Out-Null
  } catch {}
}

function Initialize-LocalActivityStore {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  Invoke-LocalDbExec "PRAGMA journal_mode=WAL"
  Invoke-LocalDbExec "PRAGMA synchronous=NORMAL"
  Invoke-LocalDbExec @"
CREATE TABLE IF NOT EXISTS activity_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  at_utc TEXT NOT NULL,
  event TEXT NOT NULL,
  state TEXT,
  tool_id TEXT,
  function_id TEXT,
  request_id TEXT,
  error_code TEXT,
  receipt_sha256 TEXT,
  approval_id TEXT,
  action_summary TEXT,
  duration_ms INTEGER,
  transport_mode TEXT,
  local_only INTEGER NOT NULL DEFAULT 1
)
"@
  Invoke-LocalDbExec "CREATE INDEX IF NOT EXISTS idx_activity_events_at ON activity_events(at_utc DESC)"
  Invoke-LocalDbExec "CREATE INDEX IF NOT EXISTS idx_activity_events_terminal ON activity_events(event,at_utc DESC)"
  Invoke-LocalDbExec "CREATE INDEX IF NOT EXISTS idx_activity_events_tool ON activity_events(tool_id,at_utc DESC)"
  Invoke-LocalDbExec "CREATE TABLE IF NOT EXISTS local_store_meta (meta_key TEXT PRIMARY KEY,meta_value TEXT NOT NULL)"
  Set-LocalStoreAcl

  $marker=@(Invoke-LocalDbQuery "SELECT meta_value FROM local_store_meta WHERE meta_key=?" @("console_events_jsonl_v1"))
  if ($marker.Count -eq 0) {
    if (Test-Path -LiteralPath $ConsoleEvents -PathType Leaf) {
      foreach($line in @(Get-Content -LiteralPath $ConsoleEvents)) {
        try {
          $legacy=$line | ConvertFrom-Json
          if ([string]$legacy.schema -ne "hara.commander-console-event.v1") { continue }
          Invoke-LocalDbExec @"
INSERT INTO activity_events
(at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)
"@ @(
            [string]$legacy.at_utc,
            [string]$legacy.event,
            $(if ($legacy.state) {[string]$legacy.state} else {$null}),
            $(if ($legacy.tool_id) {[string]$legacy.tool_id} else {$null}),
            $(if ($legacy.function_id) {[string]$legacy.function_id} else {$null}),
            $(if ($legacy.request_id) {[string]$legacy.request_id} else {$null}),
            $(if ($legacy.error_code) {[string]$legacy.error_code} else {$null}),
            $(if ($legacy.receipt_sha256) {[string]$legacy.receipt_sha256} else {$null}),
            $(if ($legacy.approval_id) {[string]$legacy.approval_id} else {$null}),
            $(if ($legacy.action_summary) {[string]$legacy.action_summary} else {$null}),
            $(if ($null -ne $legacy.duration_ms) {[long]$legacy.duration_ms} else {$null}),
            $(if ($legacy.transport_mode) {[string]$legacy.transport_mode} else {"LEGACY_JSONL"})
          )
        } catch {}
      }
    }
    Invoke-LocalDbExec "INSERT OR REPLACE INTO local_store_meta(meta_key,meta_value) VALUES(?,?)" @(
      "console_events_jsonl_v1",[DateTime]::UtcNow.ToString("o")
    )
  }
}

function Write-LocalActivityEvent($Entry) {
  try {
    Initialize-LocalActivityStore
    Invoke-LocalDbExec @"
INSERT INTO activity_events
(at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)
"@ @(
      [string]$Entry.at_utc,
      [string]$Entry.event,
      $Entry.state,
      $Entry.tool_id,
      $Entry.function_id,
      $Entry.request_id,
      $Entry.error_code,
      $Entry.receipt_sha256,
      $Entry.approval_id,
      $Entry.action_summary,
      $Entry.duration_ms,
      $(if ($Entry.transport_mode) {[string]$Entry.transport_mode} else {"OUTBOUND_RELAY"})
    )
  } catch {
    # JSONL remains the compatibility/fail-safe sink.
  }
}


function Get-NearestRankPercentile($Values,[int]$Percent) {
  $items=@($Values | Where-Object { $null -ne $_ } | ForEach-Object {[int64]$_} | Sort-Object)
  if (-not $items.Count) { return $null }
  $rank=[Math]::Max(1,[Math]::Ceiling($items.Count*$Percent/100.0))
  return [int64]$items[[Math]::Min($items.Count-1,$rank-1)]
}

function Get-SloFailureClass([string]$ErrorCode) {
  $code=([string]$ErrorCode).Trim().ToUpperInvariant()
  $policy=@("HTTP_401","HTTP_403","HTTP_409","HTTP_429","LOCAL_OPERATOR_APPROVAL_DENIED","APPROVAL_TIMEOUT")
  $client=@(
    "HTTP_400","HTTP_404","HTTP_405","HTTP_410","HTTP_422",
    "FILENOTFOUNDERROR","FILEEXISTSERROR","ISADIRECTORYERROR","NOTADIRECTORYERROR",
    "EDIT_MATCH_AMBIGUOUS","PROCESS_SESSION_EXITED","PROCESS_SESSION_NOT_FOUND"
  )
  if ($policy -contains $code) { return "POLICY" }
  if ($client -contains $code) { return "CLIENT_ACTION" }
  return "SERVICE"
}

function Get-InternalSlo($Summary) {
  $sample=[int64]$(if ($null -ne $Summary.latency_sample_size) {$Summary.latency_sample_size} else {0})
  $terminal=[int64]$Summary.completed+[int64]$Summary.service_failed
  $success=$Summary.availability_success_rate_percent
  $checks=[ordered]@{
    success_rate=$(if ($null -eq $success) {$null} else {[double]$success -ge $SloMinSuccessPercent})
    p50=$(if ($null -eq $Summary.latency_p50_ms) {$null} else {[double]$Summary.latency_p50_ms -le $SloP50MaxMs})
    p95=$(if ($null -eq $Summary.latency_p95_ms) {$null} else {[double]$Summary.latency_p95_ms -le $SloP95MaxMs})
    p99=$(if ($null -eq $Summary.latency_p99_ms) {$null} else {[double]$Summary.latency_p99_ms -le $SloP99MaxMs})
  }
  $evaluable=($sample -ge $SloMinLatencySamples -and $terminal -ge $SloMinLatencySamples)
  $allPass=$true
  foreach($value in $checks.Values){ if($value -ne $true){$allPass=$false} }
  return [ordered]@{
    profile=$SloProfile
    status=$(if(-not $evaluable){"INSUFFICIENT_DATA"}elseif($allPass){"PASS"}else{"DEGRADED"})
    evaluable=$evaluable
    success_metric="availability_success_rate_percent"
    targets=[ordered]@{
      min_success_rate_percent=$SloMinSuccessPercent
      p50_max_ms=$SloP50MaxMs
      p95_max_ms=$SloP95MaxMs
      p99_max_ms=$SloP99MaxMs
      min_latency_samples=$SloMinLatencySamples
    }
    checks=$checks
  }
}

function Get-LocalActivityWindow([string]$Window="7d") {
  Initialize-LocalActivityStore
  $hours=switch ($Window) { "24h" {24}; "30d" {720}; default {168} }
  if (@("24h","7d","30d") -notcontains $Window) { $Window="7d"; $hours=168 }
  $since=[DateTime]::UtcNow.AddHours(-$hours).ToString("o")

  $summaryRows=@(Invoke-LocalDbQuery @"
SELECT COUNT(*) AS total_calls,
       SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) AS completed,
       SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END) AS failed,
       SUM(CASE WHEN state='EXPECTED' THEN 1 ELSE 0 END) AS operational,
       ROUND(AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END),1) AS avg_total_ms,
       SUM(CASE WHEN state='COMPLETED' AND duration_ms < 3000 THEN 1 ELSE 0 END) AS under_3s,
       SUM(CASE WHEN state='COMPLETED' AND duration_ms IS NOT NULL THEN 1 ELSE 0 END) AS duration_population
FROM activity_events
WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
"@ @($since))
  $row=if ($summaryRows.Count) {$summaryRows[0]} else {$null}

  $tools=@(Invoke-LocalDbQuery @"
SELECT COALESCE(tool_id,'unknown') AS tool_id,COUNT(*) AS calls
FROM activity_events
WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
GROUP BY COALESCE(tool_id,'unknown')
ORDER BY calls DESC,tool_id LIMIT 6
"@ @($since))
  $failureRows=@(Invoke-LocalDbQuery @"
SELECT COALESCE(error_code,'UNKNOWN') AS error_code,COUNT(*) AS calls
FROM activity_events
WHERE at_utc >= ? AND event='DENIED' AND state='FAILED'
GROUP BY COALESCE(error_code,'UNKNOWN')
ORDER BY calls DESC,error_code
"@ @($since))
  $errors=@($failureRows | Select-Object -First 6)
  $transports=@(Invoke-LocalDbQuery @"
SELECT DISTINCT COALESCE(transport_mode,'OUTBOUND_RELAY') AS transport_mode
FROM activity_events
WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
ORDER BY transport_mode
"@ @($since))
  $durationRows=@(Invoke-LocalDbQuery @"
SELECT duration_ms
FROM activity_events
WHERE at_utc >= ? AND state='COMPLETED' AND duration_ms IS NOT NULL
ORDER BY rowid DESC
LIMIT ?
"@ @($since,$SloLatencySampleMax))

  $total=if ($row -and $null -ne $row["total_calls"]) {[int64]$row["total_calls"]} else {0}
  $completed=if ($row -and $null -ne $row["completed"]) {[int64]$row["completed"]} else {0}
  $failed=if ($row -and $null -ne $row["failed"]) {[int64]$row["failed"]} else {0}
  $operational=if ($row -and $null -ne $row["operational"]) {[int64]$row["operational"]} else {0}
  [int64]$clientFailed=0
  [int64]$policyFailed=0
  [int64]$serviceFailed=0
  foreach($failure in $failureRows) {
    $calls=[int64]$failure['calls']
    $class=Get-SloFailureClass ([string]$failure['error_code'])
    if ($class -eq "CLIENT_ACTION") { $clientFailed+=$calls }
    elseif ($class -eq "POLICY") { $policyFailed+=$calls }
    else { $serviceFailed+=$calls }
  }
  $under3=if ($row -and $null -ne $row["under_3s"]) {[int64]$row["under_3s"]} else {0}
  $avg=if ($row -and $null -ne $row["avg_total_ms"]) {[double]$row["avg_total_ms"]} else {$null}
  $durationPopulation=if ($row -and $null -ne $row["duration_population"]) {[int64]$row["duration_population"]} else {0}
  $terminal=$completed+$failed
  $availabilityTerminal=$completed+$serviceFailed
  $durations=@($durationRows | ForEach-Object {[int64]$_['duration_ms']})
  $summary=[ordered]@{
    total_calls=$total
    completed=$completed
    failed=$failed
    operational=$operational
    client_failed=$clientFailed
    policy_failed=$policyFailed
    service_failed=$serviceFailed
    pending=0
    executing=0
    expired=0
    cancelled=0
    success_rate_percent=$(if ($terminal) {[Math]::Round(($completed/$terminal)*100,1)} else {$null})
    availability_success_rate_percent=$(if ($availabilityTerminal) {[Math]::Round(($completed/$availabilityTerminal)*100,1)} else {$null})
    under_3s_percent=$(if ($completed) {[Math]::Round(($under3/$completed)*100,1)} else {$null})
    avg_queue_ms=$(if ($total) {0.0} else {$null})
    avg_execution_ms=$avg
    avg_total_ms=$avg
    latency_p50_ms=(Get-NearestRankPercentile $durations 50)
    latency_p95_ms=(Get-NearestRankPercentile $durations 95)
    latency_p99_ms=(Get-NearestRankPercentile $durations 99)
    latency_sample_size=$durations.Count
    latency_population_size=$durationPopulation
    latency_sample_capped=($durationPopulation -gt $durations.Count)
    device_count=$(if ($total) {1} else {0})
    transport_modes=@($transports | ForEach-Object {[string]$_['transport_mode']})
  }

  return [ordered]@{
    schema="hara.commander-local-activity.v2"
    source="LOCAL_SQLITE"
    window=[ordered]@{
      key=$Window
      label=$(switch($Window){"24h"{"24 horas"}"30d"{"30 dias"}default{"7 dias"}})
      since_at_utc=$since
    }
    privacy=[ordered]@{
      local_authoritative=$true
      payload_values_exposed=$false
      result_values_exposed=$false
      cloud_history_persisted=$false
      action_summary_local_only=$true
    }
    summary=$summary
    slo=(Get-InternalSlo $summary)
    diagnostics=[ordered]@{
      top_tools=@($tools | ForEach-Object {@{tool_id=[string]$_['tool_id'];calls=[int64]$_['calls']}})
      top_errors=@($errors | ForEach-Object {@{error_code=[string]$_['error_code'];calls=[int64]$_['calls']}})
    }
  }
}

function Get-LocalActivityHeartbeatSnapshot {
  return [ordered]@{
    schema="hara.commander-local-activity-snapshots.v1"
    generated_at_utc=[DateTime]::UtcNow.ToString("o")
    windows=[ordered]@{
      "24h"=(Get-LocalActivityWindow "24h")
      "7d"=(Get-LocalActivityWindow "7d")
      "30d"=(Get-LocalActivityWindow "30d")
    }
    detail_location="LOCAL_DEVICE"
    customer_content_synced=$false
  }
}

function Protect-LocalCommandPreview([string]$Value) {
  $text=[string]$Value
  $text=[regex]::Replace($text,'(?i)\b(password|passwd|token|secret|api[_-]?key)\s*=\s*([^\s]+)','$1=<redacted>')
  $text=[regex]::Replace($text,'(?i)(authorization\s*:\s*bearer\s+)[^\s]+','$1<redacted>')
  if ($text.Length -gt 240) { return $text.Substring(0,237)+"..." }
  return $text
}

function Get-LocalActionSummary($Call) {
  if ($null -eq $Call) { return $null }
  $tool=[string]$Call.tool_id
  $payload=$Call.payload
  if ($tool -eq "hara.process.run") {
    return "process.run cwd="+$(if ($payload.cwd) {[string]$payload.cwd} else {"~"})+
      " timeout_ms="+$(if ($null -ne $payload.timeout_ms) {[string]$payload.timeout_ms} else {"3000"})+
      " command="+(Protect-LocalCommandPreview ([string]$payload.command))
  }
  if ($tool -eq "hara.files.write") {
    $bytes=[Text.Encoding]::UTF8.GetByteCount([string]$payload.content)
    return "write mode="+$(if ($payload.mode) {[string]$payload.mode} else {"rewrite"})+
      " path="+[string]$payload.path+" bytes="+$bytes
  }
  if ($tool -eq "hara.files.create_directory") {
    return "mkdir path="+[string]$payload.path
  }
  return $null
}

function Write-ConsoleEvent([string]$Event,$Call=$null,[string]$State="",[string]$ErrorCode="",[string]$ReceiptSha="") {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $tool=$null; $functionId=$null; $requestId=$null
  if ($null -ne $Call) {
    $tool=[string]$Call.tool_id
    if ($Call.payload) { $functionId=[string]$Call.payload.function_id }
    $requestId=[string]$Call.request_id
  }
  $entry=[ordered]@{
    schema="hara.commander-console-event.v1"
    at_utc=[DateTime]::UtcNow.ToString("o")
    event=$Event
    state=if ($State) {$State} else {$null}
    tool_id=if ($tool) {$tool} else {$null}
    function_id=if ($functionId) {$functionId} else {$null}
    request_id=if ($requestId) {$requestId} else {$null}
    error_code=if ($ErrorCode) {$ErrorCode} else {$null}
    receipt_sha256=if ($ReceiptSha) {$ReceiptSha} else {$null}
    approval_id=$null
    action_summary=Get-LocalActionSummary $Call
    duration_ms=$null
    transport_mode="OUTBOUND_RELAY"
    local_only=$true
    payload_values_exposed=$false
    secret_material_exposed=$false
  }
  Write-LocalActivityEvent $entry
  Add-Content -LiteralPath $ConsoleEvents -Value ($entry | ConvertTo-Json -Compress) -Encoding UTF8
}

function Format-ConsoleEvent($Entry) {
  $stamp=([DateTime]::Parse([string]$Entry.at_utc)).ToLocalTime().ToString("HH:mm:ss")
  $tool=if ($Entry.tool_id) {[string]$Entry.tool_id} else {"-"}
  $fn=if ($Entry.function_id) {[string]$Entry.function_id} else {"-"}
  $request=if ($Entry.request_id) {[string]$Entry.request_id} else {""}
  $command=if ($fn -ne "-") {$fn} else {$tool}
  $suffix=" cliente=MCP comando=$command tool=$tool"
  if ($request) {$suffix+=" request="+$request.Substring(0,[Math]::Min(12,$request.Length))+$(if ($request.Length -gt 12) {"..."} else {""})}
  if ($Entry.state) {$suffix+=" state="+[string]$Entry.state}
  if ($Entry.error_code) {$suffix+=" error="+[string]$Entry.error_code}
  if ($Entry.receipt_sha256) {$suffix+=" receipt="+([string]$Entry.receipt_sha256).Substring(0,12)+"..."}
  return "[$stamp] $([string]$Entry.event)$suffix"
}

function Start-OperatorConsole {
  $cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  $existing=Get-OperatorSession
  if ($existing -and [int]$existing.owner_pid -ne $PID) { throw "OPERATOR_SESSION_ALREADY_ACTIVE" }
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $session=[ordered]@{
    schema="hara.commander-operator-session.v1"
    owner_pid=$PID
    owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
    device_id=[string]$cfg.device_id
    authorization="LOCAL_OPERATOR_TERMINAL"
  }
  $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
  Write-ConsoleEvent "SESSION_OPEN" $null "AUTHORIZED"
  Write-Host ""
  Write-Host "H.A.R.A. Labs - Commander"
  Write-Host ("="*58)
  Write-Host "Sessao local autorizada para clientes de IA"
  Write-Host ("Computador: "+$env:COMPUTERNAME)
  Write-Host ("Device ID : "+[string]$cfg.device_id)
  Write-Host ("Agent     : "+$AgentVersion)
  Write-Host ""
  Write-Host "Comandos permitidos nesta sessao:"
  Write-Host "  hara.health / hara.ping / hara.device.info"
  Write-Host "  hara.files.info / list / read"
  Write-Host "  hara.files.create_directory / write  [starter]"
  Write-Host "  hara.processes.list / hara.process.run  [starter]"
  Write-Host "  hara.functions.list"
  Write-Host "  hara.functions.describe"
  Write-Host "  hara.functions.invoke (somente funcoes governadas)"
  Write-Host "  hara.receipts.get"
  Write-Host ""
  Write-Host "Origem     : OpenAI / cliente MCP autorizado"
  Write-Host "Acesso     : ativo somente enquanto este terminal permanecer aberto"
  Write-Host "Argumentos sensiveis, tokens e segredos nunca sao exibidos."
  Write-Host "Cada acao sera mostrada abaixo com tool, funcao, estado e receipt."
  Write-Host "Pressione Ctrl+C para revogar o acesso imediatamente."
  Write-Host ("-"*58)
  try {
    $seen=0
    while ($true) {
      $current=Get-OperatorSession
      if (-not $current -or [int]$current.owner_pid -ne $PID) { break }
      if (Test-Path -LiteralPath $ConsoleEvents -PathType Leaf) {
        $rows=@(Get-Content -LiteralPath $ConsoleEvents)
        while ($seen -lt $rows.Count) {
          try { $entry=$rows[$seen] | ConvertFrom-Json; Write-Host (Format-ConsoleEvent $entry) } catch {}
          $seen++
        }
      }
      Start-Sleep -Milliseconds 250
    }
  } finally {
    try {
      $current=Get-OperatorSession
      if (-not $current -or [int]$current.owner_pid -eq $PID) { Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue }
    } catch {
      Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
    }
    Set-DeviceOffline $cfg | Out-Null
    Write-ConsoleEvent "SESSION_CLOSE" $null "REVOKED"
    Write-Host "HARA_COMMANDER_SESSION=INACTIVE"
  }
}

function Stop-OperatorSession {
  $was=Test-Path -LiteralPath $SessionPath -PathType Leaf
  Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
  Set-DeviceOffline | Out-Null
  Write-ConsoleEvent "SESSION_CLOSE" $null "REVOKED"
  Write-Host "HARA_COMMANDER_SESSION=INACTIVE"
  Write-Host ("SESSION_WAS_ACTIVE="+($(if ($was) {"TRUE"} else {"FALSE"})))
  Write-Host "SECRET_MATERIAL_EXPOSED=FALSE"
}

function Show-OperatorSession {
  $session=Get-OperatorSession
  Write-Host ("HARA_COMMANDER_SESSION="+($(if ($session) {"ACTIVE"} else {"INACTIVE"})))
  if ($session) { Write-Host ("SESSION_STARTED_AT_UTC="+[string]$session.started_at_utc) }
  Write-Host "SECRET_MATERIAL_EXPOSED=FALSE"
}

function Get-DeviceInfo($Cfg) {
  return @{
    device_id=[string]$Cfg.device_id
    hostname=$env:COMPUTERNAME
    platform="WINDOWS"
    platform_release=[Environment]::OSVersion.VersionString
    architecture=[string]$Cfg.architecture
    powershell_version=$PSVersionTable.PSVersion.ToString()
    agent_version=$AgentVersion
    tunnel_mode="OUTBOUND_RELAY"
  }
}

function Get-ApprovalMode($Cfg) {
  $mode=if ($Cfg.approval_mode) {[string]$Cfg.approval_mode} else {"ASK_EVERY_ACTION"}
  $mode=$mode.Trim().ToUpperInvariant()
  if (@("ASK_EVERY_ACTION","SESSION_TRUSTED","PERSISTENT_TRUSTED") -notcontains $mode) { return "ASK_EVERY_ACTION" }
  return $mode
}

function Assert-StarterMutationAuthorized($Cfg) {
  $mode=Get-ApprovalMode $Cfg
  if ($mode -eq "ASK_EVERY_ACTION") { throw "WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED" }
  if ($mode -eq "SESSION_TRUSTED" -and -not (Test-OperatorSessionActive)) { throw "LOCAL_OPERATOR_SESSION_REQUIRED" }
}

function New-DirectResult([string]$FunctionId,[string]$RiskClass,$Data,[object]$ExitCode=0) {
  return @{
    function_id=$FunctionId
    risk_class=$RiskClass
    process_exit_code=$ExitCode
    stdout=($Data | ConvertTo-Json -Depth 8 -Compress)
    domain_success_inferred=$false
  }
}

function Get-WindowsPing($Cfg) {
  return @{device_id=[string]$Cfg.device_id;hostname=$env:COMPUTERNAME;reachable=$true;agent_version=$AgentVersion}
}

function Get-WindowsProcesses([int]$Limit=50) {
  $Limit=[Math]::Max(1,[Math]::Min(500,$Limit))
  $rows=@()
  Get-Process | Sort-Object -Property CPU -Descending | Select-Object -First $Limit | ForEach-Object {
    $rows+=@{pid=$_.Id;name=$_.ProcessName;cpu_seconds=if ($null -ne $_.CPU) {[Math]::Round([double]$_.CPU,3)} else {$null};working_set_bytes=[int64]$_.WorkingSet64}
  }
  return @{processes=$rows;count=$rows.Count}
}

function Get-WindowsFileInfo([string]$PathValue) {
  $item=Get-Item -LiteralPath $PathValue -Force -ErrorAction Stop
  return @{
    path=$item.FullName
    name=$item.Name
    type=if ($item.PSIsContainer) {"directory"} else {"file"}
    size_bytes=if ($item.PSIsContainer) {$null} else {[int64]$item.Length}
    modified_at_utc=$item.LastWriteTimeUtc.ToString("o")
    created_at_utc=$item.CreationTimeUtc.ToString("o")
    attributes=[string]$item.Attributes
  }
}

function Get-WindowsDirectory([string]$PathValue,[int]$Depth=1,[int]$Limit=200) {
  $Depth=[Math]::Max(1,[Math]::Min(8,$Depth))
  $Limit=[Math]::Max(1,[Math]::Min(1000,$Limit))
  $root=(Get-Item -LiteralPath $PathValue -Force -ErrorAction Stop)
  if (-not $root.PSIsContainer) { throw "FILESYSTEM_NOT_DIRECTORY" }
  $queue=New-Object System.Collections.Queue
  $queue.Enqueue(@($root.FullName,1))
  $rows=@()
  while ($queue.Count -gt 0 -and $rows.Count -lt $Limit) {
    $entry=$queue.Dequeue(); $current=[string]$entry[0]; $level=[int]$entry[1]
    foreach ($item in @(Get-ChildItem -LiteralPath $current -Force -ErrorAction SilentlyContinue | Sort-Object Name)) {
      if ($rows.Count -ge $Limit) { break }
      $rows+=@{path=$item.FullName;name=$item.Name;type=if ($item.PSIsContainer) {"directory"} else {"file"};depth=$level;size_bytes=if ($item.PSIsContainer) {$null} else {[int64]$item.Length}}
      if ($item.PSIsContainer -and $level -lt $Depth) { $queue.Enqueue(@($item.FullName,$level+1)) }
    }
  }
  return @{path=$root.FullName;entries=$rows;count=$rows.Count;truncated=($rows.Count -ge $Limit)}
}

function Read-WindowsTextFile([string]$PathValue,[int]$Offset=0,[int]$Length=200) {
  $Offset=[Math]::Max(0,$Offset)
  $Length=[Math]::Max(1,[Math]::Min(5000,$Length))
  $lines=@(Get-Content -LiteralPath $PathValue -Encoding UTF8 -ErrorAction Stop)
  $slice=@()
  if ($Offset -lt $lines.Count) {
    $end=[Math]::Min($lines.Count,$Offset+$Length)
    if ($end -gt $Offset) { $slice=@($lines[$Offset..($end-1)]) }
  }
  return @{path=(Resolve-Path -LiteralPath $PathValue).Path;offset=$Offset;line_count=$slice.Count;total_lines=$lines.Count;text=($slice -join [Environment]::NewLine)}
}

function Write-WindowsTextFile($Cfg,[string]$PathValue,[string]$Content,[string]$Mode="rewrite") {
  Assert-StarterMutationAuthorized $Cfg
  if ($Content.Length -gt 1048576) { throw "FUNCTION_ARGUMENTS_DENIED" }
  $full=[IO.Path]::GetFullPath($PathValue)
  $parent=[IO.Path]::GetDirectoryName($full)
  if (-not $parent -or -not (Test-Path -LiteralPath $parent -PathType Container)) { throw "FILESYSTEM_PARENT_NOT_FOUND" }
  if ($Mode -eq "append") { Add-Content -LiteralPath $full -Value $Content -Encoding UTF8 }
  elseif ($Mode -eq "rewrite") { [IO.File]::WriteAllText($full,$Content,(New-Object Text.UTF8Encoding($false))) }
  else { throw "FUNCTION_ARGUMENTS_DENIED" }
  return @{path=$full;mode=$Mode;bytes_written=[Text.Encoding]::UTF8.GetByteCount($Content)}
}

function New-WindowsDirectory($Cfg,[string]$PathValue,[bool]$Parents=$true) {
  Assert-StarterMutationAuthorized $Cfg
  $full=[IO.Path]::GetFullPath($PathValue)
  if (Test-Path -LiteralPath $full) {
    if (-not (Test-Path -LiteralPath $full -PathType Container)) { throw "FILESYSTEM_PATH_EXISTS" }
    return @{path=$full;created=$false}
  }
  if (-not $Parents) {
    $parent=[IO.Path]::GetDirectoryName($full)
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw "FILESYSTEM_PARENT_NOT_FOUND" }
  }
  New-Item -ItemType Directory -Path $full -Force:$Parents | Out-Null
  return @{path=$full;created=$true}
}

function Invoke-WindowsOneShotProcess($Cfg,[string]$Command,[string]$Cwd=$null,[int]$TimeoutMs=3000,[int]$MaxLines=200) {
  Assert-StarterMutationAuthorized $Cfg
  if ([string]::IsNullOrWhiteSpace($Command) -or $Command.Length -gt 4096) { throw "FUNCTION_ARGUMENTS_DENIED" }
  $TimeoutMs=[Math]::Max(100,[Math]::Min(10000,$TimeoutMs))
  $MaxLines=[Math]::Max(1,[Math]::Min(500,$MaxLines))
  $bytes=[Text.Encoding]::Unicode.GetBytes($Command)
  $encoded=[Convert]::ToBase64String($bytes)
  $psi=New-Object Diagnostics.ProcessStartInfo
  $psi.FileName="powershell.exe"
  $psi.Arguments="-NoLogo -NoProfile -NonInteractive -EncodedCommand $encoded"
  $psi.UseShellExecute=$false
  $psi.RedirectStandardOutput=$true
  $psi.RedirectStandardError=$true
  $psi.CreateNoWindow=$true
  if ($Cwd) {
    $resolved=(Resolve-Path -LiteralPath $Cwd -ErrorAction Stop).Path
    $psi.WorkingDirectory=$resolved
  }
  $proc=New-Object Diagnostics.Process
  $proc.StartInfo=$psi
  if (-not $proc.Start()) { throw "PROCESS_START_FAILED" }
  $stdoutTask=$proc.StandardOutput.ReadToEndAsync()
  $stderrTask=$proc.StandardError.ReadToEndAsync()
  $timedOut=-not $proc.WaitForExit($TimeoutMs)
  if ($timedOut) {
    try { $proc.Kill() } catch {}
    try { $proc.WaitForExit(1000) | Out-Null } catch {}
  }
  $stdout=$stdoutTask.GetAwaiter().GetResult()
  $stderr=$stderrTask.GetAwaiter().GetResult()
  $combined=($stdout + $(if ($stderr) {[Environment]::NewLine+$stderr} else {""}))
  $lines=@($combined -split "
?
")
  $truncated=$lines.Count -gt $MaxLines
  if ($truncated) { $lines=@($lines[0..($MaxLines-1)]) }
  $exit=if ($timedOut) {$null} else {$proc.ExitCode}
  return @{
    state=if ($timedOut) {"TIMED_OUT"} else {"EXITED"}
    exit_code=$exit
    timed_out=$timedOut
    cwd=if ($psi.WorkingDirectory) {$psi.WorkingDirectory} else {(Get-Location).Path}
    command_sha256=Get-Utf8Sha256 $Command
    text=($lines -join [Environment]::NewLine)
    output_truncated=$truncated
    session_retained=$false
  }
}
function Get-Catalog {
  return @{
    registered_function_count=1
    executable_function_count=1
    active_function_count=1
    domains=@("DEVICE")
    functions=@(@{function_id=$FunctionId;state="ACTIVE"})
  }
}

function Get-Description([string]$Id) {
  if ($Id -ne $FunctionId) { throw "UNKNOWN_FUNCTION_ID" }
  return @{
    function_id=$FunctionId
    state="ACTIVE"
    IDENTITY=@{domain="DEVICE"}
    PURPOSE=@{description_pt_br="Consulta informações básicas e não sensíveis deste computador."}
    EXECUTION_SEMANTICS=@{risk_class="READ_ONLY";change_intent_required=$false}
    AUTHORITY=@{risk_class="READ_ONLY";change_intent_required=$false;fail_closed=$true}
    FAILURE_ROLLBACK=@{fail_closed=$true}
  }
}

function Invoke-LocalFunction($Cfg,[string]$Id,$Arguments) {
  if ($Id -ne $FunctionId) { throw "UNKNOWN_FUNCTION_ID" }
  if ($null -eq $Arguments -or $null -eq $Arguments.argv -or @($Arguments.argv).Count -ne 0) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  $info = Get-DeviceInfo $Cfg
  return @{
    function_id=$FunctionId
    risk_class="READ_ONLY"
    process_exit_code=0
    stdout=($info | ConvertTo-Json -Depth 5 -Compress)
    domain_success_inferred=$false
  }
}
function Get-Utf8Sha256([string]$Text) {
  $bytes=[Text.Encoding]::UTF8.GetBytes([string]$Text)
  $sha=[Security.Cryptography.SHA256]::Create()
  try { return ($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
  finally { $sha.Dispose() }
}
function New-Receipt($Cfg,$Call,[string]$State,$Result) {
  New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
  $resultBinding="NONE"
  $resultStdoutSha256=$null
  if ([string]$Call.tool_id -eq "hara.functions.invoke") {
    $resultBinding="STDOUT_SHA256_V1"
    $resultStdoutSha256=Get-Utf8Sha256 ([string]$Result.stdout)
  }
  $tool=[string]$Call.tool_id
  $mutationClass=if ($tool -eq "hara.process.run") {"PROCESS_EXECUTION_V1"} elseif (@("hara.files.create_directory","hara.files.write") -contains $tool) {"FILESYSTEM_MUTATION_V1"} else {"READ_ONLY_OR_NONE_V1"}
  $approvalMode=Get-ApprovalMode $Cfg
  $receipt = [ordered]@{
    schema="hara.commander-device-receipt.v1"
    request_id=[string]$Call.request_id
    device_id=[string]$Cfg.device_id
    tool_id=[string]$Call.tool_id
    function_id_if_any=if ($Call.payload) {[string]$Call.payload.function_id} else {$null}
    transport_mode="OUTBOUND_RELAY"
    operational_authority="HARA_SERVICES"
    execution_authority="HARA_COMMANDER_AGENT"
    mutation_class=$mutationClass
    state=$State
    payload_values_persisted=$false
    human_approval_required=($mutationClass -ne "READ_ONLY_OR_NONE_V1" -and $approvalMode -eq "ASK_EVERY_ACTION")
    human_approval_state=if ($mutationClass -ne "READ_ONLY_OR_NONE_V1") {"APPROVED"} else {$null}
    local_authorization_mode=if ($mutationClass -ne "READ_ONLY_OR_NONE_V1") {$approvalMode} else {$null}
    authorization_source=if ($mutationClass -ne "READ_ONLY_OR_NONE_V1") {$(if ($approvalMode -eq "PERSISTENT_TRUSTED") {"DEVICE_ENROLLMENT_POLICY"} else {"LOCAL_OPERATOR_SESSION"})} else {$null}
    result_binding=$resultBinding
    result_stdout_sha256=$resultStdoutSha256
    completed_at_utc=[DateTime]::UtcNow.ToString("o")
  }
  $json = $receipt | ConvertTo-Json -Depth 6 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $sha = [Security.Cryptography.SHA256]::Create()
  try { $hash = ($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
  finally { $sha.Dispose() }
  [IO.File]::WriteAllBytes((Join-Path $ReceiptDir ($hash+".json")),$bytes)
  return $hash
}

function Get-Receipt([string]$Identifier) {
  $value=$Identifier.ToLowerInvariant()
  if ($value -notmatch "^[0-9a-f]{64}$") { throw "RECEIPT_IDENTIFIER_INVALID" }
  $path=Join-Path $ReceiptDir ($value+".json")
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "RECEIPT_NOT_FOUND" }
  return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
}
function Invoke-Tool($Cfg,$Call) {
  $tool=[string]$Call.tool_id
  $payload=$Call.payload
  if ($tool -eq "hara.ping") {
    $result=New-DirectResult "device.ping" "READ_ONLY" (Get-WindowsPing $Cfg)
  } elseif ($tool -eq "hara.device.info") {
    $result=New-DirectResult "device.info" "READ_ONLY" (Get-DeviceInfo $Cfg)
  } elseif ($tool -eq "hara.processes.list") {
    $limit=if ($null -ne $payload.limit) {[int]$payload.limit} else {50}
    $result=New-DirectResult "process.list" "READ_ONLY" (Get-WindowsProcesses $limit)
  } elseif ($tool -eq "hara.files.info") {
    $result=New-DirectResult "filesystem.info" "READ_ONLY" (Get-WindowsFileInfo ([string]$payload.path))
  } elseif ($tool -eq "hara.files.list") {
    $depth=if ($null -ne $payload.depth) {[int]$payload.depth} else {1}
    $limit=if ($null -ne $payload.limit) {[int]$payload.limit} else {200}
    $result=New-DirectResult "filesystem.list" "READ_ONLY" (Get-WindowsDirectory ([string]$payload.path) $depth $limit)
  } elseif ($tool -eq "hara.files.read") {
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $length=if ($null -ne $payload.length) {[int]$payload.length} else {200}
    $result=New-DirectResult "filesystem.read" "READ_ONLY" (Read-WindowsTextFile ([string]$payload.path) $offset $length)
  } elseif ($tool -eq "hara.files.create_directory") {
    $parents=if ($null -ne $payload.parents) {[bool]$payload.parents} else {$true}
    $result=New-DirectResult "filesystem.create_directory" "MUTATING" (New-WindowsDirectory $Cfg ([string]$payload.path) $parents)
  } elseif ($tool -eq "hara.files.write") {
    $mode=if ($payload.mode) {[string]$payload.mode} else {"rewrite"}
    $result=New-DirectResult "filesystem.write" "MUTATING" (Write-WindowsTextFile $Cfg ([string]$payload.path) ([string]$payload.content) $mode)
  } elseif ($tool -eq "hara.process.run") {
    $cwd=if ($payload.cwd) {[string]$payload.cwd} else {$null}
    $timeout=if ($null -ne $payload.timeout_ms) {[int]$payload.timeout_ms} else {3000}
    $maxLines=if ($null -ne $payload.max_lines) {[int]$payload.max_lines} else {200}
    $run=Invoke-WindowsOneShotProcess $Cfg ([string]$payload.command) $cwd $timeout $maxLines
    $exit=if ($null -ne $run.exit_code) {[int]$run.exit_code} else {$null}
    $result=New-DirectResult "process.run" "PROCESS_EXECUTION" $run $exit
  } elseif ($tool -eq "hara.health") {
    $result=@{
      services_bridge_state="PASS"; hara_services_state="PASS"
      registered_function_count=1; executable_function_count=1
      authority="HARA_SERVICES"; device=(Get-DeviceInfo $Cfg)
    }
  } elseif ($tool -eq "hara.functions.list") {
    $result=Get-Catalog
  } elseif ($tool -eq "hara.functions.describe") {
    $result=Get-Description ([string]$payload.function_id)
  } elseif ($tool -eq "hara.functions.invoke") {
    $result=Invoke-LocalFunction $Cfg ([string]$payload.function_id) $payload.arguments
  } elseif ($tool -eq "hara.receipts.get") {
    $result=Get-Receipt ([string]$payload.receipt_id_or_sha256)
    return @{
      state="PASS";operational_authority="HARA_SERVICES"
      runtime_authority_from_chatgpt=$false;mutation_performed=$false
      result=$result;blocker=$null
    }
  } else { throw "TOOL_ID_INVALID" }

  $receipt=New-Receipt $Cfg $Call "PASS" $result
  return @{
    state="PASS";operational_authority="HARA_SERVICES"
    runtime_authority_from_chatgpt=$false;mutation_performed=$false
    result=$result;blocker=$null;bridge_receipt_sha256=$receipt
  }
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $headers=@{Accept="application/json";Authorization="Bearer $Token"}
  $json=$Body | ConvertTo-Json -Depth 10 -Compress
  return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Headers $headers -Body $json -TimeoutSec $Timeout -MaximumRedirection 0
}

function Set-DeviceOffline($Cfg=$null) {
  try {
    if (-not $Cfg) { $Cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json }
    $SecureToken=ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
    $Token=Get-PlainText $SecureToken
    $result=Send-Json "$($Cfg.base_url)/api/device/offline" $Token @{device_id=[string]$Cfg.device_id;agent_version=$AgentVersion;architecture=[string]$Cfg.architecture} 5
    $ok=$result -and $result.ok -eq $true -and [string]$result.state -eq "OFFLINE"
    Write-ConsoleEvent "AGENT_OFFLINE" $null $(if ($ok) {"OFFLINE"} else {"FAILED"})
    return $ok
  } catch {
    Write-ConsoleEvent "OFFLINE_SYNC_ERROR" $null "FAILED" (Get-SafeErrorCode $_)
    return $false
  } finally {
    $Token=$null
  }
}

function Complete-Call($Cfg,[string]$Token,$Call,[string]$State,$Result,[string]$ErrorCode="") {
  $body=@{call_id=[string]$Call.call_id;state=$State;result=$Result}
  if ($ErrorCode) { $body.error_code=$ErrorCode }
  Send-Json "$($Cfg.base_url)/api/device/calls/complete" $Token $body 20 | Out-Null
}

function Invoke-AgentSelfTest {
  $previousReceiptDir=$script:ReceiptDir
  $previousOperationsDb=$script:OperationsDb
  $testRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-commander-selftest-"+[guid]::NewGuid().ToString("N"))
  try {
    $script:ReceiptDir=Join-Path $testRoot "receipts"
    $script:OperationsDb=Join-Path $testRoot "operations.sqlite3"
    New-Item -ItemType Directory -Path $script:ReceiptDir -Force | Out-Null
    $cfg=[pscustomobject]@{device_id="selftest";architecture="test"}
    $base=[ordered]@{call_id="selftest";request_id="selftest-001";tool_id="hara.health";payload=[pscustomobject]@{}}

    $health=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$health.state -ne "PASS") { throw "SELF_TEST_HEALTH_FAILED" }

    $base.request_id="selftest-002"; $base.tool_id="hara.functions.list"; $base.payload=[pscustomobject]@{}
    $listing=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([int]$listing.result.registered_function_count -ne 1) { throw "SELF_TEST_LIST_FAILED" }

    $base.request_id="selftest-003"; $base.tool_id="hara.functions.describe"
    $base.payload=[pscustomobject]@{function_id=$FunctionId}
    $description=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$description.result.function_id -ne $FunctionId) { throw "SELF_TEST_DESCRIBE_FAILED" }

    $base.request_id="selftest-004"; $base.tool_id="hara.functions.invoke"
    $base.payload=[pscustomobject]@{function_id=$FunctionId;arguments=[pscustomobject]@{argv=@()}}
    $invoked=Invoke-Tool $cfg ([pscustomobject]$base)
    $receipt=[string]$invoked.bridge_receipt_sha256
    if ($receipt -notmatch "^[0-9a-f]{64}$") { throw "SELF_TEST_RECEIPT_FAILED" }

    $base.request_id="selftest-win-info"; $base.tool_id="hara.device.info"; $base.payload=[pscustomobject]@{}
    $directInfo=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$directInfo.state -ne "PASS") { throw "SELF_TEST_DIRECT_DEVICE_INFO_FAILED" }

    $sample=Join-Path $testRoot "sample.txt"
    $sampleText="alpha"+[Environment]::NewLine+"beta"
    [IO.File]::WriteAllText($sample,$sampleText,(New-Object Text.UTF8Encoding($false)))
    $base.request_id="selftest-win-read"; $base.tool_id="hara.files.read"; $base.payload=[pscustomobject]@{path=$sample;offset=0;length=10}
    $directRead=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$directRead.result.function_id -ne "filesystem.read") { throw "SELF_TEST_WINDOWS_READ_FAILED" }

    $base.request_id="selftest-005"; $base.tool_id="hara.receipts.get"
    $base.payload=[pscustomobject]@{receipt_id_or_sha256=$receipt}
    $read=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$read.result.tool_id -ne "hara.functions.invoke") { throw "SELF_TEST_RECEIPTS_GET_FAILED" }
    $expectedStdoutSha=Get-Utf8Sha256 ([string]$invoked.result.stdout)
    if ([string]$read.result.result_binding -ne "STDOUT_SHA256_V1") { throw "SELF_TEST_RECEIPT_RESULT_BINDING_FAILED" }
    if ([string]$read.result.result_stdout_sha256 -ne $expectedStdoutSha) { throw "SELF_TEST_RECEIPT_RESULT_SHA_FAILED" }

    $blocked=$false
    try { Invoke-LocalFunction $cfg "shell.run" ([pscustomobject]@{argv=@()}) | Out-Null }
    catch { if ([string]$_.Exception.Message -eq "UNKNOWN_FUNCTION_ID") { $blocked=$true } }
    if (-not $blocked) { throw "SELF_TEST_ARBITRARY_FUNCTION_ALLOWED" }

    $previousSessionPath=$script:SessionPath
    $previousConsoleEvents=$script:ConsoleEvents
    try {
      $script:SessionPath=Join-Path $testRoot "operator-session.json"
      $script:ConsoleEvents=Join-Path $testRoot "console-events.jsonl"
      if (Test-OperatorSessionActive) { throw "SELF_TEST_SESSION_SHOULD_START_INACTIVE" }
      [ordered]@{
        schema="hara.commander-operator-session.v1"
        owner_pid=$PID
        owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
        started_at_utc=[DateTime]::UtcNow.ToString("o")
      } | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:SessionPath -Encoding UTF8
      if (-not (Test-OperatorSessionActive)) { throw "SELF_TEST_SESSION_GATE_FAILED" }
      $selfCall=[pscustomobject]@{request_id="r";tool_id="hara.health";payload=[pscustomobject]@{secret="never"}}
      Write-ConsoleEvent "SELFTEST" $selfCall
      Write-ConsoleEvent "PASS" $selfCall "COMPLETED"
      $entry=(Get-Content -LiteralPath $script:ConsoleEvents | Select-Object -Last 1) | ConvertFrom-Json
      if ($entry.payload_values_exposed -ne $false -or $entry.secret_material_exposed -ne $false) { throw "SELF_TEST_CONSOLE_SANITIZATION_FAILED" }
      if (($entry | ConvertTo-Json -Compress) -match "never") { throw "SELF_TEST_CONSOLE_PAYLOAD_LEAK" }
      $columns=@(Invoke-LocalDbQuery "PRAGMA table_info(activity_events)")
      $columnNames=@($columns | ForEach-Object {[string]$_["name"]})
      if ($columnNames -contains "payload_json" -or $columnNames -contains "result_json") { throw "SELF_TEST_LOCAL_DB_RAW_CONTENT_COLUMN" }
      $activity=Get-LocalActivityWindow "7d"
      if ([string]$activity.source -ne "LOCAL_SQLITE") { throw "SELF_TEST_LOCAL_DB_SOURCE_FAILED" }
      if ([int64]$activity.summary.total_calls -lt 1) { throw "SELF_TEST_LOCAL_DB_ACTIVITY_FAILED" }
      if (-not (Test-Path -LiteralPath $script:OperationsDb -PathType Leaf)) { throw "SELF_TEST_LOCAL_DB_MISSING" }

      $snapshot=Get-LocalActivityHeartbeatSnapshot
      if ([string]$snapshot.schema -ne "hara.commander-local-activity-snapshots.v1") { throw "SELF_TEST_LOCAL_SNAPSHOT_SCHEMA_FAILED" }
      if ($snapshot.customer_content_synced -ne $false) { throw "SELF_TEST_LOCAL_SNAPSHOT_PRIVACY_FAILED" }
      $snapshotJson=$snapshot | ConvertTo-Json -Depth 12 -Compress
      if ($snapshotJson -match '"payload_json"|"result_json"|"action_summary"|"stdout"|"stderr"') { throw "SELF_TEST_LOCAL_SNAPSHOT_CONTENT_LEAK" }
    } finally {
      $script:SessionPath=$previousSessionPath
      $script:ConsoleEvents=$previousConsoleEvents
    }

    Write-Host "COMMANDER_WINDOWS_OPERATOR_SESSION_GATE=PASS"
    Write-Host "COMMANDER_WINDOWS_CONSOLE_SANITIZATION=PASS"
    Write-Host "COMMANDER_WINDOWS_STARTER_READ=PASS"
    Write-Host "COMMANDER_WINDOWS_LOCAL_ACTIVITY_SQLITE=PASS"
    Write-Host "COMMANDER_WINDOWS_LOCAL_ACTIVITY_RAW_CONTENT=ABSENT"
    Write-Host "COMMANDER_WINDOWS_LOCAL_ACTIVITY_SNAPSHOT_PRIVACY=PASS"
    Write-Host "COMMANDER_WINDOWS_FIVE_TOOL_BRIDGE=PASS"
    Write-Host "COMMANDER_WINDOWS_ARBITRARY_FUNCTION=DENIED"
    Write-Host "COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS"
  } finally {
    $script:ReceiptDir=$previousReceiptDir
    $script:OperationsDb=$previousOperationsDb
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($args -contains "--self-test") { Invoke-AgentSelfTest; exit 0 }
if ($args -contains "--session-start" -or ($args.Count -gt 0 -and [string]$args[0] -eq "start")) { Start-OperatorConsole; exit 0 }
if ($args -contains "--session-status" -or ($args.Count -gt 0 -and [string]$args[0] -eq "status")) { Show-OperatorSession; exit 0 }
if ($args -contains "--session-stop" -or ($args.Count -gt 0 -and [string]$args[0] -eq "stop")) { Stop-OperatorSession; exit 0 }
if ($args.Count -gt 0 -and @("help","--help","-h") -contains [string]$args[0]) {
  Write-Host "Usage: hara-commander [start|status|stop|help]"
  exit 0
}
if ($args.Count -gt 0) {
  Write-Host ("HARA_COMMANDER_UNKNOWN_COMMAND="+[string]$args[0])
  Write-Host "Usage: hara-commander [start|status|stop|help]"
  exit 64
}

try {
  $StartupCfg=Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
  if (-not $StartupCfg.base_url -or -not $StartupCfg.device_id -or -not $StartupCfg.encrypted_device_token -or -not $StartupCfg.architecture) { throw "DEVICE_CONFIG_INVALID" }
  $StartupSecureToken=ConvertTo-SecureString ([string]$StartupCfg.encrypted_device_token)
  $StartupToken=Get-PlainText $StartupSecureToken
  if ([string]::IsNullOrWhiteSpace($StartupToken)) { throw "DEVICE_CONFIG_INVALID" }
  $StartupToken=$null
  if (-not (Try-SetRuntimeStatus -StartedAt ([DateTime]::UtcNow.ToString("o")))) {
    throw "RUNTIME_STATUS_STARTUP_WRITE_FAILED"
  }
} catch {
  $code=Get-SafeErrorCode $_
  throw $code
}

$LastHeartbeat=[datetime]::MinValue
$PollHotUntil=(Get-Date).AddSeconds($CallPollStartupHotSeconds)
$LastErrorCode=$null
$LastErrorWrite=[datetime]::MinValue
$RateLimitBackoffSeconds=0
$RateLimitBackoffUntil=[datetime]::MinValue
$WasAuthorized=$false
if (-not (Test-OperatorSessionActive) -and (Get-ApprovalMode $StartupCfg) -ne "PERSISTENT_TRUSTED") {
  Set-DeviceOffline $StartupCfg | Out-Null
  Write-ConsoleEvent "AGENT_INERT" $null "LOCAL_SESSION_REQUIRED"
}
while ($true) {
  $Cfg=Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
  $Persistent=(Get-ApprovalMode $Cfg) -eq "PERSISTENT_TRUSTED"
  if (-not $Persistent -and -not (Test-OperatorSessionActive)) {
    $WasAuthorized=$false
    Start-Sleep -Seconds 1
    continue
  }
  if (-not $WasAuthorized) {
    $LastHeartbeat=[datetime]::MinValue
    $PollHotUntil=(Get-Date).AddSeconds($CallPollStartupHotSeconds)
    Write-ConsoleEvent "AGENT_ONLINE" $null "AUTHORIZED"
    $WasAuthorized=$true
  }
  if ((Get-Date) -lt $RateLimitBackoffUntil) {
    $remaining=[Math]::Max(1,[Math]::Ceiling(($RateLimitBackoffUntil-(Get-Date)).TotalSeconds))
    Start-Sleep -Seconds ([Math]::Min(5,$remaining))
    continue
  }
  try {
    $SecureToken=ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
    $DeviceToken=Get-PlainText $SecureToken
    if (((Get-Date)-$LastHeartbeat).TotalSeconds -ge $HeartbeatSeconds) {
      Send-Json "$($Cfg.base_url)/api/device/heartbeat" $DeviceToken @{
        device_id=[string]$Cfg.device_id
        architecture=[string]$Cfg.architecture
        agent_version=$AgentVersion
        approval_mode=(Get-ApprovalMode $Cfg)
        activity_snapshots=(Get-LocalActivityHeartbeatSnapshot)
      } 20 | Out-Null
      $LastHeartbeat=Get-Date
      $LastErrorCode=$null
      Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
    }
    try {
      $Call=Send-Json "$($Cfg.base_url)/api/device/calls/next" $DeviceToken @{} 25
    } catch {
      if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 204) { $Call=$null } else { throw }
    }
    if ($null -ne $Call -and $Call.call_id) {
      $PollHotUntil=(Get-Date).AddSeconds($CallPollHotWindowSeconds)
      if (-not $Persistent -and -not (Test-OperatorSessionActive)) {
        $code="LOCAL_OPERATOR_SESSION_REQUIRED"
        Write-ConsoleEvent "DENIED" $Call "DENIED" $code
        $denied=@{
          state="DENIED";operational_authority="LOCAL_OPERATOR_SESSION"
          runtime_authority_from_chatgpt=$false;mutation_performed=$false
          result=@{};blocker=@{code=$code}
        }
        Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
      } else {
        Write-ConsoleEvent "RECEIVED" $Call "PENDING"
        try {
          Write-ConsoleEvent "EXECUTING" $Call "EXECUTING"
          $result=Invoke-Tool $Cfg $Call
          Complete-Call $Cfg $DeviceToken $Call "COMPLETED" $result
          $receipt=if ($result.bridge_receipt_sha256) {[string]$result.bridge_receipt_sha256} else {""}
          Write-ConsoleEvent "PASS" $Call "COMPLETED" "" $receipt
        } catch {
          $code=Get-SafeErrorCode $_
          $operational=Test-OperationalErrorCode $code
          Write-ConsoleEvent $(if($operational){"OPERATIONAL"}else{"DENIED"}) $Call $(if($operational){"EXPECTED"}else{"FAILED"}) $code
          $denied=@{
            state="DENIED";operational_authority="LOCAL_OPERATOR_SESSION"
            runtime_authority_from_chatgpt=$false;mutation_performed=$false
            result=@{};blocker=@{code=$code}
          }
          Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
        }
      }
    }
    $RateLimitBackoffSeconds=0
    $RateLimitBackoffUntil=[datetime]::MinValue
  } catch {
    $code=Get-SafeErrorCode $_
    $now=Get-Date
    if ($code -eq "HTTP_429") {
      if ($RateLimitBackoffSeconds -le 0) { $RateLimitBackoffSeconds=$RateLimitBackoffInitialSeconds }
      else { $RateLimitBackoffSeconds=[Math]::Min($RateLimitBackoffMaxSeconds,$RateLimitBackoffSeconds*2) }
      $RateLimitBackoffUntil=(Get-Date).AddSeconds($RateLimitBackoffSeconds)
      $PollHotUntil=[datetime]::MinValue
      Write-ConsoleEvent "TRANSPORT_BACKOFF" $null "DEGRADED" $code
    }
    if ($code -ne $LastErrorCode -or ($now-$LastErrorWrite).TotalSeconds -ge 60) {
      Try-SetRuntimeStatus -ErrorCode $code -ErrorAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
      $LastErrorCode=$code
      $LastErrorWrite=$now
    }
  } finally {
    $DeviceToken=$null
  }
  $PollSleep=if ((Get-Date) -lt $PollHotUntil) {$CallPollHotSeconds} else {$CallPollIdleSeconds}
  Start-Sleep -Seconds $PollSleep
}
