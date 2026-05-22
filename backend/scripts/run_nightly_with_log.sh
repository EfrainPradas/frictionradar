#!/usr/bin/env bash
# FrictionRadar Nightly Intelligence Pipeline
# Runs full pipeline + pain profiles + VIP generation
# Logs each run with timestamp
#
# Crontab entry (1 AM daily):
# 0 1 * * * /home/efraiprada/frictionradar/backend/scripts/run_nightly_with_log.sh >> /home/efraiprada/frictionradar/backend/logs/cron.log 2>&1

set -euo pipefail

BACKEND_DIR="/home/efraiprada/frictionradar/backend"
LOG_DIR="${BACKEND_DIR}/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/nightly_${TIMESTAMP}.log"

cd "${BACKEND_DIR}"

echo "========================================" | tee -a "${LOG_FILE}"
echo "Nightly Pipeline Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Step 1: Nightly Intelligence Refresh (collection sweep + scoring)
echo "" | tee -a "${LOG_FILE}"
echo "[Step 1/3] Running Nightly Intelligence Refresh..." | tee -a "${LOG_FILE}"
python scripts/nightly_intelligence_refresh.py 2>&1 | tee -a "${LOG_FILE}"
STEP1_EXIT=$?

# Step 2: Generate Pain Profiles (SQL-based, via pg_cron or direct)
echo "" | tee -a "${LOG_FILE}"
echo "[Step 2/3] Generating Company Pain Profiles..." | tee -a "${LOG_FILE}"
python -m scripts.generate_company_pain_profiles --parallel 8 2>&1 | tee -a "${LOG_FILE}"
STEP2_EXIT=$?

# Step 3: Generate VIP Opportunities
echo "" | tee -a "${LOG_FILE}"
echo "[Step 3/3] Generating VIP Opportunities..." | tee -a "${LOG_FILE}"
python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv()
from app.db.session import SessionLocal
from app.services.vip_positioning_engine import vip_positioning_engine
db = SessionLocal()
try:
    opps = vip_positioning_engine.generate_opportunities('c1f53ebc-b8d1-42f1-8ed1-fd44e5ed4f4c', db)
    print(f'VIP opportunities generated: {len(opps)}')
except Exception as e:
    print(f'VIP generation failed: {e}')
    sys.exit(1)
finally:
    db.close()
" 2>&1 | tee -a "${LOG_FILE}"
STEP3_EXIT=$?

# Step 4: Sync to Ascendia (SQL-based, handled by pg_cron at 1:30 AM)
echo "" | tee -a "${LOG_FILE}"
echo "[Note] Ascendia sync handled by pg_cron at 1:30 AM" | tee -a "${LOG_FILE}"

echo "" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"
echo "Nightly Pipeline Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
echo "Exit codes: step1=${STEP1_EXIT} step2=${STEP2_EXIT} step3=${STEP3_EXIT}" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Alert on failures
if [ "${STEP1_EXIT}" -ne 0 ] || [ "${STEP2_EXIT}" -ne 0 ] || [ "${STEP3_EXIT}" -ne 0 ]; then
    echo "WARNING: One or more steps failed. Check ${LOG_FILE}" | tee -a "${LOG_FILE}"
    exit 1
fi

echo "All steps completed successfully." | tee -a "${LOG_FILE}"
exit 0