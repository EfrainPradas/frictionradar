"""
Signal type normalization script.

Renames legacy/ghost signal_types in the database to their canonical equivalents.
Run once after deploying the scoring_rules contract fix.

Usage:
    python -m scripts.normalize_signal_types --dry-run   # preview changes
    python -m scripts.normalize_signal_types --execute    # apply changes
"""

from __future__ import annotations

import argparse
import sys

# Mapping of old (ghost) signal_types to their canonical replacements.
# These signal_types were referenced in scoring_rules but never emitted by
# any collector. After the 2026-05-18 contract fix, the scoring rules
# no longer reference them. This script renames any existing rows in
# the database that use these ghost types to the canonical equivalent,
# so they contribute to scoring under the new rules.
SIGNAL_TYPE_MIGRATIONS: dict[str, str] = {
    # Ghost → Canonical replacement
    "data_hiring_detected": "analytics_role_detected",
    "revops_role_detected": "revops_language_detected",
    "software_engineering_hiring_detected": "technology_hiring_detected",
    "manufacturing_engineering_hiring_detected": "manufacturing_hiring_detected",
    # process_language_detected is special: no emitter ever produced it,
    # and the rule is now keyword-only. No migration needed — these rows
    # would have signal_text containing the keywords, so they still match
    # via the keyword path. But if any exist, rename to the closest canonical.
    "process_language_detected": "revops_language_detected",
}


def dry_run() -> list[dict]:
    """Preview changes that would be made.

    Returns a list of dicts with table, old_type, new_type, and count.
    Requires a running database connection.
    """
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
    except ImportError:
        print("ERROR: Cannot import database modules. Run from the backend directory.")
        sys.exit(1)

    engine = create_engine(settings.DATABASE_URL)
    results = []

    with engine.connect() as conn:
        for old_type, new_type in SIGNAL_TYPE_MIGRATIONS.items():
            count = conn.execute(
                text("SELECT COUNT(*) FROM company_signals WHERE signal_type = :old"),
                {"old": old_type},
            ).scalar()
            if count > 0:
                results.append({
                    "table": "company_signals",
                    "old_type": old_type,
                    "new_type": new_type,
                    "count": count,
                })

            # Also check company_role_signals if it exists
            try:
                count2 = conn.execute(
                    text("SELECT COUNT(*) FROM company_role_signals WHERE signal_type = :old"),
                    {"old": old_type},
                ).scalar()
                if count2 > 0:
                    results.append({
                        "table": "company_role_signals",
                        "old_type": old_type,
                        "new_type": new_type,
                        "count": count2,
                    })
            except Exception:
                pass  # Table may not exist

    return results


def execute_migration() -> list[dict]:
    """Apply the signal type migrations.

    Returns a list of dicts with table, old_type, new_type, and rows_updated.
    """
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
    except ImportError:
        print("ERROR: Cannot import database modules. Run from the backend directory.")
        sys.exit(1)

    engine = create_engine(settings.DATABASE_URL)
    results = []

    with engine.connect() as conn:
        for old_type, new_type in SIGNAL_TYPE_MIGRATIONS.items():
            # company_signals
            result = conn.execute(
                text(
                    "UPDATE company_signals "
                    "SET signal_type = :new, signal_text = signal_text "
                    "WHERE signal_type = :old"
                ),
                {"old": old_type, "new": new_type},
            )
            conn.commit()
            if result.rowcount > 0:
                results.append({
                    "table": "company_signals",
                    "old_type": old_type,
                    "new_type": new_type,
                    "rows_updated": result.rowcount,
                })

            # company_role_signals (if it exists)
            try:
                result2 = conn.execute(
                    text(
                        "UPDATE company_role_signals "
                        "SET signal_type = :new "
                        "WHERE signal_type = :old"
                    ),
                    {"old": old_type, "new": new_type},
                )
                conn.commit()
                if result2.rowcount > 0:
                    results.append({
                        "table": "company_role_signals",
                        "old_type": old_type,
                        "new_type": new_type,
                        "rows_updated": result2.rowcount,
                    })
            except Exception:
                pass  # Table may not exist

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Normalize legacy/ghost signal types in the database."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without applying them."
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Apply the migrations."
    )
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        print("\nSpecify --dry-run to preview or --execute to apply.")
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN — no changes will be made.\n")
        results = dry_run()
        if not results:
            print("No ghost signal types found in the database. Nothing to migrate.")
        else:
            print(f"{'Table':<25} {'Old Type':<45} {'New Type':<45} {'Count':>6}")
            print("-" * 125)
            for r in results:
                print(f"{r['table']:<25} {r['old_type']:<45} {r['new_type']:<45} {r['count']:>6}")
            print(f"\nTotal rows affected: {sum(r['count'] for r in results)}")

    elif args.execute:
        print("Applying signal type migrations...\n")
        results = execute_migration()
        if not results:
            print("No ghost signal types found in the database. Nothing to migrate.")
        else:
            print(f"{'Table':<25} {'Old Type':<45} {'New Type':<45} {'Updated':>8}")
            print("-" * 125)
            for r in results:
                print(f"{r['table']:<25} {r['old_type']:<45} {r['new_type']:<45} {r['rows_updated']:>8}")
            print(f"\nTotal rows updated: {sum(r['rows_updated'] for r in results)}")


if __name__ == "__main__":
    main()