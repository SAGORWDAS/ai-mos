$ErrorActionPreference = "Continue"
$script:fail = 0

function Ok($m)   { Write-Host "  [ ok ]   $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "  [ fail ] $m" -ForegroundColor Red; $script:fail = $script:fail + 1 }
function Warn($m) { Write-Host "  [ warn ] $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "AI-MOS - local prerequisites"
Write-Host ""

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
  $ver = & docker --version
  Ok "docker: $ver"

  & docker info --format "{{.ServerVersion}}" 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Ok "docker engine is running"
  } else {
    Bad "docker installed but the engine is not running - start Docker Desktop"
  }

  & docker compose version 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Ok "docker compose plugin available"
  } else {
    Bad "docker compose plugin missing"
  }
} else {
  Bad "docker not installed - winget install --id Docker.DockerDesktop -e"
}

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and ($py.Source -notlike "*WindowsApps*")) {
  $pv = & python --version
  Ok "python: $pv"
} else {
  Warn "python not on PATH - only needed for host-side pytest or ruff"
}

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
  $nv = & node -v
  Ok "node: $nv"
} else {
  Warn "node not on PATH - only needed for host-side frontend work"
}

if (Test-Path ".env") {
  Ok ".env present"
  $envText = Get-Content ".env" -Raw
  if ($envText -match "replace-me") {
    Warn ".env still has placeholders - T-0.2 fills OPENROUTER_API_KEY and TOKEN_ENCRYPTION_KEY"
  } else {
    Ok ".env has no placeholders"
  }
} else {
  Warn ".env missing - run: make env"
}

foreach ($p in 3000, 5432, 6379, 8000) {
  $used = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  if ($used) {
    Warn "port $p is already in use"
  } else {
    Ok "port $p free"
  }
}

Write-Host ""
if ($script:fail -gt 0) {
  Write-Host "$($script:fail) blocking issue(s). Fix those first." -ForegroundColor Red
  exit 1
}
Write-Host "Ready. Next: make up" -ForegroundColor Green
