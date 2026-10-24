param(
  [Parameter(Mandatory=$true)][string]$AgentPath,
  [string]$ReportPath
)
$ErrorActionPreference = "Stop"
$checks = New-Object System.Collections.Generic.List[object]
$temporaryRoot = Join-Path $env:TEMP ("hara-utf8-fixture-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

function Check([string]$Name,[bool]$Passed) {
  $checks.Add([ordered]@{name=$Name;passed=$Passed}) | Out-Null
  if (-not $Passed) { throw ("UTF8_FIXTURE_FAILED:"+$Name) }
}
function Byte-Sha256([byte[]]$Bytes) {
  $algorithm=[Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace("-","").ToLowerInvariant() }
  finally { $algorithm.Dispose() }
}
# This guard belongs only to the isolated filesystem fixture; no Agent session,
# config, credentials, enrollment, or consent IPC is read or changed.
function Assert-StarterMutationAuthorized($Cfg,$Call) {
  if (-not $Cfg.fixture -or [string]$Call.fixture -cne "UTF8_ISOLATED_FILE") {
    throw "FIXTURE_AUTHORIZATION_DENIED"
  }
}
$fixtureCode=@"
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;

public sealed class HaraUtf8HttpFixture : IDisposable {
  readonly TcpListener listener;
  readonly byte[] response;
  readonly string responseType;
  readonly Task task;
  public readonly int Port;
  public byte[] RequestBody;
  public string RequestContentType;
  public string RequestAuthorization;

  public HaraUtf8HttpFixture(byte[] body,string contentType) {
    response=body; responseType=contentType;
    listener=new TcpListener(IPAddress.Loopback,0);
    listener.Start();
    Port=((IPEndPoint)listener.LocalEndpoint).Port;
    task=Task.Run((Action)Serve);
  }
  void Serve() {
    using(var client=listener.AcceptTcpClient())
    using(var stream=client.GetStream()) {
      stream.ReadTimeout=10000; stream.WriteTimeout=10000;
      var head=new MemoryStream();
      int current=0;
      while (head.Length<65536) {
        current=stream.ReadByte();
        if(current<0) throw new EndOfStreamException();
        head.WriteByte((byte)current);
        var n=head.Length;
        var a=head.GetBuffer();
        if(n>=4 && a[n-4]==13 && a[n-3]==10 && a[n-2]==13 && a[n-1]==10) break;
      }
      var headers=Encoding.ASCII.GetString(head.ToArray()).Split(new[]{"\r\n"},StringSplitOptions.None);
      int length=0; bool expect=false;
      foreach(var h in headers) {
        var colon=h.IndexOf(':');
        if(colon<0) continue;
        var name=h.Substring(0,colon).Trim();
        var value=h.Substring(colon+1).Trim();
        if(name.Equals("Content-Length",StringComparison.OrdinalIgnoreCase)) length=int.Parse(value);
        if(name.Equals("Content-Type",StringComparison.OrdinalIgnoreCase)) RequestContentType=value;
        if(name.Equals("Authorization",StringComparison.OrdinalIgnoreCase)) RequestAuthorization=value;
        if(name.Equals("Expect",StringComparison.OrdinalIgnoreCase) && value.IndexOf("100-continue",StringComparison.OrdinalIgnoreCase)>=0) expect=true;
      }
      if(length<0 || length>1048576) throw new InvalidDataException("REQUEST_LIMIT");
      if(expect) {
        var interim=Encoding.ASCII.GetBytes("HTTP/1.1 100 Continue\r\n\r\n");
        stream.Write(interim,0,interim.Length); stream.Flush();
      }
      RequestBody=new byte[length];
      int consumed=0;
      while(consumed<length) {
        var read=stream.Read(RequestBody,consumed,length-consumed);
        if(read==0) throw new EndOfStreamException();
        consumed+=read;
      }
      var responseHead=Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: "+responseType+
        "\r\nContent-Length: "+response.Length+"\r\nConnection: close\r\n\r\n");
      stream.Write(responseHead,0,responseHead.Length);
      stream.Write(response,0,response.Length); stream.Flush();
    }
  }
  public void Wait() {
    if(!task.Wait(12000)) throw new TimeoutException("FIXTURE_HTTP_TIMEOUT");
  }
  public void Dispose() { listener.Stop(); }
}
"@
if (-not ("HaraUtf8HttpFixture" -as [type])) { Add-Type -TypeDefinition $fixtureCode }
$agentBytes=[IO.File]::ReadAllBytes($AgentPath)
$agentSource=[Text.Encoding]::UTF8.GetString($agentBytes)
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($agentSource,[ref]$tokens,[ref]$parseErrors)
$failure=$null
try {
  Check "native_windows_powershell_51" ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1)
  Check "source_parser_clean" ($parseErrors.Count -eq 0)
  # Dot-source extracted functions in this scope, without invoking Agent startup.
  foreach($name in @("Send-Json","Write-WindowsTextFile")) {
    $found=@($ast.FindAll({
      param($Node)
      $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq $name
    },$true))
    Check ("source_function_"+$name) ($found.Count -eq 1)
    . ([scriptblock]::Create($found[0].Extent.Text))
  }
  $cedilla=[char]0x00E7; $tilde=[char]0x00E3
  # Preserve exact LF input independent of OS line endings and source encoding.
  $latin="H.A.R.A. Commander 0.3.49"+[char]10+"Homologa"+$cedilla+$tilde+"o Windows: a"+$cedilla+$tilde+"o aprovada."+[char]10+"Etapa: escrita inicial"+[char]10
  $emoji=[char]::ConvertFromUtf32(0x1F680)
  $cjk=[string]([char]0x65E5)+[char]0x672C
  $samples=@(
    [ordered]@{name="ascii";content="plain ASCII"+[char]10+"exact LF"+[char]10},
    [ordered]@{name="accents";content=$latin},
    [ordered]@{name="emoji_cjk";content="UTF8 "+$emoji+" "+$cjk+" "+[char]0x20AC+[char]10}
  )
  foreach($sample in $samples) {
    $name=[string]$sample.name
    $text=[string]$sample.content
    $expectedFileBytes=[Text.Encoding]::UTF8.GetBytes($text)
    $payload=[ordered]@{arguments=[ordered]@{content=$text}}
    $expectedJson=$payload | ConvertTo-Json -Depth 10 -Compress
    $expectedRequestBytes=[Text.Encoding]::UTF8.GetBytes($expectedJson)
    # Server response is generated from the independent expected corpus, never
    # echoed from the received body; inverse corruption cannot pass this test.
    $server=New-Object HaraUtf8HttpFixture -ArgumentList @($expectedRequestBytes,"application/json; charset=utf-8")
    try {
      $received=Send-Json ("http://127.0.0.1:"+$server.Port+"/utf8") "FIXTURE_ONLY" $payload 10
      $server.Wait()
      Check ($name+"_request_content_type") ($server.RequestContentType -match "^application/json;\s*charset=utf-8$")
      Check ($name+"_request_body_exact_utf8_bytes") ([Convert]::ToBase64String($server.RequestBody) -ceq [Convert]::ToBase64String($expectedRequestBytes))
      Check ($name+"_request_no_bom") (-not ($server.RequestBody.Length -ge 3 -and $server.RequestBody[0] -eq 239 -and $server.RequestBody[1] -eq 187 -and $server.RequestBody[2] -eq 191))
      Check ($name+"_response_unicode_exact") ([string]$received.arguments.content -ceq $text)
      $file=Join-Path $temporaryRoot ($name+".txt")
      $write=Write-WindowsTextFile @{fixture=$true} @{fixture="UTF8_ISOLATED_FILE"} $file ([string]$received.arguments.content)
      $actual=[IO.File]::ReadAllBytes($file)
      Check ($name+"_file_exact_bytes") ([Convert]::ToBase64String($actual) -ceq [Convert]::ToBase64String($expectedFileBytes))
      Check ($name+"_file_sha256_exact") ((Byte-Sha256 $actual) -ceq (Byte-Sha256 $expectedFileBytes))
      Check ($name+"_bytes_written_exact") ([long]$write.bytes_written -eq $expectedFileBytes.Length)
      if ($name -eq "accents") {
        Check "original_repro_89_bytes" ($actual.Length -eq 89)
        Check "original_repro_expected_sha" ((Byte-Sha256 $actual) -ceq "d2db30144965bb9c1e6fb0674af17e2099908f4d115f52b137face8f64a98655")
      }
    } finally { $server.Dispose() }
  }
  # Control reproduces the actual .49 failure using real Windows PS5.1 HTTP
  # decoding with a charset-less UTF8 JSON response.
  $payload=[ordered]@{arguments=[ordered]@{content=$latin}}
  $json=$payload | ConvertTo-Json -Depth 10 -Compress
  $jsonBytes=[Text.Encoding]::UTF8.GetBytes($json)
  $server=New-Object HaraUtf8HttpFixture -ArgumentList @($jsonBytes,"application/json")
  try {
    $legacy=Invoke-RestMethod -Uri ("http://127.0.0.1:"+$server.Port+"/legacy") -Method Post -ContentType "application/json; charset=utf-8" -Body $jsonBytes -TimeoutSec 10 -MaximumRedirection 0
    $server.Wait()
    $legacyBytes=[Text.Encoding]::UTF8.GetBytes([string]$legacy.arguments.content)
    Check "ps51_charsetless_response_reproduces_97_bytes" ($legacyBytes.Length -eq 97)
    Check "ps51_charsetless_response_reproduces_actual_sha" ((Byte-Sha256 $legacyBytes) -ceq "426adfb6fb5153082316592e27f758dfb5afa29c5767a517193b850bcc58b6c1")
    Check "ps51_charsetless_response_is_not_expected_text" ([string]$legacy.arguments.content -cne $latin)
  } finally { $server.Dispose() }
} catch { $failure=$_.Exception.Message }
finally {
  Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
  $report=[ordered]@{
    schema="hara.commander.windows-utf8-http-fixture.v1"
    state=$(if ($failure) {"FAIL"} else {"PASS"})
    powershell_version=$PSVersionTable.PSVersion.ToString()
    source_sha256=(Byte-Sha256 $agentBytes)
    source_path=$AgentPath
    assertions=$checks.Count
    checks=@($checks.ToArray())
    error=$failure
    agent_entrypoint_executed=$false
    installed_agent_modified=$false
    session_or_consent_state_modified=$false
    http_scope="LOOPBACK_ONLY"
    temporary_files_removed=(-not (Test-Path -LiteralPath $temporaryRoot))
  }
  $reportJson=$report | ConvertTo-Json -Depth 6 -Compress
  if ($ReportPath) { [IO.File]::WriteAllText($ReportPath,$reportJson,(New-Object Text.UTF8Encoding($false))) }
  Write-Output $reportJson
}
if ($failure) { throw $failure }
