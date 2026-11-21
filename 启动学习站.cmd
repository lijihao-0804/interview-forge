@echo off
setlocal
chcp 65001 >nul
title Local Learning Site

where python >nul 2>nul
if not errorlevel 1 goto have_python

where py >nul 2>nul
if not errorlevel 1 goto have_py

echo.
echo Python was not found. Install Python and enable "Add Python to PATH".
echo.
pause
exit /b 1

:have_python
set "PY_CMD=python"
goto check_port

:have_py
set "PY_CMD=py -3"

:check_port
rem Reuse an already healthy server: restarting on every launch clears the
rem in-process caches, so the first page has to re-read "due for review".
if /I "%IF_FORCE_RESTART%"=="1" goto restart
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8765/api/health'; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1"
if not errorlevel 1 (
  echo [Info] A healthy study server is already running; opening the browser without restarting it.
  echo [Info] Set IF_FORCE_RESTART=1 before launch to force a restart after code changes.
  start "" "http://127.0.0.1:8765/"
  exit /b 0
)

:restart
echo [Info] Checking for an existing study server...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\stop-study-server.ps1"
if errorlevel 1 (
  echo.
  echo [Info] Port 8765 is still in use by another process.
  echo Please close that process manually, then start again.
  echo.
  pause
  exit /b 1
)

rem --open now waits for /api/health before launching the browser.
%PY_CMD% "%~dp0tools\study_server.py" --host 0.0.0.0 --open
if not errorlevel 1 exit /b 0

echo.
echo The study site failed to start. The error is shown above.
echo Press any key to close this window.
pause >nul
exit /b 1
