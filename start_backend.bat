@echo off
chcp 65001 >nul
echo === 启动后端 ===
echo 清理占用 3456 端口的旧进程...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3456 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
cd /d "%~dp0backend"
venv\Scripts\python.exe app.py
echo.
echo 后端已退出，按任意键关闭窗口...
pause >nul
