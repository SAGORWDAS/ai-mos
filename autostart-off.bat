@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI Marketing Team.vbs" 2>nul
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo Auto-start removed and the background app stopped.
pause
