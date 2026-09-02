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
echo [Info] Checking for an existing study server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*study_server.py*' }); foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('[Info] Killed old study server PID ' + $p.ProcessId) }; $listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue); if ($listeners.Count -gt 0) { foreach ($c in $listeners) { $owner = $c.OwningProcess; $p2 = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owner) -ErrorAction SilentlyContinue; if ($p2 -and $p2.CommandLine -like '*study_server.py*') { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue; Write-Host ('[Info] Killed old study server PID ' + $owner) } else { Write-Host ('[Info] Port 8765 used by PID ' + $owner + '; not study_server.py, skip') } } }"
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":8765 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo.
  echo [Info] Port 8765 is still in use by another process.
  echo Please close that process manually, then start again.
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
