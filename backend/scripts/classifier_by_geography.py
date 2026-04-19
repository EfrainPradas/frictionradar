"""
Geography-scoped classifier diagnostics.

Shows how the classifier behaves per-geography so we can compare TX/FL/UT
behavior and spot dataset-specific blind spots (e.g. patterns that recur
only in TX data but fall into 'unknown' or 'junk').

Read-only. No DB writes.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()

geographies = [row[0] for row in db.execute(text("""
    SELECT COALESCE(c.geography, 'null'), COUNT(DISTINCT r.company_id)
    FROM company_job_roles r
    JOIN companies c ON c.id = r.company_id
    GROUP BY 1 HAVING COUNT(DISTINCT r.company_id) >= 5
    ORDER BY 2 DESC
""")).fetchall()]

print("=" * 78)
print("GEOGRAPHY-SCOPED CLASSIFIER DIAGNOSTICS")
print("=" * 78)
print(f"Geographies to compare: {geographies}")

for geo in geographies:
    geo_filter = "c.geography IS NULL" if geo == "null" else "c.geography = :geo"
    params = {} if geo == "null" else {"geo": geo}

    totals = db.execute(text(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN r.functional_area NOT IN ('junk','unknown')
                        AND r.functional_area IS NOT NULL THEN 1 ELSE 0 END) AS classified,
               SUM(CASE WHEN r.functional_area = 'junk' THEN 1 ELSE 0 END) AS junk,
               SUM(CASE WHEN r.functional_area = 'unknown' THEN 1 ELSE 0 END) AS unknown,
               COUNT(DISTINCT r.company_id) AS companies
        FROM company_job_roles r
        JOIN companies c ON c.id = r.company_id
        WHERE {geo_filter}
    """), params).fetchone()

    total, classified, junk, unknown, companies = totals
    total = total or 0
    classified = classified or 0
    junk = junk or 0
    unknown = unknown or 0

    print(f"\n{'-'*78}")
    print(f"GEO={geo}  companies={companies}  total_roles={total}")
    print(f"  classified={classified} ({classified/max(total,1):.0%})  "
          f"junk={junk} ({junk/max(total,1):.0%})  "
          f"unknown={unknown} ({unknown/max(total,1):.0%})")

    family_rows = db.execute(text(f"""
        SELECT r.functional_area, COUNT(*)
        FROM company_job_roles r
        JOIN companies c ON c.id = r.company_id
        WHERE {geo_filter}
          AND r.functional_area IS NOT NULL
          AND r.functional_area NOT IN ('junk', 'unknown')
        GROUP BY 1 ORDER BY 2 DESC
    """), params).fetchall()

    if family_rows:
        print("  Family yield:")
        for fam, cnt in family_rows:
            print(f"    {fam:22s} {cnt}")

    unknown_samples = db.execute(text(f"""
        SELECT r.role_title, COUNT(*) AS c
        FROM company_job_roles r
        JOIN companies c ON c.id = r.company_id
        WHERE {geo_filter}
          AND r.functional_area = 'unknown'
          AND r.role_title IS NOT NULL
        GROUP BY r.role_title
        HAVING COUNT(*) >= 2
        ORDER BY c DESC LIMIT 10
    """), params).fetchall()

    if unknown_samples:
        print("  Top recurring UNKNOWN titles:")
        for title, cnt in unknown_samples:
            print(f"    [{cnt}x] {title}")

    junk_samples = db.execute(text(f"""
        SELECT r.role_title, COUNT(*) AS c
        FROM company_job_roles r
        JOIN companies c ON c.id = r.company_id
        WHERE {geo_filter}
          AND r.functional_area = 'junk'
          AND r.role_title IS NOT NULL
        GROUP BY r.role_title
        HAVING COUNT(*) >= 2
        ORDER BY c DESC LIMIT 10
    """), params).fetchall()

    if junk_samples:
        print("  Top recurring JUNK titles:")
        for title, cnt in junk_samples:
            print(f"    [{cnt}x] {title}")

db.close()
print("\n" + "=" * 78)
print("DONE")
print("=" * 78)
