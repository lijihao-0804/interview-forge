@echo off
setlocal
chcp 65001 >nul
title Local Learning Site

where python >nul 2>nul
if not errorlevel 1 goto run_python

where py >nul 2>nul
if not errorlevel 1 goto run_py

echo.
echo Python was not found. Install Python and enable "Add Python to PATH".
echo.
pause
exit /b 1

:check_port
netstat -ano | findstr ":8765 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo.
  echo [Info] Port 8765 is already in use. The study site may already be running.
  echo Open http://127.0.0.1:8765/ directly. To restart, close the old instance first.
  echo.
  pause
  exit /b 1
)
goto :eof

:run_python
call :check_port
python "%~dp0tools\study_server.py" --host 0.0.0.0 --open
goto after_run

:run_py
call :check_port
py -3 "%~dp0tools\study_server.py" --host 0.0.0.0 --open

:after_run
if not errorlevel 1 exit /b 0

echo.
echo The study site failed to start. The error is shown above.
echo Press any key to close this window.
echo.
pause >nul
exit /b 1
