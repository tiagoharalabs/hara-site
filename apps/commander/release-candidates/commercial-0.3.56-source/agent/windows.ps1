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
$AgentVersion = "0.3.56"
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
    "PREIMAGE_NOT_FOUND","RECEIPT_NOT_FOUND","EDIT_MATCH_NOT_FOUND","EDIT_MATCH_AMBIGUOUS","FILE_PRECONDITION_FAILED",
    "FILE_EDIT_BUSY","PROCESS_SESSION_NOT_FOUND","PROCESS_SESSION_EXITED",
    "DESTINATION_EXISTS","PATH_EXISTS_NOT_DIRECTORY","FILESYSTEM_PATH_EXISTS","FILEEXISTSERROR",
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

function Get-EnrollmentContext($Cfg) {
  $uri=$null
  if (-not [Uri]::TryCreate([string]$Cfg.base_url,[UriKind]::Absolute,[ref]$uri) -or
      $uri.Scheme -cne "https" -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne "/") {
    throw "COMMANDER_ORIGIN_INVALID"
  }
  if (-not $Cfg.device_id -or -not $Cfg.encrypted_device_token) { throw "DEVICE_CONFIG_INVALID" }
  # Hash only the protected local credential representation; never decrypt/log it here.
  $credential=Get-Utf8Sha256 ([string]$Cfg.encrypted_device_token)
  $material=@($uri.GetLeftPart([UriPartial]::Authority).ToLowerInvariant(),[string]$Cfg.device_id,[string]$Cfg.tenant_id,$credential) | ConvertTo-Json -Compress
  return Get-Utf8Sha256 $material
}

function Initialize-EnrollmentState($Cfg) {
  $context=Get-EnrollmentContext $Cfg
  $folder=Join-Path (Join-Path $Root "enrollments") $context
  foreach($path in @($Root,(Join-Path $Root "enrollments"),$folder)) {
    if (Test-Path -LiteralPath $path) {
      $item=Get-Item -LiteralPath $path -Force
      if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "ENROLLMENT_STATE_PATH_INVALID" }
    }
    New-Item -ItemType Directory -Path $path -Force | Out-Null
  }
  $script:ReceiptDir=Join-Path $folder "receipts"
  $script:OperationsDb=Join-Path $folder "operations.sqlite3"
  $script:ConsoleEvents=Join-Path $folder "console-events.jsonl"
  $script:PendingApprovalPath=Join-Path $folder "pending-action-approval.json"
  $script:ApprovalResponsePath=Join-Path $folder "action-approval-response.json"
  $acl=Get-Acl -LiteralPath $folder
  $acl.SetAccessRuleProtection($true,$false)
  $inherit=[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  foreach($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User,[Security.Principal.SecurityIdentifier]'S-1-5-18')) {
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl',$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
    $acl.SetAccessRule($rule)
  }
  Set-Acl -LiteralPath $folder -AclObject $acl
  return $context
}

function Assert-CallEnrollment($Cfg,$Call) {
  if ($Cfg.base_url -and (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    $current=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if ((Get-EnrollmentContext $Cfg) -cne (Get-EnrollmentContext $current)) { throw "ENROLLMENT_CHANGED_RESTART_REQUIRED" }
  }
  foreach($field in @("device_id","tenant_id")) {
    if ($Call.PSObject.Properties.Name -contains $field) {
      if (-not $Cfg.$field -or [string]$Call.$field -cne [string]$Cfg.$field) { throw "CALL_ENROLLMENT_MISMATCH" }
    }
  }
}

function Show-LegacyOperatorHistory([int]$Limit=50,[long]$BeforeId=0) {
  if($Limit -lt 1 -or $Limit -gt 200 -or $BeforeId -lt 0){throw "HISTORY_ARGUMENT_INVALID"}
  $database=Join-Path $Root "operations.sqlite3"
  if(Test-Path -LiteralPath $database -PathType Leaf) {
    if((Get-Item -LiteralPath $database -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw "ENROLLMENT_STATE_PATH_INVALID"}
    Initialize-WinSqlite
    $columns="event_id,at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256"
    if($BeforeId -gt 0){$sql="SELECT $columns FROM activity_events WHERE event_id < ? ORDER BY event_id DESC LIMIT ?";$values=@($BeforeId,[long]($Limit+1))}
    else{$sql="SELECT $columns FROM activity_events ORDER BY event_id DESC LIMIT ?";$values=@([long]($Limit+1))}
    $rows=@([HaraWinSqlite]::QueryReadOnly($database,$sql,$values))
    $page=@($rows | Select-Object -First $Limit);[array]::Reverse($page)
    Write-Host "HARA_COMMANDER_HISTORY=LEGACY_LOCAL_READ_ONLY"
    foreach($row in $page){Write-Host ("#"+$row.event_id+" "+(Format-ConsoleEvent $row))}
    if($rows.Count -gt $Limit -and $page.Count -gt 0){Write-Host ("HARA_COMMANDER_HISTORY_MORE=hara-commander history legacy "+$Limit+" "+$page[0].event_id)}
    return
  }
  $path=Join-Path $Root "console-events.jsonl"
  Write-Host "HARA_COMMANDER_HISTORY=LEGACY_LOCAL_READ_ONLY"
  if(Test-Path -LiteralPath $path -PathType Leaf) {
    $item=Get-Item -LiteralPath $path -Force
    if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw "ENROLLMENT_STATE_PATH_INVALID"}
    foreach($line in @(Get-Content -LiteralPath $path -Tail $Limit)) {
      try{$row=$line | ConvertFrom-Json}catch{continue}
      $stamp=[DateTime]::MinValue
      if(-not [DateTime]::TryParse([string]$row.at_utc,[ref]$stamp)){continue}
      $safe=$row | Select-Object at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256
      Write-Host (Format-ConsoleEvent $safe)
    }
  }
}

function Get-OperatorSession {
  if (-not (Test-Path -LiteralPath $SessionPath -PathType Leaf)) { return $null }
  try { $session=Get-Content -Raw -LiteralPath $SessionPath | ConvertFrom-Json } catch { return $null }
  if ([string]$session.schema -ne "hara.commander-operator-session.v1") { return $null }
  try {
    $cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if ([string]$session.enrollment_context -cne (Get-EnrollmentContext $cfg)) { return $null }
  } catch { return $null }
  try { $started=[DateTime]::Parse([string]$session.started_at_utc).ToUniversalTime() } catch { return $null }
  if ($started -gt [DateTime]::UtcNow.AddSeconds(60) -or ([DateTime]::UtcNow-$started).TotalHours -gt $SessionMaxHours) { return $null }
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
  static extern int sqlite3_open_v2(byte[] filename,out IntPtr db,int flags,IntPtr vfs);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_close(IntPtr db);
  [DllImport("winsqlite3.dll",CallingConvention=CallingConvention.Cdecl)]
  static extern int sqlite3_busy_timeout(IntPtr db,int milliseconds);
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

  static void Configure(IntPtr db,bool readOnly) {
    Check(db,sqlite3_busy_timeout(db,2000),"busy_timeout");
    if(readOnly) return;
    IntPtr stmt=IntPtr.Zero;
    try {
      Check(db,sqlite3_prepare16_v2(db,"PRAGMA synchronous=FULL",-1,out stmt,IntPtr.Zero),"durability");
      int rc=sqlite3_step(stmt);
      if(rc!=DONE && rc!=ROW) throw Failure(db,"durability",rc);
    } finally {if(stmt!=IntPtr.Zero) sqlite3_finalize(stmt);}
  }

  public static void Execute(string path,string sql,object[] values) {
    IntPtr db=IntPtr.Zero,stmt=IntPtr.Zero;
    int open=sqlite3_open16(path,out db);
    if (open!=OK) throw Failure(db,"open",open);
    try {
      Configure(db,false);
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
    return QueryCore(path,sql,values,false);
  }
  public static List<Dictionary<string,object>> QueryReadOnly(string path,string sql,object[] values) {
    return QueryCore(path,sql,values,true);
  }
  static List<Dictionary<string,object>> QueryCore(string path,string sql,object[] values,bool readOnly) {
    var rows=new List<Dictionary<string,object>>();
    IntPtr db=IntPtr.Zero,stmt=IntPtr.Zero;
    int open=readOnly ? sqlite3_open_v2(System.Text.Encoding.UTF8.GetBytes(path+"\0"),out db,1,IntPtr.Zero) : sqlite3_open16(path,out db);
    if (open!=OK) throw Failure(db,"open",open);
    try {
      Configure(db,readOnly);
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

function Get-ConsoleStreamCursor {
  # A new operator window starts at EOF. The JSONL/SQLite history is never
  # truncated or copied into the live console on startup.
  if (-not (Test-Path -LiteralPath $ConsoleEvents -PathType Leaf)) { return [long]0 }
  $stream=[System.IO.File]::Open(
    $ConsoleEvents,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,
    ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
  try { return [long]$stream.Length }
  finally { $stream.Dispose() }
}

function Read-NewConsoleEvents([ref]$Cursor) {
  if (-not (Test-Path -LiteralPath $ConsoleEvents -PathType Leaf)) { return @() }
  $stream=[System.IO.File]::Open(
    $ConsoleEvents,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,
    ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
  try {
    $from=[long]$Cursor.Value
    if ($from -lt 0 -or $from -gt $stream.Length) { $from=[long]0 }
    $length=[int][Math]::Min(131072,[Math]::Max(0,$stream.Length-$from))
    if ($length -eq 0) { return @() }
    $buffer=New-Object byte[] $length
    [void]$stream.Seek($from,[System.IO.SeekOrigin]::Begin)
    $count=$stream.Read($buffer,0,$length)
    $lastNewline=-1
    for ($i=0; $i -lt $count; $i++) {
      if ($buffer[$i] -eq 10) { $lastNewline=$i }
    }
    if ($lastNewline -lt 0) { return @() }
    $text=[System.Text.Encoding]::UTF8.GetString($buffer,0,$lastNewline+1)
    $Cursor.Value=$from+$lastNewline+1
    $newEvents=New-Object 'System.Collections.Generic.List[object]'
    foreach ($line in $text.Split([char]10)) {
      $clean=$line.TrimEnd([char]13).TrimStart([char]0xFEFF)
      if ([string]::IsNullOrWhiteSpace($clean)) { continue }
      try {
        $event=$clean | ConvertFrom-Json -ErrorAction Stop
        if ([string]$event.schema -eq "hara.commander-console-event.v1") {
          $newEvents.Add($event)
        }
      } catch {}
    }
    return $newEvents.ToArray()
  } finally {
    $stream.Dispose()
  }
}

function Show-OperatorHistory([int]$Limit=50,[long]$BeforeId=0) {
  if ($Limit -lt 1 -or $Limit -gt 200 -or $BeforeId -lt 0) {
    throw "HISTORY_ARGUMENT_INVALID"
  }
  # Explicit local SQLite history; never echo raw arguments or action_summary.
  Initialize-LocalActivityStore
  $columns="event_id,at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256"
  if ($BeforeId -gt 0) {
    $rows=@(Invoke-LocalDbQuery "SELECT $columns FROM activity_events WHERE event_id < ? ORDER BY event_id DESC LIMIT ?" @([long]$BeforeId,[long]($Limit+1)))
  } else {
    $rows=@(Invoke-LocalDbQuery "SELECT $columns FROM activity_events ORDER BY event_id DESC LIMIT ?" @([long]($Limit+1)))
  }
  $page=@($rows | Select-Object -First $Limit)
  [array]::Reverse($page)
  Write-Host "HARA_COMMANDER_HISTORY=LOCAL_READ_ONLY"
  Write-Host ("HARA_COMMANDER_HISTORY_EVENTS="+$page.Count)
  foreach ($item in $page) {
    Write-Host ("#"+[long]$item.event_id+" "+(Format-ConsoleEvent $item))
  }
  if ($rows.Count -gt $Limit -and $page.Count -gt 0) {
    $oldest=[long]$page[0].event_id
    Write-Host ("HARA_COMMANDER_HISTORY_MORE=hara-commander history "+$Limit+" "+$oldest)
  }
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
    enrollment_context=(Get-EnrollmentContext $cfg)
    authorization="LOCAL_OPERATOR_TERMINAL"
  }
  Invoke-WithLocalApprovalLock {
    $existing=Get-OperatorSession
    if ($existing -and [int]$existing.owner_pid -ne $PID) { throw "OPERATOR_SESSION_ALREADY_ACTIVE" }
    $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
    if ($null -ne $SessionOpened) { $SessionOpened.Value=$true }
  } | Out-Null
  # Retain previous JSONL/SQLite history, but show only new live events.
  $eventCursor=Get-ConsoleStreamCursor
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
    while ($true) {
      $current=Get-OperatorSession
      if (-not $current -or [int]$current.owner_pid -ne $PID) { break }
      foreach ($entry in @(Read-NewConsoleEvents ([ref]$eventCursor))) {
        Write-Host (Format-ConsoleEvent $entry)
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
    Assert-WindowsRelayDeadline
    return
  }
  if ($mode -eq "SESSION_TRUSTED" -and -not (Test-OperatorSessionActive)) {
    throw "LOCAL_OPERATOR_SESSION_REQUIRED"
  }
  Assert-WindowsRelayDeadline
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
  Write-Host ("Solicitacao valida ate "+([DateTime]::Parse([string]$pending.expires_at_utc)).ToLocalTime().ToString("dd/MM/yyyy HH:mm:ss")+"; depois, descarte esta solicitacao.")
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
$script:CompletedWindowsRuns=@{}
$script:WindowsSessionMaxActive=8
$script:WindowsSessionFinishedRetentionSeconds=900
$script:WindowsRunRetentionSeconds=3600
$script:WindowsRunMaxRetained=8

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

  public HaraWindowsProcessSession(string id, string cwd, string command) : this(id,cwd,command,false) {}

  public HaraWindowsProcessSession(string id, string cwd, string command, bool oneShot) {
    SessionId = id;
    StartedUtc = DateTime.UtcNow;
    Child = new Process();
    Child.StartInfo.FileName = "powershell.exe";
    string bootstrap=Encoding.UTF8.GetString(Convert.FromBase64String("JFByb2dyZXNzUHJlZmVyZW5jZT0nU2lsZW50bHlDb250aW51ZSc7W0NvbnNvbGVdOjpJbnB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpO1tDb25zb2xlXTo6T3V0cHV0RW5jb2Rpbmc9W1RleHQuVVRGOEVuY29kaW5nXTo6bmV3KCRmYWxzZSk7JE91dHB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpOw=="));
    // EncodedCommand normally maps a nonzero native exit to 1. Preserve the
    // final native exit code, while a successful final command still exits 0.
    // The newline also prevents a trailing comment swallowing the epilogue.
    string oneShotScript = bootstrap + "\n& {\n" + command + "\n" +
      "if (`$?) { exit 0 }\n" +
      "if (`$LASTEXITCODE -is [int] -and `$LASTEXITCODE -ne 0) { exit `$LASTEXITCODE }\nexit 1\n}\n";
    Child.StartInfo.Arguments = oneShot
      ? "-NoLogo -NoProfile -NonInteractive -EncodedCommand " + Convert.ToBase64String(Encoding.Unicode.GetBytes(oneShotScript))
      : "-NoLogo -NoProfile -NonInteractive -Command -";
    Child.StartInfo.UseShellExecute = false;
    Child.StartInfo.CreateNoWindow = true;
    Child.StartInfo.RedirectStandardInput = !oneShot;
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
    if (!oneShot) {
    Child.StandardInput.AutoFlush = true;
    Child.StandardInput.WriteLine("Invoke-Expression ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('JFByb2dyZXNzUHJlZmVyZW5jZT0nU2lsZW50bHlDb250aW51ZSc7W0NvbnNvbGVdOjpJbnB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpO1tDb25zb2xlXTo6T3V0cHV0RW5jb2Rpbmc9W1RleHQuVVRGOEVuY29kaW5nXTo6bmV3KCRmYWxzZSk7JE91dHB1dEVuY29kaW5nPVtUZXh0LlVURjhFbmNvZGluZ106Om5ldygkZmFsc2UpOw==')))" );
    Child.StandardInput.WriteLine(EncodeConsoleInput(command));
    }
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
  if ($Id -notmatch "^HARA-PROC-[0-9a-f]{32}$") { throw "PROCESS_SESSION_ID_INVALID" }
  Cleanup-WindowsCompletedRuns
  if ($script:CompletedWindowsRuns.ContainsKey($Id)) {
    if ($Offset -lt 0 -or $Length -lt 1 -or $Length -gt 500) { throw "PROCESS_OUTPUT_BOUNDS_INVALID" }
    $run=$script:CompletedWindowsRuns[$Id]
    $first=[int]$run.base_line
    $total=$first+@($run.lines).Count
    $start=[Math]::Min($total,[Math]::Max($Offset,$first))
    $end=[Math]::Min($total,$start+$Length)
    $page=@()
    for($i=$start;$i -lt $end;$i++){ $page+=,[string]$run.lines[$i-$first] }
    return @{
      session_id=$Id;run_id=$Id;state="EXITED";exit_code=$run.exit_code
      base_line=$first;total_lines=$total;next_offset=$end
      text=($page -join [Environment]::NewLine)
      buffer_truncated=$run.buffer_truncated;output_pending=$false
      result_kind="ONE_SHOT_RESULT";command_content_persisted=$false
      expires_at_utc=$run.expires_at_utc
    }
  }
  $session=Get-WindowsManagedSession $Id
  return $session.Snapshot($Offset,$Length,$WaitMs)
}

function Cleanup-WindowsCompletedRuns {
  $now=[DateTime]::UtcNow
  foreach($id in @($script:CompletedWindowsRuns.Keys)) {
    $expires=[DateTimeOffset]::Parse([string]$script:CompletedWindowsRuns[$id].expires_at_utc).UtcDateTime
    if ($now -ge $expires) {
      $script:CompletedWindowsRuns.Remove($id)
    }
  }
  while ($script:CompletedWindowsRuns.Count -gt $script:WindowsRunMaxRetained) {
    $oldest=@($script:CompletedWindowsRuns.Keys | Sort-Object { [DateTimeOffset]::Parse([string]$script:CompletedWindowsRuns[$_].created_at_utc).UtcDateTime.Ticks })[0]
    $script:CompletedWindowsRuns.Remove($oldest)
  }
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
  Cleanup-WindowsCompletedRuns
  $entries=@()
  foreach($id in @($script:ManagedWindowsSessions.Keys | Sort-Object)) {
    $x=$script:ManagedWindowsSessions[$id].Snapshot(0,1,0)
    $entries+=@{session_id=$id;pid=$x.pid;state=$x.state;started_at_utc=$x.started_at_utc;finished_at_utc=$x.finished_at_utc;buffer_truncated=$x.buffer_truncated}
  }
  foreach($id in @($script:CompletedWindowsRuns.Keys | Sort-Object)) {
    $run=$script:CompletedWindowsRuns[$id]
    $entries+=@{session_id=$id;pid=$null;state="EXITED";started_at_utc=$run.created_at_utc;finished_at_utc=$run.created_at_utc;buffer_truncated=$run.buffer_truncated;result_kind="ONE_SHOT_RESULT"}
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

function Get-WindowsDirectory([string]$PathValue,[int]$Depth=1,[int]$Limit=200,[int]$Offset=0) {
  if ($Depth -lt 1 -or $Depth -gt 5 -or $Limit -lt 1 -or $Limit -gt 200 -or $Offset -lt 0 -or $Offset -gt 10000) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  $root=(Get-Item -LiteralPath $PathValue -Force -ErrorAction Stop)
  if (-not $root.PSIsContainer) { throw "FILESYSTEM_NOT_DIRECTORY" }
  $rootModified=$root.LastWriteTimeUtc.Ticks
  $queue=New-Object System.Collections.Queue
  $queue.Enqueue(@($root.FullName,1))
  $all=New-Object 'System.Collections.Generic.List[object]'
  $fingerprintParts=New-Object 'System.Collections.Generic.List[string]'
  $deadline=[DateTime]::UtcNow.AddSeconds(3)
  $incompleteReason=$null
  while ($queue.Count -gt 0) {
    if ([DateTime]::UtcNow -ge $deadline) { $incompleteReason="TIME_LIMIT"; break }
    $entry=$queue.Dequeue(); $current=[string]$entry[0]; $level=[int]$entry[1]
    try { $children=@(Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop | Sort-Object Name) }
    catch {
      $incompleteReason=if ($_.Exception -is [UnauthorizedAccessException]) {"PERMISSION_DENIED"} else {"IO_ERROR"}
      break
    }
    foreach ($item in $children) {
      if ($all.Count -ge 10000) { $incompleteReason="SCAN_LIMIT"; break }
      if ([DateTime]::UtcNow -ge $deadline) { $incompleteReason="TIME_LIMIT"; break }
      $reparse=($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
      $kind=if ($reparse) {"symlink"} elseif ($item.PSIsContainer) {"directory"} else {"file"}
      $size=if ($kind -eq "file") {[int64]$item.Length} else {$null}
      $all.Add(@{path=$item.FullName;name=$item.Name;type=$kind;depth=$level;size_bytes=$size})
      $fingerprintParts.Add($item.FullName+"|"+$kind+"|"+[string]$size+"|"+$item.LastWriteTimeUtc.Ticks)
      if ($kind -eq "directory" -and $level -lt $Depth) { $queue.Enqueue(@($item.FullName,$level+1)) }
    }
    if ($incompleteReason) { break }
  }
  $rootNow=(Get-Item -LiteralPath $root.FullName -Force -ErrorAction Stop)
  if ($rootModified -ne $rootNow.LastWriteTimeUtc.Ticks) { $incompleteReason="DIRECTORY_CHANGED_DURING_SCAN" }
  $rows=@()
  if ($Offset -lt $all.Count) {
    $end=[Math]::Min($all.Count,$Offset+$Limit)
    for($i=$Offset;$i -lt $end;$i++){ $rows+=,$all[$i] }
  }
  $hasMore=($Offset+$rows.Count) -lt $all.Count
  $safe=[string]::IsNullOrEmpty($incompleteReason)
  return @{
    path=$root.FullName;entries=$rows;count=$rows.Count;offset=$Offset;depth=$Depth
    has_more=$hasMore;next_offset=if($hasMore -and $safe){$Offset+$rows.Count}else{$null}
    truncated=($hasMore -or -not $safe);scan_incomplete=(-not $safe);incomplete_reason=$incompleteReason
    continuation_safe=$safe;stable_across_calls=$false
    listing_revision_hint=(Get-Utf8Sha256 ($root.FullName+"|"+($fingerprintParts -join "`n")))
    visited_entries=$all.Count
  }
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

function Read-WindowsManyTextFiles($Paths,[int]$Offset=0,[int]$Length=100) {
  if ($null -eq $Paths -or @($Paths).Count -lt 1 -or @($Paths).Count -gt 10 -or
      $Offset -lt 0 -or $Offset -gt 1000000 -or $Length -lt 1 -or $Length -gt 100) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  $files=@(); $passed=0; $failed=0
  foreach($rawPath in @($Paths)) {
    $path=[string]$rawPath
    try {
      $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
      if ($item.PSIsContainer) { throw "PATH_NOT_FILE" }
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "FILESYSTEM_SYMLINK_DENIED" }
      if ($item.Length -gt 1048576) { throw "FILE_TOO_LARGE" }
      $beforeLength=[int64]$item.Length; $beforeWrite=$item.LastWriteTimeUtc.Ticks
      $bytes=[IO.File]::ReadAllBytes($item.FullName)
      if ([Array]::IndexOf($bytes,[byte]0) -ge 0) { throw "BINARY_FILE_DENIED" }
      $utf8=New-Object Text.UTF8Encoding($false,$true)
      $text=$utf8.GetString($bytes)
      $lines=if ($text.Length -eq 0) {@()} else {@($text -split "`r?`n")}
      $selected=New-Object 'System.Collections.Generic.List[string]'
      $used=0; $oversized=$false
      for($i=$Offset;$i -lt $lines.Count -and $selected.Count -lt $Length;$i++){
        $line=[string]$lines[$i]
        $cost=[Text.Encoding]::UTF8.GetByteCount($line)+1
        if ($used+$cost -gt 4096) { $oversized=($selected.Count -eq 0); break }
        $selected.Add($line); $used+=$cost
      }
      $after=Get-Item -LiteralPath $item.FullName -Force -ErrorAction Stop
      $changed=($beforeLength -ne [int64]$after.Length -or $beforeWrite -ne $after.LastWriteTimeUtc.Ticks)
      $next=$Offset+$selected.Count
      $more=$next -lt $lines.Count
      $safe=(-not $changed -and -not $oversized)
      $entry=@{
        path=$item.FullName;state="PASS";offset=$Offset;line_count=$selected.Count
        text=($selected -join [Environment]::NewLine);has_more=$more;eof=(-not $more)
        next_offset=if($more -and $safe){$next}else{$null}
        content_truncated=$oversized;continuation_safe=$safe
        file_changed_during_read=$changed
        file_revision_hint=(Get-Utf8Sha256 ($item.FullName+"|"+$beforeLength+"|"+$beforeWrite))
      }
      if ($safe -and $Offset -eq 0 -and $bytes.Length -le 131072) {
        $sha=[Security.Cryptography.SHA256]::Create()
        try { $entry.full_file_sha256=($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
        finally { $sha.Dispose() }
      }
      $files+=,$entry; $passed++
    } catch {
      $files+=,@{path=$path;state="FAILED";error_code=(Get-SafeErrorCode $_);offset=$Offset;continuation_safe=$false}
      $failed++
    }
  }
  return @{
    count=$files.Count;successful_count=$passed;failed_count=$failed;deferred_count=0
    overall_status=if($failed -eq 0){"PASS"}elseif($passed -eq 0){"FAILED"}else{"PARTIAL"}
    files=$files;offset=$Offset;length=$Length
  }
}

function Search-WindowsFiles([string]$PathValue,[string]$SearchType,[string]$Pattern,
                            [int]$MaxResults=50,[bool]$IncludeHidden=$false,
                            [bool]$IgnoreCase=$true,[string]$FileGlob="",[int]$Offset=0) {
  if (@("files","content") -notcontains $SearchType -or [string]::IsNullOrEmpty($Pattern) -or
      $Pattern.Length -gt 256 -or $FileGlob.Length -gt 180 -or
      $MaxResults -lt 1 -or $MaxResults -gt 100 -or $Offset -lt 0 -or $Offset -gt 10000) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  $root=Get-Item -LiteralPath $PathValue -Force -ErrorAction Stop
  if (-not $root.PSIsContainer) { throw "FILESYSTEM_NOT_DIRECTORY" }
  $queue=New-Object System.Collections.Queue
  $queue.Enqueue($root.FullName)
  $matches=@(); $matched=0; $scanned=0; $skippedLarge=0; $skippedBinary=0
  $permissionDenied=0; $ioErrors=0; $hasMore=$false; $reason=$null
  $deadline=[DateTime]::UtcNow.AddSeconds(3)
  $comparison=if($IgnoreCase){[StringComparison]::OrdinalIgnoreCase}else{[StringComparison]::Ordinal}
  while($queue.Count -gt 0 -and -not $hasMore){
    if ([DateTime]::UtcNow -ge $deadline) { $reason="TIME_LIMIT"; break }
    $current=[string]$queue.Dequeue()
    try { $children=@(Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop | Sort-Object Name) }
    catch {
      if ($_.Exception -is [UnauthorizedAccessException]) { $permissionDenied++ } else { $ioErrors++ }
      continue
    }
    foreach($item in $children){
      if ($scanned -ge 5000) { $reason="SCAN_LIMIT"; break }
      if ([DateTime]::UtcNow -ge $deadline) { $reason="TIME_LIMIT"; break }
      if (-not $IncludeHidden -and (($item.Attributes -band [IO.FileAttributes]::Hidden) -ne 0)) { continue }
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
      if ($item.PSIsContainer) { $queue.Enqueue($item.FullName); continue }
      $scanned++
      if ($FileGlob -and $item.Name -notlike $FileGlob) { continue }
      $relative=$item.FullName.Substring($root.FullName.Length).TrimStart([char]'\')
      if ($SearchType -eq "files") {
        if ($item.Name.IndexOf($Pattern,$comparison) -lt 0) { continue }
        $match=@{path=$relative;type="file"}
        if ($matched -ge $Offset) {
          if ($matches.Count -ge $MaxResults) { $hasMore=$true; break }
          $matches+=,$match
        }
        $matched++
      } else {
        if ($item.Length -gt 2097152) { $skippedLarge++; continue }
        try {
          $bytes=[IO.File]::ReadAllBytes($item.FullName)
          if ([Array]::IndexOf($bytes,[byte]0) -ge 0) { $skippedBinary++; continue }
          $utf8=New-Object Text.UTF8Encoding($false,$true)
          $lines=@($utf8.GetString($bytes) -split "`r?`n")
          for($lineNumber=0;$lineNumber -lt $lines.Count;$lineNumber++){
            $line=[string]$lines[$lineNumber]
            if ($line.IndexOf($Pattern,$comparison) -lt 0) { continue }
            $match=@{path=$relative;line=$lineNumber+1;text=$line.Substring(0,[Math]::Min(300,$line.Length))}
            if ($matched -ge $Offset) {
              if ($matches.Count -ge $MaxResults) { $hasMore=$true; break }
              $matches+=,$match
            }
            $matched++
          }
        } catch {
          if ($_.Exception -is [UnauthorizedAccessException]) { $permissionDenied++ } else { $ioErrors++ }
        }
        if ($hasMore) { break }
      }
    }
    if ($reason) { break }
  }
  if (-not $reason) {
    if ($permissionDenied) { $reason="PERMISSION_DENIED" }
    elseif ($ioErrors) { $reason="IO_ERROR" }
    elseif ($skippedLarge -or $skippedBinary) { $reason="CONTENT_EXCLUDED" }
  }
  $safe=[string]::IsNullOrEmpty($reason)
  return @{
    path=$root.FullName;search_type=$SearchType;pattern=$Pattern;offset=$Offset
    count=$matches.Count;matches=$matches;matched_seen=$matched;scanned_files=$scanned
    has_more=$hasMore;next_offset=if($hasMore -and $safe){$Offset+$matches.Count}else{$null}
    scan_truncated=($reason -eq "TIME_LIMIT" -or $reason -eq "SCAN_LIMIT")
    scan_incomplete=(-not $safe);incomplete_reason=$reason;continuation_safe=$safe
    truncated=($hasMore -or -not $safe);stable_across_calls=$false
    permission_denied_count=$permissionDenied;io_error_count=$ioErrors
    skipped_large_files_count=$skippedLarge;skipped_binary_files_count=$skippedBinary
  }
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

function Edit-WindowsTextFile($Cfg,$Call,[string]$PathValue,[string]$OldText,[string]$NewText,
                              [bool]$ReplaceAll=$false,[string]$ExpectedSha256=$null) {
  if ([string]::IsNullOrEmpty($OldText) -or $OldText.Length -gt 32768 -or $NewText.Length -gt 32768) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  if ($ExpectedSha256 -and $ExpectedSha256 -notmatch "^[0-9a-fA-F]{64}$") { throw "FILE_PRECONDITION_INVALID" }
  $full=[IO.Path]::GetFullPath($PathValue)
  # Consent occurs before the cross-process critical section. No approval wait
  # can pin a file lock or block another authorized editor.
  Assert-StarterMutationAuthorized $Cfg $Call
  $name="Global\HARACommanderEdit_"+(Get-Utf8Sha256 $full.ToUpperInvariant())
  $mutex=New-Object -TypeName System.Threading.Mutex -ArgumentList @($false,$name)
  $held=$false
  try {
    try { $held=$mutex.WaitOne(2000) }
    catch [Threading.AbandonedMutexException] { $held=$true }
    if (-not $held) { throw "FILE_EDIT_BUSY" }
    $item=Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ($item.PSIsContainer) { throw "PATH_NOT_FILE" }
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "FILESYSTEM_SYMLINK_DENIED" }
    if ($item.Length -gt 1048576) { throw "FILE_TOO_LARGE" }
    $bytes=[IO.File]::ReadAllBytes($full)
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $before=($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
    finally { $sha.Dispose() }
    if ($ExpectedSha256 -and $before -ne $ExpectedSha256.ToLowerInvariant()) { throw "FILE_PRECONDITION_FAILED" }
    $utf8=New-Object Text.UTF8Encoding($false,$true)
    $source=$utf8.GetString($bytes)
    $first=$source.IndexOf($OldText,[StringComparison]::Ordinal)
    if ($first -lt 0) { throw "EDIT_MATCH_NOT_FOUND" }
    $second=$source.IndexOf($OldText,$first+$OldText.Length,[StringComparison]::Ordinal)
    if ($second -ge 0 -and -not $ReplaceAll) { throw "EDIT_MATCH_AMBIGUOUS" }
    $replacements=0
    if ($ReplaceAll) {
      $cursor=$first
      while ($cursor -ge 0) { $replacements++; $cursor=$source.IndexOf($OldText,$cursor+$OldText.Length,[StringComparison]::Ordinal) }
      $changed=$source.Replace($OldText,$NewText)
    } else {
      $replacements=1
      $changed=$source.Substring(0,$first)+$NewText+$source.Substring($first+$OldText.Length)
    }
    if ($changed -ceq $source) {
      return @{path=$full;changed=$false;replacements=$replacements;sha256_before=$before;sha256_after=$before}
    }
    $afterBytes=$utf8.GetBytes($changed)
    if ($afterBytes.Length -gt 1048576) { throw "FILE_TOO_LARGE" }
    $temporary=$full+"."+[guid]::NewGuid().ToString("N")+".tmp"
    $backup=$temporary+".backup"
    try {
      [IO.File]::WriteAllBytes($temporary,$afterBytes)
      # Detect non-cooperating changes between the initial read and replace.
      $latest=(Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($latest -ne $before) { throw "FILE_PRECONDITION_FAILED" }
      [IO.File]::Replace($temporary,$full,$backup,$true)
    } finally {
      if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    }
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $after=($sha.ComputeHash($afterBytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
    finally { $sha.Dispose() }
    return @{path=$full;changed=$true;replacements=$replacements;bytes_written=$afterBytes.Length;sha256_before=$before;sha256_after=$after}
  } finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
  }
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
  if ([string]::IsNullOrWhiteSpace($Command) -or $Command.Length -gt 4096) { throw "FUNCTION_ARGUMENTS_DENIED" }
  $TimeoutMs=[Math]::Max(100,[Math]::Min(10000,$TimeoutMs))
  $MaxLines=[Math]::Max(1,[Math]::Min(500,$MaxLines))
  $where=$null
  if ($Cwd) {
    $where=(Resolve-Path -LiteralPath $Cwd -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $where -PathType Container)) { throw "PROCESS_CWD_INVALID" }
  }
  Initialize-WindowsManagedProcessType
  Assert-StarterMutationAuthorized $Cfg $Call
  $id="HARA-PROC-"+[guid]::NewGuid().ToString("N")
  $session=New-Object HaraWindowsProcessSession -ArgumentList $id,$where,$Command,$true
  $managed=$false
  try {
    $timedOut=-not $session.Child.WaitForExit($TimeoutMs)
    $exited=-not $timedOut
    if ($timedOut) {
      try { $session.Stop($true) | Out-Null } catch {}
      $exited=$session.Child.WaitForExit(1000)
    }
    if (-not $exited) {
      $script:ManagedWindowsSessions[$id]=$session
      $managed=$true
      $pending=$session.Snapshot(0,$MaxLines,0)
      return @{
        state="TERMINATING";exit_code=$null;timed_out=$true;termination_uncertain=$true
        cwd=if($where){$where}else{(Get-Location).Path};command_sha256=(Get-Utf8Sha256 $Command)
        text=$pending.text;output_truncated=$true;buffer_truncated=$pending.buffer_truncated
        session_retained=$true;run_id=$id;session_id=$id;next_offset=$pending.next_offset
        base_line=$pending.base_line;total_lines=$pending.total_lines;expires_at_utc=$null
      }
    }
    $snapshot=$session.Snapshot(0,500,200)
    for($attempt=0;$attempt -lt 10 -and $snapshot.output_pending;$attempt++) {
      Start-Sleep -Milliseconds 50
      $snapshot=$session.Snapshot(0,500,0)
    }
    if ($snapshot.output_pending) {
      $script:ManagedWindowsSessions[$id]=$session
      $managed=$true
      return @{
        state=if($timedOut){"TIMED_OUT"}else{"EXITED"}
        exit_code=if($timedOut){$null}else{$session.Child.ExitCode};timed_out=$timedOut
        cwd=if($where){$where}else{(Get-Location).Path};command_sha256=(Get-Utf8Sha256 $Command)
        text=$snapshot.text;output_truncated=$true;buffer_truncated=$snapshot.buffer_truncated
        output_pending=$true;session_retained=$true;run_id=$id;session_id=$id
        next_offset=$snapshot.next_offset;base_line=$snapshot.base_line
        total_lines=$snapshot.total_lines;expires_at_utc=$null
      }
    }
    $base=[int]$snapshot.base_line; $total=[int]$snapshot.total_lines
    $retained=New-Object 'System.Collections.Generic.List[string]'
    for($offset=$base;$offset -lt $total;){
      $part=$session.Snapshot($offset,500,0)
      $count=[int]$part.next_offset-$offset
      if ($count -le 0) { break }
      if ($count -eq 1 -and [string]$part.text -eq "") { $retained.Add("") }
      else { foreach($line in @(([string]$part.text) -split '\n')) { $retained.Add($line.TrimEnd("`r")) } }
      $offset=[int]$part.next_offset
    }
    $bufferTruncated=$snapshot.buffer_truncated
    $hasMore=$retained.Count -gt $MaxLines
    $runId=$null; $expires=$null
    if ($hasMore) {
      $created=[DateTime]::UtcNow
      $expires=$created.AddSeconds($script:WindowsRunRetentionSeconds).ToString("o")
      $runId=$id
      $script:CompletedWindowsRuns[$id]=@{
        lines=$retained.ToArray();base_line=$base
        exit_code=if($timedOut){$null}else{$session.Child.ExitCode}
        created_at_utc=$created.ToString("o");expires_at_utc=$expires
        buffer_truncated=$bufferTruncated
      }
      Cleanup-WindowsCompletedRuns
    }
    $page=@()
    for($i=0;$i -lt [Math]::Min($MaxLines,$retained.Count);$i++){ $page+=,$retained[$i] }
    return @{
      state=if($timedOut){"TIMED_OUT"}else{"EXITED"}
      exit_code=if($timedOut){$null}else{$session.Child.ExitCode}
      timed_out=$timedOut;termination_uncertain=$false
      cwd=if($where){$where}else{(Get-Location).Path};command_sha256=(Get-Utf8Sha256 $Command)
      text=($page -join [Environment]::NewLine)
      output_truncated=($hasMore -or $bufferTruncated);buffer_truncated=$bufferTruncated
      session_retained=($null -ne $runId);run_id=$runId;session_id=$runId
      next_offset=$base+$page.Count;base_line=$base;total_lines=$total;expires_at_utc=$expires
    }
  } finally {
    if (-not $managed) { $session.Dispose() }
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
  $mutationClass=if (@("hara.process.run","hara.process.start","hara.process.interact","hara.process.kill") -contains $tool) {"PROCESS_EXECUTION_V1"} elseif (@("hara.files.create_directory","hara.files.write","hara.files.edit") -contains $tool) {"FILESYSTEM_MUTATION_V1"} else {"READ_ONLY_OR_NONE_V1"}
  $approvalMode=Get-ApprovalMode $Cfg
  $receipt = [ordered]@{
    schema="hara.commander-device-receipt.v1"
    request_id=[string]$Call.request_id
    device_id=[string]$Cfg.device_id
    enrollment_context=$(if($Cfg.base_url -and $Cfg.encrypted_device_token){Get-EnrollmentContext $Cfg}else{$null})
    tool_id=[string]$Call.tool_id
    function_id_if_any=if ($Call.payload) {[string]$Call.payload.function_id} else {$null}
    transport_mode="OUTBOUND_RELAY"
    operational_authority="HARA_COMMANDER_CLOUD"
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

function Get-Receipt([string]$Identifier,$Cfg=$null) {
  $value=$Identifier.ToLowerInvariant()
  if ($value -notmatch "^[0-9a-f]{64}$") { throw "RECEIPT_IDENTIFIER_INVALID" }
  $path=Join-Path $ReceiptDir ($value+".json")
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "RECEIPT_NOT_FOUND" }
  $receipt=Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  if($Cfg) {
    if([string]$receipt.device_id -cne [string]$Cfg.device_id){throw "RECEIPT_ENROLLMENT_MISMATCH"}
    if($Cfg.base_url -and [string]$receipt.enrollment_context -cne (Get-EnrollmentContext $Cfg)){throw "RECEIPT_ENROLLMENT_MISMATCH"}
  }
  return $receipt
}
function Invoke-Tool($Cfg,$Call) {
  Assert-CallEnrollment $Cfg $Call
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
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $result=New-DirectResult "filesystem.list" "READ_ONLY" (Get-WindowsDirectory ([string]$payload.path) $depth $limit $offset)
  } elseif ($tool -eq "hara.files.read") {
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $length=if ($null -ne $payload.length) {[int]$payload.length} else {200}
    $result=New-DirectResult "filesystem.read" "READ_ONLY" (Read-WindowsTextFile ([string]$payload.path) $offset $length)
  } elseif ($tool -eq "hara.files.read_many") {
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $length=if ($null -ne $payload.length) {[int]$payload.length} else {100}
    $result=New-DirectResult "filesystem.read_many" "READ_ONLY" (Read-WindowsManyTextFiles $payload.paths $offset $length)
  } elseif ($tool -eq "hara.files.search") {
    $max=if ($null -ne $payload.max_results) {[int]$payload.max_results} else {50}
    $include=$payload.include_hidden -eq $true
    $ignore=$payload.ignore_case -ne $false
    $glob=if ($payload.file_glob) {[string]$payload.file_glob} else {""}
    $offset=if ($null -ne $payload.offset) {[int]$payload.offset} else {0}
    $result=New-DirectResult "filesystem.search" "READ_ONLY" (Search-WindowsFiles ([string]$payload.path) ([string]$payload.search_type) ([string]$payload.pattern) $max $include $ignore $glob $offset)
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
  } elseif ($tool -eq "hara.files.edit") {
    $expected=if ($payload.expected_sha256) {[string]$payload.expected_sha256} else {$null}
    $edited=Edit-WindowsTextFile $Cfg $Call ([string]$payload.path) ([string]$payload.old_text) ([string]$payload.new_text) ($payload.replace_all -eq $true) $expected
    $mutationPerformed=$edited.changed -eq $true
    $result=New-DirectResult "filesystem.edit" "MUTATING" $edited
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
      authority="HARA_COMMANDER_CLOUD"; device=(Get-DeviceInfo $Cfg)
    }
  } elseif ($tool -eq "hara.functions.list") {
    $result=Get-Catalog
  } elseif ($tool -eq "hara.functions.describe") {
    $result=Get-Description ([string]$payload.function_id)
  } elseif ($tool -eq "hara.functions.invoke") {
    $result=Invoke-LocalFunction $Cfg ([string]$payload.function_id) $payload.arguments
  } elseif ($tool -eq "hara.receipts.get") {
    $result=Get-Receipt ([string]$payload.receipt_id_or_sha256) $Cfg
    return @{
      state="PASS";operational_authority="HARA_COMMANDER_CLOUD"
      runtime_authority_from_chatgpt=$false;mutation_performed=$false
      result=$result;blocker=$null
    }
  } else { throw "TOOL_ID_INVALID" }

  $receipt=New-Receipt $Cfg $Call "PASS" $result
  return @{
    state="PASS";operational_authority="HARA_COMMANDER_CLOUD"
    runtime_authority_from_chatgpt=$false;mutation_performed=$mutationPerformed
    result=$result;blocker=$null;bridge_receipt_sha256=$receipt
  }
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $uri=[Uri]$Url
  if($uri.Scheme -cne "https" -or $uri.UserInfo -or $uri.Fragment){throw "COMMANDER_ORIGIN_INVALID"}
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
  $reply=Send-Json "$($Cfg.base_url)/api/device/calls/complete" $Token $body 20
  if(-not $reply -or $reply.ok -ne $true -or [string]$reply.call_id -cne [string]$Call.call_id -or [string]$reply.state -cne $State){throw 'CALL_COMPLETION_NOT_ACKNOWLEDGED'}
}

# Durable relay state is scoped to the enrollment and protected by its ACL.
# The named mutex serializes claims/checkpoints; SQLite commits use FULL sync.
function Invoke-WithWindowsRelayLock([scriptblock]$Action) {
  $name='Local\HARA-Relay-'+(Get-Utf8Sha256 ([IO.Path]::GetFullPath($script:OperationsDb).ToLowerInvariant()))
  $mutex=New-Object Threading.Mutex -ArgumentList $false,$name
  $held=$false
  try {
    try {$held=$mutex.WaitOne(2000)} catch [Threading.AbandonedMutexException] {$held=$true}
    if(-not $held){throw 'RELAY_JOURNAL_BUSY'}
    & $Action
  } finally {if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
}

function Get-WindowsRecoveryNow {return [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()}
function Get-WindowsRecoveryProgressKind([string]$State) {
  if(@('BLOCKED_AUTH','EXHAUSTED','EXPIRED') -ccontains $State){return 'ALERTS_BLOCKED'}
  if($State -ceq 'PERSISTED'){return 'ALERTS_PERSISTED'}
  return $null
}
function Initialize-WindowsRecoveryOutbox($Cfg) {
  $context=Get-EnrollmentContext $Cfg
  if(Test-Path -LiteralPath $ConfigPath -PathType Leaf){
    $current=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if((Get-EnrollmentContext $current) -cne $context){throw 'ENROLLMENT_CHANGED_RESTART_REQUIRED'}
  }
  $folder=Split-Path $script:OperationsDb
  $item=Get-Item -LiteralPath $folder -Force
  if(-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'ENROLLMENT_STATE_PATH_INVALID'}
  $path=Join-Path $folder 'recovery-events.sqlite3'
  if(Test-Path -LiteralPath $path){
    $item=Get-Item -LiteralPath $path -Force
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'ENROLLMENT_STATE_PATH_INVALID'}
  }
  # The enrollment directory already has the native private ACL. This separate
  # DB inherits it, without depending on the tool journal or a DPAPI plaintext.
  Initialize-WinSqlite
  [HaraWinSqlite]::Execute($path,'CREATE TABLE IF NOT EXISTS recovery_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)',@())
  [HaraWinSqlite]::Execute($path,@'
CREATE TABLE IF NOT EXISTS recovery_events (
 ordinal INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,worker TEXT NOT NULL,
 incident TEXT NOT NULL,sequence INTEGER NOT NULL,health TEXT NOT NULL,at_utc TEXT NOT NULL,
 created_ms INTEGER NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
 next_ms INTEGER NOT NULL DEFAULT 0,lease_ms INTEGER NOT NULL DEFAULT 0,server_event_id TEXT,
 UNIQUE(incident,sequence))
'@,@())
  [HaraWinSqlite]::Execute($path,'CREATE INDEX IF NOT EXISTS recovery_due ON recovery_events(state,next_ms)',@())
  [HaraWinSqlite]::Execute($path,"INSERT OR IGNORE INTO recovery_meta VALUES('context',?)",@($context))
  $stored=@([HaraWinSqlite]::Query($path,"SELECT value FROM recovery_meta WHERE key='context'",@()))
  if($stored.Count -ne 1 -or [string]$stored[0].value -cne $context){throw 'ENROLLMENT_CHANGED_RESTART_REQUIRED'}
  return $path
}
function ConvertTo-WindowsRecoveryEvent($Row) {
  return [ordered]@{schema='hara.commander.recovery-alert.proposal.v1';event_id=[string]$Row.event_id;
    client_incident_key=[string]$Row.incident;transition_seq=[long]$Row.sequence;worker=[string]$Row.worker;
    state=[string]$Row.health;observed_at_utc=[string]$Row.at_utc;detector='WINDOWS_JOB_GUARDIAN'}
}
function Add-WindowsRecoveryEvent($Cfg,[string]$Worker,[string]$State) {
  if(@('heartbeat','executor') -cnotcontains $Worker -or @('STALLED','RECOVERING','RECOVERED','DEGRADED') -cnotcontains $State){throw 'RECOVERY_EVENT_INVALID'}
  $path=Initialize-WindowsRecoveryOutbox $Cfg
  $now=[long](Get-WindowsRecoveryNow)
  $eventId=[guid]::NewGuid().ToString('N');$incident=[guid]::NewGuid().ToString('N')
  $at=[DateTimeOffset]::FromUnixTimeMilliseconds($now).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
  [HaraWinSqlite]::Execute($path,"DELETE FROM recovery_events WHERE state='PERSISTED' AND created_ms<?",@($now-90L*86400000))
  # One SQLite INSERT derives incident+sequence and deduplicates atomically.
  # A crash cannot consume a sequence without writing its event.
  [HaraWinSqlite]::Execute($path,@'
INSERT INTO recovery_events(event_id,worker,incident,sequence,health,at_utc,created_ms,state)
SELECT ?,?,COALESCE((SELECT CASE WHEN health='RECOVERED' THEN ? ELSE incident END
 FROM recovery_events WHERE worker=? ORDER BY ordinal DESC LIMIT 1),?),
 COALESCE((SELECT CASE WHEN health='RECOVERED' THEN 1 ELSE sequence+1 END
 FROM recovery_events WHERE worker=? ORDER BY ordinal DESC LIMIT 1),1),?,?,?,'PENDING'
WHERE NOT EXISTS(SELECT 1 FROM (SELECT health FROM recovery_events WHERE worker=? ORDER BY ordinal DESC LIMIT 1) WHERE health=?)
 AND (SELECT count(*) FROM recovery_events)<4096
'@,@($eventId,$Worker,$incident,$Worker,$incident,$Worker,$State,$at,$now,$Worker,$State))
  $row=@([HaraWinSqlite]::Query($path,'SELECT * FROM recovery_events WHERE worker=? ORDER BY ordinal DESC LIMIT 1',@($Worker)))
  if(-not $row.Count -or [string]$row[0].health -cne $State){throw 'RECOVERY_OUTBOX_FULL'}
  return ConvertTo-WindowsRecoveryEvent $row[0]
}
function Send-WindowsRecoveryEvents($Cfg,[string]$Token,[bool]$Authorized=$true) {
  if(-not $Authorized){return @{state='PAUSED'}}
  $path=Initialize-WindowsRecoveryOutbox $Cfg
  if(@([HaraWinSqlite]::Query($path,"SELECT 1 AS n FROM recovery_meta WHERE key='access_denied'",@())).Count){return @{state='BLOCKED_AUTH'}}
  $now=[long](Get-WindowsRecoveryNow)
  [HaraWinSqlite]::Execute($path,"UPDATE recovery_events SET state='EXPIRED' WHERE state IN ('PENDING','RETRY','INFLIGHT') AND created_ms<?",@($now-7L*86400000))
  [HaraWinSqlite]::Execute($path,"UPDATE recovery_events SET state='EXHAUSTED',lease_ms=0 WHERE state='INFLIGHT' AND lease_ms<=? AND attempts>=32",@($now))
  $rows=@([HaraWinSqlite]::Query($path,@'
UPDATE recovery_events SET state='INFLIGHT',attempts=attempts+1,lease_ms=?
WHERE event_id=(SELECT e.event_id FROM recovery_events e WHERE e.attempts<32
 AND ((e.state IN ('PENDING','RETRY') AND e.next_ms<=?) OR (e.state='INFLIGHT' AND e.lease_ms<=?))
 AND NOT EXISTS(SELECT 1 FROM recovery_events p WHERE p.incident=e.incident
  AND p.sequence<e.sequence AND p.state<>'PERSISTED')
 ORDER BY e.ordinal LIMIT 1) RETURNING *
'@,@(($now+15000),$now,$now)))
  if(-not $rows.Count){
    $terminal=@([HaraWinSqlite]::Query($path,"SELECT state FROM recovery_events WHERE state IN ('EXHAUSTED','EXPIRED') ORDER BY ordinal LIMIT 1",@()))
    return @{state=$(if($terminal.Count){[string]$terminal[0].state}else{'EMPTY'})}
  }
  $row=$rows[0];$event=ConvertTo-WindowsRecoveryEvent $row
  $serverId=$null
  try {
    $reply=Send-Json "$(([string]$Cfg.base_url).TrimEnd('/'))/api/device/recovery-events" $Token $event 5
    if(-not $reply -or [string]$reply.schema -cne 'hara.commander.recovery-ingest.v1' -or
       [string]$reply.ack -cne 'PERSISTED' -or [string]$reply.client_event_id -cne [string]$row.event_id -or
       $reply.external_delivery_confirmed -isnot [bool] -or $reply.external_delivery_confirmed -ne $false -or
       [string]$reply.event_id -cnotmatch '^HARA-REC-[0-9a-f]{48}$'){throw 'RECOVERY_PERSISTENCE_NOT_CONFIRMED'}
    $state='PERSISTED';$serverId=[string]$reply.event_id
  } catch {
    $code=Get-SafeErrorCode $_
    $state=if($code -cin @('HTTP_401','HTTP_403')){'BLOCKED_AUTH'}elseif([long]$row.attempts -ge 32){'EXHAUSTED'}else{'RETRY'}
  }
  if($state -ceq 'BLOCKED_AUTH'){[HaraWinSqlite]::Execute($path,"INSERT OR REPLACE INTO recovery_meta VALUES('access_denied','1')",@())}
  $delay=[long][Math]::Min(300000,5000*[Math]::Pow(2,[Math]::Min(16,[long]$row.attempts-1)))
  $saved=@([HaraWinSqlite]::Query($path,"UPDATE recovery_events SET state=?,server_event_id=?,next_ms=?,lease_ms=0 WHERE event_id=? AND state='INFLIGHT' AND attempts=? RETURNING event_id",@($state,$serverId,($now+$delay),[string]$row.event_id,[long]$row.attempts)))
  return @{state=$(if($saved.Count){$state}else{'STALE_ATTEMPT'});event_id=[string]$row.event_id}
}

function Initialize-WindowsRelayStore {
  if(Test-Path -LiteralPath $script:OperationsDb){
    $item=Get-Item -LiteralPath $script:OperationsDb -Force
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'ENROLLMENT_STATE_PATH_INVALID'}
  }
  Invoke-LocalDbExec @'
CREATE TABLE IF NOT EXISTS windows_relay_calls (
 request_id TEXT PRIMARY KEY, call_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
 phase TEXT NOT NULL, receipt_sha256 TEXT, completion_json TEXT,
 delivery_state TEXT NOT NULL DEFAULT 'NONE', updated_at_utc TEXT NOT NULL
)
'@
}

function ConvertTo-WindowsRelayCanonical($Value) {
  if($null -eq $Value){return $null}
  if($Value -is [Collections.IDictionary] -or $Value -is [pscustomobject]) {
    $result=[ordered]@{}
    [string[]]$keys=if($Value -is [Collections.IDictionary]){@($Value.Keys)}else{@($Value.PSObject.Properties.Name)}
    [Array]::Sort($keys,[StringComparer]::Ordinal)
    foreach($key in $keys){$result[$key]=ConvertTo-WindowsRelayCanonical $Value.$key}
    return $result
  }
  if($Value -is [Collections.IEnumerable] -and $Value -isnot [string]) {
    $items=@();foreach($item in $Value){$items+=,(ConvertTo-WindowsRelayCanonical $item)}
    return ,$items
  }
  return $Value
}

function Get-WindowsRelayFingerprint($Call) {
  $binding=[ordered]@{}
  foreach($key in @('call_id','payload','request_id','tool_id','usage')){$binding[$key]=ConvertTo-WindowsRelayCanonical $Call.$key}
  return Get-Utf8Sha256 ($binding | ConvertTo-Json -Depth 20 -Compress)
}

function New-WindowsRelayClaim($Call) {
  foreach($id in @([string]$Call.request_id,[string]$Call.call_id)){
    if([string]::IsNullOrWhiteSpace($id) -or $id.Length -gt 180){throw 'CALL_IDENTITY_INVALID'}
  }
  $fingerprint=Get-WindowsRelayFingerprint $Call
  Invoke-WithWindowsRelayLock {
    Initialize-WindowsRelayStore
    $existing=@(Invoke-LocalDbQuery 'SELECT fingerprint FROM windows_relay_calls WHERE request_id=? OR call_id=?' @([string]$Call.request_id,[string]$Call.call_id))
    if($existing.Count){
      if([string]$existing[0].fingerprint -ceq $fingerprint){throw 'CALL_REPLAY_REFUSED'}
      throw 'CALL_IDEMPOTENCY_CONFLICT'
    }
    Invoke-LocalDbExec 'INSERT INTO windows_relay_calls(request_id,call_id,fingerprint,phase,updated_at_utc) VALUES(?,?,?,?,?)' @([string]$Call.request_id,[string]$Call.call_id,$fingerprint,'PREPARING',[DateTime]::UtcNow.ToString('o'))
  }
}

function Set-WindowsRelayPhase($Call,[string]$Phase,[string]$ReceiptSha='') {
  if(@('RESERVED','EXECUTING','EXECUTED','FAILED','UNCERTAIN') -cnotcontains $Phase){throw 'CALL_PHASE_INVALID'}
  Invoke-WithWindowsRelayLock {
    Invoke-LocalDbExec 'UPDATE windows_relay_calls SET phase=?,receipt_sha256=COALESCE(NULLIF(?,?),receipt_sha256),updated_at_utc=? WHERE request_id=?' @($Phase,$ReceiptSha,'',[DateTime]::UtcNow.ToString('o'),[string]$Call.request_id)
  }
  Write-WindowsRelayProgress 'PHASE' @{request_id=[string]$Call.request_id;phase=$Phase}
}

function Set-WindowsRelayCompletion($Call,[string]$State,$Result,[string]$ErrorCode='') {
  $body=[ordered]@{call_id=[string]$Call.call_id;state=$State;result=$Result}
  if($ErrorCode){$body.error_code=$ErrorCode}
  $json=$body | ConvertTo-Json -Depth 20 -Compress
  if([Text.Encoding]::UTF8.GetByteCount($json) -gt 256*1024){throw 'CALL_COMPLETION_TOO_LARGE'}
  Invoke-WithWindowsRelayLock {
    Invoke-LocalDbExec "UPDATE windows_relay_calls SET completion_json=?,delivery_state='PENDING',phase=CASE WHEN ?='COMPLETED' THEN 'EXECUTED' ELSE phase END,receipt_sha256=COALESCE(NULLIF(?,''),receipt_sha256),updated_at_utc=? WHERE request_id=?" @($json,$State,[string]$Result.bridge_receipt_sha256,[DateTime]::UtcNow.ToString('o'),[string]$Call.request_id)
  }
}

function Get-WindowsRelayDeliveryError($ErrorRecord) {
  $code=Get-SafeErrorCode $ErrorRecord
  try {
    $wire=$ErrorRecord.ErrorDetails.Message | ConvertFrom-Json
    if([string]$wire.code -ceq 'DEVICE_CALL_EXPIRED' -or [string]$wire.error -ceq 'DEVICE_CALL_EXPIRED'){return 'DEVICE_CALL_EXPIRED'}
  } catch {}
  if($ErrorRecord.Exception.Message -ceq 'DEVICE_CALL_EXPIRED'){return 'DEVICE_CALL_EXPIRED'}
  return $code
}

function Send-WindowsRelayCompletion($Cfg,[string]$Token,[string]$RequestId,$Body) {
  try {Complete-Call $Cfg $Token ([pscustomobject]@{call_id=[string]$Body.call_id}) ([string]$Body.state) $Body.result ([string]$Body.error_code)}
  catch {
    $code=Get-WindowsRelayDeliveryError $_
    Invoke-WithWindowsRelayLock {
      if($code -ceq 'DEVICE_CALL_EXPIRED'){
        Invoke-LocalDbExec "UPDATE windows_relay_calls SET delivery_state='EXPIRED',completion_json=NULL,updated_at_utc=? WHERE request_id=?" @([DateTime]::UtcNow.ToString('o'),$RequestId)
      } else {
        Invoke-LocalDbExec 'UPDATE windows_relay_calls SET updated_at_utc=? WHERE request_id=?' @([DateTime]::UtcNow.ToString('o'),$RequestId)
      }
    }
    throw
  }
  Invoke-WithWindowsRelayLock {
    Invoke-LocalDbExec "UPDATE windows_relay_calls SET delivery_state='ACKNOWLEDGED',completion_json=NULL,updated_at_utc=? WHERE request_id=?" @([DateTime]::UtcNow.ToString('o'),$RequestId)
  }
}

function Repair-WindowsRelayJournal($Cfg=$null,[string]$Token=$null,[int]$Limit=64) {
  Initialize-WindowsRelayStore
  $rows=@(Invoke-LocalDbQuery "SELECT * FROM windows_relay_calls WHERE phase IN ('PREPARING','RESERVED','EXECUTING') OR completion_json IS NOT NULL ORDER BY updated_at_utc LIMIT ?" @($Limit))
  foreach($row in $rows){
    $call=[pscustomobject]@{call_id=[string]$row.call_id;request_id=[string]$row.request_id}
    if(@('PREPARING','RESERVED','EXECUTING') -ccontains [string]$row.phase){
      $uncertain=[string]$row.phase -ceq 'EXECUTING'
      $phase=if($uncertain){'UNCERTAIN'}else{'FAILED'}
      $code=if($uncertain){'CALL_OUTCOME_UNCERTAIN'}else{'DEVICE_CALL_TIMEOUT'}
      Set-WindowsRelayPhase $call $phase
      if(-not $row.completion_json){
        $result=@{state=if($uncertain){'INDETERMINATE'}else{'DENIED'};runtime_authority_from_chatgpt=$false;mutation_performed=if($uncertain){$null}else{$false};result=@{};blocker=@{code=$code}}
        Set-WindowsRelayCompletion $call 'FAILED' $result $code
      }
    }
    if($Cfg){
      $pending=@(Invoke-LocalDbQuery 'SELECT completion_json FROM windows_relay_calls WHERE request_id=?' @([string]$row.request_id))
      if($pending.Count -and $pending[0].completion_json){Send-WindowsRelayCompletion $Cfg $Token ([string]$row.request_id) ($pending[0].completion_json | ConvertFrom-Json)}
    }
  }
}

function Test-WindowsMutationTool([string]$Tool) {
  return @('hara.files.create_directory','hara.files.write','hara.files.edit','hara.process.start','hara.process.run','hara.process.interact','hara.process.kill') -ccontains $Tool
}

function Invoke-WindowsRelayCall($Cfg,[string]$Token,$Call) {
  New-WindowsRelayClaim $Call
  $executing=$false
  try {
    Assert-WindowsRelayDeadline
    if((Get-ApprovalMode $Cfg) -cne 'PERSISTENT_TRUSTED' -and -not (Test-OperatorSessionActive)){throw 'LOCAL_OPERATOR_SESSION_REQUIRED'}
    if([string]$Call.usage.mode -ceq 'LOCAL_BUDGET'){throw 'WINDOWS_LOCAL_BUDGET_UNSUPPORTED'}
    Write-ConsoleEvent 'RECEIVED' $Call 'PENDING'
    Assert-WindowsRelayDeadline
    Set-WindowsRelayPhase $Call 'EXECUTING'
    $executing=$true
    Assert-WindowsRelayDeadline
    $result=Invoke-Tool $Cfg $Call
  } catch {
    $code=Get-SafeErrorCode $_
    $uncertain=$executing -and (Test-WindowsMutationTool ([string]$Call.tool_id))
    Set-WindowsRelayPhase $Call $(if($uncertain){'UNCERTAIN'}else{'FAILED'})
    $result=@{state=if($uncertain){'INDETERMINATE'}else{'DENIED'};runtime_authority_from_chatgpt=$false;mutation_performed=if($uncertain){$null}else{$false};result=@{};blocker=@{code=$code}}
    Set-WindowsRelayCompletion $Call 'FAILED' $result $code
    Send-WindowsRelayCompletion $Cfg $Token ([string]$Call.request_id) ([pscustomobject]@{call_id=[string]$Call.call_id;state='FAILED';result=$result;error_code=$code})
    Write-ConsoleEvent $(if($uncertain){'OPERATIONAL'}else{'DENIED'}) $Call $(if($uncertain){'UNCERTAIN'}else{'FAILED'}) $code
    return
  }
  # Atomic success + outbox checkpoint; delivery failure never rewrites effects.
  Set-WindowsRelayCompletion $Call 'COMPLETED' $result
  Send-WindowsRelayCompletion $Cfg $Token ([string]$Call.request_id) ([pscustomobject]@{call_id=[string]$Call.call_id;state='COMPLETED';result=$result})
  Write-ConsoleEvent 'PASS' $Call 'COMPLETED' '' ([string]$result.bridge_receipt_sha256)
}

function Get-WindowsRelayNow {return [Diagnostics.Stopwatch]::GetTimestamp()/[double][Diagnostics.Stopwatch]::Frequency}
$script:WindowsRelayDeadline=$null
function Assert-WindowsRelayDeadline {
  if($null -ne $script:WindowsRelayDeadline -and (Get-WindowsRelayNow) -ge $script:WindowsRelayDeadline){throw 'DEVICE_CALL_EXPIRED'}
}
function Write-WindowsRelayProgress([string]$Kind,$Details=@{}) {
  if(-not $script:WindowsRelayWorkerMode){return}
  $message=[ordered]@{schema='hara.commander.relay-progress.v1';kind=$Kind}
  foreach($key in $Details.Keys){$message[$key]=$Details[$key]}
  [Console]::Out.WriteLine('HARA_RELAY_PROGRESS='+($message | ConvertTo-Json -Depth 5 -Compress))
  [Console]::Out.Flush()
}

function Initialize-WindowsRelayProcessType {
  if('HaraRelayProcess' -as [type]){return}
  Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public sealed class HaraRelayProcess : IDisposable {
  [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
    public long ProcessTime,JobTime; public uint Flags;
    public UIntPtr MinWorkingSet,MaxWorkingSet; public uint ActiveLimit;
    public UIntPtr Affinity; public uint Priority,Scheduling;
  }
  [StructLayout(LayoutKind.Sequential)] struct Counters {
    public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes;
  }
  [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
    public BasicLimits Basic; public Counters Io;
    public UIntPtr ProcessMemory,JobMemory,PeakProcessMemory,PeakJobMemory;
  }
  [StructLayout(LayoutKind.Sequential)] struct Accounting {
    public long UserTime,KernelTime,PeriodUserTime,PeriodKernelTime;
    public uint PageFaults,TotalProcesses,ActiveProcesses,TerminatedProcesses;
  }
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes,string name);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int info,IntPtr value,uint length);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int info,IntPtr value,uint length,IntPtr resultLength);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint exitCode);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  readonly ConcurrentQueue<string> Progress=new ConcurrentQueue<string>();
  int Pending=0;
  IntPtr Job=IntPtr.Zero;
  public readonly Process Child;
  public volatile bool ProtocolOverflow=false;

  static string Quote(string value) {
    if(value==null || value.IndexOfAny(new char[]{'"','\r','\n','\0'})>=0) throw new InvalidOperationException("RELAY_ARGUMENT_INVALID");
    return "\""+value+"\"";
  }
  public HaraRelayProcess(string shell,string script,string role,string parentPid,string parentStart,string context,string nonce,string handshake) {
    if(Environment.OSVersion.Platform!=PlatformID.Win32NT) throw new PlatformNotSupportedException("WINDOWS_JOB_REQUIRED");
    if(role!="heartbeat" && role!="executor" && role!="alerts") throw new InvalidOperationException("RELAY_ROLE_INVALID");
    if(handshake==null || handshake.Length>4096) throw new InvalidOperationException("RELAY_HANDSHAKE_INVALID");
    Job=CreateJobObject(IntPtr.Zero,null);
    if(Job==IntPtr.Zero) throw new InvalidOperationException("RELAY_JOB_CREATE_FAILED");
    try {
      ExtendedLimits limits=new ExtendedLimits();limits.Basic.Flags=0x2000; // KILL_ON_JOB_CLOSE; no breakaway.
      int size=Marshal.SizeOf(typeof(ExtendedLimits));IntPtr buffer=Marshal.AllocHGlobal(size);
      try {Marshal.StructureToPtr(limits,buffer,false);if(!SetInformationJobObject(Job,9,buffer,(uint)size)) throw new InvalidOperationException("RELAY_JOB_LIMIT_FAILED");}
      finally {Marshal.FreeHGlobal(buffer);}
      Child=new Process();
      Child.StartInfo.FileName=shell;
      Child.StartInfo.Arguments="-NoLogo -NoProfile -NonInteractive -File "+Quote(script)+" --relay-worker "+Quote(role)+" "+Quote(parentPid)+" "+Quote(parentStart)+" "+Quote(context)+" "+Quote(nonce);
      Child.StartInfo.UseShellExecute=false;Child.StartInfo.CreateNoWindow=true;
      Child.StartInfo.RedirectStandardInput=true;Child.StartInfo.RedirectStandardOutput=true;Child.StartInfo.RedirectStandardError=true;
      Child.StartInfo.StandardOutputEncoding=new UTF8Encoding(false);
      Child.OutputDataReceived+=OnOutput;
      Child.ErrorDataReceived+=delegate(object sender,DataReceivedEventArgs e) {}; // Never relay raw stderr/secrets.
      if(!Child.Start()) throw new InvalidOperationException("RELAY_WORKER_START_FAILED");
      // The worker waits for this handshake before touching enrollment or tools.
      if(!AssignProcessToJobObject(Job,Child.Handle)) throw new InvalidOperationException("RELAY_JOB_ASSIGN_FAILED");
      Child.BeginOutputReadLine();Child.BeginErrorReadLine();
      Child.StandardInput.WriteLine(handshake);Child.StandardInput.Flush();Child.StandardInput.Close();
    } catch {
      if(Child!=null) {try {if(!Child.HasExited) Child.Kill();Child.WaitForExit(1000);}catch{}}
      if(Job!=IntPtr.Zero){CloseHandle(Job);Job=IntPtr.Zero;}
      throw;
    }
  }
  void OnOutput(object sender,DataReceivedEventArgs e) {
    if(e.Data==null || !e.Data.StartsWith("HARA_RELAY_PROGRESS=",StringComparison.Ordinal)) return;
    if(e.Data.Length>4096) {ProtocolOverflow=true;return;}
    if(Interlocked.Increment(ref Pending)>128) {ProtocolOverflow=true;Interlocked.Decrement(ref Pending);return;}
    Progress.Enqueue(e.Data.Substring(20));
  }
  public string[] Drain() {
    var result=new System.Collections.Generic.List<string>();string line;
    for(int i=0;i<128 && Progress.TryDequeue(out line);i++){Interlocked.Decrement(ref Pending);result.Add(line);}
    return result.ToArray();
  }
  public bool IsAlive {get {return !Child.HasExited;}}
  public bool IsQuiescent {
    get {
      if(Job==IntPtr.Zero) return Child.HasExited;
      int size=Marshal.SizeOf(typeof(Accounting));IntPtr buffer=Marshal.AllocHGlobal(size);
      try {
        if(!QueryInformationJobObject(Job,1,buffer,(uint)size,IntPtr.Zero)) return false;
        Accounting value=(Accounting)Marshal.PtrToStructure(buffer,typeof(Accounting));
        return Child.HasExited && value.ActiveProcesses==0;
      } finally {Marshal.FreeHGlobal(buffer);}
    }
  }
  public bool Stop() {
    if(Job!=IntPtr.Zero && !TerminateJobObject(Job,1)) return IsQuiescent;
    try {Child.WaitForExit(1000);}catch{return false;}
    return IsQuiescent;
  }
  public void Dispose() {
    if(Job!=IntPtr.Zero){CloseHandle(Job);Job=IntPtr.Zero;}
    if(Child!=null) Child.Dispose();
    GC.SuppressFinalize(this);
  }
  ~HaraRelayProcess(){if(Job!=IntPtr.Zero)CloseHandle(Job);}
}
'@
}

function Start-WindowsRelayProcess([string]$Role,$Cfg,$Abandoned,[string]$AgentPath) {
  Initialize-WindowsRelayProcessType
  $nonce=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
  $handshake=@{schema='hara.commander.relay-worker-handshake.v1';nonce=$nonce;abandoned=@($Abandoned)} | ConvertTo-Json -Depth 6 -Compress
  $parentStart=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
  return New-Object HaraRelayProcess -ArgumentList (Join-Path $PSHOME 'powershell.exe'),([IO.Path]::GetFullPath($AgentPath)),$Role,([string]$PID),$parentStart,(Get-EnrollmentContext $Cfg),$nonce,$handshake
}
function Read-WindowsRelayProgress($Process) {
  if($Process.ProtocolOverflow){throw 'RELAY_PROGRESS_OVERFLOW'}
  foreach($line in $Process.Drain()){
    $message=$line | ConvertFrom-Json
    if([string]$message.schema -cne 'hara.commander.relay-progress.v1'){throw 'RELAY_PROGRESS_INVALID'}
    $message
  }
}
function Test-WindowsRelayProcessAlive($Process) {return $Process.IsAlive}
function Stop-WindowsRelayProcess($Process) {
  if(-not $Process.Stop()){return $false}
  $Process.Dispose();return $true
}
function Get-WindowsRelayDeadline($Call,[double]$Now=(Get-WindowsRelayNow)) {
  $expiry=[DateTimeOffset]::MinValue
  if([string]$Call.expires_at_utc -cnotmatch '(Z|[+-][0-9]{2}:[0-9]{2})$' -or -not [DateTimeOffset]::TryParse([string]$Call.expires_at_utc,[ref]$expiry)){throw 'CALL_DEADLINE_REQUIRED'}
  $limit=if([string]$Call.tool_id -ceq 'hara.process.run'){20.0}elseif([string]$Call.tool_id -ceq 'hara.process.start'){15.0}else{30.0}
  return $Now+[Math]::Max(0.0,[Math]::Min($limit,($expiry.UtcDateTime-[DateTime]::UtcNow).TotalSeconds))
}
function New-WindowsRelaySupervisorState([string]$AgentPath,[scriptblock]$Reporter=$null) {
  return @{agentPath=$AgentPath;reporter=$Reporter;children=@{};attempts=@{heartbeat=@();executor=@()};restartCounts=@{heartbeat=0;executor=0};heartbeatCount=0;lastHeartbeat=$null;startedAt=$null;states=@{};recovering=@{};blockedUntil=@{};abandoned=@{};revoked=$false;pendingHealth=(New-Object Collections.Generic.List[object]);lastHealthError=$null}
}
function Flush-WindowsRecoveryHealth($State,[double]$Now) {
  while($State.pendingHealth.Count){
    try {Add-WindowsRecoveryEvent $State.recoveryCfg $State.pendingHealth[0].worker $State.pendingHealth[0].state | Out-Null}
    catch {
      if($null -eq $State.lastHealthError -or $Now-$State.lastHealthError -ge 30){
        [Console]::Error.WriteLine('RECOVERY_OUTBOX_WRITE_FAILED');$State.lastHealthError=$Now
      }
      break
    }
    $State.pendingHealth.RemoveAt(0)
  }
}
function Write-WindowsRelayHealth($State,[string]$Role,[string]$Health,[double]$Now) {
  if($State.states[$Role] -ceq $Health){return}
  $State.states[$Role]=$Health
  if($State.recoveryCfg -and @('heartbeat','executor') -ccontains $Role){
    if($State.pendingHealth.Count -lt 128){$State.pendingHealth.Add(@{worker=$Role;state=$Health})}
    else{[Console]::Error.WriteLine('RECOVERY_OUTBOX_FULL')}
    Flush-WindowsRecoveryHealth $State $Now
  }
  $event=@{schema='hara.commander.relay-health.v1';worker=$Role;state=$Health;monotonic=$Now}
  if($State.reporter){& $State.reporter $event}else{[Console]::Error.WriteLine(($event | ConvertTo-Json -Compress))}
}
function Stop-WindowsRelayChild($State,[string]$Role) {
  $child=$State.children[$Role]
  if(-not $child){return $true}
  if(-not (Stop-WindowsRelayProcess $child.process)){$child.fenced=$true;return $false}
  $State.children.Remove($Role);return $true
}
function Start-WindowsRelayChild($State,$Cfg,[string]$Role,[double]$Now) {
  $seeds=if($Role -ceq 'executor'){@($State.abandoned.Values)}else{@()}
  $process=Start-WindowsRelayProcess $Role $Cfg $seeds $State.agentPath
  $State.children[$Role]=@{process=$process;deadline=$Now+35.0;ready=$false;networkBackoff=$false;call=$null;fenced=$false}
}
function Restart-WindowsRelayChild($State,$Cfg,[string]$Role,[double]$Now) {
  Write-WindowsRelayHealth $State $Role 'STALLED' $Now
  $child=$State.children[$Role]
  if($Role -ceq 'executor' -and $child.call){$State.abandoned[[string]$child.call.request_id]=$child.call}
  if(-not (Stop-WindowsRelayChild $State $Role)){Write-WindowsRelayHealth $State $Role 'DEGRADED' $Now;return}
  $recent=@($State.attempts[$Role]|Where-Object {$Now-$_ -lt 1800})
  $State.attempts[$Role]=$recent
  if($recent.Count -ge 2){$State.blockedUntil[$Role]=$recent[0]+1800;Write-WindowsRelayHealth $State $Role 'DEGRADED' $Now;return}
  $delay=if($recent.Count){[Math]::Max(0,5-($Now-$recent[-1]))}else{0.0}
  if($delay -gt 0){$delay+=(Get-Random -Minimum 0 -Maximum 1000)/1000.0}
  $State.attempts[$Role]=@($recent)+@($Now+$delay);$State.restartCounts[$Role]++
  $State.recovering[$Role]=$Now;Write-WindowsRelayHealth $State $Role 'RECOVERING' $Now
  if($delay -gt 0){$State.blockedUntil[$Role]=$Now+$delay}else{Start-WindowsRelayChild $State $Cfg $Role $Now}
}
function Step-WindowsRelaySupervisor($State,$Cfg,[bool]$Authorized,[double]$Now=(Get-WindowsRelayNow)) {
  if(-not $Authorized -or $State.revoked){
    foreach($role in @($State.children.Keys)){[void](Stop-WindowsRelayChild $State $role)}
    $State.startedAt=$null;$State.lastHeartbeat=$null;$State.recovering.Clear();return
  }
  if($null -eq $State.startedAt){$State.startedAt=$Now}
  Flush-WindowsRecoveryHealth $State $Now
  $roles=@('heartbeat','executor');if($State.alertsEnabled){$roles+=@('alerts')}
  foreach($role in $roles){
    if(-not $State.children.ContainsKey($role) -and $Now -ge [double]$State.blockedUntil[$role]){Start-WindowsRelayChild $State $Cfg $role $Now}
  }
  foreach($role in @($State.children.Keys)){
    $child=$State.children[$role]
    if($child.fenced){[void](Stop-WindowsRelayChild $State $role);continue}
    try {$messages=@(Read-WindowsRelayProgress $child.process)}catch{Restart-WindowsRelayChild $State $Cfg $role $Now;continue}
    foreach($message in $messages){
      $tag=[string]$message.kind
      if($role -ceq 'alerts' -and $tag -ceq 'ALERTS_BLOCKED'){Write-WindowsRelayHealth $State $role 'DEGRADED' $Now}
      elseif($role -ceq 'alerts' -and $tag -ceq 'ALERTS_PERSISTED'){Write-WindowsRelayHealth $State $role 'RECOVERED' $Now}
      if($tag -ceq 'REVOKED'){$State.revoked=$true;Step-WindowsRelaySupervisor $State $Cfg $false $Now;return}
      if($role -ceq 'heartbeat'){
        if($tag -ceq 'HEARTBEAT_CONFIRMED'){$State.lastHeartbeat=$Now;$State.heartbeatCount++;$child.networkBackoff=$false;$child.deadline=$Now+$HeartbeatSeconds+35}
        elseif($tag -ceq 'HEARTBEAT_ATTEMPT'){$child.deadline=$Now+35}
        elseif($tag -ceq 'HEARTBEAT_RETRY'){$child.networkBackoff=$true;$child.deadline=$Now+[Math]::Min(60,[double]$message.delay)+35}
      } elseif($tag -ceq 'CALL'){
        $child.deadline=[Math]::Min([double]$message.deadline,$Now+900);$child.ready=$false
        $child.call=@{request_id=[string]$message.request_id;call_id=[string]$message.call_id;fingerprint=[string]$message.fingerprint}
      } elseif($tag -ceq 'READY' -or $tag -ceq 'BUSY'){
        $sleep=if($tag -ceq 'READY'){[Math]::Min(60,[Math]::Max(0,[double]$message.delay))}else{0.0}
        $child.deadline=$Now+$sleep+35;$child.ready=$tag -ceq 'READY'
        if($child.ready -and $role -ceq 'executor'){$child.call=$null;$State.abandoned.Clear()}
      }
    }
    $anchor=if($null -ne $State.lastHeartbeat){$State.lastHeartbeat}else{$State.startedAt}
    $absent=$role -ceq 'heartbeat' -and $Now-$anchor -ge 150
    $alive=Test-WindowsRelayProcessAlive $child.process
    if($absent -and $child.networkBackoff -and $alive -and $Now -lt $child.deadline){
      if(-not $State.recovering.ContainsKey($role)){
        Write-WindowsRelayHealth $State $role 'STALLED' $Now;Write-WindowsRelayHealth $State $role 'RECOVERING' $Now
        $State.recovering[$role]=$Now;Write-WindowsRelayHealth $State $role 'DEGRADED' $Now
      }
    } elseif(-not $alive -or $Now -ge $child.deadline -or $absent){Restart-WindowsRelayChild $State $Cfg $role $Now}
  }
  foreach($role in @($State.recovering.Keys)){
    $child=$State.children[$role]
    if($child -and $null -ne $State.lastHeartbeat -and $State.lastHeartbeat -gt $State.recovering[$role] -and ($role -ceq 'heartbeat' -or $child.ready)){
      Write-WindowsRelayHealth $State $role 'RECOVERED' $Now;$State.recovering.Remove($role)
    }
  }
}

function Read-WindowsRelayConfig {
  $item=Get-Item -LiteralPath $ConfigPath -Force
  if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 32768){throw 'DEVICE_CONFIG_INVALID'}
  $cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  [void](Get-EnrollmentContext $cfg)
  if(-not $cfg.architecture){throw 'DEVICE_CONFIG_INVALID'}
  if($cfg.transport_mode -and [string]$cfg.transport_mode -cne 'OUTBOUND_RELAY'){throw 'WINDOWS_RELAY_TRANSPORT_REQUIRED'}
  return $cfg
}
function Test-WindowsRelayWorkerContext([int]$ParentId,[string]$ParentStart,[string]$ExpectedContext) {
  try {$parent=Get-Process -Id $ParentId -ErrorAction Stop}catch{return $null}
  if($parent.StartTime.ToUniversalTime().ToString('o') -cne $ParentStart){return $null}
  $cfg=Read-WindowsRelayConfig
  if((Get-EnrollmentContext $cfg) -cne $ExpectedContext){throw 'ENROLLMENT_CHANGED_RESTART_REQUIRED'}
  if((Get-ApprovalMode $cfg) -cne 'PERSISTENT_TRUSTED' -and -not (Test-OperatorSessionActive)){return $null}
  return $cfg
}
function Restore-WindowsRelayClaims($Claims) {
  foreach($claim in @($Claims)){
    if([string]$claim.fingerprint -cnotmatch '^[0-9a-f]{64}$' -or -not $claim.call_id -or -not $claim.request_id -or ([string]$claim.call_id).Length -gt 180 -or ([string]$claim.request_id).Length -gt 180){throw 'CALL_RECOVERY_BINDING_INVALID'}
    Invoke-WithWindowsRelayLock {
      Initialize-WindowsRelayStore
      $row=@(Invoke-LocalDbQuery 'SELECT call_id,fingerprint FROM windows_relay_calls WHERE request_id=?' @([string]$claim.request_id))
      if($row.Count){
        if([string]$row[0].call_id -cne [string]$claim.call_id -or [string]$row[0].fingerprint -cne [string]$claim.fingerprint){throw 'CALL_IDEMPOTENCY_CONFLICT'}
      } else {
        Invoke-LocalDbExec 'INSERT INTO windows_relay_calls(request_id,call_id,fingerprint,phase,updated_at_utc) VALUES(?,?,?,?,?)' @([string]$claim.request_id,[string]$claim.call_id,[string]$claim.fingerprint,'PREPARING',[DateTime]::UtcNow.ToString('o'))
      }
    }
  }
}
function Start-WindowsRelayWorker([string[]]$WorkerArgs) {
  if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $WorkerArgs.Count -ne 6 -or @('heartbeat','executor','alerts') -cnotcontains $WorkerArgs[1]){throw 'RELAY_WORKER_ARGUMENTS_INVALID'}
  [int]$parentId=0
  if(-not [int]::TryParse($WorkerArgs[2],[ref]$parentId) -or $parentId -le 1 -or $WorkerArgs[4] -cnotmatch '^[0-9a-f]{64}$' -or $WorkerArgs[5] -cnotmatch '^[0-9a-f]{64}$' -or -not [Console]::IsInputRedirected){throw 'RELAY_HANDSHAKE_REQUIRED'}
  # START is sent only after the guardian has assigned the native Job Object.
  $line=[Console]::In.ReadLine()
  if(-not $line -or $line.Length -gt 4096){throw 'RELAY_HANDSHAKE_REQUIRED'}
  $hello=$line | ConvertFrom-Json
  if([string]$hello.schema -cne 'hara.commander.relay-worker-handshake.v1' -or [string]$hello.nonce -cne $WorkerArgs[5] -or @($hello.abandoned).Count -gt 2){throw 'RELAY_HANDSHAKE_INVALID'}
  $script:WindowsRelayWorkerMode=$true
  $cfg=Test-WindowsRelayWorkerContext $parentId $WorkerArgs[3] $WorkerArgs[4]
  if(-not $cfg){return}
  if(@('executor','alerts') -ccontains $WorkerArgs[1]){$script:EnrollmentContext=Initialize-EnrollmentState $cfg}
  if($WorkerArgs[1] -ceq 'executor'){
    Restore-WindowsRelayClaims $hello.abandoned
    Repair-WindowsRelayJournal
    Write-WindowsRelayProgress 'READY' @{delay=0}
  }
  $failures=0;$lastRepair=0.0;$burst=0
  $hotUntil=(Get-WindowsRelayNow)+$CallPollStartupHotSeconds
  $approvalLimit=$ApprovalTimeoutSeconds
  try {
    while($true){
      $cfg=Test-WindowsRelayWorkerContext $parentId $WorkerArgs[3] $WorkerArgs[4]
      if(-not $cfg){return}
      $deviceToken=$null
      $delay=2.0;$completed=$false
      try {
        $deviceToken=Get-PlainText (ConvertTo-SecureString ([string]$cfg.encrypted_device_token))
        if([string]::IsNullOrWhiteSpace($deviceToken)){throw 'DEVICE_CONFIG_INVALID'}
        if($WorkerArgs[1] -ceq 'heartbeat'){
          Write-WindowsRelayProgress 'HEARTBEAT_ATTEMPT'
          $reply=Send-Json "$($cfg.base_url)/api/device/heartbeat" $deviceToken @{
            device_id=[string]$cfg.device_id;architecture=[string]$cfg.architecture;agent_version=$AgentVersion;approval_mode=(Get-ApprovalMode $cfg)
          } 20
          if(-not $reply -or $reply.ok -ne $true -or [string]$reply.schema -cne 'hara.commander-device-heartbeat.v1' -or [string]$reply.device_id -cne [string]$cfg.device_id -or [string]$reply.state -cne 'ACTIVE'){throw 'HEARTBEAT_NOT_CONFIRMED'}
          Write-WindowsRelayProgress 'HEARTBEAT_CONFIRMED'
          Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString('o')) -ErrorCode '' -ErrorAt '' | Out-Null
          $delay=[double]$HeartbeatSeconds;$failures=0
        } elseif($WorkerArgs[1] -ceq 'alerts') {
          Write-WindowsRelayProgress 'BUSY'
          $sent=Send-WindowsRecoveryEvents $cfg $deviceToken $true
          $progress=Get-WindowsRecoveryProgressKind ([string]$sent.state)
          if($progress){Write-WindowsRelayProgress $progress}
          # Alert-route admission does not revoke the base Agent. Enrollment
          # authority remains the authenticated heartbeat/executor response.
          $delay=if($progress -ceq 'ALERTS_BLOCKED'){60.0}elseif($sent.state -ceq 'PERSISTED'){0.1}else{2.0}
        } else {
          Write-WindowsRelayProgress 'BUSY'
          if((Get-WindowsRelayNow)-$lastRepair -ge 10){
            try {Repair-WindowsRelayJournal $cfg $deviceToken 1}catch{if((Get-SafeErrorCode $_) -cin @('HTTP_401','HTTP_403')){throw}}
            $lastRepair=Get-WindowsRelayNow
          }
          Write-WindowsRelayProgress 'BUSY'
          try {$call=Send-Json "$($cfg.base_url)/api/device/calls/next" $deviceToken @{} 25}
          catch {if($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 204){$call=$null}else{throw}}
          if($call -and $call.call_id){
            $hotUntil=(Get-WindowsRelayNow)+$CallPollHotWindowSeconds
            $script:WindowsRelayDeadline=Get-WindowsRelayDeadline $call
            Write-WindowsRelayProgress 'CALL' @{call_id=[string]$call.call_id;request_id=[string]$call.request_id;fingerprint=(Get-WindowsRelayFingerprint $call);deadline=$script:WindowsRelayDeadline}
            $script:ApprovalTimeoutSeconds=[Math]::Min($approvalLimit,[Math]::Max(1,[Math]::Ceiling($script:WindowsRelayDeadline-(Get-WindowsRelayNow))))
            try {Assert-WindowsRelayDeadline;Invoke-WindowsRelayCall $cfg $deviceToken $call;$completed=$true}
            finally {$script:WindowsRelayDeadline=$null;$script:ApprovalTimeoutSeconds=$approvalLimit}
          }
          if($completed){$burst++}else{$burst=0}
          $delay=Get-WindowsRelayPollSleep $completed $burst ((Get-WindowsRelayNow) -lt $hotUntil)
          $failures=0
        }
      } catch {
        $code=Get-SafeErrorCode $_
        if($code -cin @('HTTP_401','HTTP_403','DEVICE_AUTH_INVALID')){Write-WindowsRelayProgress 'REVOKED' @{code=$code};return}
        $failures=[Math]::Min(6,$failures+1)
        $delay=[Math]::Min(60.0,$(if($code -ceq 'HTTP_429'){30.0}else{2.0})*[Math]::Pow(2,$failures-1))
        if($WorkerArgs[1] -ceq 'heartbeat'){Write-WindowsRelayProgress 'HEARTBEAT_RETRY' @{delay=$delay;code=$code}}
      } finally {$deviceToken=$null}
      if(@('executor','alerts') -ccontains $WorkerArgs[1]){Write-WindowsRelayProgress 'READY' @{delay=$delay}}
      Start-Sleep -Milliseconds ([int]($delay*1000))
    }
  } finally {
    foreach($session in @($script:ManagedWindowsSessions.Values)){try{$session.Dispose()}catch{}}
  }
}
function Start-WindowsRelaySupervisor($Cfg,[string]$AgentPath) {
  $context=Get-EnrollmentContext $Cfg
  $state=New-WindowsRelaySupervisorState $AgentPath
  $state.recoveryCfg=$Cfg;$state.alertsEnabled=$true
  $state.attempts.alerts=@();$state.restartCounts.alerts=0
  Initialize-WindowsRecoveryOutbox $Cfg | Out-Null
  try {
    while($true){
      $current=Read-WindowsRelayConfig
      if((Get-EnrollmentContext $current) -cne $context){throw 'ENROLLMENT_CHANGED_RESTART_REQUIRED'}
      if((Get-ApprovalMode $current) -cne (Get-ApprovalMode $Cfg)){
        foreach($role in @($state.children.Keys)){
          if(-not (Stop-WindowsRelayChild $state $role)){throw 'RELAY_PREVIOUS_JOB_NOT_QUIESCENT'}
        }
        $Cfg=$current
      }
      $authorized=(Get-ApprovalMode $current) -ceq 'PERSISTENT_TRUSTED' -or (Test-OperatorSessionActive)
      Step-WindowsRelaySupervisor $state $current $authorized
      Start-Sleep -Milliseconds 100
    }
  } finally {
    foreach($role in @($state.children.Keys)){[void](Stop-WindowsRelayChild $state $role)}
  }
}

function Get-WindowsRelayPollSleep([bool]$Completed,[int]$BurstCount,[bool]$Hot) {
  if ($Completed -and $BurstCount -lt 8) { return 0 }
  if ($Hot) { return $CallPollHotSeconds }
  return $CallPollIdleSeconds
}

function Invoke-AgentSelfTest {
  $previousConfigPath=$script:ConfigPath
  $previousReceiptDir=$script:ReceiptDir
  $previousOperationsDb=$script:OperationsDb
  $testRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-commander-selftest-"+[guid]::NewGuid().ToString("N"))
  try {
    $script:ReceiptDir=Join-Path $testRoot "receipts"
    $script:OperationsDb=Join-Path $testRoot "operations.sqlite3"
    New-Item -ItemType Directory -Path $script:ReceiptDir -Force | Out-Null
    $cfg=[pscustomobject]@{device_id="selftest";architecture="test";base_url="https://commander.invalid";encrypted_device_token="synthetic-protected-credential"}
    $script:ConfigPath=Join-Path $testRoot "synthetic-device.json"
    $cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:ConfigPath -Encoding UTF8
    # ASK_EVERY_ACTION must deny writes and execution without a local session.
    $savedSelfTestSessionPath=$script:SessionPath
    try {
      $script:SessionPath=Join-Path $testRoot "no-session-selftest.json"
      foreach($unsafe in @(
        @{tool="hara.files.create_directory";payload=[pscustomobject]@{path=(Join-Path $testRoot "must-not-create");parents=$true}},
        @{tool="hara.files.write";payload=[pscustomobject]@{path=(Join-Path $testRoot "must-not-write.txt");content="blocked";mode="rewrite"}},
        @{tool="hara.files.edit";payload=[pscustomobject]@{path=(Join-Path $testRoot "must-not-edit.txt");old_text="x";new_text="y";replace_all=$false}},
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

    $base.request_id="selftest-win-list"; $base.tool_id="hara.files.list"
    $base.payload=[pscustomobject]@{path=$testRoot;depth=1;limit=20;offset=0}
    $directList=Invoke-Tool $cfg ([pscustomobject]$base)
    $listed=$directList.result.stdout | ConvertFrom-Json
    if ([string]$directList.result.function_id -ne "filesystem.list" -or
        @($listed.entries | Where-Object {$_.name -eq "sample.txt"}).Count -ne 1) { throw "SELF_TEST_WINDOWS_LIST_OFFSET_FAILED" }

    $base.request_id="selftest-win-read-many"; $base.tool_id="hara.files.read_many"
    $base.payload=[pscustomobject]@{paths=@($sample,(Join-Path $testRoot "missing.txt"));offset=0;length=2}
    $directMany=Invoke-Tool $cfg ([pscustomobject]$base)
    $manyResult=$directMany.result.stdout | ConvertFrom-Json
    if ([string]$directMany.result.function_id -ne "filesystem.read_many" -or
        [string]$manyResult.overall_status -ne "PARTIAL") { throw "SELF_TEST_WINDOWS_READ_MANY_FAILED" }

    $base.request_id="selftest-win-search"; $base.tool_id="hara.files.search"
    $base.payload=[pscustomobject]@{path=$testRoot;search_type="files";pattern="sample";max_results=5;offset=0}
    $directSearch=Invoke-Tool $cfg ([pscustomobject]$base)
    $searchResult=$directSearch.result.stdout | ConvertFrom-Json
    if ([string]$directSearch.result.function_id -ne "filesystem.search" -or
        [int]$searchResult.count -lt 1) { throw "SELF_TEST_WINDOWS_SEARCH_FAILED" }

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
        enrollment_context=(Get-EnrollmentContext $cfg)
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
    $script:ConfigPath=$previousConfigPath
    $script:ReceiptDir=$previousReceiptDir
    $script:OperationsDb=$previousOperationsDb
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($args.Count -gt 0 -and [string]$args[0] -ceq '--relay-worker') { Start-WindowsRelayWorker $args; exit 0 }
if ($args -contains "--version") { Write-Output $AgentVersion; exit 0 }
if ($args -contains "--self-test") { Invoke-AgentSelfTest; exit 0 }
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
  $scopeCfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  $EnrollmentContext=Initialize-EnrollmentState $scopeCfg
}
if ($args.Count -gt 1 -and [string]$args[0] -eq "history" -and [string]$args[1] -eq "legacy") {
  if($args.Count -gt 4){throw "HISTORY_ARGUMENT_INVALID"}
  $limit=50;$beforeId=0L
  if($args.Count -ge 3 -and -not [int]::TryParse([string]$args[2],[ref]$limit)){throw "HISTORY_ARGUMENT_INVALID"}
  if($args.Count -eq 4 -and -not [long]::TryParse([string]$args[3],[ref]$beforeId)){throw "HISTORY_ARGUMENT_INVALID"}
  Show-LegacyOperatorHistory $limit $beforeId
  exit 0
}
if ($args.Count -gt 0 -and [string]$args[0] -eq "history") {
  if ($args.Count -gt 3) { throw "HISTORY_ARGUMENT_INVALID" }
  [int]$limit=50
  [long]$beforeId=0
  if ($args.Count -ge 2 -and -not [int]::TryParse([string]$args[1],[ref]$limit)) {
    throw "HISTORY_ARGUMENT_INVALID"
  }
  if ($args.Count -ge 3 -and -not [long]::TryParse([string]$args[2],[ref]$beforeId)) {
    throw "HISTORY_ARGUMENT_INVALID"
  }
  Show-OperatorHistory $limit $beforeId
  exit 0
}
if ($args -contains "--session-start" -or ($args.Count -gt 0 -and [string]$args[0] -eq "start")) { Start-ManualOperatorConsole; exit 0 }
if ($args -contains "--session-status" -or ($args.Count -gt 0 -and [string]$args[0] -eq "status")) { Show-OperatorSession; exit 0 }
if ($args -contains "--session-stop" -or ($args.Count -gt 0 -and [string]$args[0] -eq "stop")) {
  Stop-OperatorSession
  Stop-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
  exit 0
}
if ($args.Count -gt 0 -and @("help","--help","-h") -contains [string]$args[0]) {
  Write-Host "Usage: hara-commander [start|status|stop|history [limit [before_id]]|help]"
  exit 0
}
if ($args.Count -gt 0) {
  Write-Host ("HARA_COMMANDER_UNKNOWN_COMMAND="+[string]$args[0])
  Write-Host "Usage: hara-commander [start|status|stop|history [limit [before_id]]|help]"
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

Start-WindowsRelaySupervisor $StartupCfg $PSCommandPath
