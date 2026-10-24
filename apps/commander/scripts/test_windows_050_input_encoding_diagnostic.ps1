$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$p='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-050-rc-r2\agent\windows.ps1'
$t=$null;$e=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($p,[ref]$t,[ref]$e)
$d=$ast.Find({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Initialize-WindowsManagedProcessType'},$true)
. ([scriptblock]::Create($d.Extent.Text));Initialize-WindowsManagedProcessType
$word='Ol'+[char]0xE1+' '+[char]::ConvertFromUtf32(0x1F680)+' '+[char]0x65E5+[char]0x672C+[char]0x8A9E
$cmd="Write-Output '"+$word+"'; exit 0"
$rows=@()
foreach($kind in @('default','utf8raw')){
 $s=New-Object HaraWindowsProcessSession -ArgumentList @('ENCODING_DIAGNOSTIC',$env:TEMP,"Write-Output ('INPUT_ENCODING='+[Console]::InputEncoding.WebName)")
 try {
  $f=$s.GetType().GetField('Child',([Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance));$c=$f.GetValue($s)
  $enc=$c.StandardInput.Encoding.WebName
  if($kind -ceq 'default'){$s.Input($cmd)}else{$b=[Text.Encoding]::UTF8.GetBytes($cmd+[char]10);$c.StandardInput.BaseStream.Write($b,0,$b.Length);$c.StandardInput.BaseStream.Flush()}
  $end=[DateTime]::UtcNow.AddSeconds(8)
  do{$x=$s.Snapshot(0,200,200);Start-Sleep -Milliseconds 25}while(([string]$x.state -cne 'EXITED' -or $x.output_pending) -and [DateTime]::UtcNow -lt $end)
  $rows+=[pscustomobject]@{kind=$kind;writer_encoding=$enc;state=$x.state;exit=$x.exit_code;text_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$x.text));expected_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($word))}
 }finally{$s.Dispose()}
}
[pscustomobject]@{rows=$rows;parent_input=[Console]::InputEncoding.WebName;installed_agent_touched=$false}|ConvertTo-Json -Depth 5 -Compress
