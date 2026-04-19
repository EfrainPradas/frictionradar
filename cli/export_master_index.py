"""CLI entry point for exporting the Company Master Index downstream dataset.

Usage:
    python cli/export_master_index.py --summary
    python cli/export_master_index.py --output output/master_input.json
    python cli/export_master_index.py --output output/with_domains.json --has-domain
    python cli/export_master_index.py --output output/needs_domain.json --no-domain
    python cli/export_master_index.py --output output/ready.json --status ready_for_careers_discovery
    python cli/export_master_index.py --sample 5

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
from app.master.downstream import (
    export_downstream_json,
    get_downstream_dataset,
    get_downstream_summary,
)


def main():
    parser = argparse.ArgumentParser(
        description="Export Company Master Index downstream dataset"
    )
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--summary", action="store_true", help="Show summary stats only")
    parser.add_argument("--sample", type=int, help="Show N sample records")
    parser.add_argument(
        "--status",
        choices=[
            "ready_for_careers_discovery",
            "ready_for_domain_resolution",
            "needs_domain",
            "needs_review",
        ],
        help="Filter by readiness status",
    )
    parser.add_argument("--has-domain", action="store_true", help="Only companies with resolved domain")
    parser.add_argument("--no-domain", action="store_true", help="Only companies without domain")
    parser.add_argument("--high-confidence", action="store_true", help="Only high confidence records")
    parser.add_argument("--state", help="Filter by jurisdiction state (2-letter code)")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.summary:
            _show_summary(db)
        elif args.sample:
            _show_sample(db, args)
        elif args.output:
            _export(db, args)
        else:
            _show_summary(db)
    except Exception as e:
        print(f"\nFATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def _show_summary(db):
    s = get_downstream_summary(db)
    print()
    print("=" * 60)
    print("  MASTER INDEX — DOWNSTREAM DATASET SUMMARY")
    print("=" * 60)
    print(f"  Total companies:               {s.total_companies}")
    print(f"  Ready for careers discovery:    {s.ready_for_careers_discovery}")
    print(f"  Ready for domain resolution:    {s.ready_for_domain_resolution}")
    print(f"  Needs domain:                   {s.needs_domain}")
    print(f"  Needs review:                   {s.needs_review}")
    print(f"  With external IDs:              {s.with_external_ids}")
    print(f"  High confidence (>=0.70):        {s.high_confidence}")
    print()
    if s.by_state:
        print("  By state:")
        for state, count in list(s.by_state.items())[:10]:
            print(f"    {state}:  {count}")
    print("=" * 60)


def _show_sample(db, args):
    has_domain = True if args.has_domain else (False if args.no_domain else None)
    dataset = get_downstream_dataset(
        db,
        status_filter=args.status,
        has_domain=has_domain,
        high_confidence_only=args.high_confidence,
        jurisdiction=args.state,
        limit=args.sample,
    )

    print(f"\nSample ({len(dataset)} records):\n")
    for r in dataset:
        ids_str = ", ".join(f"{k}={v}" for k, v in r.external_ids.items()) if r.external_ids else "-"
        print(f"  {r.legal_name:40s}  dom={r.primary_domain or '(none)':25s}  st={r.jurisdiction_state or '?'}")
        print(f"    status={r.readiness_status}  conf={r.source_confidence:.2f}  ids=[{ids_str}]")
        print()


def _export(db, args):
    has_domain = True if args.has_domain else (False if args.no_domain else None)
    output_path = str((_ORIG_CWD / args.output).resolve())

    result = export_downstream_json(
        db,
        output_path,
        status_filter=args.status,
        has_domain=has_domain,
        high_confidence_only=args.high_confidence,
    )

    print()
    print("=" * 60)
    print("  EXPORT COMPLETE")
    print("=" * 60)
    print(f"  Output:   {result['output_path']}")
    print(f"  Exported: {result['total_exported']} companies")
    s = result["summary"]
    print(f"  Ready:    {s['ready_for_careers_discovery']} for careers discovery")
    print(f"  Missing:  {s['needs_domain']} need domain")
    print("=" * 60)


if __name__ == "__main__":
    main()
