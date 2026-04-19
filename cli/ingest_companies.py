"""CLI entry point for ingesting company JSON files into the Master Index.

Usage:
    python cli/ingest_companies.py --input tools/data/utah_companies.json
    python cli/ingest_companies.py --input cli/example_input.json --batch-id my_test_batch
    python cli/ingest_companies.py --input companies.json --dry-run

Run from the repo root directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Resolve CWD-relative paths before changing directory
_ORIG_CWD = Path.cwd()

# Add backend to path and load its .env
_BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Ensure Settings finds the backend .env
os.chdir(_BACKEND)

from app.db.session import SessionLocal
import app.models  # noqa: F401 — register all models so FK references resolve
from app.master.ingestion import ingest_json_file


def main():
    parser = argparse.ArgumentParser(
        description="Ingest company JSON into the Master Index"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to JSON input file",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Optional batch identifier (auto-generated if omitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and normalize only — do not write to company_master",
    )

    args = parser.parse_args()

    input_path = (_ORIG_CWD / args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    print(f"Ingesting: {input_path}")
    print(f"Batch ID:  {args.batch_id or '(auto)'}")

    if args.dry_run:
        _dry_run(input_path)
        return

    db = SessionLocal()
    try:
        result = ingest_json_file(
            db,
            str(input_path),
            batch_id=args.batch_id,
        )
        print()
        print("=" * 50)
        print("  INGESTION COMPLETE")
        print("=" * 50)
        print(f"  Status:       {result['status']}")
        print(f"  Batch ID:     {result['batch_id']}")
        print(f"  Source:        {result['source_file']}")
        print(f"  Raw records:   {result['total_raw']}")
        print(f"  Normalized:    {result['total_normalized']}")
        print(f"  Inserted:      {result['total_inserted']}")
        print(f"  Updated:       {result['total_updated']}")
        print(f"  Skipped:       {result['total_skipped']}")
        print(f"  Errors:        {result['total_errors']}")
        print("=" * 50)

        if result["status"] != "success":
            sys.exit(1)

    except Exception as e:
        print(f"\nFATAL: {e}")
        sys.exit(1)
    finally:
        db.close()


def _dry_run(path: Path):
    """Parse and normalize without writing to DB. Shows what would happen."""
    from app.master.canonical import normalize_company_name
    from app.master.ingestion import _clean_domain, _clean_legal_name, _extract_state, _load_json

    entries = _load_json(path)
    print(f"\nParsed {len(entries)} entries\n")

    for i, entry in enumerate(entries):
        raw_name = (entry.get("company_name") or entry.get("name") or "").strip()
        raw_domain = (entry.get("domain") or "").strip()
        location = (entry.get("location") or entry.get("hq") or "").strip()

        legal = _clean_legal_name(raw_name) if raw_name else "(none)"
        normalized = normalize_company_name(legal) if legal != "(none)" else "(none)"
        domain = _clean_domain(raw_domain) or "(invalid)"
        state = _extract_state(location) or "?"

        print(f"  [{i:3d}] {raw_name:40s} -> {normalized:30s}  dom={domain:25s}  st={state}")

    print(f"\nTotal: {len(entries)} entries ready for ingestion")


if __name__ == "__main__":
    main()
