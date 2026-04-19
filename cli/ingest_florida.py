"""CLI entry point for ingesting Florida DOS corporate data into the Master Index.

Usage:
    # Scan file stats
    python cli/ingest_florida.py --file tools/data/florida_sample.txt --scan

    # Dry run (parse + preview, no DB writes)
    python cli/ingest_florida.py --file tools/data/florida_sample.txt --dry-run --limit 10

    # Import first 100 active companies
    python cli/ingest_florida.py --file tools/data/florida_sample.txt --limit 100

    # Import next 100 (offset)
    python cli/ingest_florida.py --file tools/data/florida_sample.txt --limit 100 --offset 100

    # Import only LLCs
    python cli/ingest_florida.py --file data.txt --limit 50 --filing-types FLAL,FORL

Run from the repo root directory.
"""

from __future__ import annotations

import argparse
import json
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
        description="Ingest Florida DOS corporate data into the Master Index"
    )
    parser.add_argument("--file", "-f", required=True, help="Path to Florida fixed-width data file")
    parser.add_argument("--limit", type=int, default=100, help="Max companies to import (default: 100)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records")
    parser.add_argument("--batch-id", help="Optional batch identifier")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without DB writes")
    parser.add_argument("--scan", action="store_true", help="Scan file and show statistics only")
    parser.add_argument("--filing-types", help="Comma-separated filing types (e.g., DOMP,FLAL)")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive companies")

    args = parser.parse_args()

    file_path = str((_ORIG_CWD / args.file).resolve())
    if not Path(file_path).exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    filing_types = set(args.filing_types.split(",")) if args.filing_types else None

    if args.scan:
        _scan(file_path)
        return

    from app.master.connectors.florida_ingestion import ingest_florida_file

    if args.dry_run:
        result = ingest_florida_file(
            db=None,
            file_path=file_path,
            limit=args.limit,
            offset=args.offset,
            active_only=not args.include_inactive,
            filing_types=filing_types,
            dry_run=True,
        )
        _print_dry_run(result)
        return

    db = SessionLocal()
    try:
        result = ingest_florida_file(
            db=db,
            file_path=file_path,
            limit=args.limit,
            offset=args.offset,
            batch_id=args.batch_id,
            active_only=not args.include_inactive,
            filing_types=filing_types,
        )

        print()
        print("=" * 55)
        print("  FLORIDA INGESTION COMPLETE")
        print("=" * 55)
        print(f"  Status:       {result['status']}")
        print(f"  Batch ID:     {result['batch_id']}")
        print(f"  Raw records:   {result['total_raw']}")
        print(f"  Normalized:    {result['total_normalized']}")
        print(f"  Inserted:      {result['total_inserted']}")
        print(f"  Updated:       {result['total_updated']}")
        print(f"  Skipped:       {result['total_skipped']}")
        print(f"  Errors:        {result['total_errors']}")
        print("=" * 55)

        if result["status"] not in ("success", "partial"):
            sys.exit(1)

    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _scan(file_path: str):
    from app.master.connectors.florida import count_records
    print(f"\nScanning: {file_path}")
    stats = count_records(file_path, active_only=False)
    print()
    print("=" * 55)
    print("  FLORIDA FILE SCAN")
    print("=" * 55)
    print(f"  Total records:     {stats['total']}")
    print()
    print("  By status:")
    for status, count in sorted(stats["by_status"].items()):
        label = "Active" if status == "A" else "Inactive" if status == "I" else status
        print(f"    {label}: {count}")
    print()
    print("  By filing type:")
    for ftype, count in sorted(stats["by_filing_type"].items(), key=lambda x: -x[1]):
        print(f"    {ftype:15s} {count}")
    print("=" * 55)


def _print_dry_run(result: dict):
    print()
    print("=" * 55)
    print("  FLORIDA INGESTION (DRY RUN)")
    print("=" * 55)
    print(f"  Total parsed:  {result['total_parsed']}")
    print()
    if result.get("sample"):
        for r in result["sample"]:
            print(f"  [{r['corp_number']}] {r['corp_name'][:40]:40s} {r['filing_type']:8s} {r['city'] or '':15s} {r['state'] or '':2s}")
            print(f"    -> normalized: {r['normalized']}")
        if result.get("remaining", 0) > 0:
            print(f"  ... and {result['remaining']} more")
    print("=" * 55)


if __name__ == "__main__":
    main()
