@echo off
REM Nightly Smart Match refresh wrapper — invoked by Windows Task Scheduler at 01:00.
REM Logs rotate per-day.

setlocal
set "BACKEND_DIR=C:\Ubuntu\home\efraiprada\frictionradar\backend"
set "LOG_DIR=%BACKEND_DIR%\runs\nightly_logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM YYYY-MM-DD timestamp for log filename
for /f "tokens=1-3 delims=/-. " %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%a-%%b-%%c"
set "LOG_FILE=%LOG_DIR%\refresh_%TODAY%.log"

cd /d "%BACKEND_DIR%"
echo ========================================== >> "%LOG_FILE%" 2>&1
echo Nightly refresh started: %DATE% %TIME% >> "%LOG_FILE%" 2>&1
echo ========================================== >> "%LOG_FILE%" 2>&1

python3.13 scripts\nightly_smart_match_refresh.py --parallel 4 >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo ========================================== >> "%LOG_FILE%" 2>&1
echo Nightly refresh finished: %DATE% %TIME% (exit=%EXIT_CODE%) >> "%LOG_FILE%" 2>&1
echo ========================================== >> "%LOG_FILE%" 2>&1

endlocal
exit /b %EXIT_CODE%
