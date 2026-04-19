"""CLI entry point for parsing and staging Florida DOS data.

Usage:
    # Dry run — parse and preview
    python cli/stage_florida.py --file tools/data/raw/florida/20260413c.txt --dry-run --limit 20

    # Stage first 100 records
    python cli/stage_florida.py --file tools/data/raw/florida/20260413c.txt --limit 100

    # Stage all records
    python cli/stage_florida.py --file tools/data/raw/florida/20260413c.txt --limit 0

    # Inspect staged records from a run
    python cli/stage_florida.py --inspect <import_run_id>

    # Show staging summary for a run
    python cli/stage_florida.py --summary <import_run_id>

    # List recent staging runs
    python cli/stage_florida.py --runs

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
        description="Parse and stage Florida DOS data (no master index import)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", help="Path to Florida fixed-width data file")
    group.add_argument("--inspect", metavar="RUN_ID", help="Inspect staged records from a run")
    group.add_argument("--summary", metavar="RUN_ID", help="Show summary for a staging run")
    group.add_argument("--runs", action="store_true", help="List recent staging runs")

    parser.add_argument("--limit", type=int, default=100, help="Max records to parse (0=all, default: 100)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records")
    parser.add_argument("--batch-id", help="Optional batch identifier")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without staging")
    parser.add_argument("--filing-types", help="Comma-separated filing types (e.g., DOMP,FLAL)")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive companies")
    parser.add_argument("--rows", type=int, default=20, help="Rows to show in --inspect (default: 20)")

    args = parser.parse_args()

    if args.runs:
        _list_runs()
        return

    if args.inspect:
        _inspect(args.inspect, args.rows, args.offset)
        return

    if args.summary:
        _show_summary(args.summary)
        return

    # Stage
    _stage(args)


def _stage(args):
    from app.master.connectors.florida_staging import stage_florida_file

    file_path = str((_ORIG_CWD / args.file).resolve())
    if not Path(file_path).exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    filing_types = set(args.filing_types.split(",")) if args.filing_types else None
    limit = args.limit if args.limit > 0 else None

    if args.dry_run:
        result = stage_florida_file(
            db=None, file_path=file_path,
            limit=limit or 100, offset=args.offset,
            active_only=not args.include_inactive,
            filing_types=filing_types,
            dry_run=True,
        )
        _print_dry_run(result)
        return

    db = SessionLocal()
    try:
        result = stage_florida_file(
            db=db, file_path=file_path,
            limit=limit, offset=args.offset,
            batch_id=args.batch_id,
            active_only=not args.include_inactive,
            filing_types=filing_types,
        )

        print()
        print("=" * 60)
        print("  FLORIDA STAGING COMPLETE")
        print("=" * 60)
        print(f"  Status:        {result['status']}")
        print(f"  Batch ID:      {result['batch_id']}")
        print(f"  Run ID:        {result['import_run_id']}")
        print(f"  Parsed:        {result['total_parsed']}")
        print(f"  Raw staged:    {result['total_raw']}")
        print(f"  Normalized:    {result['total_normalized']}")
        print(f"  Skipped:       {result['total_skipped']}")
        print(f"  Errors:        {result['total_errors']}")
        print()
        print(f"  {result['note']}")
        print()
        print(f"  Inspect with: python cli/stage_florida.py --inspect {result['import_run_id']}")
        print(f"  Summary with: python cli/stage_florida.py --summary {result['import_run_id']}")
        print("=" * 60)

    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _inspect(run_id: str, limit: int, offset: int):
    from app.master.connectors.florida_staging import inspect_staged

    db = SessionLocal()
    try:
        records = inspect_staged(db, run_id, limit=limit, offset=offset)
        print(f"\nStaged records (run {run_id[:8]}..., showing {len(records)}):\n")
        for r in records:
            fei_str = f"  fei={r['fei_number']}" if r.get("fei_number") else ""
            print(
                f"  [{r['corp_number'] or '?':14s}] "
                f"{r['legal_name'][:45]:45s} "
                f"{r['filing_type'] or '':8s} "
                f"{r['city'] or '':15s} "
                f"{r['jurisdiction_state'] or '':2s}"
                f"{fei_str}"
            )
            print(f"    -> {r['normalized_name']}")
        if not records:
            print("  (no records found)")
    finally:
        db.close()


def _show_summary(run_id: str):
    from app.master.connectors.florida_staging import inspect_summary

    db = SessionLocal()
    try:
        s = inspect_summary(db, run_id)
        if "error" in s:
            print(f"\nERROR: {s['error']}")
            sys.exit(1)

        print()
        print("=" * 60)
        print("  FLORIDA STAGING SUMMARY")
        print("=" * 60)
        print(f"  Run ID:        {s['import_run_id'][:8]}...")
        print(f"  Batch ID:      {s['batch_id']}")
        print(f"  Status:        {s['status']}")
        print(f"  Raw staged:    {s['total_raw']}")
        print(f"  Normalized:    {s['total_normalized']}")
        print(f"  Skipped:       {s['total_skipped']}")
        print(f"  With FEI/EIN:  {s['with_fei_number']}")
        print()
        print("  By filing type:")
        for ft, cnt in s["by_filing_type"].items():
            print(f"    {ft:15s}  {cnt}")
        print()
        print("  By state:")
        for st, cnt in s["by_state"].items():
            print(f"    {st or '(empty)':15s}  {cnt}")
        print("=" * 60)
    finally:
        db.close()


def _list_runs():
    from app.master.staging_models import ImportRun

    db = SessionLocal()
    try:
        runs = (
            db.query(ImportRun)
            .filter(ImportRun.source_type == "florida_sunbiz")
            .order_by(ImportRun.created_at.desc())
            .limit(10)
            .all()
        )
        print()
        print("=" * 75)
        print("  RECENT FLORIDA STAGING RUNS")
        print("=" * 75)
        if not runs:
            print("  (no runs found)")
        for r in runs:
            ts = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "?"
            print(
                f"  [{r.status:8s}] {r.batch_id:35s} "
                f"raw={r.total_raw or 0:5d}  norm={r.total_normalized or 0:5d}  "
                f"{ts}"
            )
            print(f"             ID: {r.id}")
        print("=" * 75)
    finally:
        db.close()


def _print_dry_run(result: dict):
    print()
    print("=" * 60)
    print("  FLORIDA STAGING (DRY RUN)")
    print("=" * 60)
    print(f"  Total parsed:  {result['total_parsed']}")
    print()
    if result.get("sample"):
        for r in result["sample"]:
            fei_str = f"  fei={r['fei']}" if r.get("fei") else ""
            print(
                f"  [{r['corp_number']:14s}] "
                f"{r['corp_name'][:42]:42s} "
                f"{r['filing_type']:8s} "
                f"{r['city'] or '':15s} "
                f"{r['state'] or '':2s}"
                f"{fei_str}"
            )
            print(f"    -> {r['normalized']}")
        if result.get("remaining", 0) > 0:
            print(f"\n  ... and {result['remaining']} more")
    print("=" * 60)


if __name__ == "__main__":
    main()
