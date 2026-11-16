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
  echo.
  echo [!] Python 3 not found.
  echo.
  pause
  exit /b 1
)

rem LAN mode: phones / iOS PWA can open the printed URL (token protected)
rem First run may trigger a Windows Firewall prompt - click Allow.
set ZTE_BIND=0.0.0.0

echo.
echo   ZTE Router Home  -  LAN mode for phones / iPhone PWA
echo   Open the URL printed below on your phone (Safari: Share - Add to Home Screen).
echo   Keep this window open. Close it to stop.
echo.
"%PY%" panel.py
echo.
pause
