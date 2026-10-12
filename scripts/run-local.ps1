<#
.SYNOPSIS
  Run the FHIR JMeter plan in non-GUI mode, build the HTML report, then apply the threshold gate.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1                  # smoke vs public HAPI
  powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1 -Target local -Profile load
#>
param(
  [ValidateSet('smoke', 'load', 'stress', 'spike')] [string] $Profile = 'smoke',
  [ValidateSet('public', 'local')] [string] $Target = 'public',
  [string] $JMeterHome = "$env:USERPROFILE\tools\apache-jmeter-5.6.3"
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

# hapi.fhir.org is a shared community server. Smoke-level traffic only; real load goes to your own server.
if ($Target -eq 'public' -and $Profile -ne 'smoke') {
  throw "Refusing to run '$Profile' against the public HAPI server. Use -Target local (your own HAPI) or CI."
}
$targetArgs = if ($Target -eq 'public') {
  @('-Jprotocol=https', '-Jhost=hapi.fhir.org', '-Jport=443', '-JbasePath=/baseR4')
} else {
  @('-Jprotocol=http', '-Jhost=localhost', '-Jport=8080', '-JbasePath=/fhir')
}

$jmeter = Join-Path $JMeterHome 'bin\jmeter.bat'
if (-not (Test-Path $jmeter)) { throw "JMeter not found at $jmeter. Pass -JMeterHome." }

$out = Join-Path $root "results\$Profile-$Target"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }   # -e -o needs an empty report folder
New-Item -ItemType Directory -Force $out | Out-Null

& $jmeter -n `
  -t (Join-Path $root 'test-plans\fhir-patient-journey.jmx') `
  -q (Join-Path $root "profiles\$Profile.properties") `
  @targetArgs `
  -l (Join-Path $out 'results.jtl') `
  -j (Join-Path $out 'jmeter.log') `
  -e -o (Join-Path $out 'report')
if ($LASTEXITCODE -ne 0) { throw "JMeter exited with $LASTEXITCODE. See $out\jmeter.log" }

python (Join-Path $root 'scripts\check_thresholds.py') `
  --stats (Join-Path $out 'report\statistics.json') `
  --thresholds (Join-Path $root 'scripts\thresholds.json')
$gate = $LASTEXITCODE
Write-Host "HTML report: $out\report\index.html"
exit $gate
