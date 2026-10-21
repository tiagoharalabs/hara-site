$ErrorActionPreference="Stop"
$qa=Join-Path $env:TEMP ("HARA_R22_HISTORY_QA_"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $qa -Force | Out-Null
$ConsoleEvents=Join-Path $qa "events.jsonl"
function Assert-R22([bool]$Condition,[string]$Label){
 if(-not $Condition){throw ("R22_FAILED_"+$Label)}
 Write-Output ("R22_"+$Label+"=PASS")
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


try {
  $old=[ordered]@{schema="hara.commander-console-event.v1";at_utc="2026-10-21T00:00:00Z";event="OLD_EVENT";state="OLD"}
  $old | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConsoleEvents -Encoding UTF8
  $before=[System.IO.File]::ReadAllBytes($ConsoleEvents)
  $cursor=Get-ConsoleStreamCursor
  Assert-R22 ($cursor -eq $before.LongLength) "INITIAL_CURSOR_AT_EOF"
  $noOld=@(Read-NewConsoleEvents ([ref]$cursor))
  Assert-R22 ($noOld.Count -eq 0) "OLD_EVENTS_NOT_REPLAYED"
  $new=[ordered]@{schema="hara.commander-console-event.v1";at_utc="2026-10-21T18:30:00Z";event="FRESH_EVENT";state="AUTHORIZED"}
  Add-Content -LiteralPath $ConsoleEvents -Value ($new | ConvertTo-Json -Compress) -Encoding UTF8
  $fresh=@(Read-NewConsoleEvents ([ref]$cursor))
  Assert-R22 ($fresh.Count -eq 1 -and $fresh[0].event -eq "FRESH_EVENT") "ONLY_FRESH_EVENTS"
  $empty=@(Read-NewConsoleEvents ([ref]$cursor))
  Assert-R22 ($empty.Count -eq 0) "NO_DUPLICATE_AFTER_CURSOR"
  $partial='{"schema":"hara.commander-console-event.v1","at_utc":"2026-10-21T18:31:00Z","event":"PARTIAL_EVENT","state":"OK"}'
  [System.IO.File]::AppendAllText($ConsoleEvents,$partial,(New-Object System.Text.UTF8Encoding($false)))
  $blocked=@(Read-NewConsoleEvents ([ref]$cursor))
  Assert-R22 ($blocked.Count -eq 0) "PARTIAL_JSONL_UNTIL_NEWLINE"
  [System.IO.File]::AppendAllText($ConsoleEvents,[Environment]::NewLine,(New-Object System.Text.UTF8Encoding($false)))
  $complete=@(Read-NewConsoleEvents ([ref]$cursor))
  Assert-R22 ($complete.Count -eq 1 -and $complete[0].event -eq "PARTIAL_EVENT") "COMPLETE_EVENT_AFTER_NEWLINE"
  $final=@(Get-Content -LiteralPath $ConsoleEvents)
  Assert-R22 ($final.Count -eq 3 -and (Test-Path -LiteralPath $ConsoleEvents)) "HISTORY_FILE_UNCHANGED_AND_PRESERVED"
  function Initialize-LocalActivityStore { }
  $script:r22Events=@(
    [pscustomobject]@{event_id=105;event="NEW_105";at_utc="2026-10-21T18:00:00Z";state="OK";tool_id="hara.ping";function_id=$null;request_id=$null;error_code=$null;receipt_sha256=$null;action_summary="SYNTHETIC_PRIVATE_MARKER"},
    [pscustomobject]@{event_id=104;event="NEW_104";at_utc="2026-10-21T17:00:00Z";state="OK";tool_id="hara.ping";function_id=$null;request_id=$null;error_code=$null;receipt_sha256=$null;action_summary="SYNTHETIC_PRIVATE_MARKER"},
    [pscustomobject]@{event_id=103;event="OLD_103";at_utc="2026-10-21T16:00:00Z";state="OK";tool_id="hara.ping";function_id=$null;request_id=$null;error_code=$null;receipt_sha256=$null;action_summary="SYNTHETIC_PRIVATE_MARKER"},
    [pscustomobject]@{event_id=102;event="OLD_102";at_utc="2026-10-21T15:00:00Z";state="OK";tool_id="hara.ping";function_id=$null;request_id=$null;error_code=$null;receipt_sha256=$null;action_summary="SYNTHETIC_PRIVATE_MARKER"}
  )
  function Invoke-LocalDbQuery([string]$Sql,[object[]]$Values=@()) {
    $data=@($script:r22Events | Sort-Object -Property event_id -Descending)
    if ($Sql -match 'event_id <') { $data=@($data | Where-Object { [long]$_.event_id -lt [long]$Values[0] });$limit=[int]$Values[1] }
    else {$limit=[int]$Values[0]}
    return @($data | Select-Object -First $limit)
  }
  $history=(Show-OperatorHistory 2 0 6>&1 | Out-String)
  Assert-R22 ($history.Contains("NEW_105") -and $history.Contains("NEW_104")) "HISTORY_OPTIN_LAST_TWO"
  Assert-R22 (-not $history.Contains("OLD_103")) "HISTORY_PAGE_LIMIT"
  Assert-R22 ($history.Contains("hara-commander history 2 104")) "HISTORY_NEXT_PAGE_CURSOR"
  $page2=(Show-OperatorHistory 2 104 6>&1 | Out-String)
  Assert-R22 ($page2.Contains("OLD_103") -and $page2.Contains("OLD_102")) "HISTORY_PAGINATED_BACKWARD"
  Assert-R22 (-not $history.Contains("SYNTHETIC_PRIVATE_MARKER") -and -not $page2.Contains("SYNTHETIC_PRIVATE_MARKER")) "HISTORY_PRIVATE_SUMMARY_NOT_SHOWN"
  Assert-R22 (($before.LongLength -lt ([System.IO.File]::ReadAllBytes($ConsoleEvents)).LongLength)) "RETAINED_HISTORY_GROWTH"
  Write-Output "R22_LIVE_WINDOWS_HISTORY_FIXTURE=PASS"
} finally { Remove-Item -LiteralPath $qa -Recurse -Force -ErrorAction SilentlyContinue }
