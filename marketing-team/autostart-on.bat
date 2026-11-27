@echo off
rem Runs the marketing team hidden in the background every time you log in to Windows.
cd /d "%~dp0"
where node >nul 2>nul || (echo Install Node.js LTS from https://nodejs.org first. & pause & exit /b)
if not exist node_modules call npm install --no-audit --no-fund
if not exist data mkdir data
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AI Marketing Team.vbs"
(
echo Set sh = CreateObject("WScript.Shell"^)
echo sh.CurrentDirectory = "%~dp0"
echo sh.Run "cmd /c node --no-warnings server.js >> data\app.log 2>&1", 0, False
) > "%VBS%"
wscript "%VBS%"
timeout /t 3 >nul
start "" http://localhost:3000
echo Done. The team now starts automatically when you log in. Open http://localhost:3000 any time.
pause
