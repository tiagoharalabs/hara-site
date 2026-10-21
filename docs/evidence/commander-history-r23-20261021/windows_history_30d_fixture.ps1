$ErrorActionPreference="Stop"
$qa=Join-Path $env:TEMP ("HARA_HISTORY_R23_"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $qa -Force|Out-Null
$script:Root=$qa
$script:OperationsDb=Join-Path $qa "operations.sqlite3"
$script:ConsoleEvents=Join-Path $qa "console-events.jsonl"
$script:ReceiptDir=Join-Path $qa "receipts"
$script:SessionPath=Join-Path $qa "operator-session.json"
$script:AgentTaskName="HARA Commander Agent"
function A([bool]$ok,[string]$label){
 if(-not $ok){throw "R23_FAILED_"+$label}
 Write-Output ("R23_"+$label+"=PASS")
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
  # Only COMMAND events from the rolling 30-day window. Never print
  # raw payload, action_summary, passwords or device credentials.
  Initialize-LocalActivityStore
  $cutoff=[DateTime]::UtcNow.AddDays(-30).ToString("o")
  $columns="event_id,at_utc,event,state,tool_id,function_id,request_id,error_code,receipt_sha256"
  if ($BeforeId -gt 0) {
    $rows=@(Invoke-LocalDbQuery "SELECT $columns FROM activity_events WHERE at_utc >= ? AND tool_id IS NOT NULL AND tool_id != '' AND event_id < ? ORDER BY event_id DESC LIMIT ?" @($cutoff,[long]$BeforeId,[long]($Limit+1)))
  } else {
    $rows=@(Invoke-LocalDbQuery "SELECT $columns FROM activity_events WHERE at_utc >= ? AND tool_id IS NOT NULL AND tool_id != '' ORDER BY event_id DESC LIMIT ?" @($cutoff,[long]($Limit+1)))
  }
  $page=@($rows | Select-Object -First $Limit)
  [array]::Reverse($page)
  Write-Host "HARA_COMMANDER_HISTORY=LOCAL_READ_ONLY"
  Write-Host "HARA_COMMANDER_HISTORY_WINDOW_DAYS=30"
  Write-Host ("HARA_COMMANDER_HISTORY_EVENTS="+$page.Count)
  foreach ($item in $page) {
    Write-Host ("#"+[long]$item.event_id+" "+(Format-ConsoleEvent $item))
  }
  if ($rows.Count -gt $Limit -and $page.Count -gt 0) {
    $oldest=[long]$page[0].event_id
    Write-Host ("HARA_COMMANDER_HISTORY_MORE=hara-commander history "+$Limit+" "+$oldest)
  }
}

function Clear-LocalHistoryData {
  # Called only AFTER explicit UAC-admin verification and local TTY consent.
  # This is separately unit-tested against a completely disposable QA root.
  Initialize-LocalActivityStore
  $counts=@(Invoke-LocalDbQuery "SELECT COUNT(*) AS count FROM activity_events")
  $count=if($counts.Count){[long]$counts[0]["count"]}else{[long]0}
  Invoke-LocalDbExec "DELETE FROM activity_events"
  if(Test-Path -LiteralPath $ConsoleEvents -PathType Leaf){
    if((Get-Item -LiteralPath $ConsoleEvents).Attributes -band [IO.FileAttributes]::ReparsePoint){
      throw "HISTORY_CLEAR_SYMLINK_DENIED"
    }
    [IO.File]::WriteAllText($ConsoleEvents,"",(New-Object System.Text.UTF8Encoding($false)))
  }
  New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
  $record=[ordered]@{
    schema="hara.commander-history-clear-receipt.v1"
    at_utc=[DateTime]::UtcNow.ToString("o")
    old_activity_rows=$count
    audit_receipts_preserved=$true
    device_credentials_modified=$false
  }
  $receiptFile=Join-Path $ReceiptDir ("history-clear-"+[guid]::NewGuid().ToString("N")+".json")
  $record | ConvertTo-Json -Compress | Set-Content -LiteralPath $receiptFile -Encoding UTF8
  Write-ConsoleEvent "HISTORY_CLEARED" $null "ADMIN_CONFIRMED"
  Write-Host "HARA_COMMANDER_HISTORY_CLEAR=PASS"
  Write-Host ("HARA_COMMANDER_HISTORY_EVENTS_CLEARED="+$count)
  Write-Host "HARA_COMMANDER_AUDIT_RECEIPTS_PRESERVED=TRUE"
}

function Clear-LocalActivityHistory {
  $who=[Security.Principal.WindowsIdentity]::GetCurrent()
  $admin=[Security.Principal.WindowsPrincipal]::new($who).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
  if(-not $admin){throw "HISTORY_CLEAR_SUPERUSER_REQUIRED"}
  if(-not [Environment]::UserInteractive -or [Console]::IsInputRedirected){
    throw "HISTORY_CLEAR_LOCAL_TTY_REQUIRED"
  }
  if(Get-OperatorSession){throw "HISTORY_CLEAR_ACTIVE_SESSION_DENIED"}
  $task=Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
  if($task -and [string]$task.State -eq "Running"){throw "HISTORY_CLEAR_AGENT_MUST_BE_STOPPED"}
  Write-Host "Limpeza local do historico (SQLite/JSONL); recibos preservados."
  Write-Host "Encerre antes o Commander na janela pessoal."
  $answer=Read-Host "Digite LIMPAR HISTORICO LOCAL para confirmar"
  if($answer -cne "LIMPAR HISTORICO LOCAL"){throw "HISTORY_CLEAR_CONFIRMATION_DENIED"}
  Clear-LocalHistoryData
}


try {
 Initialize-LocalActivityStore
 $now=[DateTime]::UtcNow
 foreach($age in @(-31,-29,-2,0)){
   $when=$now.AddDays($age).ToString("o")
   Invoke-LocalDbExec "INSERT INTO activity_events(at_utc,event,state,tool_id,function_id,request_id,action_summary) VALUES (?,?,?,?,?,?,?)" @(
     $when,"COMPLETED","PASS","hara.process.run","process.run",("qa_"+$age),"SYNTHETIC_SUPER_SECRET_NEVER_DISPLAY")
 }
 Invoke-LocalDbExec "INSERT INTO activity_events(at_utc,event,state,tool_id) VALUES (?,?,?,?)" @($now.ToString("o"),"HEARTBEAT","PASS",$null)
 $view=(Show-OperatorHistory 10 0 6>&1|Out-String)
 A ($view.Contains("HARA_COMMANDER_HISTORY_WINDOW_DAYS=30")) "WINDOW_30_DAYS"
 A ($view.Contains("HARA_COMMANDER_HISTORY_EVENTS=3")) "RECENT_THREE_EVENTS"
 A (-not $view.Contains("qa_-31")) "OLD_31_DAYS_NOT_VISIBLE"
 A (-not $view.Contains("HEARTBEAT")) "CONTROL_EVENTS_NOT_LISTED"
 A (-not $view.Contains("SYNTHETIC_SUPER_SECRET_NEVER_DISPLAY")) "PRIVATE_ACTION_SUMMARY_REDACTED"
 $limited=(Show-OperatorHistory 1 0 6>&1|Out-String)
 A ($limited.Contains("HARA_COMMANDER_HISTORY_EVENTS=1")) "PAGINATION_BOUND"
 A ($limited.Contains("HARA_COMMANDER_HISTORY_MORE=hara-commander history 1 ")) "OLDER_PAGE_OFFERED"
 $latest=@(Invoke-LocalDbQuery "SELECT event_id FROM activity_events WHERE tool_id IS NOT NULL ORDER BY event_id DESC LIMIT 1")
 $id=[long]$latest[0]["event_id"]
 $older=(Show-OperatorHistory 2 $id 6>&1|Out-String)
 A ($older.Contains("HARA_COMMANDER_HISTORY_EVENTS=2")) "PREVIOUS_PAGE"
 New-Item -ItemType Directory -Path $ReceiptDir -Force|Out-Null
 [IO.File]::WriteAllText((Join-Path $ReceiptDir 'audit-preexisting.json'),'{"receipt":"PRESERVE"}')
 Write-ConsoleEvent "SESSION_OPEN" $null "AUTHORIZED"
 $cursor=Get-ConsoleStreamCursor
 A ($cursor -gt 0 -and @(Read-NewConsoleEvents ([ref]$cursor)).Count -eq 0) "STARTS_WITH_EMPTY_CONSOLE"
 Write-ConsoleEvent "AFTER_START" ([pscustomobject]@{tool_id="hara.ping";request_id="qa-live"}) "PASS"
 $live=@(Read-NewConsoleEvents ([ref]$cursor))
 A ($live.Count -eq 1 -and $live[0].event -eq "AFTER_START") "LIVE_ONLY_NEW_EVENTS"
 $clean=(Clear-LocalHistoryData 6>&1 | Out-String)
 A ($clean.Contains("HARA_COMMANDER_HISTORY_CLEAR=PASS")) "QA_CLEAR_ON_DISPOSABLE_DIR"
 A ((Get-Content -Raw (Join-Path $ReceiptDir 'audit-preexisting.json')).Contains("PRESERVE")) "IMMUTABLE_AUDIT_FILE_UNTOUCHED"
 $receipt=@(Get-ChildItem -LiteralPath $ReceiptDir -Filter 'history-clear-*.json')
 A ($receipt.Count -eq 1) "ADMIN_CLEAR_RECEIPT_CREATED"
 $last=@(Invoke-LocalDbQuery "SELECT event FROM activity_events")
 A ($last.Count -eq 1 -and $last[0]["event"] -eq "HISTORY_CLEARED") "CLEAR_LEAVES_AUDIT_MARKER"
 $empty=(Show-OperatorHistory 50 0 6>&1|Out-String)
 A ($empty.Contains("HARA_COMMANDER_HISTORY_EVENTS=0")) "NO_COMMAND_HISTORY_AFTER_CLEAR"
 A ((Get-Content -LiteralPath $ConsoleEvents).Count -eq 1) "OLD_JSONL_CLEARED_WITH_MARKER"
 Write-Output "R23_WINDOWS_HISTORY_30D_ADMIN_FIXTURE=PASS"
} finally {
 Remove-Item -LiteralPath $qa -Recurse -Force -ErrorAction SilentlyContinue
}
