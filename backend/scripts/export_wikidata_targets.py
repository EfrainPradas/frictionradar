"""Export wikidata-sourced never-collected companies to JSON for run_parallel_batch.

Usage:
  python scripts/export_wikidata_targets.py
  # writes: output/wikidata_targets.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


def main():
    os.makedirs("output", exist_ok=True)
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT id::text AS id, name, domain
        FROM companies
        WHERE source_added_from = 'wikidata'
          AND last_collection_at IS NULL
          AND domain IS NOT NULL AND domain <> ''
        ORDER BY name
    """)).fetchall()
    data = [{"id": r.id, "name": r.name, "domain": r.domain, "roles": 0} for r in rows]
    out = Path("output/wikidata_targets.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Exported {len(data)} companies to {out}")
    db.close()


if __name__ == "__main__":
    main()
