"""Test whether persist_job_role successfully saves extracted jobs for
Angel Studios (a known Bug-B case). This bypasses batch_runner orchestration
so any failure is isolated to the persist path itself.

DRY RUN: rolls back at the end. No DB changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.extraction.dispatcher import extract_company
from app.services.role_ingest import persist_job_role


def main():
    db = SessionLocal()

    cid = db.execute(text(
        "SELECT id FROM companies WHERE domain = :d"
    ), {"d": "angel.com"}).scalar()
    print(f"Angel Studios company_id = {cid}")

    print("Running extract_company...")
    r = extract_company(
        domain="angel.com",
        company_name="Angel Studios",
        company_id=cid,
        skip_playwright=False,
    )
    print(f"strategy={r.strategy_used.value} success={r.success} jobs={r.jobs_count}")

    existing_urls = set(
        u for (u,) in db.execute(text(
            "SELECT source_url FROM company_job_roles WHERE company_id = :c"
        ), {"c": cid}).fetchall() if u
    )
    print(f"existing_urls = {existing_urls}")
    print()

    fallback_url = r.careers_url or ""
    added = 0
    skipped_no_title = 0
    skipped_dedup = 0

    for job in r.jobs[:40]:
        if not job.title:
            skipped_no_title += 1
            continue
        src = job.job_url or fallback_url
        if src and src in existing_urls:
            skipped_dedup += 1
            continue
        try:
            role = persist_job_role(
                db,
                company_id=cid,
                raw_title=job.title,
                source_url=src or None,
                role_location=job.location,
                role_department=job.department,
                role_description=job.description_snippet,
            )
        except Exception as exc:
            print(f"   persist_job_role RAISED: {type(exc).__name__}: {exc}")
            break
        if role is None:
            print(f"   persist returned None for title='{job.title[:50]}'")
            continue
        added += 1
        if src:
            existing_urls.add(src)

    print()
    print(f"added (staged, not committed): {added}")
    print(f"skipped (no title): {skipped_no_title}")
    print(f"skipped (dedup on existing_url): {skipped_dedup}")

    print()
    print("Attempting commit...")
    try:
        db.commit()
        print("   commit SUCCESS")
        count = db.execute(text(
            "SELECT COUNT(*) FROM company_job_roles WHERE company_id = :c"
        ), {"c": cid}).scalar()
        print(f"   current roles count: {count}")
        print("Rolling back (dry run)...")
        db.execute(text(
            "DELETE FROM company_job_roles WHERE company_id = :c"
        ), {"c": cid})
        db.commit()
        after = db.execute(text(
            "SELECT COUNT(*) FROM company_job_roles WHERE company_id = :c"
        ), {"c": cid}).scalar()
        print(f"   after cleanup: {after} roles")
    except Exception as exc:
        print(f"   commit RAISED: {type(exc).__name__}: {exc}")
        db.rollback()

    db.close()


if __name__ == "__main__":
    main()
