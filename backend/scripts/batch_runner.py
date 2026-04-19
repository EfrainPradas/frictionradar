"""
Hardened Batch Runner — staging-ready batch analysis CLI.

Runs deep-intelligence pipeline on company subsets with:
  - Run isolation (each run gets its own directory)
  - JSONL progress tracking (append-only, crash-safe)
  - Resume from previous run (skip successes, retry errors)
  - Manifest with full run metadata
  - Structured report with before/after KPIs
  - Run comparison mode
  - Dual logging (stdout + file)

Usage:
    cd backend

    # Full run on ALL companies (including those with 0 roles)
    python scripts/batch_runner.py --all --limit 1500 --label full_prod

    # Only companies with 2+ roles (default)
    python scripts/batch_runner.py --limit 100

    # Only companies not yet processed in a previous run
    python scripts/batch_runner.py --all --pending-only --since-run <RUN_ID>

    # Dry run (select companies, print plan, don't process)
    python scripts/batch_runner.py --all --limit 1500 --dry-run

    # Resume a previous run (skip successes)
    python scripts/batch_runner.py --resume 20260414_153022_tier100

    # Resume and also retry errors from previous run
    python scripts/batch_runner.py --resume 20260414_153022_tier100 --retry-errors

    # Filter by minimum role count
    python scripts/batch_runner.py --limit 50 --min-roles 5

    # Single company
    python scripts/batch_runner.py --company-id <uuid>

    # Compare two runs
    python scripts/batch_runner.py --compare 20260414_153022_tier100 20260415_091000_tier100

    # List previous runs
    python scripts/batch_runner.py --list-runs
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func as sqlfunc, text as sqltext
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.collection_run import CollectionRun
from app.services.company_evaluation import CompanyEvaluationEngine
from app.services.jd_scraper_service import extract_jds_for_company
from app.services.hiring_pattern_service import compute_hiring_pattern
from app.core.logging import setup_batch_logging

# ── Constants ────────────────────────────────────────────────────────

RUNS_DIR = Path(__file__).resolve().parent.parent / "output" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

DS_RANKS = {
    "insufficient_evidence": 0,
    "broad_hiring_pattern_detected": 1,
    "specific_pain_emerging": 2,
    "specific_pain_identified": 3,
    "ready_for_positioning": 4,
}

evaluation_engine = CompanyEvaluationEngine()


# ── Run context ──────────────────────────────────────────────────────

def _git_commit_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "unknown"


def _generate_run_id(label: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_label = label.replace(" ", "_").replace("/", "_")[:30]
    return f"{ts}_{safe_label}"


class RunContext:
    """Manages run directory, manifest, progress, and logging."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = RUNS_DIR / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.run_dir / "manifest.json"
        self.progress_path = self.run_dir / "progress.jsonl"
        self.report_path = self.run_dir / "report.json"
        self.log_path = self.run_dir / "run.log"

        self.logger = setup_batch_logging(self.log_path)

    def write_manifest(self, params: dict, total_companies: int):
        manifest = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "status": "running",
            "params": params,
            "total_companies": total_companies,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "git_commit": _git_commit_short(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        }
        self._save_manifest(manifest)
        return manifest

    def update_manifest(self, **updates):
        manifest = self.load_manifest()
        manifest.update(updates)
        self._save_manifest(manifest)

    def finalize_manifest(self, succeeded: int, failed: int, skipped: int):
        self.update_manifest(
            finished_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            processed=succeeded + failed,
        )

    def load_manifest(self) -> dict:
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: dict):
        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)

    def append_progress(self, entry: dict):
        with open(self.progress_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_progress(self) -> list[dict]:
        if not self.progress_path.exists():
            return []
        entries = []
        with open(self.progress_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def get_done_ids(self, include_errors: bool = False) -> set[str]:
        """Return company IDs already processed. If include_errors=False, skip errors."""
        done = set()
        for entry in self.load_progress():
            if include_errors or entry.get("status") == "ok":
                done.add(entry["company_id"])
        return done

    def save_report(self, report: dict):
        with open(self.report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)


# ── Company selection ────────────────────────────────────────────────

def select_companies(db, limit: int, min_roles: int = 2) -> list[dict]:
    """Select companies with at least min_roles roles, sorted by role count."""
    role_counts = (
        db.query(
            CompanyJobRole.company_id,
            sqlfunc.count(CompanyJobRole.id).label("cnt"),
        )
        .group_by(CompanyJobRole.company_id)
        .having(sqlfunc.count(CompanyJobRole.id) >= min_roles)
        .all()
    )

    candidates = []
    for cid, cnt in role_counts:
        c = db.query(Company).filter(Company.id == cid).first()
        if not c or not c.domain:
            continue

        score = (
            db.query(FrictionScore)
            .filter(FrictionScore.company_id == cid)
            .order_by(FrictionScore.computed_at.desc())
            .first()
        )

        candidates.append({
            "id": str(cid),
            "name": c.name,
            "domain": c.domain,
            "roles": cnt,
            "score": float(score.total_score) if score and score.total_score else 0,
        })

    candidates.sort(key=lambda x: x["roles"], reverse=True)
    return candidates[:limit]


def select_all_companies(db, limit: int) -> list[dict]:
    """Select ALL companies with a domain, regardless of role count.

    Returns companies sorted: those with roles first (by role count desc),
    then the rest alphabetically.
    """
    # Get role counts per company (only companies that have roles)
    role_map = {}
    role_counts = (
        db.query(
            CompanyJobRole.company_id,
            sqlfunc.count(CompanyJobRole.id).label("cnt"),
        )
        .group_by(CompanyJobRole.company_id)
        .all()
    )
    for cid, cnt in role_counts:
        role_map[cid] = cnt

    # Get all companies with domain
    all_companies = (
        db.query(Company)
        .filter(Company.domain.isnot(None), Company.domain != "")
        .limit(limit)
        .all()
    )

    candidates = []
    for c in all_companies:
        roles = role_map.get(c.id, 0)
        candidates.append({
            "id": str(c.id),
            "name": c.name,
            "domain": c.domain,
            "roles": roles,
            "score": 0,  # Skip score lookup for speed on full dataset
        })

    # Sort: companies with roles first (desc), then rest alphabetically
    candidates.sort(key=lambda x: (-x["roles"], x["name"].lower()))
    return candidates


# ── KPI snapshot ─────────────────────────────────────────────────────

def snapshot_kpis(db, company_id) -> dict:
    ev = evaluation_engine.evaluate(company_id=company_id, db=db)
    kpis = ev.get("kpis", {})
    return {
        "fc": kpis.get("function_concentration", "low"),
        "pc": kpis.get("pain_clarity", "low"),
        "pr": kpis.get("positioning_readiness", "low"),
        "ds": ev.get("diagnostic_state", ""),
        "ec": kpis.get("extraction_coverage", "low"),
        "hp": kpis.get("hiring_pressure", "low"),
    }


# ── Single company pipeline ─────────────────────────────────────────

def process_company(db, company_id: str, name: str, domain: str, logger) -> dict:
    """Run deep intelligence on one company. Returns structured result."""
    cid = UUID(company_id) if isinstance(company_id, str) else company_id
    t0 = time.monotonic()

    before = snapshot_kpis(db, cid)

    # Count current role state
    roles = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == cid).all()
    junk_count = sum(1 for r in roles if r.functional_area == "junk")
    unknown_count = sum(1 for r in roles if r.functional_area in ("unknown", None))
    classified_count = sum(1 for r in roles if r.functional_area and r.functional_area not in ("junk", "unknown"))
    desc_count = sum(1 for r in roles if r.role_description)

    # Pipeline: extract JDs -> classify -> pattern
    # Skip JD extraction for companies with no roles (no source_urls to fetch)
    has_extractable_roles = any(
        r.source_url for r in roles
        if r.source_url and not r.role_description
    )
    if has_extractable_roles:
        jd_result = extract_jds_for_company(cid, db, max_jds=10, delay=0.5)
    else:
        jd_result = {"total_attempted": 0, "successful": 0, "failed": 0}
    pattern_result = compute_hiring_pattern(cid, db)

    after = snapshot_kpis(db, cid)
    elapsed = round(time.monotonic() - t0, 2)

    # Determine changes
    changes = {}
    for key in ["fc", "pc", "pr", "ds", "ec", "hp"]:
        if before[key] != after[key]:
            changes[key] = {"before": before[key], "after": after[key]}

    ds_before_rank = DS_RANKS.get(before["ds"], 0)
    ds_after_rank = DS_RANKS.get(after["ds"], 0)
    if ds_after_rank > ds_before_rank:
        direction = "improved"
    elif ds_after_rank < ds_before_rank:
        direction = "degraded"
    else:
        direction = "same"

    pattern = (pattern_result.get("pattern") or {})

    return {
        "company_id": company_id,
        "name": name,
        "domain": domain,
        "status": "ok",
        "elapsed_s": elapsed,
        "total_roles": len(roles),
        "junk": junk_count,
        "unknown": unknown_count,
        "classified": classified_count,
        "descriptions": desc_count + jd_result.get("successful", 0),
        "jds_extracted": jd_result.get("successful", 0),
        "top_function": pattern.get("dominant_function"),
        "top_share": pattern.get("dominant_share", 0),
        "unique_areas": pattern.get("unique_functions", 0),
        "distribution": pattern.get("function_distribution", {}),
        "before": before,
        "after": after,
        "changes": changes,
        "direction": direction,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── Full pipeline processing (collection + extraction + scoring) ─────

def process_company_full(db, company_id: str, name: str, domain: str, logger) -> dict:
    """Run FULL pipeline: collection → extraction → scoring → JD → classify → evaluate.

    Collection orchestrator now runs sequentially (no ThreadPoolExecutor),
    so it's safe to use a single session per step. Each step still gets
    its own session for clean transaction boundaries.
    """
    from uuid import uuid4 as _uuid4
    from app.services.collection_orchestrator import run_collection_for_company
    from app.services.scoring_engine import compute_and_persist_score
    from app.services.hypothesis_engine import generate_and_persist_hypothesis

    cid = UUID(company_id) if isinstance(company_id, str) else company_id
    t0 = time.monotonic()

    before = snapshot_kpis(db, cid)
    collection_result = None

    # Step 1: Collection (sequential HTTP crawlers — thread-safe now)
    s1 = None
    try:
        s1 = SessionLocal()
        run_id = _uuid4()
        crun = CollectionRun(
            id=run_id, company_id=cid,
            collector_type="orchestrator", status="pending",
        )
        s1.add(crun)
        s1.commit()
        collection_result = run_collection_for_company(s1, cid, run_id)
        s1.commit()

        # Log collection outcome explicitly
        cr_status = collection_result.get("status", "unknown")
        cr_signals = collection_result.get("signals_persisted", 0)
        cr_careers = collection_result.get("careers_found", False)
        logger.info(
            f"[FullPipeline] {name} collection: status={cr_status}, "
            f"signals={cr_signals}, careers={'YES' if cr_careers else 'NO'}"
        )
    except Exception as e:
        logger.warning(f"[FullPipeline] {name} collection FAILED: {e}", exc_info=True)
    finally:
        if s1:
            try:
                s1.close()
            except Exception:
                pass

    # Step 2: Extraction + Scoring (ATS → HTTP, skip Playwright for batch)
    s2 = None
    try:
        from app.extraction.dispatcher import extract_company
        from app.services.collection_orchestrator import _persist_signals_deduped

        s2 = SessionLocal()
        company = s2.query(Company).filter(Company.id == cid).first()
        open_positions = None

        if company and company.domain:
            detected_ats = None
            ats_signal = (
                s2.query(CompanySignal)
                .filter(
                    CompanySignal.company_id == cid,
                    CompanySignal.signal_type.like("%_board_detected"),
                )
                .first()
            )
            if ats_signal:
                detected_ats = ats_signal.signal_type.replace("_board_detected", "")

            ext_result = extract_company(
                domain=company.domain,
                company_name=company.name,
                company_id=cid,
                detected_ats_platform=detected_ats,
                skip_playwright=False,
            )

            if ext_result and ext_result.success:
                open_positions = ext_result.open_positions_count
                source_type = f"extraction_{ext_result.strategy_used.value}"
                url = ext_result.careers_url or ""
                new_signals = []

                if ext_result.open_positions_count and ext_result.open_positions_count > 0:
                    sig_type = (
                        "high_open_positions_count_detected"
                        if ext_result.open_positions_count >= 100
                        else "open_positions_count_detected"
                    )
                    new_signals.append(CompanySignal(
                        company_id=cid, source_type=source_type,
                        source_url=url, signal_type=sig_type,
                        signal_text=f"Open positions: {ext_result.open_positions_count}",
                        numeric_value=ext_result.open_positions_count,
                        confidence=ext_result.confidence,
                    ))

                if ext_result.jobs_count > 0:
                    new_signals.append(CompanySignal(
                        company_id=cid, source_type=source_type,
                        source_url=url, signal_type="job_cards_visible_detected",
                        signal_text=f"Job listings: {ext_result.jobs_count}",
                        numeric_value=ext_result.jobs_count,
                        confidence=ext_result.confidence,
                    ))

                for area in ext_result.hiring_areas[:8]:
                    area_key = area.lower().replace(" ", "_").replace("&", "and")
                    new_signals.append(CompanySignal(
                        company_id=cid, source_type=source_type,
                        source_url=url,
                        signal_type=f"{area_key}_hiring_detected",
                        signal_text=f"Hiring area: {area}",
                        confidence=0.8,
                    ))

                if ext_result.careers_url:
                    new_signals.append(CompanySignal(
                        company_id=cid, source_type=source_type,
                        source_url=ext_result.careers_url,
                        signal_type="careers_page_found",
                        signal_text=f"Careers page: {ext_result.careers_url}",
                        confidence=0.95,
                    ))

                if new_signals:
                    _persist_signals_deduped(s2, cid, new_signals)

                roles_persisted = 0
                if ext_result.jobs:
                    from app.services.role_ingest import persist_job_role
                    existing_urls = {
                        u for (u,) in s2.query(CompanyJobRole.source_url)
                        .filter(CompanyJobRole.company_id == cid)
                        .all()
                        if u
                    }
                    fallback_url = ext_result.careers_url or ""
                    for job in ext_result.jobs[:40]:
                        if not job.title:
                            continue
                        src = job.job_url or fallback_url
                        if src and src in existing_urls:
                            continue
                        if persist_job_role(
                            s2,
                            company_id=cid,
                            raw_title=job.title,
                            source_url=src or None,
                            role_location=job.location,
                            role_department=job.department,
                            role_description=job.description_snippet,
                        ) is None:
                            continue
                        if src:
                            existing_urls.add(src)
                        roles_persisted += 1
                    if roles_persisted:
                        try:
                            s2.commit()
                        except Exception as e:
                            logger.warning(f"[FullPipeline] {name} job_roles persist FAILED: {e}")
                            s2.rollback()
                            roles_persisted = 0

                logger.info(
                    f"[FullPipeline] {name} extraction: strategy={ext_result.strategy_used.value}, "
                    f"jobs={ext_result.jobs_count}, positions={open_positions}, roles_saved={roles_persisted}"
                )
            else:
                reason = ext_result.error if ext_result else "no result"
                logger.info(f"[FullPipeline] {name} extraction: no success ({reason})")

        score = compute_and_persist_score(s2, cid, open_positions_count=open_positions)
        s2.commit()
    except Exception as e:
        logger.warning(f"[FullPipeline] {name} extraction/scoring FAILED: {e}", exc_info=True)
        if s2:
            try:
                s2.rollback()
            except Exception:
                pass
    finally:
        if s2:
            try:
                s2.close()
            except Exception:
                pass

    # Step 3: Hypothesis
    s3 = None
    try:
        s3 = SessionLocal()
        latest_score = (
            s3.query(FrictionScore)
            .filter(FrictionScore.company_id == cid)
            .order_by(FrictionScore.computed_at.desc())
            .first()
        )
        if latest_score:
            generate_and_persist_hypothesis(s3, cid, latest_score)
        s3.commit()
    except Exception as e:
        logger.warning(f"[FullPipeline] {name} hypothesis FAILED: {e}")
        if s3:
            try:
                s3.rollback()
            except Exception:
                pass
    finally:
        if s3:
            try:
                s3.close()
            except Exception:
                pass

    # Step 4: JD extraction + classification + pattern
    # Refresh main session to see all new data
    db.expire_all()
    roles = db.query(CompanyJobRole).filter(CompanyJobRole.company_id == cid).all()
    junk_count = sum(1 for r in roles if r.functional_area == "junk")
    unknown_count = sum(1 for r in roles if r.functional_area in ("unknown", None))
    classified_count = sum(1 for r in roles if r.functional_area and r.functional_area not in ("junk", "unknown"))
    desc_count = sum(1 for r in roles if r.role_description)

    has_extractable_roles = any(
        r.source_url for r in roles if r.source_url and not r.role_description
    )
    if has_extractable_roles:
        jd_result = extract_jds_for_company(cid, db, max_jds=10, delay=0.5)
    else:
        jd_result = {"total_attempted": 0, "successful": 0, "failed": 0}
    pattern_result = compute_hiring_pattern(cid, db)

    # Step 5: Final evaluation
    after = snapshot_kpis(db, cid)
    elapsed = round(time.monotonic() - t0, 2)

    # Determine changes
    changes = {}
    for key in ["fc", "pc", "pr", "ds", "ec", "hp"]:
        if before[key] != after[key]:
            changes[key] = {"before": before[key], "after": after[key]}

    ds_before_rank = DS_RANKS.get(before["ds"], 0)
    ds_after_rank = DS_RANKS.get(after["ds"], 0)
    if ds_after_rank > ds_before_rank:
        direction = "improved"
    elif ds_after_rank < ds_before_rank:
        direction = "degraded"
    else:
        direction = "same"

    pattern = (pattern_result.get("pattern") or {})

    return {
        "company_id": company_id,
        "name": name,
        "domain": domain,
        "status": "ok",
        "elapsed_s": elapsed,
        "total_roles": len(roles),
        "junk": junk_count,
        "unknown": unknown_count,
        "classified": classified_count,
        "descriptions": desc_count + jd_result.get("successful", 0),
        "jds_extracted": jd_result.get("successful", 0),
        "top_function": pattern.get("dominant_function"),
        "top_share": pattern.get("dominant_share", 0),
        "unique_areas": pattern.get("unique_functions", 0),
        "distribution": pattern.get("function_distribution", {}),
        "before": before,
        "after": after,
        "changes": changes,
        "direction": direction,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── Credibility assessment ───────────────────────────────────────────

def credibility_assessment(result: dict) -> str:
    if result["direction"] == "same":
        return "unchanged"
    classified = result.get("classified", 0)
    descs = result.get("descriptions", 0)
    share = result.get("top_share", 0)
    if classified >= 5 and descs >= 3 and share >= 0.4:
        return "credible"
    elif classified >= 3 and share >= 0.35:
        return "borderline"
    elif result["direction"] == "degraded":
        return "correction"
    else:
        return "forced"


# ── Batch orchestrator ───────────────────────────────────────────────

def run_batch(ctx: RunContext, companies: list[dict], skip_ids: set[str] = None, full_pipeline: bool = False):
    """Process companies with progress tracking and crash recovery."""
    skip_ids = skip_ids or set()
    pending = [c for c in companies if c["id"] not in skip_ids]
    skipped_count = len(companies) - len(pending)

    ctx.logger.info(f"Run {ctx.run_id}: {len(pending)} to process, {skipped_count} skipped (resume)")

    succeeded = 0
    failed = 0
    t_start = time.monotonic()

    for i, c in enumerate(pending):
        elapsed_total = time.monotonic() - t_start
        avg = elapsed_total / max(i, 1)
        eta = avg * (len(pending) - i) if i > 0 else 0
        eta_str = f"ETA {eta/60:.0f}m" if eta > 60 else f"ETA {eta:.0f}s"

        progress_pct = (i + skipped_count) / len(companies) * 100
        print(
            f"[{i+1+skipped_count}/{len(companies)}] ({progress_pct:.0f}%) "
            f"{c['name'][:35]:35s} ",
            end="", flush=True,
        )

        db = SessionLocal()
        try:
            if full_pipeline:
                result = process_company_full(db, c["id"], c["name"], c["domain"], ctx.logger)
            else:
                result = process_company(db, c["id"], c["name"], c["domain"], ctx.logger)
            ctx.append_progress(result)
            succeeded += 1

            marker = ">>>" if result["direction"] == "improved" else \
                     "<<<" if result["direction"] == "degraded" else "   "
            print(
                f"{marker} ds:{result['after']['ds'][:20]:20s} "
                f"fc:{result['after']['fc']:8s} "
                f"{result['elapsed_s']:.1f}s  {eta_str}"
            )
            ctx.logger.info(
                f"OK {c['name']} | ds:{result['after']['ds']} "
                f"fc:{result['after']['fc']} dir:{result['direction']} "
                f"{result['elapsed_s']:.1f}s"
            )

        except Exception as e:
            failed += 1
            error_entry = {
                "company_id": c["id"],
                "name": c["name"],
                "domain": c["domain"],
                "status": "error",
                "error": str(e),
                "elapsed_s": round(time.monotonic() - t_start, 2),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            ctx.append_progress(error_entry)
            print(f"ERROR: {e}")
            ctx.logger.error(f"FAIL {c['name']}: {e}")
            db.rollback()
        finally:
            db.close()

        # Update manifest periodically (every 10 companies)
        if (i + 1) % 10 == 0:
            ctx.update_manifest(
                processed=succeeded + failed + skipped_count,
                succeeded=succeeded,
                failed=failed,
                skipped=skipped_count,
            )

    total_time = time.monotonic() - t_start
    ctx.finalize_manifest(
        succeeded=succeeded, failed=failed, skipped=skipped_count
    )

    ctx.logger.info(
        f"Run complete: {succeeded} ok, {failed} errors, "
        f"{skipped_count} skipped, {total_time:.0f}s total "
        f"({total_time/max(succeeded+failed, 1):.1f}s avg)"
    )

    return succeeded, failed, skipped_count


# ── Report generation ────────────────────────────────────────────────

def generate_report(ctx: RunContext) -> dict:
    """Build report from progress JSONL."""
    entries = ctx.load_progress()
    valid = [e for e in entries if e.get("status") == "ok"]
    errors = [e for e in entries if e.get("status") == "error"]

    if not valid:
        return {"run_id": ctx.run_id, "total": len(entries), "valid": 0, "errors": len(errors)}

    before_ds = Counter(e["before"]["ds"] for e in valid)
    after_ds = Counter(e["after"]["ds"] for e in valid)
    before_fc = Counter(e["before"]["fc"] for e in valid)
    after_fc = Counter(e["after"]["fc"] for e in valid)
    before_pc = Counter(e["before"]["pc"] for e in valid)
    after_pc = Counter(e["after"]["pc"] for e in valid)
    before_pr = Counter(e["before"]["pr"] for e in valid)
    after_pr = Counter(e["after"]["pr"] for e in valid)

    improved = [e for e in valid if e["direction"] == "improved"]
    degraded = [e for e in valid if e["direction"] == "degraded"]
    changed = [e for e in valid if e.get("changes")]

    credibility = Counter(
        credibility_assessment(e) for e in valid if e["direction"] != "same"
    )

    avg_time = sum(e["elapsed_s"] for e in valid) / len(valid)

    report = {
        "run_id": ctx.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(entries),
        "valid": len(valid),
        "errors": len(errors),
        "improved": len(improved),
        "degraded": len(degraded),
        "changed": len(changed),
        "avg_time_s": round(avg_time, 2),
        "credibility": dict(credibility),
        "diagnostic_state": {"before": dict(before_ds), "after": dict(after_ds)},
        "function_concentration": {"before": dict(before_fc), "after": dict(after_fc)},
        "pain_clarity": {"before": dict(before_pc), "after": dict(after_pc)},
        "positioning_readiness": {"before": dict(before_pr), "after": dict(after_pr)},
        "error_details": [
            {"name": e["name"], "domain": e["domain"], "error": e["error"]}
            for e in errors
        ],
        "company_details": [
            {
                "name": e["name"],
                "domain": e["domain"],
                "classified": e.get("classified", 0),
                "descriptions": e.get("descriptions", 0),
                "top_function": e.get("top_function"),
                "top_share": e.get("top_share", 0),
                "before_ds": e["before"]["ds"],
                "after_ds": e["after"]["ds"],
                "before_fc": e["before"]["fc"],
                "after_fc": e["after"]["fc"],
                "direction": e["direction"],
                "credibility": credibility_assessment(e),
                "elapsed_s": e["elapsed_s"],
            }
            for e in valid
        ],
    }

    ctx.save_report(report)
    return report


# ── Report printing ──────────────────────────────────────────────────

def print_report(report: dict):
    run_id = report.get("run_id", "")
    print(f"\n{'='*80}")
    print(f"  Run: {run_id}")
    print(f"  {report['valid']} companies, {report['errors']} errors, avg {report.get('avg_time_s', 0):.1f}s/co")
    print(f"{'='*80}")

    print(f"\n  Improved: {report['improved']}  |  Degraded: {report['degraded']}  |  Changed: {report['changed']}")
    if report.get("credibility"):
        print(f"  Credibility: {report['credibility']}")

    for kpi_name in ["diagnostic_state", "function_concentration", "pain_clarity", "positioning_readiness"]:
        kpi = report.get(kpi_name, {})
        before = kpi.get("before", {})
        after = kpi.get("after", {})
        all_keys = sorted(set(list(before.keys()) + list(after.keys())))
        if not all_keys:
            continue
        print(f"\n  {kpi_name}:")
        for k in all_keys:
            b = before.get(k, 0)
            a = after.get(k, 0)
            delta = a - b
            marker = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
            if b or a:
                print(f"    {k:40s}: {b:3d} -> {a:3d}{marker}")

    # Error summary
    if report.get("error_details"):
        print(f"\n  {'-'*76}")
        print(f"  ERRORS ({len(report['error_details'])}):")
        for ed in report["error_details"][:10]:
            print(f"    {ed['name']} ({ed['domain']}): {ed['error'][:80]}")

    # Per-company audit for changed
    changed = [d for d in report.get("company_details", []) if d["direction"] != "same"]
    if changed:
        print(f"\n  {'-'*76}")
        print(f"  COMPANIES THAT CHANGED ({len(changed)}):")
        print(f"  {'-'*76}")
        for d in changed:
            cred_marker = {
                "credible": "[OK]", "borderline": "[~~]",
                "forced": "[!!]", "correction": "[<<]"
            }.get(d["credibility"], "[??]")
            print(f"  {cred_marker} {d['name']} ({d['domain']})")
            print(f"      ds: {d['before_ds']} -> {d['after_ds']}")
            print(f"      fc: {d['before_fc']} -> {d['after_fc']}")
            print(f"      top: {d['top_function']} ({d['top_share']:.0%}), "
                  f"{d['classified']} classified, {d['descriptions']} descs")
            print(f"      verdict: {d['credibility']} ({d['elapsed_s']:.1f}s)")
            print()


# ── Run comparison ───────────────────────────────────────────────────

def compare_runs(run_a_id: str, run_b_id: str):
    """Compare two runs and print differences."""
    ctx_a = RunContext(run_a_id)
    ctx_b = RunContext(run_b_id)

    report_a_path = ctx_a.report_path
    report_b_path = ctx_b.report_path

    if not report_a_path.exists():
        print(f"Run A report not found: {report_a_path}")
        return
    if not report_b_path.exists():
        print(f"Run B report not found: {report_b_path}")
        return

    with open(report_a_path) as f:
        report_a = json.load(f)
    with open(report_b_path) as f:
        report_b = json.load(f)

    print(f"\n{'='*80}")
    print(f"  COMPARISON: {run_a_id} vs {run_b_id}")
    print(f"{'='*80}")

    # Summary comparison
    for key in ["valid", "errors", "improved", "degraded", "changed", "avg_time_s"]:
        va = report_a.get(key, 0)
        vb = report_b.get(key, 0)
        delta = vb - va if isinstance(va, (int, float)) else "N/A"
        print(f"  {key:30s}: {va:>6} -> {vb:>6}  (delta: {delta})")

    # Per-KPI comparison
    for kpi_name in ["diagnostic_state", "function_concentration", "pain_clarity"]:
        print(f"\n  {kpi_name}:")
        after_a = report_a.get(kpi_name, {}).get("after", {})
        after_b = report_b.get(kpi_name, {}).get("after", {})
        all_keys = sorted(set(list(after_a.keys()) + list(after_b.keys())))
        for k in all_keys:
            va = after_a.get(k, 0)
            vb = after_b.get(k, 0)
            delta = vb - va
            marker = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
            if va or vb:
                print(f"    {k:40s}: {va:3d} -> {vb:3d}{marker}")

    # Per-company diff (companies present in both)
    details_a = {d["domain"]: d for d in report_a.get("company_details", [])}
    details_b = {d["domain"]: d for d in report_b.get("company_details", [])}

    common = set(details_a.keys()) & set(details_b.keys())
    diffs = []
    for domain in common:
        da = details_a[domain]
        db_ = details_b[domain]
        if da["after_ds"] != db_["after_ds"] or da["after_fc"] != db_["after_fc"]:
            diffs.append({
                "name": db_["name"],
                "domain": domain,
                "ds_a": da["after_ds"],
                "ds_b": db_["after_ds"],
                "fc_a": da["after_fc"],
                "fc_b": db_["after_fc"],
            })

    if diffs:
        print(f"\n  {'-'*76}")
        print(f"  COMPANIES WITH DIFFERENT OUTCOMES ({len(diffs)}):")
        for d in diffs:
            print(f"    {d['name']} ({d['domain']})")
            print(f"      ds: {d['ds_a']} -> {d['ds_b']}")
            print(f"      fc: {d['fc_a']} -> {d['fc_b']}")
    else:
        print(f"\n  No outcome differences across {len(common)} common companies.")

    only_a = set(details_a.keys()) - set(details_b.keys())
    only_b = set(details_b.keys()) - set(details_a.keys())
    if only_a:
        print(f"\n  Only in run A: {len(only_a)} companies")
    if only_b:
        print(f"\n  Only in run B: {len(only_b)} companies")


# ── Backfill diagnostic state ────────────────────────────────────────

def backfill_diagnostic_state(ctx: RunContext):
    """Update companies.latest_diagnostic_state from run progress."""
    entries = ctx.load_progress()
    ok_entries = [e for e in entries if e.get("status") == "ok"]
    if not ok_entries:
        return 0

    db = SessionLocal()
    updated = 0
    try:
        for e in ok_entries:
            ds = e.get("after", {}).get("ds")
            if ds:
                db.execute(
                    sqltext(
                        "UPDATE companies SET latest_diagnostic_state = :ds, "
                        "last_analysis_run_id = :run_id "
                        "WHERE id = CAST(:cid AS uuid)"
                    ),
                    {"ds": ds, "run_id": ctx.run_id, "cid": e["company_id"]},
                )
                updated += 1
        db.commit()
    except Exception as ex:
        ctx.logger.error(f"Backfill failed: {ex}")
        db.rollback()
    finally:
        db.close()

    ctx.logger.info(f"Backfilled latest_diagnostic_state for {updated} companies")
    return updated


# ── List runs ────────────────────────────────────────────────────────

def list_runs():
    """List all previous runs with their status."""
    if not RUNS_DIR.exists():
        print("No runs found.")
        return

    runs = sorted(RUNS_DIR.iterdir(), reverse=True)
    if not runs:
        print("No runs found.")
        return

    print(f"\n{'='*80}")
    print(f"  Previous Runs ({len(runs)})")
    print(f"{'='*80}")
    print(f"  {'Run ID':<40s} {'Status':<12s} {'Companies':<12s} {'Errors':<8s}")
    print(f"  {'-'*76}")

    for run_dir in runs:
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"  {run_dir.name:<40s} {'no manifest':<12s}")
            continue

        with open(manifest_path) as f:
            m = json.load(f)

        status = m.get("status", "unknown")
        total = m.get("total_companies", 0)
        succeeded = m.get("succeeded", 0)
        failed = m.get("failed", 0)
        print(
            f"  {run_dir.name:<40s} {status:<12s} "
            f"{succeeded}/{total:<10s} {failed:<8d}"
        )


# ── Shard progress writer ────────────────────────────────────────────

class ShardProgressWriter:
    """Writes structured progress.json for master orchestrator monitoring."""

    def __init__(self, progress_dir: str, shard_index: int, shard_total: int,
                 run_id: str, parent_run_id: str, total_in_shard: int):
        self.progress_dir = Path(progress_dir)
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.progress_dir / "progress.json"
        self.summary_file = self.progress_dir / "summary.json"

        self.state = {
            "pid": os.getpid(),
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "shard_index": shard_index,
            "shard_total": shard_total,
            "total_in_shard": total_in_shard,
            "status": "running",
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "percent": 0.0,
            "current_company_name": "",
            "current_stage": "starting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_sec": 0,
            "avg_sec_per_company": 0,
            "eta_sec": 0,
            "careers_found": 0,
            "roles_detected": 0,
            "roles_classified": 0,
            "jds_extracted": 0,
            "eligible_positioning": 0,
            "last_error_message": "",
        }
        self._start_time = time.monotonic()
        self._write()

    def update_current(self, company_name: str, stage: str = "processing"):
        self.state["current_company_name"] = company_name
        self.state["current_stage"] = stage
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write()

    def record_result(self, result: dict):
        status = result.get("status", "error")
        if status == "ok":
            self.state["success"] += 1
        else:
            self.state["failed"] += 1
            self.state["last_error_message"] = result.get("error", "")[:200]

        self.state["processed"] = self.state["success"] + self.state["failed"]
        total = max(self.state["total_in_shard"], 1)
        self.state["percent"] = round(self.state["processed"] / total * 100, 1)

        elapsed = time.monotonic() - self._start_time
        self.state["elapsed_sec"] = round(elapsed)
        processed = self.state["processed"]
        if processed > 0:
            avg = elapsed / processed
            self.state["avg_sec_per_company"] = round(avg, 1)
            remaining = total - processed
            self.state["eta_sec"] = round(avg * remaining)

        # Accumulate funnel metrics from result
        if status == "ok":
            after = result.get("after", {})
            ds = after.get("ds", "")
            # Eligibility — mirror positioning_engine.check_eligibility() gates.
            # specific_pain_emerging requires classified >= 3 (the engine
            # rejects it otherwise); ready_for_positioning and
            # specific_pain_identified are always full-gate eligible.
            classified = result.get("classified", 0)
            top_share = result.get("top_share", 0)
            if ds in ("ready_for_positioning", "specific_pain_identified"):
                self.state["eligible_positioning"] += 1
            elif ds == "specific_pain_emerging" and classified >= 3:
                self.state["eligible_positioning"] += 1
            elif ds == "broad_hiring_pattern_detected":
                # Conditional gate: classified >= 5 AND concentration != low.
                # top_share >= 0.35 is the concentration proxy.
                if classified >= 5 and top_share >= 0.35:
                    self.state.setdefault("eligible_positioning_conditional", 0)
                    self.state["eligible_positioning_conditional"] += 1
            self.state["jds_extracted"] += result.get("jds_extracted", 0)
            classified = result.get("classified", 0)
            if classified > 0:
                self.state["roles_classified"] += 1
            total_roles = result.get("total_roles", 0)
            if total_roles > 0:
                self.state["roles_detected"] += 1
            # Check careers from collection result or before/after
            before_ds_rank = DS_RANKS.get(result.get("before", {}).get("ds", ""), 0)
            after_ds_rank = DS_RANKS.get(ds, 0)
            if after_ds_rank >= 1:
                self.state["careers_found"] += 1

        self.state["current_stage"] = "idle"
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write()

    def finalize(self, status: str = "completed"):
        self.state["status"] = status
        self.state["current_stage"] = "done"
        self.state["current_company_name"] = ""
        elapsed = time.monotonic() - self._start_time
        self.state["elapsed_sec"] = round(elapsed)
        self.state["eta_sec"] = 0
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write()

        # Write summary
        with open(self.summary_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def _write(self):
        tmp = self.progress_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)
        # Windows: os.replace() intermittently hits PermissionError when an
        # antivirus or file indexer briefly locks the target ~ms after the
        # previous write. This is a known Windows issue, not a bug in our
        # logic. Retry with short backoff; on exhaustion swallow the error —
        # progress.json is observational (overwritten on the next company),
        # so losing one snapshot is vastly preferable to killing the worker.
        last_err = None
        for attempt in range(6):
            try:
                tmp.replace(self.progress_file)
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.05 * (attempt + 1))
        try:
            tmp.unlink()
        except Exception:
            pass
        # Don't raise — this is non-fatal telemetry state.


# ── Worker progress writer (dynamic scheduling mode) ────────────────

class WorkerProgressWriter:
    """Per-worker progress.json for dynamic scheduling mode.

    Unlike ShardProgressWriter (which tracks one fixed shard), this
    tracks a worker that claims arbitrary chunks from a central queue.
    """

    def __init__(self, worker_dir: str, worker_id: int,
                 run_id: str, parent_run_id: str):
        self.worker_dir = Path(worker_dir)
        self.worker_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.worker_dir / "progress.json"
        self.summary_file = self.worker_dir / "summary.json"
        now = datetime.now(timezone.utc).isoformat()
        self.state = {
            "worker_id": worker_id,
            "pid": os.getpid(),
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "status": "idle",
            "current_chunk_id": None,
            "current_chunk_size": 0,
            "current_chunk_processed": 0,
            "chunks_completed": 0,
            "chunks_failed": 0,
            "companies_processed": 0,
            "companies_success": 0,
            "companies_failed": 0,
            "current_company_name": "",
            "current_stage": "starting",
            "started_at": now,
            "updated_at": now,
            "elapsed_sec": 0,
            "avg_sec_per_company": 0,
            "careers_found": 0,
            "roles_detected": 0,
            "roles_classified": 0,
            "jds_extracted": 0,
            "eligible_positioning": 0,
            "last_error_message": "",
        }
        self._t_start = time.monotonic()
        self._write()

    def start_chunk(self, chunk_id: int, size: int):
        self.state["status"] = "running"
        self.state["current_chunk_id"] = chunk_id
        self.state["current_chunk_size"] = size
        self.state["current_chunk_processed"] = 0
        self.state["current_stage"] = "claimed_chunk"
        self._touch()

    def update_company(self, name: str, stage: str = "processing"):
        self.state["current_company_name"] = (name or "")[:60]
        self.state["current_stage"] = stage
        self._touch()

    def record_company_result(self, result: dict):
        status = result.get("status", "error")
        if status == "ok":
            self.state["companies_success"] += 1
            after = result.get("after", {})
            ds = after.get("ds", "")
            # Mirror positioning_engine gates (see ShardProgressWriter above).
            classified = result.get("classified", 0)
            top_share = result.get("top_share", 0)
            if ds in ("ready_for_positioning", "specific_pain_identified"):
                self.state["eligible_positioning"] += 1
            elif ds == "specific_pain_emerging" and classified >= 3:
                self.state["eligible_positioning"] += 1
            elif ds == "broad_hiring_pattern_detected":
                if classified >= 5 and top_share >= 0.35:
                    self.state.setdefault("eligible_positioning_conditional", 0)
                    self.state["eligible_positioning_conditional"] += 1
            self.state["jds_extracted"] += result.get("jds_extracted", 0)
            if result.get("classified", 0) > 0:
                self.state["roles_classified"] += 1
            if result.get("total_roles", 0) > 0:
                self.state["roles_detected"] += 1
            after_rank = DS_RANKS.get(ds, 0)
            if after_rank >= 1:
                self.state["careers_found"] += 1
        else:
            self.state["companies_failed"] += 1
            self.state["last_error_message"] = (result.get("error") or "")[:200]

        self.state["companies_processed"] = (
            self.state["companies_success"] + self.state["companies_failed"]
        )
        self.state["current_chunk_processed"] += 1

        elapsed = time.monotonic() - self._t_start
        self.state["elapsed_sec"] = round(elapsed)
        p = self.state["companies_processed"]
        if p > 0:
            self.state["avg_sec_per_company"] = round(elapsed / p, 1)
        self._touch()

    def finish_chunk(self, success: bool = True):
        if success:
            self.state["chunks_completed"] += 1
        else:
            self.state["chunks_failed"] += 1
        self.state["status"] = "idle"
        self.state["current_chunk_id"] = None
        self.state["current_chunk_size"] = 0
        self.state["current_chunk_processed"] = 0
        self.state["current_company_name"] = ""
        self.state["current_stage"] = "between_chunks"
        self._touch()

    def finalize(self, status: str = "completed"):
        self.state["status"] = status
        self.state["current_stage"] = "done"
        elapsed = time.monotonic() - self._t_start
        self.state["elapsed_sec"] = round(elapsed)
        self._touch()
        with open(self.summary_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def _touch(self):
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write()

    def _write(self):
        tmp = self.progress_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)
        # See ShardProgressWriter._write: Windows os.replace() is flaky under
        # AV/indexer load. Retry + swallow keeps the worker alive.
        for attempt in range(6):
            try:
                tmp.replace(self.progress_file)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
        try:
            tmp.unlink()
        except Exception:
            pass


def run_dynamic_worker(worker_id: int, queue_dir: Path, worker_dir: Path,
                       parent_run_id: str, full_pipeline: bool):
    """Worker main loop: claim chunks from the central queue until drained.

    Exits cleanly when:
      - pending/ is empty AND running/ is empty (queue fully drained)

    Loiters (with exponential backoff) when pending/ is empty but
    running/ still has work (a peer might crash and orphan a chunk).
    """
    from scripts import chunk_queue as cq

    run_id = _generate_run_id(f"worker_{worker_id:02d}")
    ctx = RunContext(run_id)
    progress_writer = WorkerProgressWriter(
        worker_dir=str(worker_dir), worker_id=worker_id,
        run_id=run_id, parent_run_id=parent_run_id,
    )

    ctx.write_manifest(
        params={
            "mode": "dynamic_worker",
            "worker_id": worker_id,
            "parent_run_id": parent_run_id,
            "full_pipeline": full_pipeline,
        },
        total_companies=0,
    )

    print(f"[worker {worker_id}] PID={os.getpid()}, starting dynamic loop")

    chunks_done = 0
    total_success = 0
    total_failed = 0
    backoff = 1.0
    max_backoff = 10.0

    def _safe(fn, *a, **kw):
        """Swallow exceptions in progress/queue side-effects so they can't kill the worker."""
        try:
            return fn(*a, **kw)
        except Exception as ex:
            print(f"[worker {worker_id}] WARN: {fn.__name__} raised: {ex}")
            return None

    try:
        while True:
            # --- Claim next chunk (defensive against queue I/O errors) ---
            try:
                chunk = cq.claim_next_chunk(queue_dir, worker_id, os.getpid())
            except Exception as e:
                print(f"[worker {worker_id}] claim_next_chunk raised: {e}. Retrying in 2s.")
                time.sleep(2)
                continue

            if chunk is None:
                try:
                    counts = cq.queue_state_counts(queue_dir)
                except Exception:
                    counts = {"pending": 0, "running": 0}
                if counts.get("pending", 0) == 0 and counts.get("running", 0) == 0:
                    print(f"[worker {worker_id}] Queue fully drained. Exiting.")
                    break
                print(
                    f"[worker {worker_id}] No pending chunks "
                    f"(running={counts.get('running', 0)}). Sleeping {backoff:.1f}s..."
                )
                time.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 1.5, max_backoff)
                continue
            backoff = 1.0

            chunk_id = chunk.get("chunk_id", -1)
            companies = chunk.get("companies", [])
            # Pre-cooked failures from prior watchdog kills — count them
            # toward the chunk's failed total so master summary reflects reality.
            pre_skipped = list(chunk.get("watchdog_skipped", []))
            _safe(progress_writer.start_chunk, chunk_id, len(companies))
            if pre_skipped:
                print(
                    f"[worker {worker_id}] Chunk {chunk_id:04d} has "
                    f"{len(pre_skipped)} watchdog-skipped companies from prior run."
                )

            t_chunk = time.monotonic()
            chunk_success = 0
            chunk_failed = len(pre_skipped)
            results = list(pre_skipped)
            chunk_crashed = False
            chunk_error_msg = ""

            # --- Process chunk companies (per-company errors are handled inline) ---
            try:
                for c in companies:
                    _safe(progress_writer.update_company, c.get("name", ""), "processing")
                    db = None
                    try:
                        db = SessionLocal()
                        if full_pipeline:
                            result = process_company_full(
                                db, c["id"], c["name"], c["domain"], ctx.logger
                            )
                        else:
                            result = process_company(
                                db, c["id"], c["name"], c["domain"], ctx.logger
                            )
                        _safe(ctx.append_progress, result)
                        _safe(progress_writer.record_company_result, result)
                        results.append(result)
                        chunk_success += 1
                    except Exception as e:
                        err = {
                            "company_id": c.get("id"),
                            "name": c.get("name"),
                            "domain": c.get("domain"),
                            "status": "error",
                            "error": str(e),
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                        _safe(ctx.append_progress, err)
                        _safe(progress_writer.record_company_result, err)
                        results.append(err)
                        chunk_failed += 1
                        try:
                            if db is not None:
                                db.rollback()
                        except Exception:
                            pass
                        try:
                            ctx.logger.error(f"FAIL {c.get('name')}: {e}")
                        except Exception:
                            pass
                    finally:
                        try:
                            if db is not None:
                                db.close()
                        except Exception:
                            pass
            except Exception as e:
                chunk_crashed = True
                chunk_error_msg = f"chunk loop crashed: {e}"
                try:
                    ctx.logger.error(
                        f"Chunk {chunk_id} loop crashed: {e}", exc_info=True
                    )
                except Exception:
                    pass

            elapsed = time.monotonic() - t_chunk

            # --- Persist chunk outcome (both calls are wrapped to never kill worker) ---
            if chunk_crashed:
                _safe(cq.mark_chunk_failed, queue_dir, chunk, chunk_error_msg)
                _safe(progress_writer.finish_chunk, success=False)
                print(f"[worker {worker_id}] Chunk {chunk_id:04d} CRASHED: {chunk_error_msg}")
            else:
                moved = _safe(
                    cq.mark_chunk_completed,
                    queue_dir, chunk, chunk_success, chunk_failed, elapsed, results,
                )
                if moved is None and chunk.get("_running_file"):
                    # mark_completed couldn't move it; try to mark as failed so
                    # it doesn't get stuck in running/ forever.
                    _safe(cq.mark_chunk_failed, queue_dir, chunk,
                          "mark_chunk_completed failed to move file")
                    _safe(progress_writer.finish_chunk, success=False)
                    print(
                        f"[worker {worker_id}] Chunk {chunk_id:04d} completed "
                        f"but file move failed; marked as failed."
                    )
                else:
                    _safe(progress_writer.finish_chunk, success=True)
                    chunks_done += 1
                    total_success += chunk_success
                    total_failed += chunk_failed
                    print(
                        f"[worker {worker_id}] Chunk {chunk_id:04d} done: "
                        f"{chunk_success} ok, {chunk_failed} fail, {elapsed:.0f}s"
                    )
    finally:
        _safe(progress_writer.finalize)
        _safe(
            ctx.finalize_manifest,
            succeeded=total_success, failed=total_failed, skipped=0,
        )
        print(
            f"[worker {worker_id}] Finished. "
            f"{chunks_done} chunks, {total_success + total_failed} companies processed "
            f"({total_success} ok, {total_failed} fail)."
        )


def run_batch_shard(ctx: RunContext, companies: list[dict], full_pipeline: bool,
                    shard_writer: ShardProgressWriter):
    """Process companies in shard mode with detailed progress reporting."""
    succeeded = 0
    failed = 0
    t_start = time.monotonic()

    for i, c in enumerate(companies):
        shard_writer.update_current(c["name"], "processing")

        elapsed_total = time.monotonic() - t_start
        avg = elapsed_total / max(i, 1)
        eta = avg * (len(companies) - i) if i > 0 else 0

        print(
            f"[shard] [{i+1}/{len(companies)}] {c['name'][:35]:35s} ",
            end="", flush=True,
        )

        db = SessionLocal()
        try:
            if full_pipeline:
                result = process_company_full(db, c["id"], c["name"], c["domain"], ctx.logger)
            else:
                result = process_company(db, c["id"], c["name"], c["domain"], ctx.logger)
            ctx.append_progress(result)
            shard_writer.record_result(result)
            succeeded += 1

            marker = ">>>" if result["direction"] == "improved" else \
                     "<<<" if result["direction"] == "degraded" else "   "
            print(
                f"{marker} ds:{result['after']['ds'][:20]:20s} "
                f"{result['elapsed_s']:.1f}s"
            )
        except Exception as e:
            failed += 1
            error_entry = {
                "company_id": c["id"],
                "name": c["name"],
                "domain": c["domain"],
                "status": "error",
                "error": str(e),
                "elapsed_s": round(time.monotonic() - t_start, 2),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            ctx.append_progress(error_entry)
            shard_writer.record_result(error_entry)
            print(f"ERROR: {e}")
            ctx.logger.error(f"FAIL {c['name']}: {e}")
            db.rollback()
        finally:
            db.close()

        if (i + 1) % 10 == 0:
            ctx.update_manifest(processed=succeeded + failed, succeeded=succeeded, failed=failed)

    total_time = time.monotonic() - t_start
    ctx.finalize_manifest(succeeded=succeeded, failed=failed, skipped=0)
    shard_writer.finalize("completed")

    ctx.logger.info(
        f"Shard complete: {succeeded} ok, {failed} errors, "
        f"{total_time:.0f}s total ({total_time/max(succeeded+failed, 1):.1f}s avg)"
    )
    return succeeded, failed


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hardened Batch Runner — staging-ready analysis CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit", type=int, default=100, help="Max companies to process (default: 100)")
    parser.add_argument("--min-roles", type=int, default=2, help="Minimum role count for selection (default: 2)")
    parser.add_argument("--all", action="store_true",
                        help="Select ALL companies with domain (not just those with roles)")
    parser.add_argument("--full-pipeline", action="store_true",
                        help="Run full pipeline (collection + extraction + scoring + evaluation)")
    parser.add_argument("--pending-only", action="store_true",
                        help="Only companies not yet processed in a previous run")
    parser.add_argument("--since-run", type=str, default=None, metavar="RUN_ID",
                        help="With --pending-only, skip companies processed in this run")
    parser.add_argument("--label", type=str, default=None, help="Label for the run (default: tier{limit})")
    parser.add_argument("--resume", type=str, default=None, metavar="RUN_ID",
                        help="Resume a previous run by ID")
    parser.add_argument("--retry-errors", action="store_true",
                        help="With --resume, also retry companies that errored")
    parser.add_argument("--company-id", type=str, default=None, help="Process a single company")
    parser.add_argument("--dry-run", action="store_true", help="Select companies and print plan, don't process")
    parser.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"),
                        help="Compare two runs")
    parser.add_argument("--list-runs", action="store_true", help="List previous runs")

    # Shard mode (used by run_parallel_batch.py)
    parser.add_argument("--shard-file", type=str, default=None,
                        help="Path to JSON file with company list for this shard")
    parser.add_argument("--shard-index", type=int, default=None,
                        help="Shard index (0-based)")
    parser.add_argument("--shard-total", type=int, default=None,
                        help="Total number of shards")
    parser.add_argument("--shard-progress-dir", type=str, default=None,
                        help="Directory to write progress.json for master monitoring")
    parser.add_argument("--parent-run-id", type=str, default=None,
                        help="Parent run ID (set by master orchestrator)")

    # Dynamic scheduling worker mode (used by run_parallel_batch.py --dynamic-scheduling)
    parser.add_argument("--queue-dir", type=str, default=None,
                        help="Queue directory (dynamic scheduling mode)")
    parser.add_argument("--worker-id", type=int, default=None,
                        help="Worker index (0-based) for dynamic scheduling")
    parser.add_argument("--worker-dir", type=str, default=None,
                        help="Directory for worker progress.json (dynamic mode)")

    args = parser.parse_args()

    # ── Mode: list runs
    if args.list_runs:
        list_runs()
        return

    # ── Mode: compare
    if args.compare:
        compare_runs(args.compare[0], args.compare[1])
        return

    # ── Mode: dynamic worker (launched by run_parallel_batch.py --dynamic-scheduling)
    if args.queue_dir:
        if args.worker_id is None or args.worker_dir is None:
            print("ERROR: --queue-dir requires --worker-id and --worker-dir")
            sys.exit(1)

        run_dynamic_worker(
            worker_id=args.worker_id,
            queue_dir=Path(args.queue_dir),
            worker_dir=Path(args.worker_dir),
            parent_run_id=args.parent_run_id or "",
            full_pipeline=args.full_pipeline,
        )
        return

    # ── Mode: shard (launched by run_parallel_batch.py)
    if args.shard_file:
        if args.shard_index is None or args.shard_total is None or args.shard_progress_dir is None:
            print("ERROR: --shard-file requires --shard-index, --shard-total, and --shard-progress-dir")
            sys.exit(1)

        with open(args.shard_file, "r", encoding="utf-8") as f:
            companies = json.load(f)

        label = args.label or f"shard_{args.shard_index:02d}"
        ctx = RunContext(_generate_run_id(label))

        shard_writer = ShardProgressWriter(
            progress_dir=args.shard_progress_dir,
            shard_index=args.shard_index,
            shard_total=args.shard_total,
            run_id=ctx.run_id,
            parent_run_id=args.parent_run_id or "",
            total_in_shard=len(companies),
        )

        ctx.write_manifest(
            params={
                "shard_index": args.shard_index,
                "shard_total": args.shard_total,
                "shard_file": args.shard_file,
                "full_pipeline": args.full_pipeline,
                "parent_run_id": args.parent_run_id,
            },
            total_companies=len(companies),
        )

        print(f"[Shard {args.shard_index}/{args.shard_total}] PID={os.getpid()}, {len(companies)} companies")
        succeeded, failed = run_batch_shard(
            ctx, companies, full_pipeline=args.full_pipeline, shard_writer=shard_writer,
        )

        report = generate_report(ctx)
        print_report(report)
        backfill_diagnostic_state(ctx)
        return

    # ── Mode: single company
    if args.company_id:
        label = args.label or "single"
        ctx = RunContext(_generate_run_id(label))
        ctx.logger.info(f"Single company: {args.company_id}")
        db = SessionLocal()
        try:
            result = process_company(db, args.company_id, "single", "", ctx.logger)
            ctx.append_progress(result)
            print(json.dumps(result, indent=2, default=str))
        except Exception as e:
            print(f"ERROR: {e}")
            db.rollback()
        finally:
            db.close()
        return

    # ── Mode: batch
    db = SessionLocal()

    # Handle resume
    skip_ids = set()
    if args.resume:
        resume_ctx = RunContext(args.resume)
        if not resume_ctx.manifest_path.exists():
            print(f"Run not found: {args.resume}")
            db.close()
            return
        skip_ids = resume_ctx.get_done_ids(include_errors=not args.retry_errors)
        print(f"[Resume] Loading {args.resume}: {len(skip_ids)} already done")

    # Handle --pending-only: load already-processed IDs from a previous run
    if args.pending_only:
        if args.since_run:
            prev_ctx = RunContext(args.since_run)
            prev_done = prev_ctx.get_done_ids(include_errors=False)
            skip_ids = skip_ids | prev_done
            print(f"[Pending] Excluding {len(prev_done)} companies from run {args.since_run}")
        else:
            # Scan all runs and collect all successfully processed IDs
            all_done = set()
            if RUNS_DIR.exists():
                for run_dir in RUNS_DIR.iterdir():
                    if run_dir.is_dir():
                        prev_ctx = RunContext(run_dir.name)
                        all_done |= prev_ctx.get_done_ids(include_errors=False)
            skip_ids = skip_ids | all_done
            print(f"[Pending] Excluding {len(all_done)} companies from all previous runs")

    # Select companies
    if args.all:
        print(f"Selecting ALL companies with domain (up to {args.limit})...")
        companies = select_all_companies(db, limit=args.limit)
    else:
        print(f"Selecting up to {args.limit} companies with >= {args.min_roles} roles...")
        companies = select_companies(db, limit=args.limit, min_roles=args.min_roles)
    db.close()

    if not companies:
        print("No companies matched selection criteria.")
        return

    pending_count = len([c for c in companies if c["id"] not in skip_ids])
    print(f"Selected {len(companies)} companies, {pending_count} pending")

    # Dry run
    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"  DRY RUN — would process {pending_count} companies")
        print(f"{'='*60}")
        for i, c in enumerate(companies):
            skip_mark = " [SKIP]" if c["id"] in skip_ids else ""
            print(f"  {i+1:4d}. {c['name'][:40]:40s} {c['domain']:30s} {c['roles']:3d} roles{skip_mark}")
        return

    # Create run context
    label = args.label or (f"all{args.limit}" if args.all else f"tier{args.limit}")
    if args.resume:
        ctx = RunContext(args.resume)
        ctx.logger.info(f"Resuming run with {pending_count} pending")
    else:
        ctx = RunContext(_generate_run_id(label))

    ctx.write_manifest(
        params={
            "limit": args.limit,
            "min_roles": args.min_roles,
            "select_all": args.all,
            "full_pipeline": args.full_pipeline,
            "pending_only": args.pending_only,
            "since_run": args.since_run,
            "label": label,
            "resume_from": args.resume,
            "retry_errors": args.retry_errors,
        },
        total_companies=len(companies),
    )

    # Run batch
    succeeded, failed, skipped = run_batch(
        ctx, companies, skip_ids=skip_ids, full_pipeline=args.full_pipeline
    )

    # Generate and print report
    report = generate_report(ctx)
    print_report(report)

    # Backfill latest_diagnostic_state on companies table
    print("\n  Backfilling latest_diagnostic_state...", end=" ", flush=True)
    updated = backfill_diagnostic_state(ctx)
    print(f"{updated} companies updated")

    print(f"\n  Run artifacts:")
    print(f"    Manifest:  {ctx.manifest_path}")
    print(f"    Progress:  {ctx.progress_path}")
    print(f"    Report:    {ctx.report_path}")
    print(f"    Log:       {ctx.log_path}")


if __name__ == "__main__":
    main()
