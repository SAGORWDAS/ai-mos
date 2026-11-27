@echo off
title AI Marketing Team
cd /d "%~dp0"
curl -s -o nul http://localhost:3000/api/state && (start "" http://localhost:3000 & exit /b)
where node >nul 2>nul || (echo Node.js is not installed. Download the LTS version from https://nodejs.org then run this again. & pause & exit /b)
if not exist node_modules (echo First run: installing... & call npm install --no-audit --no-fund)
start "" http://localhost:3000
node --no-warnings server.js
pause
