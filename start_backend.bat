@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === 后台启动后端 ===

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到 .venv，请先在仓库根目录安装依赖：
  echo   uv sync
  echo   或: python -m venv .venv
  echo   然后: .venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)

REM Cursor 会把 PLAYWRIGHT_BROWSERS_PATH 指到空的 sandbox 缓存，导致 Chromium 找不到
if defined PLAYWRIGHT_BROWSERS_PATH (
  echo %PLAYWRIGHT_BROWSERS_PATH% | findstr /I "cursor-sandbox-cache" >nul
  if not errorlevel 1 (
    echo [提示] 清除错误的 PLAYWRIGHT_BROWSERS_PATH（Cursor sandbox）
    set "PLAYWRIGHT_BROWSERS_PATH="
  )
)
if not defined PLAYWRIGHT_BROWSERS_PATH (
  if exist "%LOCALAPPDATA%\ms-playwright" (
    set "PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\ms-playwright"
  )
)

if not exist "logs" mkdir "logs"

echo 清理占用 3456 端口的旧进程...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 3456 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$py = Join-Path '%CD%' '.venv\Scripts\python.exe'; $wd = Join-Path '%CD%' 'backend'; $out = Join-Path '%CD%' 'logs\backend.out.log'; $err = Join-Path '%CD%' 'logs\backend.err.log'; $pidFile = Join-Path '%CD%' 'logs\backend.pid'; $p = Start-Process -FilePath $py -ArgumentList 'app.py' -WorkingDirectory $wd -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err; Set-Content -Path $pidFile -Value $p.Id -Encoding ASCII; Write-Host ('[OK] 后端已后台运行 PID=' + $p.Id)"

if errorlevel 1 (
  echo [错误] 启动失败，请查看 logs\backend.err.log
  pause
  exit /b 1
)

echo.
echo 接口: http://localhost:3456
echo 日志: logs\backend.out.log  /  logs\backend.err.log
echo 停止: 双击 stop_backend.bat
echo.
echo 本窗口可关闭，后端会继续在后台运行。
timeout /t 4 >nul
endlocal
exit /b 0
