"""Run full pipeline on the 22 never-collected companies that already
have an ATS detection signal. These are stuck in 'imported' + last_collection_at IS NULL.

Expected recovery profile:
  - 16 Workday companies (corporates: AIG, Alcoa, Apollo, GE, Xylem, etc.)
  - 3 Greenhouse + 1 iCIMS + minor others

Target: any that land roles≥3 + classified≥5 become Eligible.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from scripts.batch_runner import process_company_full, snapshot_kpis


class _L:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): print("  [WARN]", *a)
    def error(self, *a, **k): print("  [ERR]", *a)


def main():
    db = SessionLocal()

    rows = db.execute(text("""
        SELECT DISTINCT c.id::text AS id, c.name, c.domain
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
        WHERE s.signal_type LIKE '%_board_detected'
          AND c.last_collection_at IS NULL
          AND c.domain IS NOT NULL
          AND c.domain <> ''
        ORDER BY c.name
    """)).fetchall()

    targets = [{"id": r.id, "name": r.name, "domain": r.domain} for r in rows]
    db.close()

    print(f"Backlog target: {len(targets)} companies")
    for t in targets:
        print(f"  {t['name']:45s} {t['domain']}")
    print("=" * 80)

    logger = _L()
    succeeded = 0
    failed = 0
    improved = 0
    t_start = time.monotonic()

    for i, c in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {c['name'][:40]:40s} ... ", end="", flush=True)
        db = SessionLocal()
        try:
            r = process_company_full(db, c["id"], c["name"], c["domain"], logger)
            succeeded += 1
            if r.get("direction") == "improved":
                improved += 1
            print(
                f"ds:{r['after']['ds'][:18]:18s} fc:{r['after']['fc']:7s} "
                f"dir:{r['direction']:12s} {r['elapsed_s']:.1f}s"
            )
        except Exception as e:
            failed += 1
            print(f"FAILED: {str(e)[:80]}")
        finally:
            db.close()

    elapsed = time.monotonic() - t_start
    print("=" * 80)
    print(f"Done in {elapsed:.0f}s — succeeded={succeeded} failed={failed} improved={improved}")


if __name__ == "__main__":
    main()
