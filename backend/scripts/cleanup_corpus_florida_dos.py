"""Corpus cleanup: remove florida_dos LLC noise (non-eligible only).

Decision justification:
  - Of 540 florida_dos companies, only 1 is eligible (MILLION VENTURES LLC).
  - Ratio 540:1. Visual inspection confirms micro-LLCs, contratistas,
    domain-squatting errors (e.g. "FOUR SEASONS PRESTIGE TRUCKING LLC" ->
    fourseasons.com).
  - Pipeline is correctly discarding them; they are not NovaWork targets.

Deletes cascade (verified FKs):
  collection_runs, company_job_roles, company_role_signals, company_signals,
  friction_scores, hiring_patterns, opportunity_hypotheses, pipeline_entries,
  review_queue (all ON DELETE CASCADE)
  company_master.linked_company_id (ON DELETE SET NULL)

Usage:
  python scripts/cleanup_corpus_florida_dos.py --dry-run
  python scripts/cleanup_corpus_florida_dos.py --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.positioning_engine import compute_eligibility_snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    print("Loading eligibility snapshot (~30s)...")
    snap = compute_eligibility_snapshot(db)
    eligible_ids = {str(c["company_id"]) for c in snap["by_company"] if c.get("eligible")}

    candidates = db.execute(text("""
        SELECT id::text AS id, name, domain
        FROM companies
        WHERE source_added_from = 'florida_dos'
        ORDER BY name
    """)).fetchall()

    to_delete = [c for c in candidates if c.id not in eligible_ids]
    to_preserve = [c for c in candidates if c.id in eligible_ids]

    print(f"\nflorida_dos total:     {len(candidates)}")
    print(f"florida_dos preserved: {len(to_preserve)} (elegibles)")
    print(f"florida_dos to delete: {len(to_delete)}")
    print()
    print("PRESERVED:")
    for c in to_preserve:
        print(f"  - {c.name} ({c.domain})")

    print(f"\nSample 10 of {len(to_delete)} to delete:")
    for c in to_delete[:10]:
        print(f"  - {c.name[:50]:50s} {c.domain}")

    cascades = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM company_signals WHERE company_id::text = ANY(:ids)) AS signals,
          (SELECT COUNT(*) FROM company_job_roles WHERE company_id::text = ANY(:ids)) AS roles,
          (SELECT COUNT(*) FROM collection_runs WHERE company_id::text = ANY(:ids)) AS runs,
          (SELECT COUNT(*) FROM friction_scores WHERE company_id::text = ANY(:ids)) AS scores,
          (SELECT COUNT(*) FROM hiring_patterns WHERE company_id::text = ANY(:ids)) AS patterns,
          (SELECT COUNT(*) FROM opportunity_hypotheses WHERE company_id::text = ANY(:ids)) AS hyps,
          (SELECT COUNT(*) FROM pipeline_entries WHERE company_id::text = ANY(:ids)) AS pipe,
          (SELECT COUNT(*) FROM review_queue WHERE company_id::text = ANY(:ids)) AS review
    """), {"ids": [c.id for c in to_delete]}).first()

    print(f"\nCascade impact:")
    print(f"  company_signals:      {cascades.signals}")
    print(f"  company_job_roles:    {cascades.roles}")
    print(f"  collection_runs:      {cascades.runs}")
    print(f"  friction_scores:      {cascades.scores}")
    print(f"  hiring_patterns:      {cascades.patterns}")
    print(f"  opportunity_hypotheses: {cascades.hyps}")
    print(f"  pipeline_entries:     {cascades.pipe}")
    print(f"  review_queue:         {cascades.review}")

    if not args.execute:
        print("\n[DRY RUN] No changes. Re-run with --execute to delete.")
        db.close()
        return

    print("\nExecuting delete...")
    result = db.execute(
        text("DELETE FROM companies WHERE id::text = ANY(:ids)"),
        {"ids": [c.id for c in to_delete]},
    )
    db.commit()
    print(f"Deleted {result.rowcount} rows from companies (cascades applied).")

    remaining = db.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    print(f"Corpus now: {remaining} companies")

    db.close()


if __name__ == "__main__":
    main()
