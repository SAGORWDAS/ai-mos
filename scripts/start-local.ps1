param([string]$PythonPath = '', [switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runRoot = Join-Path $projectRoot '.run'
$venvRoot = Join-Path $projectRoot '.venv'
$pythonExe = Join-Path $venvRoot 'Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." }
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    if ($PythonPath) {
        & $PythonPath -m venv $venvRoot
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $venvRoot
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Install Python 3.12+, or pass -PythonPath to its executable.' }
        & $pythonCommand.Source -m venv $venvRoot
    }
    Assert-Exit 'Creating the Python environment'
}
$nodeCommand = Get-Command node -ErrorAction Stop
$npmCommand = Get-Command npm.cmd -ErrorAction Stop
$lockPath = Join-Path $projectRoot 'backend\requirements-dev.lock'
$lockHash = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash
$installedStamp = Join-Path $runRoot 'python-lock.hash'
if (-not (Test-Path $installedStamp) -or (Get-Content $installedStamp -Raw).Trim() -ne $lockHash) {
    & $pythonExe -m pip install -r $lockPath
    Assert-Exit 'Installing backend dependencies'
    Set-Content -LiteralPath $installedStamp -Value $lockHash
}
Push-Location (Join-Path $projectRoot 'frontend')
try {
    $webHash = (Get-FileHash package-lock.json -Algorithm SHA256).Hash
    $webStamp = Join-Path $runRoot 'web-lock.hash'
    if (-not (Test-Path node_modules) -or -not (Test-Path $webStamp) -or (Get-Content $webStamp -Raw).Trim() -ne $webHash) {
        & $npmCommand.Source ci --no-audit --no-fund
        Assert-Exit 'Installing frontend dependencies'
        Set-Content -LiteralPath $webStamp -Value $webHash
    }
    & $npmCommand.Source run build
    Assert-Exit 'Building the frontend'
} finally { Pop-Location }
if ($PrepareOnly) { Write-Host 'Dependencies installed and build verified.'; exit 0 }

foreach ($port in @(8000, 3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing app before starting another instance."
    }
}
$priorDatabase = $env:DATABASE_URL
$priorEnvironment = $env:APP_ENV
$priorBackend = $env:BACKEND_URL
$priorEncryptionKey = $env:TOKEN_ENCRYPTION_KEY
$schemaHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'backend\app\schema.py') -Algorithm SHA256).Hash
$schemaStamp = Join-Path $runRoot 'schema.hash'
$localDatabase = Join-Path $runRoot 'local.db'
if ((Test-Path -LiteralPath $localDatabase) -and (-not (Test-Path -LiteralPath $schemaStamp) -or (Get-Content -LiteralPath $schemaStamp -Raw).Trim() -ne $schemaHash)) {
    $backupPath = Join-Path $runRoot ('backups\before-upgrade-' + [guid]::NewGuid().ToString('N') + '.db')
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $pythonExe -m app.backup backup $localDatabase $backupPath | Out-Null
        Assert-Exit 'Backing up the existing database before schema upgrade'
    } finally { Pop-Location }
}
try {
    $keyFile = Join-Path $runRoot 'encryption.key'
    if (-not (Test-Path -LiteralPath $keyFile)) {
        $generatedKey = & $pythonExe -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
        Assert-Exit 'Generating the local credential encryption key'
        Set-Content -LiteralPath $keyFile -Value $generatedKey -Encoding ascii
    }
    $env:TOKEN_ENCRYPTION_KEY = (Get-Content -LiteralPath $keyFile -Raw).Trim()
    $env:DATABASE_URL = 'sqlite+aiosqlite:///' + ((Join-Path $runRoot 'local.db') -replace '\\', '/')
    $env:APP_ENV = 'development'
    $env:BACKEND_URL = 'http://127.0.0.1:8000'
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runRoot 'api.log') -RedirectStandardError (Join-Path $runRoot 'api-error.log')
    $nextScript = Join-Path $projectRoot 'frontend\node_modules\next\dist\bin\next'
    $webProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList @('"' + $nextScript + '"','start','-H','127.0.0.1','-p','3000') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runRoot 'web.log') -RedirectStandardError (Join-Path $runRoot 'web-error.log')
    @{api=$apiProcess.Id; web=$webProcess.Id} | ConvertTo-Json | Set-Content (Join-Path $runRoot 'processes.json')
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $apiHealth = Invoke-RestMethod 'http://127.0.0.1:8000/healthz' -TimeoutSec 2
            $webHealth = Invoke-WebRequest 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 2
            if ($apiHealth.status -eq 'ok' -and $webHealth.StatusCode -eq 200) { $ready=$true; break }
        } catch { }
    }
    if (-not $ready) { throw "App did not become healthy. Check $runRoot logs and run Stop-AI-MOS.cmd." }
    Set-Content -LiteralPath $schemaStamp -Value $schemaHash
    Write-Host 'AI-MOS is ready: http://localhost:3000'
    Write-Host 'Use Stop-AI-MOS.cmd to stop it. Your data remains in .run/local.db.'
} finally {
    $env:DATABASE_URL = $priorDatabase
    $env:APP_ENV = $priorEnvironment
    $env:BACKEND_URL = $priorBackend
    $env:TOKEN_ENCRYPTION_KEY = $priorEncryptionKey
}
