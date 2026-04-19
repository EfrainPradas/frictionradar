"""CLI for filtering and previewing Florida staged company batches.

Usage:
    # Show available filter options and counts
    python cli/select_florida_batch.py --stats

    # Preview first 100 (default filters: exclude AGENT/TRUST)
    python cli/select_florida_batch.py --preview --batch-size 100

    # Preview domestic LLCs and corps only
    python cli/select_florida_batch.py --preview --domestic --entity-types corporation,llc --batch-size 250

    # Preview only companies with FEI/EIN
    python cli/select_florida_batch.py --preview --has-fei --batch-size 50

    # Preview next page
    python cli/select_florida_batch.py --preview --batch-size 100 --offset 100

    # Compact list (just names)
    python cli/select_florida_batch.py --preview --batch-size 20 --compact

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
        description="Filter and preview Florida staged company batches"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stats", action="store_true", help="Show filter options and counts")
    mode.add_argument("--preview", action="store_true", help="Preview a filtered batch")

    # Filters
    parser.add_argument("--entity-types", help="Comma-separated: corporation,llc,nonprofit,limited_partnership")
    parser.add_argument("--filing-types", help="Comma-separated: DOMP,FLAL,DOMNP,...")
    parser.add_argument("--domestic", action="store_true", help="Domestic filings only")
    parser.add_argument("--state", help="Jurisdiction state filter (e.g., FL)")
    parser.add_argument("--has-fei", action="store_true", help="Only companies with FEI/EIN")
    parser.add_argument("--include-irrelevant", action="store_true", help="Include AGENT/TRUST types")
    parser.add_argument("--run-id", help="Specific staging run ID")

    # Batch
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size (default: 100)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N candidates")

    # Display
    parser.add_argument("--compact", action="store_true", help="Compact output (names only)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip duplicate check against master")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.stats:
            _show_stats(db, args)
        elif args.preview:
            _preview(db, args)
    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _show_stats(db, args):
    from app.master.connectors.florida_batch_selector import get_filter_stats

    stats = get_filter_stats(db, run_id=args.run_id)

    print()
    print("=" * 60)
    print("  FLORIDA STAGED DATA — FILTER OPTIONS")
    print("=" * 60)
    print(f"  Total staged:             {stats['total_staged']}")
    print(f"  After exclude irrelevant: {stats['after_exclude_irrelevant']}")
    print(f"  Domestic:                 {stats['domestic']}")
    print(f"  Foreign:                  {stats['foreign']}")
    print(f"  Irrelevant (AGENT/TRUST): {stats['irrelevant']}")
    print(f"  With FEI/EIN:             {stats['with_fei']}")
    print()
    print("  By entity type:")
    for et, cnt in stats["by_entity_type"].items():
        print(f"    {et:25s}  {cnt:5d}")
    print()
    print("  By filing type:")
    for ft, cnt in stats["by_filing_type"].items():
        print(f"    {ft:15s}  {cnt:5d}")
    print()
    print("  By state (top 10):")
    for st, cnt in stats["by_state"].items():
        print(f"    {st:5s}  {cnt:5d}")
    print("=" * 60)


def _preview(db, args):
    from app.master.connectors.florida_batch_selector import BatchFilter, select_batch

    filters = BatchFilter(
        entity_types=set(args.entity_types.split(",")) if args.entity_types else None,
        filing_types=set(args.filing_types.split(",")) if args.filing_types else None,
        domestic_only=args.domestic,
        exclude_irrelevant=not args.include_irrelevant,
        state=args.state,
        has_fei=args.has_fei,
        run_id=args.run_id,
    )

    result = select_batch(
        db, filters,
        batch_size=args.batch_size,
        offset=args.offset,
        check_duplicates=not args.no_dedup,
    )

    print()
    print("=" * 70)
    print("  FLORIDA BATCH PREVIEW")
    print("=" * 70)
    print(f"  Total staged:        {result['total_staged']}")
    print(f"  After filters:       {result['total_candidates']}")
    print(f"  Batch size:          {result['batch_size']}")
    print(f"  Offset:              {result['offset']}")
    print(f"  This batch:          {result['batch_count']}")
    print(f"  New companies:       {result['new_companies']}")
    print(f"  Already in master:   {result['already_in_master']}")
    print(f"  Has more:            {'yes' if result['has_more'] else 'no'}")
    if result.get("next_offset"):
        print(f"  Next offset:         {result['next_offset']}")
    print()
    print("  Filters: " + " | ".join(result["filters_applied"]))
    print()

    if args.compact:
        for r in result["records"]:
            dup = " [DUP]" if r["existing_in_master"] else ""
            print(f"    {r['legal_name'][:55]:55s} {r['filing_type'] or '':8s}{dup}")
    else:
        for r in result["records"]:
            dup_marker = ""
            if r["existing_in_master"]:
                dup_marker = f"  [DUP -> {r['match_master_name']}]"
            fei = f"  fei={r['fei_number']}" if r.get("fei_number") else ""
            print(
                f"  [{r['corp_number'] or '?':14s}] "
                f"{r['legal_name'][:42]:42s} "
                f"{r['entity_type'] or '':15s} "
                f"{r['jurisdiction_state'] or '':2s}"
                f"{fei}{dup_marker}"
            )
            print(f"    -> {r['normalized_name']}")

    if not result["records"]:
        print("    (no records match filters)")

    print()
    if result["has_more"]:
        next_cmd = f"--offset {result['next_offset']}"
        print(f"  Next page: add {next_cmd}")
    print("=" * 70)


if __name__ == "__main__":
    main()
