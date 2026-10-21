param(
  [Parameter(Mandatory=$true)][string]$CandidatePath,
  [Parameter(Mandatory=$true)][string]$QaRoot
)
$ErrorActionPreference = "Stop"

# Parse the complete unsigned candidate, then evaluate only the intent helper.
# This never starts the installer, Agent, scheduled task, or any HTTP request.
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($CandidatePath,[ref]$tokens,[ref]$errors)
if ($errors.Count -ne 0) { throw "WINDOWS_R13_CANDIDATE_PARSE_FAILED" }
Write-Host "WINDOWS_R13_CANDIDATE_PARSE=PASS"
$definition=$ast.Find({param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
  $node.Name -ceq "Get-EnrollmentIntentToken"
},$true)
if (-not $definition) { throw "WINDOWS_R13_INTENT_HELPER_MISSING" }
Invoke-Expression $definition.Extent.Text

$BaseUrl="https://qa.invalid"
$Root=Join-Path $QaRoot ("R13IntentProbe-"+[guid]::NewGuid().ToString("N"))
$EnrollmentIntent=Join-Path $Root "enrollment-intent.json"
try {
  $first=Get-EnrollmentIntentToken "QA_SYNTHETIC_PAIRING_A"
  if ($first -cnotmatch '^[A-Za-z0-9_-]{64}$') { throw "WINDOWS_R13_SECRET_FORMAT_FAILED" }
  $raw=Get-Content -Raw -LiteralPath $EnrollmentIntent
  if ($raw.Contains($first) -or $raw.Contains("QA_SYNTHETIC_PAIRING_A")) {
    throw "WINDOWS_R13_SECRET_PLAINTEXT_LEAK"
  }
  $stored=$raw | ConvertFrom-Json
  if ([string]$stored.base_url -cne $BaseUrl -or
      [string]$stored.pairing_sha256 -cnotmatch '^[0-9a-f]{64}$') {
    throw "WINDOWS_R13_INTENT_BINDING_FAILED"
  }
  $second=Get-EnrollmentIntentToken "QA_SYNTHETIC_PAIRING_A"
  if ($second -cne $first) { throw "WINDOWS_R13_RETRY_SECRET_CHANGED" }
  try { Get-EnrollmentIntentToken "QA_SYNTHETIC_PAIRING_B" | Out-Null; throw "WINDOWS_R13_PAIRING_MISMATCH_ACCEPTED" }
  catch {
    if ($_.Exception.Message -ne "ENROLLMENT_INTENT_PAIRING_MISMATCH") { throw }
  }
  $BaseUrl="https://other.invalid"
  try { Get-EnrollmentIntentToken "QA_SYNTHETIC_PAIRING_A" | Out-Null; throw "WINDOWS_R13_ORIGIN_MISMATCH_ACCEPTED" }
  catch {
    if ($_.Exception.Message -ne "ENROLLMENT_INTENT_PAIRING_MISMATCH") { throw }
  }
  Write-Host "WINDOWS_R13_INTENT_DPAPI_RETRY_AND_BINDING=PASS"
} finally {
  if (Test-Path -LiteralPath $Root) { Remove-Item -LiteralPath $Root -Recurse -Force }
}
