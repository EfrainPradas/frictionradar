"""Run full pipeline on wikidata-sourced companies that have never been collected.

Targets: source_added_from='wikidata' + last_collection_at IS NULL + has domain.

Usage:
  python scripts/run_wikidata_batch.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from scripts.batch_runner import process_company_full


class _L:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): print("  [WARN]", *a)
    def error(self, *a, **k): print("  [ERR]", *a)


def main():
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT id::text AS id, name, domain
        FROM companies
        WHERE source_added_from = 'wikidata'
          AND last_collection_at IS NULL
          AND domain IS NOT NULL
          AND domain <> ''
        ORDER BY name
    """)).fetchall()
    targets = [{"id": r.id, "name": r.name, "domain": r.domain} for r in rows]
    db.close()

    print(f"Wikidata backlog: {len(targets)} companies")
    for t in targets:
        print(f"  {t['name'][:45]:45s} {t['domain']}")
    print("=" * 80)

    logger = _L()
    succeeded = failed = improved = eligible = 0
    t_start = time.monotonic()

    for i, c in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {c['name'][:40]:40s} ... ", end="", flush=True)
        db = SessionLocal()
        try:
            r = process_company_full(db, c["id"], c["name"], c["domain"], logger)
            succeeded += 1
            after = r.get("after", {})
            ds = after.get("ds", "")[:18]
            fc = after.get("fc", "")
            direction = r.get("direction", "")
            if direction == "improved":
                improved += 1
            if fc in ("ready_for_positioning", "conditional_ready"):
                eligible += 1
            print(f"ds:{ds:18s} fc:{fc:22s} dir:{direction:12s} {r.get('elapsed_s', 0):.1f}s")
        except Exception as e:
            failed += 1
            print(f"FAILED: {str(e)[:80]}")
        finally:
            db.close()

    elapsed = time.monotonic() - t_start
    print("=" * 80)
    print(f"Done in {elapsed:.0f}s")
    print(f"  succeeded:  {succeeded}")
    print(f"  failed:     {failed}")
    print(f"  improved:   {improved}")
    print(f"  eligible:   {eligible}  <-- key metric")


if __name__ == "__main__":
    main()
