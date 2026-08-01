@echo off
chcp 65001 >nul
echo === 启动后端 ===
cd /d "%~dp0backend"
venv\Scripts\python.exe app.py
