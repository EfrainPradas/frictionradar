"""Backfill: re-run Ashby ATS extraction for every company with
`ashby_board_detected` signal, persisting roles + signals.

Context: Ashby's GraphQL schema changed (teams.jobs -> jobBoard.jobPostings).
The adapter was silently broken, so 722 companies with the detected signal
had 0 roles via ATS_API. The adapter is now fixed — this backfill recovers
the roles for every company in one pass.

Usage:
  python scripts/backfill_ashby_roles.py --dry-run           # preview
  python scripts/backfill_ashby_roles.py                     # apply
  python scripts/backfill_ashby_roles.py --only-empty        # skip companies already >=1 role
  python scripts/backfill_ashby_roles.py --limit 20          # sample run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.company_signal import CompanySignal
from app.models.company_job_role import CompanyJobRole
from app.extraction.adapters import ATS_ADAPTERS
from app.extraction.constants import ATSPlatform
from app.services.role_ingest import persist_job_role
from app.services.collection_orchestrator import _persist_signals_deduped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-empty", action="store_true",
                    help="Skip companies that already have >=1 role")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-jobs-per-company", type=int, default=40)
    args = ap.parse_args()

    db = SessionLocal()

    where_only_empty = (
        "AND NOT EXISTS (SELECT 1 FROM company_job_roles r WHERE r.company_id = c.id)"
        if args.only_empty else ""
    )
    limit_clause = f"LIMIT {int(args.limit)}" if args.limit else ""

    rows = db.execute(text(f"""
        SELECT DISTINCT c.id, c.name, c.domain,
               MIN(s.source_url) AS ashby_url
        FROM companies c
        JOIN company_signals s ON s.company_id = c.id
          AND s.signal_type = 'ashby_board_detected'
        WHERE c.domain IS NOT NULL AND c.domain != ''
          {where_only_empty}
        GROUP BY c.id, c.name, c.domain
        ORDER BY c.name
        {limit_clause}
    """)).fetchall()

    total = len(rows)
    print(f"Processing {total} companies with ashby_board_detected"
          f"{' (only empty)' if args.only_empty else ''}"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    print("-" * 78)

    adapter = ATS_ADAPTERS[ATSPlatform.ASHBY]
    stats = {
        "processed": 0,
        "resolved": 0,       # adapter.success=True
        "not_resolved": 0,   # likely false-positive detection
        "jobs_total": 0,
        "roles_persisted": 0,
        "signals_persisted": 0,
        "errors": 0,
    }

    for company_id, name, domain, ashby_url in rows:
        stats["processed"] += 1
        # Extract slug directly from the signal's URL — faster than slugify_company's
        # 5-variant loop and uses the slug the collector actually computed.
        hinted_slug = None
        if ashby_url and "ashbyhq.com/" in ashby_url:
            hinted_slug = ashby_url.rstrip("/").split("ashbyhq.com/")[-1]
        try:
            if hinted_slug:
                raw = adapter._ashby_query(hinted_slug)
                if raw:
                    result = adapter.parse_jobs(raw, hinted_slug, domain)
                else:
                    result = adapter.extract(domain=domain, company_name=name)
            else:
                result = adapter.extract(domain=domain, company_name=name)
        except Exception as e:
            stats["errors"] += 1
            print(f"  [{stats['processed']:>4d}/{total}] ERR   {name[:40]:40s} {domain:30s}  exception={type(e).__name__}")
            continue

        if not result.success or result.jobs_count == 0:
            stats["not_resolved"] += 1
            if stats["not_resolved"] <= 10 or stats["processed"] % 50 == 0:
                print(f"  [{stats['processed']:>4d}/{total}] SKIP  {name[:40]:40s} {domain:30s}  (no valid Ashby workspace)")
            continue

        stats["resolved"] += 1
        stats["jobs_total"] += result.jobs_count

        if args.dry_run:
            print(f"  [{stats['processed']:>4d}/{total}] DRY   {name[:40]:40s} jobs={result.jobs_count:>3d} "
                  f"depts={len(result.hiring_areas):>2d} url={result.careers_url}")
            continue

        # Persist signals
        source_type = "extraction_ats_api"
        new_signals = []
        if result.open_positions_count and result.open_positions_count > 0:
            sig_type = (
                "high_open_positions_count_detected"
                if result.open_positions_count >= 100
                else "open_positions_count_detected"
            )
            new_signals.append(CompanySignal(
                company_id=company_id,
                source_type=source_type,
                source_url=result.careers_url,
                signal_type=sig_type,
                signal_text=f"Open positions: {result.open_positions_count}",
                numeric_value=result.open_positions_count,
                confidence=result.confidence,
            ))
        if result.jobs_count > 0:
            new_signals.append(CompanySignal(
                company_id=company_id,
                source_type=source_type,
                source_url=result.careers_url,
                signal_type="job_cards_visible_detected",
                signal_text=f"Job listings: {result.jobs_count}",
                numeric_value=result.jobs_count,
                confidence=result.confidence,
            ))
        for area in result.hiring_areas[:8]:
            area_key = area.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
            new_signals.append(CompanySignal(
                company_id=company_id,
                source_type=source_type,
                source_url=result.careers_url,
                signal_type=f"{area_key}_hiring_detected",
                signal_text=f"Hiring area: {area}",
                confidence=0.8,
            ))
        if result.careers_url:
            new_signals.append(CompanySignal(
                company_id=company_id,
                source_type=source_type,
                source_url=result.careers_url,
                signal_type="careers_page_found",
                signal_text=f"Careers page: {result.careers_url}",
                confidence=0.95,
            ))

        persisted = _persist_signals_deduped(db, company_id, new_signals)
        stats["signals_persisted"] += persisted

        # Persist roles
        existing_urls = {
            u for (u,) in db.query(CompanyJobRole.source_url)
            .filter(CompanyJobRole.company_id == company_id).all() if u
        }
        roles_here = 0
        for job in (result.jobs or [])[:args.max_jobs_per_company]:
            if not job.title:
                continue
            src = job.job_url or result.careers_url
            if src and src in existing_urls:
                continue
            if persist_job_role(
                db,
                company_id=company_id,
                raw_title=job.title,
                source_url=src or None,
                role_location=job.location,
                role_department=job.department,
            ) is not None:
                roles_here += 1
                if src:
                    existing_urls.add(src)

        if roles_here:
            try:
                db.commit()
                stats["roles_persisted"] += roles_here
            except Exception as e:
                db.rollback()
                print(f"    commit FAILED for {name}: {e}")

        print(f"  [{stats['processed']:>4d}/{total}] OK    {name[:40]:40s} jobs={result.jobs_count:>3d} "
              f"roles={roles_here:>3d} signals={persisted:>2d}  url={result.careers_url}")

    db.close()

    print("-" * 78)
    print("BACKFILL SUMMARY")
    print("-" * 78)
    for k, v in stats.items():
        print(f"  {k:25s} {v}")
    if stats["processed"]:
        success_rate = stats["resolved"] / stats["processed"] * 100
        print(f"  {'resolve rate':25s} {success_rate:.1f}%")


if __name__ == "__main__":
    main()
