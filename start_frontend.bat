@echo off
chcp 65001 >nul
echo === 启动前端 ===
cd /d "%~dp0frontend"
call npm run dev
echo.
echo 前端已退出，按任意键关闭窗口...
pause >nul
