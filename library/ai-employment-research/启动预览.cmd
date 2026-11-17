@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 tools\serve.py --port 8765
) else (
  python tools\serve.py --port 8765
)
pause
