@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === 后台启动前端 ===

where npm >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 npm，请先安装 Node.js 或执行 nvm use
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [提示] 未检测到 node_modules，正在执行 npm install...
  pushd frontend
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败
    popd
    pause
    exit /b 1
  )
  popd
)

if not exist "logs" mkdir "logs"

echo 清理占用 5180 端口的旧进程...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-NetTCPConnection -LocalPort 5180 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source; if (-not $npm) { $npm = (Get-Command npm -ErrorAction Stop).Source };" ^
  "$wd = Join-Path '%CD%' 'frontend';" ^
  "$out = Join-Path '%CD%' 'logs\frontend.out.log';" ^
  "$err = Join-Path '%CD%' 'logs\frontend.err.log';" ^
  "$pidFile = Join-Path '%CD%' 'logs\frontend.pid';" ^
  "$p = Start-Process -FilePath $npm -ArgumentList 'run','dev' -WorkingDirectory $wd -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err;" ^
  "Set-Content -Path $pidFile -Value $p.Id -Encoding ASCII;" ^
  "Write-Host ('[OK] 前端已后台运行 PID=' + $p.Id)"

if errorlevel 1 (
  echo [错误] 启动失败，请查看 logs\frontend.err.log
  pause
  exit /b 1
)

echo.
echo 页面: http://localhost:5180
echo 日志: logs\frontend.out.log  /  logs\frontend.err.log
echo 停止: 双击 stop_frontend.bat
echo.
echo 本窗口可关闭，前端会继续在后台运行。
timeout /t 3 >nul
start "" "http://localhost:5180"
timeout /t 2 >nul
endlocal
exit /b 0
