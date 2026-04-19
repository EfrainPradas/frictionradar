"""CLI entry point for enriching Company Master Index with external identifiers.

Usage:
    python cli/enrich_companies.py --source edgar --dry-run
    python cli/enrich_companies.py --source edgar
    python cli/enrich_companies.py --source csv --file data/identifiers.csv
    python cli/enrich_companies.py --source sam
    python cli/enrich_companies.py --summary

Run from the repo root directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ORIG_CWD = Path.cwd()
_BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

import app.models  # noqa: F401
from app.db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(
        description="Enrich Company Master Index with external identifiers"
    )
    parser.add_argument(
        "--source", choices=["edgar", "sam", "csv"], help="Enrichment source"
    )
    parser.add_argument("--file", help="Input file for CSV adapter")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--summary", action="store_true", help="Show current enrichment stats")
    parser.add_argument("--limit", type=int, help="Max companies to process")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.summary:
            _show_summary(db)
            return

        if not args.source:
            parser.error("--source is required (unless --summary)")

        adapters = _build_adapters(args)
        _run(db, adapters, args)

    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _build_adapters(args):
    adapters = []
    if args.source == "edgar":
        from app.master.enrichment.edgar_adapter import EdgarAdapter
        adapters.append(EdgarAdapter())
    elif args.source == "sam":
        from app.master.enrichment.sam_adapter import SamAdapter
        adapter = SamAdapter()
        if not adapter.is_available():
            print("WARNING: SAM_API_KEY not set. SAM adapter will return empty results.")
        adapters.append(adapter)
    elif args.source == "csv":
        if not args.file:
            print("ERROR: --file is required for csv source")
            sys.exit(1)
        file_path = (_ORIG_CWD / args.file).resolve()
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)
        from app.master.enrichment.csv_adapter import CsvAdapter
        adapter = CsvAdapter(str(file_path))
        adapter.load()
        adapters.append(adapter)
    return adapters


def _run(db, adapters, args):
    from app.master.enrichment.orchestrator import run_enrichment
    from app.master.models import CompanyMaster

    master_ids = None
    if args.limit:
        masters = (
            db.query(CompanyMaster)
            .filter(CompanyMaster.entity_status != "merged")
            .limit(args.limit)
            .all()
        )
        master_ids = [m.id for m in masters]

    result = run_enrichment(
        db, adapters, master_ids=master_ids, dry_run=args.dry_run,
    )

    print()
    print("=" * 55)
    if args.dry_run:
        print("  ENRICHMENT (DRY RUN)")
        print("=" * 55)
        print(f"  Total companies:   {result['total_companies']}")
        print(f"  With identifiers:  {result.get('companies_with_ids', 0)}")
        if result.get("entries"):
            print()
            for e in result["entries"][:15]:
                ids_str = ", ".join(
                    f"{i['id_type']}={i['id_value']}" for i in e["identifiers"]
                )
                print(f"    {e['company']:35s}  {ids_str}")
            remaining = len(result["entries"]) - 15
            if remaining > 0:
                print(f"    ... and {remaining} more")
    else:
        print("  ENRICHMENT COMPLETE")
        print("=" * 55)
        print(f"  Status:            {result['status']}")
        print(f"  Processed:         {result['total_processed']}")
        print(f"  IDs added:         {result['total_ids_added']}")
        print(f"  IDs skipped:       {result['total_ids_skipped']}")
        print(f"  Errors:            {result['total_errors']}")
    print("=" * 55)


def _show_summary(db):
    from app.master.enrichment.orchestrator import get_enrichment_summary
    summary = get_enrichment_summary(db)

    print()
    print("=" * 55)
    print("  ENRICHMENT SUMMARY")
    print("=" * 55)
    print(f"  Total companies:       {summary['total_companies']}")
    print(f"  With any external ID:  {summary['companies_with_any_id']}")
    print(f"  Without external IDs:  {summary['companies_without_ids']}")

    if summary["by_type"]:
        print()
        print("  By identifier type:")
        for id_type, info in sorted(summary["by_type"].items()):
            print(f"    {id_type:25s}  {info['count']:4d} IDs across {info['companies']:3d} companies")
    else:
        print("  No external identifiers found yet.")
    print("=" * 55)


if __name__ == "__main__":
    main()
