"""Re-run batch_runner.process_company_full on the 14 Bug-B companies:
those where extract_company already succeeds (extraction_* signals exist)
but 0 roles were persisted. Manual test showed persist_job_role works
in the current code — so these just need a fresh pass.

Strategy: identify companies, run them sequentially, report delta.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.logging import get_logger
from scripts.batch_runner import process_company_full

logger = get_logger("rerun_f3a_bugB")


def identify_targets(db):
    """Bug B: has extraction_* job_cards_visible_detected signal but 0 roles."""
    rows = db.execute(text("""
        SELECT c.id, c.name, c.domain
        FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
          AND EXISTS (
              SELECT 1 FROM company_signals s
              WHERE s.company_id = c.id
                AND s.source_type LIKE 'extraction_%'
                AND s.signal_type = 'job_cards_visible_detected'
          )
        ORDER BY c.name
    """)).fetchall()
    return [(str(r.id), r.name, r.domain) for r in rows]


def main():
    db = SessionLocal()
    targets = identify_targets(db)
    print(f"Bug-B targets: {len(targets)}")
    for cid, name, domain in targets:
        print(f"  - {name} ({domain})")

    print()
    print("Running process_company_full...")
    t0 = time.monotonic()
    results = []

    for idx, (cid, name, domain) in enumerate(targets, 1):
        t_start = time.monotonic()
        print(f"\n[{idx}/{len(targets)}] {name} ({domain})")
        try:
            r = process_company_full(db, cid, name, domain, logger)
            elapsed = round(time.monotonic() - t_start, 1)
            total = r.get("total_roles", 0)
            classified = r.get("classified", 0)
            direction = r.get("direction", "?")
            print(f"    roles={total} classified={classified} direction={direction} elapsed={elapsed}s")
            results.append({"name": name, "ok": True, "total": total, "classified": classified})
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            results.append({"name": name, "ok": False, "error": str(e)})

    total_elapsed = round(time.monotonic() - t0, 1)
    print()
    print("=" * 80)
    print(f"DONE in {total_elapsed}s")
    ok = sum(1 for r in results if r["ok"])
    recovered = sum(1 for r in results if r.get("ok") and r.get("total", 0) > 0)
    print(f"  success:   {ok}/{len(targets)}")
    print(f"  recovered: {recovered} companies now have >0 roles")

    db.close()


if __name__ == "__main__":
    main()
