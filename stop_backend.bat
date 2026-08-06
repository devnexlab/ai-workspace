@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 停止后端 ===

if exist "logs\backend.pid" (
  set /p PID=<logs\backend.pid
  echo 结束 PID %PID% ...
  taskkill /PID %PID% /T /F >nul 2>&1
  del /f /q "logs\backend.pid" >nul 2>&1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-NetTCPConnection -LocalPort 3456 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [OK] 后端已停止（若在运行）
timeout /t 2 >nul
exit /b 0
