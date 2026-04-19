"""Deep-dive: for 65 companies with role-evidence signals but 0 persisted
roles, dump the full signal chain to pinpoint which code path emitted
each signal and why persistence never fired.

Run:  python scripts/diag_f3a_signal_chain.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


SAMPLE_LIMIT = 6


def main():
    db = SessionLocal()

    rows = db.execute(text("""
        SELECT c.id, c.name, c.domain, c.geography, c.last_collection_at
        FROM companies c
        WHERE c.last_collection_at IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
          AND EXISTS (
              SELECT 1 FROM company_signals s
              WHERE s.company_id = c.id
                AND s.signal_type IN (
                    'job_cards_visible_detected',
                    'job_links_extracted',
                    'open_positions_count_detected',
                    'high_open_positions_count_detected'
                )
          )
        ORDER BY c.name
        LIMIT :lim
    """), {"lim": SAMPLE_LIMIT}).fetchall()

    print("=" * 100)
    print(f"F3a DEEP-DIVE — {len(rows)} sample companies with evidence signals but 0 roles")
    print("=" * 100)

    for cid, name, domain, geo, last_col in rows:
        print()
        print("-" * 100)
        print(f"[{geo or 'n/a'}] {name}  domain={domain}")
        print(f"  last_collection_at={last_col}")

        signals = db.execute(text("""
            SELECT source_type, signal_type, numeric_value, source_url,
                   created_at, confidence
            FROM company_signals
            WHERE company_id = :cid
            ORDER BY created_at ASC
        """), {"cid": cid}).fetchall()

        print(f"  signals ({len(signals)}):")
        for s in signals:
            src = s.source_type or "-"
            stype = s.signal_type
            nv = s.numeric_value if s.numeric_value is not None else ""
            url = (s.source_url or "")[:70]
            print(f"    [{src:24s}] {stype:40s} n={nv!s:>5s}  {url}")

        run = db.execute(text("""
            SELECT collector_type, status, started_at, finished_at,
                   error_message, metadata_json
            FROM collection_runs
            WHERE company_id = :cid
            ORDER BY started_at DESC
            LIMIT 3
        """), {"cid": cid}).fetchall()

        print(f"  recent collection_runs:")
        for r in run:
            print(f"    {r.collector_type:15s} status={r.status:10s} "
                  f"started={r.started_at} err={(r.error_message or '')[:60]}")
            meta = r.metadata_json or {}
            if isinstance(meta, dict):
                if meta.get("collectors_run"):
                    for cr in meta["collectors_run"]:
                        print(f"       → {cr}")

    db.close()


if __name__ == "__main__":
    main()
