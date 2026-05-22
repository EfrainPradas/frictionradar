#!/usr/bin/env python3
"""Nightly Intelligence Refresh — run via cron at 1:00 AM.

Usage:
    python scripts/nightly_intelligence_refresh.py [--dry-run]

Cron entry:
    0 1 * * * cd /path/to/frictionradar/backend && python scripts/nightly_intelligence_refresh.py >> /var/log/frictionradar/nightly.log 2>&1
"""
import argparse
import os
import sys

# Ensure the backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.nightly_orchestrator import nightly_orchestrator


def main():
    parser = argparse.ArgumentParser(description="Nightly Intelligence Refresh Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] Nightly Intelligence Refresh would execute the following steps:")
        print("  1. ATS refresh — re-probe detected ATS boards")
        print("  2. Careers page refresh — re-capture known careers URLs")
        print("  3. Signal extraction — re-classify roles, update hiring patterns")
        print("  4. Pain recomputation — re-score all companies")
        print("  5. Heatmap regeneration — rebuild sector×function grid")
        print("  6. Candidate alignment — re-align VIP candidates")
        print("  7. VIP opportunity regeneration — refresh VIP opportunities")
        print("  8. Snapshot persistence — store temporal snapshots")
        print("  9. Temporal trend tracking — compute deltas and velocity")
        print("  10. Delta computation — compare current vs previous scores")
        return

    db = SessionLocal()
    try:
        summary = nightly_orchestrator.run(db)
        print(f"\nNightly run complete: {summary['run_id']}")
        print(f"Total time: {summary.get('total_elapsed_s', 0):.1f}s")
        print(f"Errors: {summary.get('error_count', 0)}")

        for step_name, step_result in summary.get("steps", {}).items():
            status = step_result.get("status", "unknown")
            elapsed = step_result.get("elapsed_s", 0)
            emoji = "✓" if status == "ok" else "✗"
            print(f"  {emoji} {step_name}: {status} ({elapsed:.1f}s)")

        if summary.get("errors"):
            print("\nErrors:")
            for err in summary["errors"]:
                print(f"  - {err['step']}: {err['error']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()