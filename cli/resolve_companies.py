"""CLI entry point for running entity resolution on the Company Master Index.

Usage:
    python cli/resolve_companies.py --dry-run        # preview matches only
    python cli/resolve_companies.py                   # find + auto-merge
    python cli/resolve_companies.py --no-auto-merge   # find candidates, don't merge

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
from app.master.resolver import run_resolution


def main():
    parser = argparse.ArgumentParser(
        description="Run entity resolution on the Company Master Index"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matches without writing anything",
    )
    parser.add_argument(
        "--no-auto-merge",
        action="store_true",
        help="Find candidates but do not auto-merge high-confidence pairs",
    )

    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run_resolution(
            db,
            auto_merge=not args.no_auto_merge,
            dry_run=args.dry_run,
        )

        print()
        print("=" * 55)
        print("  ENTITY RESOLUTION " + ("(DRY RUN)" if args.dry_run else "COMPLETE"))
        print("=" * 55)
        print(f"  Status:            {result['status']}")
        print(f"  Total records:     {result['total_records']}")
        print(f"  Total candidates:  {result['total_candidates']}")

        if args.dry_run:
            print(f"  Would auto-merge:  {result.get('would_auto_merge', 0)}")
            print(f"  Would flag:        {result.get('would_flag', 0)}")
            if result.get("pairs"):
                print()
                print("  Candidate pairs:")
                for p in result["pairs"]:
                    marker = "AUTO" if p["would_auto_merge"] else "FLAG"
                    print(
                        f"    [{marker}] {p['confidence']:.3f}  "
                        f"{p['company_a']} <-> {p['company_b']}"
                    )
                    print(f"           {p['reason_code']}: {p['reason_detail']}")
        else:
            print(f"  Auto-merged:       {result.get('auto_merged', 0)}")
            print(f"  Flagged for review:{result.get('flagged_for_review', 0)}")

        print("=" * 55)

    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
