@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
  )
)
if not defined PY (
  echo [!] Python 3 not found.
  pause
  exit /b 1
)

echo.
echo   Router Lab (capture / proxy)  -  http://127.0.0.1:8899/__ui
echo.
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8899/__ui"
"%PY%" server.py
echo.
pause
