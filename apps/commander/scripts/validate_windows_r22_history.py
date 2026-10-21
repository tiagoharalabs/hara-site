#!/usr/bin/env python3
"""Fail closed on loss of the R22 Windows opt-in local activity UX contract."""
import hashlib,json,re
from pathlib import Path
root=Path(__file__).resolve().parents[3]
src=(root/"apps/commander/candidate/windows_agent_055.ps1").read_text()
assert src.count('$AgentVersion = "0.3.55"')==1
assert "function Get-ConsoleStreamCursor {" in src
assert "function Read-NewConsoleEvents([ref]$Cursor) {" in src
assert "function Show-OperatorHistory([int]$Limit=50,[long]$BeforeId=0) {" in src
assert '$eventCursor=Get-ConsoleStreamCursor' in src
assert 'Read-NewConsoleEvents ([ref]$eventCursor)' in src
assert "    $seen=0" not in src
assert "Get-Content -LiteralPath $ConsoleEvents)" not in src[src.index("function Start-OperatorConsole("):src.index("function Stop-OperatorSession {")]
assert 'if ($args.Count -gt 0 -and [string]$args[0] -eq "history")' in src
assert "HARA_COMMANDER_HISTORY_MORE=hara-commander history " in src
assert '"SELECT $columns FROM activity_events WHERE event_id < ? ORDER BY event_id DESC LIMIT ?"' in src
assert 'action_summary' not in src[src.index('function Show-OperatorHistory('):src.index('function Start-ManualOperatorConsole {')].split('$columns=')[1].split('\n')[0]
r={
 "schema":"hara.commander.windows-history-optin.r22.v1",
 "candidate_version":"0.3.55",
 "source_sha256":hashlib.sha256(src.encode()).hexdigest(),
 "behavior":"LIVE_FROM_FILE_EOF_HISTORY_SQLITE_ON_DEMAND",
 "startup_replay_full_jsonl":False,
 "incremental_read_bytes_max":131072,
 "history_default_limit":50,"history_limit_max":200,
 "history_read_only":True,"secret_fields_in_history":False,
 "installed_agent_changed":False,"official_signature_created":False,
}
print(json.dumps(r,indent=2))
