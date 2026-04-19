"""CLI entry point for resolving company domains in the Master Index.

Usage:
    python cli/resolve_domains.py --dry-run          # preview candidates
    python cli/resolve_domains.py                     # resolve + HTTP verify
    python cli/resolve_domains.py --skip-http         # resolve without HTTP checks

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
from app.master.domain_resolver import resolve_domains


def main():
    parser = argparse.ArgumentParser(
        description="Resolve company domains in the Master Index"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--skip-http", action="store_true", help="Skip HTTP verification")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = resolve_domains(
            db,
            verify_http=not args.skip_http,
            dry_run=args.dry_run,
        )

        print()
        print("=" * 55)
        if args.dry_run:
            print("  DOMAIN RESOLUTION (DRY RUN)")
            print("=" * 55)
            print(f"  Total companies:   {result['total_companies']}")
            print(f"  With candidates:   {result['with_candidates']}")
            if result.get("entries"):
                print()
                for e in result["entries"][:20]:
                    doms = ", ".join(c["domain"] for c in e["candidates"])
                    print(f"    {e['company']:40s} -> {doms}")
                remaining = len(result["entries"]) - 20
                if remaining > 0:
                    print(f"    ... and {remaining} more")
        else:
            print("  DOMAIN RESOLUTION COMPLETE")
            print("=" * 55)
            print(f"  Status:            {result['status']}")
            print(f"  Processed:         {result['total_processed']}")
            print(f"  Resolved:          {result['total_resolved']}")
            print(f"  Rejected:          {result['total_rejected']}")
            print(f"  Ambiguous:         {result['total_ambiguous']}")
            print(f"  Errors:            {result['total_errors']}")
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
