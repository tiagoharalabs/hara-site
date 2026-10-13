$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$RuntimeStatus = Join-Path $Root "runtime-status.json"
$SessionPath = Join-Path $Root "operator-session.json"
$ConsoleEvents = Join-Path $Root "console-events.jsonl"
$PendingApprovalPath = Join-Path $Root "pending-action-approval.json"
$ApprovalResponsePath = Join-Path $Root "action-approval-response.json"
$ApprovalTimeoutSeconds = 900
$OperationsDb = Join-Path $Root "operations.sqlite3"
$AgentTaskName = "HARA Commander Agent"
$SessionMaxHours = 12
$AgentVersion = "0.3.54"
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
  $lastHeartbeat=if ($PSBoundParameters.ContainsKey("HeartbeatAt")) {$HeartbeatAt} elseif ($existing) {[string]$existing.last_successful_heartbeat_at_utc} else {$null}
  $runtimeStartedAt=if ($PSBoundParameters.ContainsKey("StartedAt")) {$StartedAt} elseif ($existing) {[string]$existing.started_at_utc} else {$null}
  $runtimeErrorCode=if ($PSBoundParameters.ContainsKey("ErrorCode")) {$ErrorCode} elseif ($existing) {[string]$existing.last_runtime_error_code} else {$null}
  $runtimeErrorAt=if ($PSBoundParameters.ContainsKey("ErrorAt")) {$ErrorAt} elseif ($existing) {[string]$existing.last_runtime_error_at_utc} else {$null}
  $payload=[ordered]@{
    schema="hara.commander-agent-runtime-status.v1"
    agent_version=$AgentVersion
    started_at_utc=$runtimeStartedAt
    last_successful_heartbeat_at_utc=$lastHeartbeat
    last_runtime_error_code=$runtimeErrorCode
    last_runtime_error_at_utc=$runtimeErrorAt
    updated_at_utc=[DateTime]::UtcNow.ToString("o")
  }
  $tmp=$RuntimeStatus+".tmp"
  $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -Force -LiteralPath $tmp -Destination $RuntimeStatus
}

function Try-SetRuntimeStatus([string]$HeartbeatAt=$null,[string]$ErrorCode=$null,[string]$ErrorAt=$null,[string]$StartedAt=$null) {
  try {
    Set-RuntimeStatus @PSBoundParameters
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
  try {
    $ownerPid=[int]$session.owner_pid
    if ($ownerPid -le 1) { return $null }
    $proc=Get-OperatorProcess $ownerPid
    if (-not $proc) { return $null }
    $ownerStarted=$proc.StartTime
    if ($ownerStarted -isnot [DateTime]) { return $null }
    $marker=$ownerStarted.ToUniversalTime().ToString("o")
    if ($marker -ne [string]$session.owner_started_at_utc) { return $null }
  } catch { return $null }
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
  if (@("hara.process.run","hara.process.start") -contains $tool) {
    return $tool+" cwd="+$(if ($payload.cwd) {[string]$payload.cwd} else {"~"})+
      " timeout_ms="+$(if ($null -ne $payload.timeout_ms) {[string]$payload.timeout_ms} else {"3000"})+
      " command="+(Protect-LocalCommandPreview ([string]$payload.command))
  }
  if ($tool -eq "hara.process.interact") {
    return "process.interact session_id="+[string]$payload.session_id+
      " input_preview="+(Protect-LocalCommandPreview ([string]$payload.input))
  }
  if ($tool -eq "hara.process.kill") {
    return "process.kill session_id="+[string]$payload.session_id+
      " force="+$(if ($payload.force) {"true"} else {"false"})
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
    # Persistent telemetry must never include command previews, paths or payload values.
    # The transient consent prompt still uses Get-LocalActionSummary locally.
    action_summary=$null
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

function Start-ManualOperatorConsole {
  # Repeated start resumes the worker behind an existing operator console.
  # It neither renews that session nor stops another console's worker.
  if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { throw "DEVICE_NOT_ENROLLED" }
  $existing=Get-OperatorSession
  $task = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
  if (-not $task) { throw "AGENT_TASK_NOT_INSTALLED" }
  $startedHere = [string]$task.State -ne "Running"
  if ($startedHere) {
    Start-ScheduledTask -TaskName $AgentTaskName -ErrorAction Stop
    Start-Sleep -Seconds 1
    $nowRunning = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
    if (-not $nowRunning -or [string]$nowRunning.State -ne "Running") { throw "AGENT_TASK_START_FAILED" }
  }
  # The prior console may have closed while the scheduled task was starting.
  $existing=Get-OperatorSession
  if ($existing) {
    Write-Host "HARA_COMMANDER_SESSION=ACTIVE"
    Write-Host $(if ($startedHere) {"HARA_COMMANDER_AGENT=RESUMED"} else {"HARA_COMMANDER_AGENT=RUNNING"})
    Write-Host "Use a janela do operador que ja esta aberta para aprovar cada acao."
    return
  }
  $sessionOpenedHere=$false
  try {
    Start-OperatorConsole ([ref]$sessionOpenedHere)
  } finally {
    # A competing start can acquire the session after the initial check.
    # Only the caller that actually opened a session may stop its own task,
    # and it must preserve any other active operator session.
    if ($startedHere -and $sessionOpenedHere) {
      Invoke-WithLocalApprovalLock {
        $currentTask = Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
        $active=Get-OperatorSession
        if ($currentTask -and -not $currentTask.Triggers -and -not $active) {
          Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
        }
      } | Out-Null
    }
  }
}

function Start-OperatorConsole([ref]$SessionOpened=$null) {
  $cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $session=[ordered]@{
    schema="hara.commander-operator-session.v1"
    owner_pid=$PID
    owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
    device_id=[string]$cfg.device_id
    authorization="LOCAL_OPERATOR_TERMINAL"
  }
  Invoke-WithLocalApprovalLock {
    $existing=Get-OperatorSession
    if ($existing -and [int]$existing.owner_pid -ne $PID) { throw "OPERATOR_SESSION_ALREADY_ACTIVE" }
    $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
    if ($null -ne $SessionOpened) { $SessionOpened.Value=$true }
  } | Out-Null
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
      Respond-ToLocalApprovalRequest
      Start-Sleep -Milliseconds 250
    }
  } finally {
    Invoke-WithLocalApprovalLock {
      if (Test-Path -LiteralPath $SessionPath -PathType Leaf) {
        try {
          $current=Get-Content -Raw -LiteralPath $SessionPath | ConvertFrom-Json
          if ([int]$current.owner_pid -eq $PID -and
              [string]$current.owner_started_at_utc -ceq [string]$session.owner_started_at_utc) {
            Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
          }
        } catch {}
      }
    } | Out-Null
    Set-DeviceOffline $cfg | Out-Null
    Write-ConsoleEvent "SESSION_CLOSE" $null "REVOKED"
    Write-Host "HARA_COMMANDER_SESSION=INACTIVE"
  }
}

function Stop-OperatorSession {
  $was=Invoke-WithLocalApprovalLock {
    $present=Test-Path -LiteralPath $SessionPath -PathType Leaf
    Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
    return $present
  }
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

function Invoke-WithLocalApprovalLock([Alias("Action")][scriptblock]$ApprovalCriticalSection) {
  # Prefix private locals so caller scriptblocks cannot resolve unrelated names.
  $approvalMutexIdentity=[IO.Path]::GetFullPath($script:PendingApprovalPath).ToUpperInvariant()
  $approvalMutexName="Global\HARACommanderApproval_"+(Get-Utf8Sha256 $approvalMutexIdentity)
  $approvalMutexObject=New-Object -TypeName System.Threading.Mutex -ArgumentList @($false,$approvalMutexName)
  $approvalMutexHeld=$false
  try {
    try { $approvalMutexHeld=$approvalMutexObject.WaitOne(2000) }
    catch [Threading.AbandonedMutexException] { $approvalMutexHeld=$true }
    if (-not $approvalMutexHeld) { throw "LOCAL_APPROVAL_LOCK_BUSY" }
    & $ApprovalCriticalSection
  } finally {
    if ($approvalMutexHeld) { $approvalMutexObject.ReleaseMutex() }
    $approvalMutexObject.Dispose()
  }
}

function Test-LocalApprovalConsumerAlive($Pending) {
  # Consent cannot be sent to a consumer that died while its prompt was open.
  try {
    if ([int]$Pending.consumer_pid -le 1 -or
        [string]::IsNullOrWhiteSpace([string]$Pending.consumer_started_at_utc)) { return $false }
    $consumer=Get-OperatorProcess ([int]$Pending.consumer_pid)
    if (-not $consumer) { return $false }
    $marker=$consumer.StartTime.ToUniversalTime().ToString("o")
    return $marker -ceq [string]$Pending.consumer_started_at_utc
  } catch { return $false }
}

function Test-LocalApprovalRequestCurrent($Pending) {
  # Call under Invoke-WithLocalApprovalLock when publishing or consuming.
  # Revalidation also binds what the human saw to the still-current request.
  try {
    if (-not $Pending -or
        [string]$Pending.schema -cne "hara.commander-local-action-approval.v1" -or
        [string]$Pending.nonce -cnotmatch "^[0-9a-f]{32}$" -or
        [string]$Pending.challenge -cne ([string]$Pending.nonce).Substring(0,8).ToUpperInvariant() -or
        [string]$Pending.arguments_sha256 -cnotmatch "^[0-9a-f]{64}$" -or
        [string]::IsNullOrWhiteSpace([string]$Pending.request_id)) { return $false }
    $created=[DateTime]::Parse([string]$Pending.created_at_utc).ToUniversalTime()
    $expires=[DateTime]::Parse([string]$Pending.expires_at_utc).ToUniversalTime()
    if ($expires -le $created -or [DateTime]::UtcNow -ge $expires) { return $false }
    if (-not (Test-Path -LiteralPath $PendingApprovalPath -PathType Leaf)) { return $false }
    $current=Get-Content -Raw -LiteralPath $PendingApprovalPath | ConvertFrom-Json
    foreach($field in @(
      "schema","nonce","challenge","request_id","tool_id","arguments_sha256",
      "owner_started_at_utc","consumer_started_at_utc","created_at_utc","expires_at_utc","action_summary"
    )) {
      if ([string]$current.$field -cne [string]$Pending.$field) { return $false }
    }
    if ([int]$current.owner_pid -ne [int]$Pending.owner_pid -or
        [int]$current.consumer_pid -ne [int]$Pending.consumer_pid) { return $false }
    if (-not (Test-LocalApprovalConsumerAlive $Pending)) { return $false }
    $active=Get-OperatorSession
    if (-not $active -or [int]$active.owner_pid -ne [int]$Pending.owner_pid -or
        [string]$active.owner_started_at_utc -cne [string]$Pending.owner_started_at_utc) { return $false }
    return $true
  } catch { return $false }
}

function Remove-LocalApprovalFiles([string]$Nonce) {
  # A late cleanup must never delete a newer request or its response.
  Invoke-WithLocalApprovalLock {
    foreach($path in @($PendingApprovalPath,$ApprovalResponsePath)) {
      if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
      try {
        $entry=Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
        if ([string]$entry.nonce -ceq $Nonce) {
          Remove-Item -LiteralPath $path -Force -ErrorAction Stop
        }
      } catch {}
    }
  } | Out-Null
}

function Send-LocalApprovalConsumerHeartbeat($Cfg,[string]$ApprovalDeviceToken) {
  # The waiting consumer keeps its authenticated lease; heartbeat never grants consent.
  if (-not $Cfg -or -not $Cfg.base_url -or -not $Cfg.device_id -or
      [string]::IsNullOrWhiteSpace($ApprovalDeviceToken)) { return $false }
  try {
    Send-Json "$($Cfg.base_url)/api/device/heartbeat" $ApprovalDeviceToken @{
      device_id=[string]$Cfg.device_id
      architecture=[string]$Cfg.architecture
      agent_version=$AgentVersion
      approval_mode=(Get-ApprovalMode $Cfg)
      activity_snapshots=(Get-LocalActivityHeartbeatSnapshot)
    } 5 | Out-Null
    $script:LastHeartbeat=Get-Date
    Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o")) -ErrorCode "" -ErrorAt "" | Out-Null
    return $true
  } catch {
    Try-SetRuntimeStatus -ErrorCode (Get-SafeErrorCode $_) -ErrorAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
    return $false
  }
}

function Invoke-LocalActionApproval($Call,$Cfg=$null,[string]$ApprovalDeviceToken=$null) {
  # The user, not ChatGPT or an API response, must approve the exact operation.
  # A per-action nonce and SHA-256 of the payload bind the local response.
  $session=Get-OperatorSession
  if (-not $session) { throw "LOCAL_OPERATOR_SESSION_REQUIRED" }
  if ($Call.request_id -eq $null -or [string]$Call.request_id -eq "") {
    throw "LOCAL_APPROVAL_REQUEST_ID_REQUIRED"
  }
  $payloadJson=$Call.payload | ConvertTo-Json -Depth 10 -Compress
  $nonce=[guid]::NewGuid().ToString("N")
  $digest=Get-Utf8Sha256 ([string]$Call.tool_id+"|"+[string]$Call.request_id+"|"+[string]$payloadJson)
  $expires=[DateTime]::UtcNow.AddSeconds($ApprovalTimeoutSeconds)
  $pending=[ordered]@{
    schema="hara.commander-local-action-approval.v1"
    nonce=$nonce
    challenge=$nonce.Substring(0,8).ToUpperInvariant()
    request_id=[string]$Call.request_id
    tool_id=[string]$Call.tool_id
    arguments_sha256=$digest
    owner_pid=[int]$session.owner_pid
    owner_started_at_utc=[string]$session.owner_started_at_utc
    consumer_pid=$PID
    consumer_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    created_at_utc=[DateTime]::UtcNow.ToString("o")
    expires_at_utc=$expires.ToString("o")
    action_summary=Get-LocalActionSummary $Call
  }
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $temporary=$PendingApprovalPath+"."+[guid]::NewGuid().ToString("N")+".tmp"
  try {
    Invoke-WithLocalApprovalLock {
      $expiredPrior=$null
      foreach($existing in @($PendingApprovalPath,$ApprovalResponsePath)) {
        if (Test-Path -LiteralPath $existing -PathType Leaf) {
          # A future request remains BUSY for its entire approval window.
          # Cleanup never grants consent and is bound to unchanged file bytes.
          $priorHash=(Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash
          $older=$false
          try {
            $prior=Get-Content -Raw -LiteralPath $existing | ConvertFrom-Json
            if ($existing -ceq $PendingApprovalPath) {
              $priorExpires=[DateTime]::Parse([string]$prior.expires_at_utc).ToUniversalTime()
              $older=([string]$prior.schema -ceq "hara.commander-local-action-approval.v1" -and
                [string]$prior.nonce -cmatch "^[0-9a-f]{32}$" -and
                [string]$prior.arguments_sha256 -cmatch "^[0-9a-f]{64}$" -and
                [int]$prior.owner_pid -gt 1 -and [int]$prior.consumer_pid -gt 1 -and
                -not [string]::IsNullOrWhiteSpace([string]$prior.owner_started_at_utc) -and
                -not [string]::IsNullOrWhiteSpace([string]$prior.consumer_started_at_utc) -and
                $priorExpires -le [DateTime]::UtcNow)
              if ($older) { $expiredPrior=$prior }
            } else {
              $priorResponded=[DateTime]::Parse([string]$prior.responded_at_utc).ToUniversalTime()
              $replyValid=([string]$prior.schema -ceq "hara.commander-local-action-response.v1" -and
                [string]$prior.nonce -cmatch "^[0-9a-f]{32}$" -and
                [string]$prior.arguments_sha256 -cmatch "^[0-9a-f]{64}$" -and
                $prior.approved -is [bool] -and [int]$prior.owner_pid -gt 1 -and
                [int]$prior.consumer_pid -gt 1 -and
                -not [string]::IsNullOrWhiteSpace([string]$prior.owner_started_at_utc) -and
                -not [string]::IsNullOrWhiteSpace([string]$prior.consumer_started_at_utc))
              if ($expiredPrior) {
                $older=($replyValid -and [string]$prior.nonce -ceq [string]$expiredPrior.nonce -and
                  [string]$prior.request_id -ceq [string]$expiredPrior.request_id -and
                  [string]$prior.arguments_sha256 -ceq [string]$expiredPrior.arguments_sha256 -and
                  [int]$prior.owner_pid -eq [int]$expiredPrior.owner_pid -and
                  [string]$prior.owner_started_at_utc -ceq [string]$expiredPrior.owner_started_at_utc -and
                  [int]$prior.consumer_pid -eq [int]$expiredPrior.consumer_pid -and
                  [string]$prior.consumer_started_at_utc -ceq [string]$expiredPrior.consumer_started_at_utc)
              } else {
                $cutoff=[DateTime]::UtcNow.AddSeconds(-[Math]::Max(120,$ApprovalTimeoutSeconds))
                $older=($replyValid -and $priorResponded -le $cutoff -and
                  (Get-Item -LiteralPath $existing).LastWriteTimeUtc -le $cutoff)
              }
            }
          } catch { $older=$false }
          if ($older -and (Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash -ceq $priorHash) {
            Remove-Item -LiteralPath $existing -Force
          } else { throw "LOCAL_APPROVAL_REQUEST_BUSY" }
        }
      }
      [IO.File]::WriteAllText($temporary,($pending | ConvertTo-Json -Depth 5 -Compress),(New-Object Text.UTF8Encoding($false)))
      if ([DateTime]::UtcNow -ge $expires) { throw "LOCAL_ACTION_APPROVAL_EXPIRED" }
      [IO.File]::Move($temporary,$PendingApprovalPath)
    } | Out-Null
    $nextApprovalHeartbeat=[DateTime]::UtcNow.AddSeconds([Math]::Max(1,$HeartbeatSeconds))
    while ([DateTime]::UtcNow -lt $expires) {
      $accepted=Invoke-WithLocalApprovalLock {
        $active=Get-OperatorSession
        if (-not $active -or [int]$active.owner_pid -ne [int]$pending.owner_pid -or
            [string]$active.owner_started_at_utc -cne [string]$pending.owner_started_at_utc) {
          throw "LOCAL_OPERATOR_SESSION_REQUIRED"
        }
        if ([DateTime]::UtcNow -ge $expires) { throw "LOCAL_ACTION_APPROVAL_EXPIRED" }
        if (-not (Test-LocalApprovalRequestCurrent $pending)) {
          throw "LOCAL_ACTION_APPROVAL_REQUEST_CHANGED"
        }
        if (-not (Test-Path -LiteralPath $ApprovalResponsePath -PathType Leaf)) { return $false }
        $answer=Get-Content -Raw -LiteralPath $ApprovalResponsePath | ConvertFrom-Json
        if ($answer.approved -isnot [bool] -or
            [string]$answer.schema -cne "hara.commander-local-action-response.v1" -or
            [string]$answer.nonce -cne $nonce -or
            [string]$answer.request_id -cne [string]$pending.request_id -or
            [string]$answer.arguments_sha256 -cne $digest -or
            [int]$answer.owner_pid -ne [int]$pending.owner_pid -or
            [string]$answer.owner_started_at_utc -cne [string]$pending.owner_started_at_utc -or
            [int]$answer.consumer_pid -ne [int]$pending.consumer_pid -or
            [string]$answer.consumer_started_at_utc -cne [string]$pending.consumer_started_at_utc) {
          throw "LOCAL_ACTION_APPROVAL_RESPONSE_INVALID"
        }
        try { $responded=[DateTime]::Parse([string]$answer.responded_at_utc).ToUniversalTime() }
        catch { throw "LOCAL_ACTION_APPROVAL_RESPONSE_INVALID" }
        $created=[DateTime]::Parse([string]$pending.created_at_utc).ToUniversalTime()
        if ($responded -lt $created -or $responded -ge $expires -or
            $responded -gt [DateTime]::UtcNow) { throw "LOCAL_ACTION_APPROVAL_RESPONSE_INVALID" }
        if ($answer.approved -cne $true) { throw "HUMAN_ACTION_APPROVAL_DENIED" }
        # Session, current request, and time are checked again at acceptance.
        if ([DateTime]::UtcNow -ge $expires) { throw "LOCAL_ACTION_APPROVAL_EXPIRED" }
        if (-not (Test-LocalApprovalRequestCurrent $pending)) {
          throw "LOCAL_ACTION_APPROVAL_REQUEST_CHANGED"
        }
        return $true
      }
      if ($accepted -eq $true) { return $true }
      # Consume a valid reply first; never spend the final five seconds on I/O.
      if ([DateTime]::UtcNow -ge $nextApprovalHeartbeat -and
          ($expires-[DateTime]::UtcNow).TotalSeconds -gt 5) {
        $nextApprovalHeartbeat=[DateTime]::UtcNow.AddSeconds([Math]::Max(1,$HeartbeatSeconds))
        Send-LocalApprovalConsumerHeartbeat $Cfg $ApprovalDeviceToken | Out-Null
      }
      Start-Sleep -Milliseconds 150
    }
    throw "LOCAL_ACTION_APPROVAL_EXPIRED"
  } finally {
    if (Test-Path -LiteralPath $temporary) {
      Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
    Remove-LocalApprovalFiles $nonce
  }
}

function Assert-StarterMutationAuthorized($Cfg,$Call) {
  $mode=Get-ApprovalMode $Cfg
  if ($mode -eq "ASK_EVERY_ACTION") {
    $approvedSession=Get-OperatorSession
    if (-not $approvedSession) { throw "LOCAL_OPERATOR_SESSION_REQUIRED" }
    Invoke-LocalActionApproval $Call $Cfg $script:DeviceToken | Out-Null
    # Cleanup may wait for the console mutex. Revocation during that wait
    # must deny before the caller starts its filesystem or process action.
    $active=Invoke-WithLocalApprovalLock { Get-OperatorSession }
    if (-not $active -or [int]$active.owner_pid -ne [int]$approvedSession.owner_pid -or
        [string]$active.owner_started_at_utc -cne [string]$approvedSession.owner_started_at_utc) {
      throw "LOCAL_OPERATOR_SESSION_REQUIRED"
    }
    return
  }
  if ($mode -eq "SESSION_TRUSTED" -and -not (Test-OperatorSessionActive)) {
    throw "LOCAL_OPERATOR_SESSION_REQUIRED"
  }
}

function Initialize-LocalApprovalConsoleInput {
  # Redirected stdin and hosts without a real console never grant consent.
  try {
    if ($Host.Name -ne "ConsoleHost" -or [Console]::IsInputRedirected) {
      throw "LOCAL_APPROVAL_CONSOLE_UNAVAILABLE"
    }
    $available=[Console]::KeyAvailable
    return $true
  } catch { throw "LOCAL_APPROVAL_CONSOLE_UNAVAILABLE" }
}

function Read-LocalApprovalConsoleKey {
  try {
    if ([Console]::IsInputRedirected) { throw "LOCAL_APPROVAL_CONSOLE_UNAVAILABLE" }
    if ([Console]::KeyAvailable) { return [Console]::ReadKey($true) }
    return $null
  } catch { throw "LOCAL_APPROVAL_CONSOLE_UNAVAILABLE" }
}

function Clear-LocalApprovalConsoleInput {
  # Bounded draining prevents keys from an expired prompt reaching the next one.
  for($i=0;$i -lt 256;$i++) {
    $key=Read-LocalApprovalConsoleKey
    if ($null -eq $key) { return }
    if ($key.Key -eq [ConsoleKey]::C -and
        ($key.Modifiers -band [ConsoleModifiers]::Control)) {
      throw "LOCAL_OPERATOR_SESSION_REVOKED"
    }
  }
  throw "LOCAL_APPROVAL_CONSOLE_INPUT_OVERFLOW"
}

function Read-LocalApprovalResponse($Pending) {
  Initialize-LocalApprovalConsoleInput | Out-Null
  Clear-LocalApprovalConsoleInput
  $text=""
  $expires=[DateTime]::Parse([string]$Pending.expires_at_utc).ToUniversalTime()
  Write-Host ("Digite a frase completa APROVAR "+[string]$Pending.challenge+" e pressione Enter para enviar (APROVAR sozinho nao autoriza; Enter vazio nega): ") -NoNewline
  try {
    while ([DateTime]::UtcNow -lt $expires) {
      $current=Invoke-WithLocalApprovalLock { Test-LocalApprovalRequestCurrent $Pending }
      if (-not $current) { break }
      $key=Read-LocalApprovalConsoleKey
      if ($null -eq $key) { Start-Sleep -Milliseconds 100; continue }
      if ($key.Key -eq [ConsoleKey]::C -and
          ($key.Modifiers -band [ConsoleModifiers]::Control)) {
        throw "LOCAL_OPERATOR_SESSION_REVOKED"
      }
      if ($key.Key -eq [ConsoleKey]::Enter) {
        Write-Host ""
        $stillCurrent=Invoke-WithLocalApprovalLock { Test-LocalApprovalRequestCurrent $Pending }
        if ([DateTime]::UtcNow -ge $expires -or -not $stillCurrent) {
          return [pscustomobject]@{state="EXPIRED";text=$null}
        }
        # Publishing revalidates time and request under the same worker mutex.
        return [pscustomobject]@{state="SUBMITTED";text=$text}
      }
      if ($key.Key -eq [ConsoleKey]::Backspace) {
        if ($text.Length -gt 0) {
          $text=$text.Substring(0,$text.Length-1)
          Write-Host ([char]8+" "+[char]8) -NoNewline
        }
        continue
      }
      $char=[int]$key.KeyChar
      if ($char -ge 32 -and $char -le 126 -and $text.Length -lt 64 -and
          -not ($key.Modifiers -band ([ConsoleModifiers]::Control -bor [ConsoleModifiers]::Alt))) {
        $text+=[string]$key.KeyChar
        Write-Host ([string]$key.KeyChar) -NoNewline
      }
    }
    Write-Host ""
    return [pscustomobject]@{state="EXPIRED";text=$null}
  } finally {
    $text=$null
    Clear-LocalApprovalConsoleInput
  }
}

function Publish-LocalApprovalResponse($Pending,[bool]$Approved) {
  # The UI writes only while this exact request and session remain valid.
  # Publication and worker cleanup cannot interleave across the mutex.
  return Invoke-WithLocalApprovalLock {
    if ([int]$Pending.owner_pid -ne $PID -or
        -not (Test-LocalApprovalRequestCurrent $Pending) -or
        (Test-Path -LiteralPath $ApprovalResponsePath)) { return $false }
    $reply=[ordered]@{
      schema="hara.commander-local-action-response.v1"
      nonce=[string]$Pending.nonce
      request_id=[string]$Pending.request_id
      arguments_sha256=[string]$Pending.arguments_sha256
      owner_pid=$PID
      owner_started_at_utc=[string]$Pending.owner_started_at_utc
      consumer_pid=[int]$Pending.consumer_pid
      consumer_started_at_utc=[string]$Pending.consumer_started_at_utc
      approved=[bool]$Approved
      responded_at_utc=[DateTime]::UtcNow.ToString("o")
    }
    $temporary=$ApprovalResponsePath+"."+[guid]::NewGuid().ToString("N")+".tmp"
    try {
      [IO.File]::WriteAllText($temporary,($reply|ConvertTo-Json -Depth 4 -Compress),(New-Object Text.UTF8Encoding($false)))
      if (-not (Test-LocalApprovalRequestCurrent $Pending)) { return $false }
      [IO.File]::Move($temporary,$ApprovalResponsePath)
      return $true
    } finally {
      if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

function Respond-ToLocalApprovalRequest {
  # Only the process owning the active operator console reads human input.
  $pending=Invoke-WithLocalApprovalLock {
    if (-not (Test-Path -LiteralPath $PendingApprovalPath -PathType Leaf)) { return $null }
    try { $candidate=Get-Content -Raw -LiteralPath $PendingApprovalPath | ConvertFrom-Json }
    catch { return $null }
    if ([int]$candidate.owner_pid -ne $PID -or
        -not (Test-LocalApprovalRequestCurrent $candidate) -or
        (Test-Path -LiteralPath $ApprovalResponsePath)) { return $null }
    return $candidate
  }
  if (-not $pending) { return }
  Write-Host ""
  Write-Host "H.A.R.A. - SOLICITACAO DE APROVACAO INDIVIDUAL" -ForegroundColor Yellow
  Write-Host ("Ferramenta: "+[string]$pending.tool_id)
  Write-Host ("Resumo local: "+[string]$pending.action_summary)
  Write-Host ("SHA256 argumentos: "+[string]$pending.arguments_sha256)
  Write-Host "Apenas esta acao sera autorizada. A sessao nao vira permanente."
  Write-Host ("Voce tem ate "+[int]($ApprovalTimeoutSeconds/60)+" minutos para aprovar esta acao; depois, descarte esta solicitacao.")
  $response=Read-LocalApprovalResponse $pending
  if ($response.state -cne "SUBMITTED") {
    Write-Host "APROVACAO_INDIVIDUAL=EXPIRADA" -ForegroundColor Yellow
    return
  }
  $approved=[string]$response.text -ceq ("APROVAR "+[string]$pending.challenge)
  $published=Publish-LocalApprovalResponse $pending $approved
  $response=$null
  if (-not $published) {
    Write-Host "APROVACAO_INDIVIDUAL=EXPIRADA" -ForegroundColor Yellow
    return
  }
  Write-Host ($(if($approved){"APROVACAO_INDIVIDUAL=ENVIADA"}else{"APROVACAO_INDIVIDUAL=NEGADA"}))
}

# Windows PowerShell 5.1 has no durable PTY abstraction. This runspace-safe
# .NET process wrapper handles asynchronous streams without PowerShell event
# callbacks on threads lacking a runspace. Limits: 8 active processes,
# 5,000 lines or 2 MiB retained per session, 15m completed retention.
$script:ManagedWindowsSessions=@{}
$script:WindowsSessionMaxActive=8
$script:WindowsSessionFinishedRetentionSeconds=900

function Initialize-WindowsManagedProcessType {
  if ("HaraWindowsProcessSession" -as [type]) { return }
  $source=@"
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

public sealed class HaraWindowsProcessSession : IDisposable {
  public readonly string SessionId;
  public readonly DateTime StartedUtc;
  public readonly Process Child;
  public DateTime FinishedUtc = DateTime.MinValue;
  readonly object Sync = new object();
  readonly List<string> Buffer = new List<string>();
  bool StdoutFinished = false;
  bool StderrFinished = false;
  bool Truncated = false;
  int FirstLine = 0;
  int BufferChars = 0;
  bool Killed = false;
  const int MaxLines = 5000;
  const int MaxChars = 2 * 1024 * 1024;

  public HaraWindowsProcessSession(string id, string cwd, string command) {
    SessionId = id;
    StartedUtc = DateTime.UtcNow;
    Child = new Process();
    Child.StartInfo.FileName = "powershell.exe";
    Child.StartInfo.Arguments = "-NoLogo -NoProfile -NonInteractive -Command -";
    Child.StartInfo.UseShellExecute = false;
    Child.StartInfo.CreateNoWindow = true;
    Child.StartInfo.RedirectStandardInput = true;
    Child.StartInfo.RedirectStandardOutput = true;
    Child.StartInfo.RedirectStandardError = true;
    Child.StartInfo.StandardOutputEncoding = new UTF8Encoding(false);
    Child.StartInfo.StandardErrorEncoding = new UTF8Encoding(false);
    if (!string.IsNullOrEmpty(cwd)) Child.StartInfo.WorkingDirectory = cwd;
    Child.OutputDataReceived += new DataReceivedEventHandler(OnStdout);
    Child.ErrorDataReceived += new DataReceivedEventHandler(OnStderr);
    if (!Child.Start()) throw new InvalidOperationException("PROCESS_START_FAILED");
    Child.BeginOutputReadLine();
    Child.BeginErrorReadLine();
    Child.StandardInput.AutoFlush = true;
    Child.StandardInput.WriteLine("Invoke-Expression ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('JFByb2dyZXNzUHJlZmVyZW5jZT0nU2lsZW50bHlDb250aW51ZSc7W0NvbnNvbGVdOjpJbnB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpO1tDb25zb2xlXTo6T3V0cHV0RW5jb2Rpbmc9W1RleHQuVVRGOEVuY29kaW5nXTo6bmV3KCRmYWxzZSk7JE91dHB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpOw==')))" );
    Child.StandardInput.WriteLine(EncodeConsoleInput(command));
  }

  void OnStdout(object sender, DataReceivedEventArgs e) {
    if (e.Data == null) {lock(Sync) StdoutFinished=true; return;}
    AddLine(e.Data);
  }
  void OnStderr(object sender, DataReceivedEventArgs e) {
    if (e.Data == null) {lock(Sync) StderrFinished=true; return;}
    AddLine("STDERR: " + e.Data);
  }

  void AddLine(string value) {
    if (value == null) return;
    lock(Sync) {
      if(value.Length > 65536) { value=value.Substring(0,65536); Truncated=true; }
      Buffer.Add(value); BufferChars += value.Length+1;
      while (Buffer.Count > MaxLines || BufferChars > MaxChars) {
        if (Buffer.Count == 0) break;
        BufferChars -= Buffer[0].Length+1;
        Buffer.RemoveAt(0);
        FirstLine++;
        Truncated=true;
      }
    }
  }

  // ConsoleHost caches its OEM stdin reader before the UTF-8 bootstrap.
  // An ASCII envelope carries complete Unicode commands without OEM loss.
  private static string EncodeConsoleInput(string input) {
    foreach (char value in input) {
      if (value > 127) {
        string payload = Convert.ToBase64String(Encoding.UTF8.GetBytes(input));
        return ". ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "'))))";
      }
    }
    return input;
  }

  public void Input(string input) {
    if (input == null || input.Length > 4096 || input.IndexOf('\0') >= 0)
      throw new InvalidOperationException("PROCESS_INPUT_INVALID");
    if (Child.HasExited) throw new InvalidOperationException("PROCESS_SESSION_EXITED");
    Child.StandardInput.WriteLine(EncodeConsoleInput(input.TrimEnd('\r','\n')));
    Child.StandardInput.Flush();
  }

  public bool Stop(bool force) {
    if (Child.HasExited) return false;
    if (force) {
      Killed = true;
      Child.Kill();
    } else {
      Child.StandardInput.WriteLine("exit");
      Child.StandardInput.Flush();
    }
    return true;
  }

  public Dictionary<string,object> Snapshot(int offset,int length,int waitMs) {
    if (offset < 0 || length < 1 || length > 500 || waitMs < 0 || waitMs > 3000)
      throw new InvalidOperationException("PROCESS_OUTPUT_BOUNDS_INVALID");
    DateTime deadline = DateTime.UtcNow.AddMilliseconds(waitMs);
    while (DateTime.UtcNow < deadline) {
      bool available;
      lock (Sync) { available=(FirstLine+Buffer.Count) > offset; }
      if (available || Child.HasExited) break;
      Thread.Sleep(20);
    }
    bool exited = Child.HasExited;
    if (exited) {
      if (FinishedUtc == DateTime.MinValue) FinishedUtc = DateTime.UtcNow;
      DateTime finalDeadline = DateTime.UtcNow.AddMilliseconds(200);
      while (DateTime.UtcNow < finalDeadline) {
        bool drained;
        lock(Sync) { drained=StdoutFinished && StderrFinished; }
        if (drained) break;
        Thread.Sleep(5);
      }
    }
    lock (Sync) {
      int total=FirstLine+Buffer.Count;
      int start=Math.Max(offset,FirstLine);
      int count=Math.Min(length,Math.Max(0,total-start));
      List<string> lines=new List<string>();
      for(int i=0;i<count;i++) lines.Add(Buffer[start-FirstLine+i]);
      bool drained=StdoutFinished && StderrFinished;
      return new Dictionary<string,object>{
        {"session_id",SessionId},
        {"pid",Child.Id},
        {"state", exited ? (Killed ? "KILLED" : "EXITED") : "RUNNING"},
        {"exit_code",exited ? (object)Child.ExitCode : null},
        {"started_at_utc",StartedUtc.ToString("o")},
        {"finished_at_utc",exited ? (object)FinishedUtc.ToString("o") : null},
        {"base_line",FirstLine},
        {"total_lines",total},
        {"next_offset",start+count},
        {"text",string.Join("\n",lines.ToArray())},
        {"buffer_truncated",Truncated || (exited && !drained)},
        {"output_pending",!exited || !drained},
        {"command_content_persisted",false}
      };
    }
  }

  public void Dispose() {
    try { if(!Child.HasExited) Child.Kill(); }catch{}
    try { Child.Dispose(); }catch{}
  }
}
"@
  Add-Type -TypeDefinition $source -ErrorAction Stop
}

function Cleanup-WindowsManagedSessions {
  $ids=@($script:ManagedWindowsSessions.Keys)
  foreach($id in $ids){
    $session=$script:ManagedWindowsSessions[$id]
    $state=$session.Snapshot(0,1,0)
    if([string]$state.state -ne "RUNNING" -and $session.FinishedUtc -ne [DateTime]::MinValue -and
       ([DateTime]::UtcNow-$session.FinishedUtc).TotalSeconds -gt $script:WindowsSessionFinishedRetentionSeconds){
      $session.Dispose()
      $script:ManagedWindowsSessions.Remove($id)
    }
  }
}

function Get-WindowsManagedSession([string]$Id) {
  if ($Id -notmatch "^HARA-PROC-[0-9a-f]{32}$") { throw "PROCESS_SESSION_ID_INVALID" }
  Cleanup-WindowsManagedSessions
  if (-not $script:ManagedWindowsSessions.ContainsKey($Id)) { throw "PROCESS_SESSION_NOT_FOUND" }
  return $script:ManagedWindowsSessions[$Id]
}

function Start-WindowsManagedSession($Cfg,$Call,[string]$Command,[string]$Cwd=$null,[int]$TimeoutMs=1000) {
  if ([string]::IsNullOrWhiteSpace($Command) -or $Command.Length -gt 4096){throw "PROCESS_COMMAND_INVALID"}
  if ($TimeoutMs -lt 0 -or $TimeoutMs -gt 3000){throw "PROCESS_TIMEOUT_INVALID"}
  $where=$null
  if ($Cwd) {
    $where=(Resolve-Path -LiteralPath $Cwd -ErrorAction Stop).Path
    if(-not (Test-Path -LiteralPath $where -PathType Container)){throw "PROCESS_CWD_INVALID"}
  }
  Cleanup-WindowsManagedSessions
  if (@($script:ManagedWindowsSessions.Values | Where-Object {$_.Snapshot(0,1,0).state -eq "RUNNING"}).Count -ge $script:WindowsSessionMaxActive) {
    throw "PROCESS_SESSION_CAPACITY"
  }
  # Compile the local wrapper before consent, so accepted actions can start promptly.
  Initialize-WindowsManagedProcessType
  # Every new process, including a session, requires on-device approval.
  Assert-StarterMutationAuthorized $Cfg $Call
  $id="HARA-PROC-"+[guid]::NewGuid().ToString("N")
  $session=New-Object HaraWindowsProcessSession -ArgumentList $id,$where,$Command
  $script:ManagedWindowsSessions[$id]=$session
  $snapshot=$session.Snapshot(0,200,$TimeoutMs)
  return $snapshot
}

function Read-WindowsManagedSession([string]$Id,[int]$Offset=0,[int]$Length=200,[int]$WaitMs=500) {
  $session=Get-WindowsManagedSession $Id
  return $session.Snapshot($Offset,$Length,$WaitMs)
}

function Send-WindowsManagedSessionInput($Cfg,$Call,[string]$Id,[string]$InputText,[int]$WaitMs=1000) {
  if ($WaitMs -lt 0 -or $WaitMs -gt 3000){throw "PROCESS_TIMEOUT_INVALID"}
  if ($InputText.Length -gt 4096 -or $InputText.Contains([char]0)){throw "PROCESS_INPUT_INVALID"}
  $session=Get-WindowsManagedSession $Id
  Assert-StarterMutationAuthorized $Cfg $Call
  $session.Input($InputText)
  return $session.Snapshot(0,100,$WaitMs)
}

function Stop-WindowsManagedSession($Cfg,$Call,[string]$Id,[bool]$Force=$false) {
  $session=Get-WindowsManagedSession $Id
  Assert-StarterMutationAuthorized $Cfg $Call
  $mutationPerformed=$session.Stop($Force)
  $snapshot=$session.Snapshot(0,200,200)
  $snapshot["mutation_performed"]=$mutationPerformed
  return $snapshot
}

function List-WindowsManagedSessions {
  Cleanup-WindowsManagedSessions
  $entries=@()
  foreach($id in @($script:ManagedWindowsSessions.Keys | Sort-Object)) {
    $x=$script:ManagedWindowsSessions[$id].Snapshot(0,1,0)
    $entries+=@{session_id=$id;pid=$x.pid;state=$x.state;started_at_utc=$x.started_at_utc;finished_at_utc=$x.finished_at_utc;buffer_truncated=$x.buffer_truncated}
  }
  return @{count=$entries.Count;sessions=$entries}
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

function Write-WindowsTextFile($Cfg,$Call,[string]$PathValue,[string]$Content,[string]$Mode="rewrite",[string]$ExpectedSha256=$null) {
  if ($Content.Length -gt 1048576 -or @("rewrite","append") -notcontains $Mode) { throw "FUNCTION_ARGUMENTS_DENIED" }
  $full=[IO.Path]::GetFullPath($PathValue)
  $parent=[IO.Path]::GetDirectoryName($full)
  if (-not $parent -or -not (Test-Path -LiteralPath $parent -PathType Container)) { throw "FILESYSTEM_PARENT_NOT_FOUND" }
  # Never follow a leaf reparse point. Compare the hash after local approval,
  # immediately before mutation, to reject stale ChatGPT edits.
  Assert-StarterMutationAuthorized $Cfg $Call
  $exists=Test-Path -LiteralPath $full
  if ($exists) {
    $leaf=Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (($leaf.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "FILESYSTEM_SYMLINK_DENIED" }
    if ($leaf.PSIsContainer) { throw "PATH_NOT_FILE" }
  }
  if (-not [string]::IsNullOrWhiteSpace($ExpectedSha256)) {
    if ($ExpectedSha256 -notmatch "^[0-9a-fA-F]{64}$") { throw "FILE_PRECONDITION_INVALID" }
    if (-not $exists) { throw "FILE_PRECONDITION_FAILED" }
    $actual=(Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) { throw "FILE_PRECONDITION_FAILED" }
  }
  if ($Mode -eq "append") {
    Add-Content -LiteralPath $full -Value $Content -Encoding UTF8
  } else {
    $temporary=$full+"."+[guid]::NewGuid().ToString("N")+".tmp"
    $backup=$temporary+".backup"
    try {
      [IO.File]::WriteAllText($temporary,$Content,(New-Object Text.UTF8Encoding($false)))
      if ($exists) { [IO.File]::Replace($temporary,$full,$backup,$true) }
      else { [IO.File]::Move($temporary,$full) }
    } finally {
      if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    }
  }
  return @{path=$full;mode=$Mode;bytes_written=[Text.Encoding]::UTF8.GetByteCount($Content)}
}

function New-WindowsDirectory($Cfg,$Call,[string]$PathValue,[bool]$Parents=$true) {
  Assert-StarterMutationAuthorized $Cfg $Call
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

function Invoke-WindowsOneShotProcess($Cfg,$Call,[string]$Command,[string]$Cwd=$null,[int]$TimeoutMs=3000,[int]$MaxLines=200) {
  Assert-StarterMutationAuthorized $Cfg $Call
  if ([string]::IsNullOrWhiteSpace($Command) -or $Command.Length -gt 4096) { throw "FUNCTION_ARGUMENTS_DENIED" }
  $TimeoutMs=[Math]::Max(100,[Math]::Min(10000,$TimeoutMs))
  $MaxLines=[Math]::Max(1,[Math]::Min(500,$MaxLines))
  $utf8Bootstrap="`$ProgressPreference='SilentlyContinue';[Console]::InputEncoding=[Text.UTF8Encoding]::new(`$false);[Console]::OutputEncoding=[Text.UTF8Encoding]::new(`$false);`$OutputEncoding=[Text.UTF8Encoding]::new(`$false);"
  $bytes=[Text.Encoding]::Unicode.GetBytes($utf8Bootstrap+$Command)
  $encoded=[Convert]::ToBase64String($bytes)
  $psi=New-Object Diagnostics.ProcessStartInfo
  $psi.FileName="powershell.exe"
  $psi.Arguments="-NoLogo -NoProfile -NonInteractive -EncodedCommand $encoded"
  $psi.UseShellExecute=$false
  $psi.RedirectStandardOutput=$true
  $psi.RedirectStandardError=$true
  $psi.StandardOutputEncoding=New-Object Text.UTF8Encoding($false)
  $psi.StandardErrorEncoding=New-Object Text.UTF8Encoding($false)
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
  $mutationClass=if (@("hara.process.run","hara.process.start","hara.process.interact","hara.process.kill") -contains $tool) {"PROCESS_EXECUTION_V1"} elseif (@("hara.files.create_directory","hara.files.write") -contains $tool) {"FILESYSTEM_MUTATION_V1"} else {"READ_ONLY_OR_NONE_V1"}
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
    authorization_source=if ($mutationClass -ne "READ_ONLY_OR_NONE_V1") {$(if ($approvalMode -eq "PERSISTENT_TRUSTED") {"DEVICE_ENROLLMENT_POLICY"} elseif ($approvalMode -eq "ASK_EVERY_ACTION") {"LOCAL_INDIVIDUAL_APPROVAL"} else {"LOCAL_OPERATOR_SESSION"})} else {$null}
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
  # Report completed effects, including explicit no-op outcomes, independently of risk.
  $mutationPerformed=$false
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
    $directory=New-WindowsDirectory $Cfg $Call ([string]$payload.path) $parents
    $mutationPerformed=$directory.created -eq $true
    $result=New-DirectResult "filesystem.create_directory" "MUTATING" $directory
  } elseif ($tool -eq "hara.files.write") {
    $mode=if ($payload.mode) {[string]$payload.mode} else {"rewrite"}
    $expected=if ($payload.expected_sha256) {[string]$payload.expected_sha256} else {$null}
    $written=Write-WindowsTextFile $Cfg $Call ([string]$payload.path) ([string]$payload.content) $mode $expected
    $mutationPerformed=$true
    $result=New-DirectResult "filesystem.write" "MUTATING" $written
  } elseif ($tool -eq "hara.process.sessions") {
    $result=New-DirectResult "process.sessions" "READ_ONLY" (List-WindowsManagedSessions)
  } elseif ($tool -eq "hara.process.start") {
    $cwd=if ($payload.cwd) {[string]$payload.cwd} else {$null}
    $timeout=if ($null -ne $payload.timeout_ms) {[int]$payload.timeout_ms} else {1000}
    $started=Start-WindowsManagedSession $Cfg $Call ([string]$payload.command) $cwd $timeout
    $mutationPerformed=$true
    $result=New-DirectResult "process.start" "PROCESS_EXECUTION" $started
  } elseif ($tool -eq "hara.process.output") {
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $length=if ($null -ne $payload.length) {[int]$payload.length} else {200}
    $wait=if ($null -ne $payload.timeout_ms) {[int]$payload.timeout_ms} else {500}
    $result=New-DirectResult "process.output" "READ_ONLY" (Read-WindowsManagedSession ([string]$payload.session_id) $offset $length $wait)
  } elseif ($tool -eq "hara.process.interact") {
    $wait=if ($null -ne $payload.timeout_ms) {[int]$payload.timeout_ms} else {1000}
    $interaction=Send-WindowsManagedSessionInput $Cfg $Call ([string]$payload.session_id) ([string]$payload.input) $wait
    $mutationPerformed=$true
    $result=New-DirectResult "process.interact" "PROCESS_EXECUTION" $interaction
  } elseif ($tool -eq "hara.process.kill") {
    $force=$payload.force -eq $true
    $stopped=Stop-WindowsManagedSession $Cfg $Call ([string]$payload.session_id) $force
    $mutationPerformed=$stopped.mutation_performed -eq $true
    $result=New-DirectResult "process.kill" "PROCESS_EXECUTION" $stopped
  } elseif ($tool -eq "hara.process.run") {
    $cwd=if ($payload.cwd) {[string]$payload.cwd} else {$null}
    $timeout=if ($null -ne $payload.timeout_ms) {[int]$payload.timeout_ms} else {3000}
    $maxLines=if ($null -ne $payload.max_lines) {[int]$payload.max_lines} else {200}
    $run=Invoke-WindowsOneShotProcess $Cfg $Call ([string]$payload.command) $cwd $timeout $maxLines
    $mutationPerformed=$true
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
    runtime_authority_from_chatgpt=$false;mutation_performed=$mutationPerformed
    result=$result;blocker=$null;bridge_receipt_sha256=$receipt
  }
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $headers=@{Accept="application/json";Authorization="Bearer $Token"}
  $json=$Body | ConvertTo-Json -Depth 10 -Compress
  # Windows PowerShell 5.1 otherwise falls back to its legacy body encoding.
  $bytes=[Text.Encoding]::UTF8.GetBytes($json)
  return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json; charset=utf-8" -Headers $headers -Body $bytes -TimeoutSec $Timeout -MaximumRedirection 0
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
    # ASK_EVERY_ACTION must deny writes and execution without a local session.
    $savedSelfTestSessionPath=$script:SessionPath
    try {
      $script:SessionPath=Join-Path $testRoot "no-session-selftest.json"
      foreach($unsafe in @(
        @{tool="hara.files.create_directory";payload=[pscustomobject]@{path=(Join-Path $testRoot "must-not-create");parents=$true}},
        @{tool="hara.files.write";payload=[pscustomobject]@{path=(Join-Path $testRoot "must-not-write.txt");content="blocked";mode="rewrite"}},
        @{tool="hara.process.run";payload=[pscustomobject]@{command="Write-Output should_not_run";timeout_ms=1000}}
      )) {
        $attempt=[pscustomobject]@{request_id="selftest-unapproved";tool_id=$unsafe.tool;payload=$unsafe.payload}
        $denied=$false
        try { Invoke-Tool $cfg $attempt | Out-Null }
        catch { $denied=([string]$_.Exception.Message -eq "LOCAL_OPERATOR_SESSION_REQUIRED") }
        if (-not $denied) { throw "SELF_TEST_PER_ACTION_FAIL_CLOSED" }
      }
      if (Test-Path -LiteralPath (Join-Path $testRoot "must-not-create")) { throw "SELF_TEST_UNAPPROVED_DIRECTORY_CREATED" }
      if (Test-Path -LiteralPath (Join-Path $testRoot "must-not-write.txt")) { throw "SELF_TEST_UNAPPROVED_FILE_CREATED" }
    } finally {
      $script:SessionPath=$savedSelfTestSessionPath
    }
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
      $privateMarker="HARA_PRIVATE_SYNTHETIC_STRING_" + [guid]::NewGuid().ToString("N")
      $privateCall=[pscustomobject]@{
        request_id="selftest-private-event"
        tool_id="hara.process.run"
        payload=[pscustomobject]@{command=("Write-Output "+$privateMarker);cwd=("C:\LAB-PRIVATE-"+$privateMarker)}
      }
      Write-ConsoleEvent "SELFTEST_PRIVACY" $privateCall "COMPLETED"
      $lastEvent=Get-Content -LiteralPath $script:ConsoleEvents | Select-Object -Last 1
      $lastJson=$lastEvent | ConvertFrom-Json
      if ($lastEvent.Contains($privateMarker) -or $null -ne $lastJson.action_summary) {
        throw "SELF_TEST_LOCAL_CONSOLE_PRIVATE_COMMAND_PERSISTED"
      }
      if ([string]$lastJson.tool_id -ne "hara.process.run" -or
          [string]$lastJson.request_id -ne "selftest-private-event") {
        throw "SELF_TEST_LOCAL_CONSOLE_EVENT_METADATA_LOST"
      }
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
if ($args -contains "--session-start" -or ($args.Count -gt 0 -and [string]$args[0] -eq "start")) { Start-ManualOperatorConsole; exit 0 }
if ($args -contains "--session-status" -or ($args.Count -gt 0 -and [string]$args[0] -eq "status")) { Show-OperatorSession; exit 0 }
if ($args -contains "--session-stop" -or ($args.Count -gt 0 -and [string]$args[0] -eq "stop")) {
  Stop-OperatorSession
  Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
  exit 0
}
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
      Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o")) -ErrorCode "" -ErrorAt "" | Out-Null
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
