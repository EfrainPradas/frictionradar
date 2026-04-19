"""F2 diagnostic: count companies per ATS platform and their outcomes.

For each detected ATS platform, segment by:
  - has roles persisted? (success)
  - has careers_page_found but 0 roles? (silent failure)
  - has last_collection_at but 0 signals? (failed collection)
  - never collected

Priority cases for F2:
  - workday: routes to Playwright (no JSON API), expect timeouts
  - smartrecruiters: declared ATS_WITH_JSON_API but adapter missing
  - jobvite: declared ATS_WITH_JSON_API but adapter missing
  - greenhouse/lever: adapters exist — if failing, adapter bug
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal


ATS_SIGNALS = [
    "workday_board_detected",
    "greenhouse_board_detected",
    "lever_board_detected",
    "ashby_board_detected",
    "smartrecruiters_board_detected",
    "jobvite_board_detected",
    "icims_board_detected",
]


def main():
    db = SessionLocal()

    print("=" * 80)
    print("F2 ATS STATE — empresas por plataforma y outcome")
    print("=" * 80)

    rows = db.execute(text("""
        SELECT signal_type, COUNT(DISTINCT company_id) AS n
        FROM company_signals
        WHERE signal_type = ANY(:sigs)
        GROUP BY signal_type
        ORDER BY n DESC
    """).bindparams(sigs=ATS_SIGNALS)).fetchall()

    print("\nEmpresas con señal ATS detectada:")
    for r in rows:
        print(f"  {r.signal_type:30s} {r.n:>4d}")

    print("\n" + "=" * 80)
    print("Outcome por ATS: role persisted / silent-fail / never-collected")
    print("=" * 80)

    for ats_sig in [s for s in ATS_SIGNALS]:
        stats = db.execute(text("""
            WITH ats_cos AS (
                SELECT DISTINCT company_id
                FROM company_signals
                WHERE signal_type = :sig
            )
            SELECT
                COUNT(DISTINCT c.id) AS total,
                COUNT(DISTINCT CASE WHEN EXISTS (
                    SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id
                ) THEN c.id END) AS with_roles,
                COUNT(DISTINCT CASE WHEN c.last_collection_at IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
                    THEN c.id END) AS collected_no_roles,
                COUNT(DISTINCT CASE WHEN c.last_collection_at IS NULL
                    THEN c.id END) AS never_collected
            FROM companies c
            JOIN ats_cos a ON a.company_id = c.id
        """).bindparams(sig=ats_sig)).first()

        if stats.total == 0:
            continue

        print(f"\n[{ats_sig}] total={stats.total}")
        print(f"  with roles:         {stats.with_roles}")
        print(f"  collected, no roles: {stats.collected_no_roles}")
        print(f"  never collected:    {stats.never_collected}")

        samples = db.execute(text("""
            SELECT c.name, c.domain
            FROM companies c
            JOIN company_signals s ON s.company_id = c.id
            WHERE s.signal_type = :sig
              AND c.last_collection_at IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)
            LIMIT 5
        """).bindparams(sig=ats_sig)).fetchall()

        if samples:
            print("  silent-failure samples:")
            for s in samples:
                print(f"    - {s.name:40s} {s.domain}")

    db.close()


if __name__ == "__main__":
    main()
