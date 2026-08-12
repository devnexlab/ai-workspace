@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

title AI 智能运营 - 安装并启动
echo ========================================
echo   AI 智能运营 · Docker 一键安装并启动
echo ========================================
echo.

:: ---- 检查 Docker 是否安装 ----
where docker >nul 2>&1
if errorlevel 1 (
  echo [错误] 未检测到 Docker。
  echo 请先安装 Docker Desktop：
  echo   https://www.docker.com/products/docker-desktop/
  echo 安装完成后重新打开本脚本。
  echo.
  pause
  exit /b 1
)

:: ---- 检查 Docker 引擎是否在跑 ----
docker info >nul 2>&1
if errorlevel 1 (
  echo [提示] Docker 已安装，但引擎未就绪，尝试启动 Docker Desktop...
  if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  ) else if exist "%LocalAppData%\Docker\Docker Desktop.exe" (
    start "" "%LocalAppData%\Docker\Docker Desktop.exe"
  ) else (
    echo [错误] 找不到 Docker Desktop，请手动打开后再运行本脚本。
    pause
    exit /b 1
  )
  echo 等待 Docker 启动（最多约 90 秒）...
  set /a _wait=0
  :wait_docker
  timeout /t 3 /nobreak >nul
  docker info >nul 2>&1
  if not errorlevel 1 goto docker_ok
  set /a _wait+=3
  if %_wait% geq 90 (
    echo [错误] Docker 启动超时，请确认 Docker Desktop 已打开并显示 Running。
    pause
    exit /b 1
  )
  echo   ...已等待 %_wait% 秒
  goto wait_docker
)
:docker_ok
echo [OK] Docker 已就绪
echo.

:: ---- 准备 .env（默认账号，无需改密码）----
if not exist "backend\.env" (
  if not exist "backend\.env.example" (
    echo [错误] 缺少 backend\.env.example
    pause
    exit /b 1
  )
  copy /Y "backend\.env.example" "backend\.env" >nul
  echo [OK] 已复制 backend\.env.example -^> backend\.env
) else (
  echo [OK] 已存在 backend\.env，跳过复制
)

:: ---- 运行时目录 ----
if not exist "backend\data" mkdir "backend\data"
if not exist "backend\outputs" mkdir "backend\outputs"
if not exist "backend\uploads" mkdir "backend\uploads"
echo [OK] 数据目录已准备
echo.

:: ---- 构建并启动 ----
echo 正在构建并启动容器（首次会较久，请耐心等待）...
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo [错误] docker compose 失败。可查看日志：
  echo   docker compose logs
  echo.
  pause
  exit /b 1
)

echo.
echo ========================================
echo   启动完成
echo ========================================
echo   前端： http://localhost:5180
echo   后端： http://localhost:3456
echo   数据库： localhost:5432  （ai_ops / postgres / postgres）
echo.
echo   常用命令：
echo     docker compose ps
echo     docker compose logs -f
echo     docker compose down
echo ========================================
echo.

:: 等前端就绪再打开浏览器（最多约 60 秒）
echo 等待前端就绪...
set /a _w=0
:wait_web
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5180' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200) { exit 0 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto open_browser
set /a _w+=2
if %_w% geq 60 goto open_browser
goto wait_web

:open_browser
REM 客户机可能没有默认浏览器，优先 Edge/Chrome，失败只提示不弹错
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='http://localhost:5180';" ^
  "$cands=@(" ^
  "  (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')," ^
  "  (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')," ^
  "  (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe')," ^
  "  (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe')," ^
  "  (Join-Path $env:LocalAppData 'Google\Chrome\Application\chrome.exe')" ^
  ");" ^
  "$ok=$false; foreach($b in $cands){ if($b -and (Test-Path $b)){ try{ Start-Process -FilePath $b -ArgumentList $url; $ok=$true; break }catch{} } };" ^
  "if(-not $ok){ try{ Start-Process $url }catch{ Write-Host '[提示] 未检测到浏览器，请手动打开 http://localhost:5180' } }"
echo 已尝试打开浏览器。若未弹出，请手动访问 http://localhost:5180
echo 窗口可关闭，服务在后台继续运行。
echo.
pause
endlocal
exit /b 0
