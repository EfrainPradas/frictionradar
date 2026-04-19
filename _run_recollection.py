"""Re-run the batch for companies that need recollection."""
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

# Paths
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
CLI = ROOT / "cli"
RESULTS = CLI / "results"

# Setup paths
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(CLI))

# Load env
env_file = BACKEND / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            import os
            os.environ.setdefault(key.strip(), val.strip())

# Now import
from dotenv import load_dotenv
load_dotenv(env_file)

from services.input_loader import load_companies
from services.batch_processor import process_company

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("recollection")

def main():
    input_file = RESULTS / "recollection_input.json"
    companies = load_companies(input_file)
    valid = [c for c in companies if not c.get("_exclude_reason")]

    log.info(f"Loaded {len(valid)} companies for re-collection")

    # Load progress
    state_file = RESULTS / ".batch_state.json"
    done = set()
    if state_file.exists():
        data = json.loads(state_file.read_text(encoding="utf-8"))
        done = set(data.get("done_domains", []))
    valid = [c for c in valid if c["domain"] not in done]
    log.info(f"After resume filter: {len(valid)} to process")

    results = []
    errors = 0
    consecutive_errors = 0
    started = datetime.now(timezone.utc)

    for i, entry in enumerate(valid, 1):
        name = entry.get("company_name", "?")
        domain = entry.get("domain", "?")
        log.info(f"[{i}/{len(valid)}] {domain}")

        t0 = time.monotonic()
        try:
            result = process_company(entry)
            status = result["status"]
            signals = result.get("signals_count", 0)
            hp = result.get("hiring_pressure", "-")
            pc = result.get("pain_clarity", "-")
            diag = result.get("diagnosis_status", "-")
            elapsed = round(time.monotonic() - t0, 1)

            log.info(f"  signals: {signals} | hp: {hp} | pc: {pc} | status: {status} | diag: {diag} ({elapsed}s)")

            results.append(result)
            done.add(domain)
            consecutive_errors = 0
        except Exception as e:
            log.error(f"  ERROR: {e}")
            consecutive_errors += 1
            errors += 1

        # Save progress every 5
        if i % 5 == 0:
            state_file.write_text(json.dumps({"done_domains": sorted(done)}), encoding="utf-8")

        # Max 20 consecutive errors
        if consecutive_errors >= 20:
            log.error("Aborting: 20 consecutive errors")
            break

        if i < len(valid):
            time.sleep(2)

        log.info("")

    # Merge with existing results
    all_file = RESULTS / "all_results.json"
    if all_file.exists():
        prev = json.loads(all_file.read_text(encoding="utf-8"))
        updated_domains = {r["domain"] for r in results if r.get("domain")}
        for r in prev:
            if r["domain"] not in updated_domains:
                results.append(r)

    # Write outputs
    from services.result_writer import write_results
    write_results(results, RESULTS, started)

    # Summary
    from collections import Counter
    sc = Counter(r["status"] for r in results)
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=" * 50)
    log.info(f"DONE: {len(results)} total | ready: {sc.get('ready_for_review',0)} | needs: {sc.get('needs_recollection',0)} | excluded: {sc.get('excluded',0)} | errors: {errors}")
    log.info(f"Duration: {duration:.0f}s")
    log.info("=" * 50)

if __name__ == "__main__":
    main()
