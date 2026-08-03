@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === 强制对齐远端 main（清除本地冲突）===
git merge --abort 2>nul
git rebase --abort 2>nul
git am --abort 2>nul
git cherry-pick --abort 2>nul

git fetch origin
if errorlevel 1 (
  echo fetch 失败，请检查网络后重试
  pause
  exit /b 1
)

git checkout -f main
git reset --hard origin/main
git clean -fd
git stash clear

echo.
echo 当前状态：
git status
git log -1 --oneline
echo.
echo 完成。请重启后端，前端 Ctrl+F5。
pause
