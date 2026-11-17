$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot '.run\processes.json'
if (-not (Test-Path -LiteralPath $processFile)) { Write-Host 'No launcher-managed processes found.'; exit 0 }
$record = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
foreach ($service in @('api','web')) {
    $processId = $record.$service
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and $process.CommandLine.Contains($projectRoot)) {
        Stop-Process -Id $processId -ErrorAction Stop
        Write-Host "Stopped $service."
    } elseif ($process) {
        Write-Warning "Skipped reused process ID $processId because it does not belong to this project."
    }
}
Remove-Item -LiteralPath $processFile
Write-Host 'Stopped. Your database has been preserved.'
