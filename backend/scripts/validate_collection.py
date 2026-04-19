"""
Validate Collection Fix — staged testing of the collection orchestrator.

Runs collection on small batches and compares results against the
previous broken run to verify the fix actually discovers new evidence.

Usage:
    cd backend

    # Stage 1: 5 known companies with roles (sanity check)
    python scripts/validate_collection.py --stage smoke

    # Stage 2: 50 companies (mixed: some with roles, some without)
    python scripts/validate_collection.py --stage 50

    # Stage 3: 100 companies
    python scripts/validate_collection.py --stage 100

    # Stage 4: 200 companies
    python scripts/validate_collection.py --stage 200

    # Compare results against a previous run
    python scripts/validate_collection.py --stage 50 --compare-run <RUN_ID>

    # Dry run (just show which companies would be selected)
    python scripts/validate_collection.py --stage 50 --dry-run
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func as sqlfunc
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.models.company_signal import CompanySignal
from app.models.collection_run import CollectionRun
from app.services.collection_orchestrator import run_collection_for_company
from app.core.logging import get_logger

logger = get_logger(__name__)

RUNS_DIR = Path(__file__).resolve().parent.parent / "output" / "runs"


def select_smoke_companies(db) -> list:
    """Select 5 companies known to have roles (best test candidates)."""
    companies = (
        db.query(Company)
        .join(CompanyJobRole, Company.id == CompanyJobRole.company_id)
        .group_by(Company.id)
        .having(sqlfunc.count(CompanyJobRole.id) >= 2)
        .order_by(sqlfunc.count(CompanyJobRole.id).desc())
        .limit(5)
        .all()
    )
    return companies


def select_stage_companies(db, count: int) -> list:
    """Select a mix of companies: half with roles, half without."""
    half = count // 2

    with_roles = (
        db.query(Company)
        .join(CompanyJobRole, Company.id == CompanyJobRole.company_id)
        .filter(Company.domain.isnot(None), Company.domain != "")
        .group_by(Company.id)
        .having(sqlfunc.count(CompanyJobRole.id) >= 1)
        .limit(half)
        .all()
    )

    with_role_ids = {c.id for c in with_roles}

    without_roles = (
        db.query(Company)
        .filter(
            Company.domain.isnot(None),
            Company.domain != "",
            ~Company.id.in_(with_role_ids) if with_role_ids else True,
        )
        .order_by(Company.created_at)
        .limit(count - len(with_roles))
        .all()
    )

    return with_roles + without_roles


def count_signals_before(db, company_id: UUID) -> dict:
    """Snapshot signal counts before collection."""
    signals = db.query(CompanySignal).filter(CompanySignal.company_id == company_id).all()
    roles = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == company_id).all()
    return {
        "total_signals": len(signals),
        "careers_found": any(s.signal_type == "careers_page_found" for s in signals),
        "total_roles": len(roles),
        "signal_types": Counter(s.signal_type for s in signals),
    }


def run_validation(companies: list, stage: str, compare_run_id: str = None):
    """Run collection on companies and report results."""
    results = []
    total = len(companies)

    # Load comparison data if provided
    compare_data = {}
    if compare_run_id:
        progress_path = RUNS_DIR / compare_run_id / "progress.jsonl"
        if progress_path.exists():
            with open(progress_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        compare_data[entry.get("company_id", "")] = entry

    print(f"\n{'='*80}")
    print(f"  COLLECTION VALIDATION - Stage: {stage}")
    print(f"  {total} companies to process")
    print(f"{'='*80}\n")

    new_signals_total = 0
    careers_found_total = 0
    errors_total = 0

    for i, company in enumerate(companies):
        db = SessionLocal()
        try:
            before = count_signals_before(db, company.id)
            run_id = uuid4()

            crun = CollectionRun(
                id=run_id, company_id=company.id,
                collector_type="orchestrator", status="pending",
            )
            db.add(crun)
            db.commit()

            t0 = time.monotonic()
            result = run_collection_for_company(db, company.id, run_id)
            db.commit()
            elapsed = round(time.monotonic() - t0, 2)

            after = count_signals_before(db, company.id)
            new_signals = after["total_signals"] - before["total_signals"]
            new_roles = after["total_roles"] - before["total_roles"]

            status = result.get("status", "unknown")
            collectors = result.get("collectors", [])
            collector_errors = [c for c in collectors if c["status"].startswith("error")]

            entry = {
                "company_id": str(company.id),
                "name": company.name,
                "domain": company.domain,
                "status": status,
                "elapsed_s": elapsed,
                "signals_before": before["total_signals"],
                "signals_after": after["total_signals"],
                "new_signals": new_signals,
                "new_roles": new_roles,
                "careers_found": after["careers_found"],
                "collector_errors": len(collector_errors),
                "collectors": collectors,
            }
            results.append(entry)

            if new_signals > 0:
                new_signals_total += new_signals
            if after["careers_found"]:
                careers_found_total += 1
            if collector_errors:
                errors_total += len(collector_errors)

            # Compare with previous run
            delta_note = ""
            if compare_run_id:
                prev = compare_data.get(str(company.id))
                if prev:
                    prev_signals = prev.get("signals_raw", 0) if "signals_raw" in prev else 0
                    delta_note = f" (prev: {prev_signals} raw)"

            marker = "+" if new_signals > 0 else " "
            err_marker = "!" if collector_errors else " "
            print(
                f"  [{i+1:3d}/{total}] {marker}{err_marker} "
                f"{company.name[:30]:<30s} {company.domain:<25s} "
                f"+{new_signals:2d} signals, +{new_roles:d} roles, "
                f"careers={'Y' if after['careers_found'] else 'N'}, "
                f"{elapsed:.1f}s{delta_note}"
            )

        except Exception as e:
            print(f"  [{i+1:3d}/{total}] !! {company.name[:30]:<30s} CRASHED: {e}")
            results.append({
                "company_id": str(company.id),
                "name": company.name,
                "domain": company.domain,
                "status": "crash",
                "error": str(e),
            })
        finally:
            db.close()

    # Summary
    print(f"\n{'='*80}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*80}")

    ok = [r for r in results if r.get("status") == "completed"]
    crashed = [r for r in results if r.get("status") == "crash"]
    with_new = [r for r in ok if r.get("new_signals", 0) > 0]
    with_careers = [r for r in ok if r.get("careers_found")]
    with_errors = [r for r in ok if r.get("collector_errors", 0) > 0]

    print(f"  Total processed:     {len(ok)}")
    print(f"  Crashed:             {len(crashed)}")
    print(f"  With new signals:    {len(with_new)} ({len(with_new)/max(len(ok),1)*100:.0f}%)")
    print(f"  With careers page:   {len(with_careers)} ({len(with_careers)/max(len(ok),1)*100:.0f}%)")
    print(f"  With collector errs: {len(with_errors)}")
    print(f"  Total new signals:   {new_signals_total}")

    # Readiness assessment
    print(f"\n  READINESS ASSESSMENT:")
    careers_rate = len(with_careers) / max(len(ok), 1) * 100
    error_rate = len(with_errors) / max(len(ok), 1) * 100
    crash_rate = len(crashed) / max(total, 1) * 100

    checks = []
    if crash_rate == 0:
        checks.append(("No crashes", "PASS"))
    else:
        checks.append(("No crashes", f"FAIL ({crash_rate:.0f}%)"))

    if error_rate < 20:
        checks.append(("Collector error rate < 20%", "PASS"))
    else:
        checks.append(("Collector error rate < 20%", f"FAIL ({error_rate:.0f}%)"))

    if careers_rate > 50:
        checks.append(("Careers discovery > 50%", "PASS"))
    else:
        checks.append(("Careers discovery > 50%", f"FAIL ({careers_rate:.0f}%)"))

    if len(with_new) > len(ok) * 0.3:
        checks.append(("New signals > 30% of companies", "PASS"))
    else:
        checks.append(("New signals > 30% of companies", f"FAIL ({len(with_new)/max(len(ok),1)*100:.0f}%)"))

    all_pass = all(c[1] == "PASS" for c in checks)
    for label, status in checks:
        print(f"    [{status:>20s}] {label}")

    if all_pass:
        next_stage = {"smoke": "50", "50": "100", "100": "200", "200": "FULL RERUN"}
        ns = next_stage.get(stage, "done")
        print(f"\n  >> ALL CHECKS PASS. Ready for next stage: {ns}")
    else:
        print(f"\n  >> SOME CHECKS FAILED. Investigate before proceeding.")

    # Save results
    output_dir = RUNS_DIR / f"validation_{stage}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_dir}")

    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Validate collection fix")
    parser.add_argument("--stage", required=True, choices=["smoke", "50", "100", "200"],
                        help="Validation stage")
    parser.add_argument("--compare-run", type=str, help="Previous run ID to compare against")
    parser.add_argument("--dry-run", action="store_true", help="Just show selected companies")
    args = parser.parse_args()

    db = SessionLocal()

    if args.stage == "smoke":
        companies = select_smoke_companies(db)
    else:
        count = int(args.stage)
        companies = select_stage_companies(db, count)

    if args.dry_run:
        print(f"\nDry run - {len(companies)} companies selected:")
        for i, c in enumerate(companies):
            role_count = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == c.id).count()
            print(f"  {i+1:3d}. {c.name[:40]:<40s} {c.domain:<30s} roles={role_count}")
        db.close()
        return

    db.close()
    run_validation(companies, args.stage, args.compare_run)


if __name__ == "__main__":
    main()
