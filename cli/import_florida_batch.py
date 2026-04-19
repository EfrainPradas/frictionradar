"""CLI for importing filtered Florida staged batches into Company Master Index.

Usage:
    # Dry-run first 100 (default filters)
    python cli/import_florida_batch.py --dry-run

    # Import first 100 domestic companies
    python cli/import_florida_batch.py --domestic --batch-size 100

    # Import next 100
    python cli/import_florida_batch.py --domestic --batch-size 100 --offset 100

    # Import only corporations
    python cli/import_florida_batch.py --entity-types corporation --batch-size 250

    # Import all domestic LLCs + corps
    python cli/import_florida_batch.py --domestic --entity-types corporation,llc --batch-size 0

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
        description="Import filtered Florida staged batches into Company Master Index"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size (default: 100, 0=all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N candidates")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")

    # Filters (same as select_florida_batch)
    parser.add_argument("--entity-types", help="Comma-separated: corporation,llc,nonprofit")
    parser.add_argument("--filing-types", help="Comma-separated: DOMP,FLAL,...")
    parser.add_argument("--domestic", action="store_true", help="Domestic filings only")
    parser.add_argument("--state", help="Jurisdiction state filter")
    parser.add_argument("--has-fei", action="store_true", help="Only with FEI/EIN")
    parser.add_argument("--include-irrelevant", action="store_true", help="Include AGENT/TRUST")
    parser.add_argument("--run-id", help="Specific staging run ID")

    args = parser.parse_args()

    from app.master.connectors.florida_batch_selector import BatchFilter
    from app.master.connectors.florida_import import import_florida_batch

    filters = BatchFilter(
        entity_types=set(args.entity_types.split(",")) if args.entity_types else None,
        filing_types=set(args.filing_types.split(",")) if args.filing_types else None,
        domestic_only=args.domestic,
        exclude_irrelevant=not args.include_irrelevant,
        state=args.state,
        has_fei=args.has_fei,
        run_id=args.run_id,
    )

    batch_size = args.batch_size if args.batch_size > 0 else 999999

    db = SessionLocal()
    try:
        result = import_florida_batch(
            db, filters,
            batch_size=batch_size,
            offset=args.offset,
            dry_run=args.dry_run,
        )

        print()
        print("=" * 60)
        if args.dry_run:
            print("  FLORIDA IMPORT (DRY RUN)")
            print("=" * 60)
            print(f"  Total candidates:    {result['total_candidates']}")
            print(f"  Batch count:         {result['batch_count']}")
            print(f"  Would import:        {result['would_import']}")
            print(f"  Already imported:    {result['already_imported']}")
            print(f"  Has more:            {'yes' if result['has_more'] else 'no'}")
            if result["records"]:
                print()
                shown = 0
                for r in result["records"]:
                    if shown >= 20:
                        print(f"  ... and {len(result['records']) - 20} more")
                        break
                    marker = "NEW" if r["would_import"] else "DONE" if r["already_imported"] else r["action"]
                    print(f"    [{marker:4s}] {r['legal_name'][:50]:50s} {r['filing_type'] or '':8s}")
                    shown += 1
        else:
            print("  FLORIDA IMPORT COMPLETE")
            print("=" * 60)
            print(f"  Status:              {result['status']}")
            print(f"  Total candidates:    {result['total_candidates']}")
            print(f"  Processed:           {result['processed']}")
            print(f"  Inserted:            {result['inserted']}")
            print(f"  Updated:             {result['updated']}")
            print(f"  Skipped:             {result['skipped']}")
            print(f"  Errors:              {result['errors']}")
            if result.get("has_more"):
                print(f"  Has more:            yes (next: --offset {result['next_offset']})")
        print("=" * 60)

    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
