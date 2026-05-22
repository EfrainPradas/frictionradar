@echo off
REM FrictionRadar Nightly Pipeline - Windows Task Scheduler wrapper
REM Runs at 12:30 AM daily, 30 min before pg_cron SQL jobs at 1:00 AM

set BACKEND_DIR=C:\Ubuntu\home\efraiprada\frictionradar\backend
set LOG_DIR=%BACKEND_DIR%\logs
set TIMESTAMP=%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set LOG_FILE=%LOG_DIR%\nightly_%TIMESTAMP%.log

echo ======================================== >> "%LOG_FILE%" 2>&1
echo Nightly Pipeline Started: %date% %time% >> "%LOG_FILE%" 2>&1
echo ======================================== >> "%LOG_FILE%" 2>&1

cd /d "%BACKEND_DIR%"

python scripts\nightly_intelligence_refresh.py >> "%LOG_FILE%" 2>&1
set STEP1=%errorlevel%

echo. >> "%LOG_FILE%" 2>&1
echo [Step 2/3] Generating Company Pain Profiles... >> "%LOG_FILE%" 2>&1
python -m scripts.generate_company_pain_profiles --parallel 8 >> "%LOG_FILE%" 2>&1
set STEP2=%errorlevel%

echo. >> "%LOG_FILE%" 2>&1
echo [Step 3/3] Generating VIP Opportunities... >> "%LOG_FILE%" 2>&1
python -c "import sys,os;sys.path.insert(0,os.getcwd());from dotenv import load_dotenv;load_dotenv();from app.db.session import SessionLocal;from app.services.vip_positioning_engine import vip_positioning_engine;db=SessionLocal();opps=vip_positioning_engine.generate_opportunities('c1f53ebc-b8d1-42f1-8ed1-fd44e5ed4f4c',db);print(f'VIP opportunities generated: {len(opps)}');db.close()" >> "%LOG_FILE%" 2>&1
set STEP3=%errorlevel%

echo. >> "%LOG_FILE%" 2>&1
echo ======================================== >> "%LOG_FILE%" 2>&1
echo Nightly Pipeline Finished: %date% %time% >> "%LOG_FILE%" 2>&1
echo Exit codes: step1=%STEP1% step2=%STEP2% step3=%STEP3% >> "%LOG_FILE%" 2>&1
echo ======================================== >> "%LOG_FILE%" 2>&1

REM Clean up logs older than 30 days
forfiles /p "%LOG_DIR%" /m nightly_*.log /d -30 /c "cmd /c del @path" 2>nul

if %STEP1% neq 0 exit /b %STEP1%
if %STEP2% neq 0 exit /b %STEP2%
if %STEP3% neq 0 exit /b %STEP3%
exit /b 0