"""Nightly Intelligence Orchestrator — runs at 1:00 AM server time daily.

Pipeline responsibilities:
  1. ATS refresh — re-probe detected ATS boards
  2. Careers page refresh — re-capture known careers URLs
  3. Signal extraction — re-classify roles, update signals
  4. Pain recomputation — re-score all companies
  5. Heatmap regeneration — rebuild sector×function grid
  6. Candidate alignment recomputation — re-align VIP candidates
  7. VIP opportunity regeneration — refresh VIP opportunities
  8. Snapshot persistence — store temporal snapshots
  9. Temporal trend tracking — compute deltas and velocity
  10. Delta computation — compare current vs previous scores

Implements:
  - Retry logic with exponential backoff
  - Observability via structured logging
  - Failure recovery (partial success allowed)
  - Incremental refresh (skip recently refreshed)
  - Snapshot versioning
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.logging import get_logger
from app.models.company import Company
from app.models.friction_score import FrictionScore
from app.models.company_signal import CompanySignal
from app.models.company_job_role import CompanyJobRole
from app.models.candidate_intelligence import (
    FrictionCompanyProfile,
    FrictionTemporalSnapshot,
)
from app.services.scoring_engine import compute_and_persist_score
from app.services.positioning_engine import (
    positioning_engine,
    is_company_positioning_eligible,
    compute_eligibility_snapshot,
)
from app.services.final_verdict_engine import final_verdict_engine
from app.services.company_evaluation import company_evaluation_engine
from app.services.company_type_engine import company_type_engine
from app.services.hiring_pattern_service import compute_hiring_pattern
from app.services.vip_positioning_engine import vip_positioning_engine
from app.services.candidate_intelligence_extractor import candidate_intelligence_extractor

logger = get_logger(__name__)

# Maximum retries per step
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class NightlyOrchestrator:
    """Orchestrates the nightly intelligence refresh pipeline."""

    def __init__(self):
        self.run_id = f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.results = {}
        self.start_time = None
        self.errors = []

    # ── Lock/result file paths for status endpoint ─────────────────
    RUNS_DIR = Path("runs")
    LOCK_FILE = RUNS_DIR / "nightly_running.lock"
    RESULT_FILE = RUNS_DIR / "nightly_last_result.json"

    def _write_lock(self):
        self.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.LOCK_FILE.write_text(json.dumps({
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }))

    def _write_result(self, summary: dict):
        self.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.RESULT_FILE.write_text(json.dumps(summary, default=str))

    def _remove_lock(self):
        if self.LOCK_FILE.exists():
            self.LOCK_FILE.unlink(missing_ok=True)

    def run(self, db: Session) -> dict:
        """Execute the full nightly pipeline.

        Returns a summary dict with step results and timing.
        """
        self.start_time = datetime.now(timezone.utc)
        self._write_lock()
        logger.info(f"[Nightly] Starting nightly run: {self.run_id}")

        steps = [
            ("1_ats_refresh", self._step_ats_refresh),
            ("2_careers_refresh", self._step_careers_refresh),
            ("3_signal_extraction", self._step_signal_extraction),
            ("4_pain_recomputation", self._step_pain_recomputation),
            ("5_heatmap_regen", self._step_heatmap_regeneration),
            ("6_candidate_alignment", self._step_candidate_alignment),
            ("7_vip_regeneration", self._step_vip_regeneration),
            ("8_snapshot_persistence", self._step_snapshot_persistence),
            ("9_temporal_tracking", self._step_temporal_tracking),
            ("10_delta_computation", self._step_delta_computation),
        ]

        for step_name, step_fn in steps:
            step_start = time.monotonic()
            try:
                result = self._run_with_retry(step_fn, db)
                elapsed = round(time.monotonic() - step_start, 2)
                self.results[step_name] = {
                    "status": "ok",
                    "elapsed_s": elapsed,
                    "result": result,
                }
                logger.info(f"[Nightly] Step {step_name}: OK ({elapsed}s)")
            except Exception as e:
                elapsed = round(time.monotonic() - step_start, 2)
                self.results[step_name] = {
                    "status": "error",
                    "elapsed_s": elapsed,
                    "error": str(e),
                }
                self.errors.append({"step": step_name, "error": str(e)})
                logger.error(f"[Nightly] Step {step_name}: FAILED ({elapsed}s) — {e}")

        total_elapsed = round(time.monotonic() - (self.start_time.timestamp() if hasattr(self.start_time, 'timestamp') else 0), 2)
        summary = {
            "run_id": self.run_id,
            "started_at": self.start_time.isoformat() if self.start_time else None,
            "total_elapsed_s": total_elapsed,
            "steps": self.results,
            "errors": self.errors,
            "error_count": len(self.errors),
        }

        logger.info(
            f"[Nightly] Run complete: {self.run_id} "
            f"({len(self.errors)} errors, {total_elapsed}s)"
        )

        self._write_result(summary)
        self._remove_lock()

        return summary

    def _run_with_retry(self, fn, db: Session, *args, **kwargs):
        """Run a step function with exponential backoff retry."""
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn(db, *args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    backoff = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        f"[Nightly] Retry {attempt + 1}/{MAX_RETRIES} "
                        f"after {backoff}s: {e}"
                    )
                    time.sleep(backoff)
                    # Rollback any partial DB state
                    try:
                        db.rollback()
                    except Exception:
                        pass
        raise last_error

    # ── Step implementations ────────────────────────────────────────────────

    def _step_ats_refresh(self, db: Session) -> dict:
        """Re-probe detected ATS boards for updated job counts."""
        companies_with_ats = (
            db.query(Company)
            .join(CompanySignal, Company.id == CompanySignal.company_id)
            .filter(
                CompanySignal.signal_type.in_([
                    "greenhouse_board_detected",
                    "lever_board_detected",
                    "ashby_board_detected",
                    "smartrecruiters_board_detected",
                    "jobvite_board_detected",
                    "icims_board_detected",
                    "workday_board_detected",
                ])
            )
            .distinct()
            .all()
        )

        refreshed = 0
        skipped = 0

        # Only refresh if stale (> 24h since last collection)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        for company in companies_with_ats:
            if company.last_collection_at and company.last_collection_at > cutoff:
                skipped += 1
                continue

            try:
                from app.services.collection_orchestrator import run_collection_for_company
                from app.models.collection_run import CollectionRun

                run = CollectionRun(
                    company_id=company.id,
                    collector_type="nightly_ats_refresh",
                    status="pending",
                )
                db.add(run)
                db.commit()
                db.refresh(run)

                run_collection_for_company(company.id, run.id)
                refreshed += 1
            except Exception as e:
                logger.warning(f"[Nightly] ATS refresh failed for {company.domain}: {e}")

        return {"refreshed": refreshed, "skipped_fresh": skipped}

    def _step_careers_refresh(self, db: Session) -> dict:
        """Re-capture known careers URLs for companies with stale data."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        stale_companies = (
            db.query(Company)
            .filter(
                Company.careers_url.isnot(None),
                (Company.last_collection_at == None) | (Company.last_collection_at < cutoff),  # noqa: E711
            )
            .limit(100)  # Cap to avoid overnight overload
            .all()
        )

        refreshed = 0
        for company in stale_companies:
            try:
                from app.services.collection_orchestrator import extract_careers_evidence
                import asyncio

                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        extract_careers_evidence(
                            db, company.id, company.domain,
                            known_careers_url=company.careers_url
                        )
                    )
                    refreshed += 1
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"[Nightly] Careers refresh failed for {company.domain}: {e}")

        return {"refreshed": refreshed, "total_stale": len(stale_companies)}

    def _step_signal_extraction(self, db: Session) -> dict:
        """Re-classify roles and update hiring patterns."""
        companies_with_roles = (
            db.query(Company)
            .join(CompanyJobRole, Company.id == CompanyJobRole.company_id)
            .distinct()
            .limit(200)
            .all()
        )

        updated = 0
        for company in companies_with_roles:
            try:
                compute_hiring_pattern(db, company.id)
                updated += 1
            except Exception as e:
                logger.warning(f"[Nightly] Hiring pattern failed for {company.domain}: {e}")

        return {"updated_patterns": updated}

    def _step_pain_recomputation(self, db: Session) -> dict:
        """Re-score all companies and update eligibility."""
        companies = db.query(Company).all()

        scored = 0
        eligible = 0
        for company in companies:
            try:
                score = compute_and_persist_score(db, company.id)

                # Update eligibility
                eligibility = is_company_positioning_eligible(db, company.id)
                company.positioning_eligible = eligibility.eligible
                company.latest_diagnostic_state = eligibility.diagnostic_state
                if eligibility.eligible:
                    eligible += 1

                # Update company profile enrichment
                self._update_friction_company_profile(company, score, eligibility, db)

                scored += 1
            except Exception as e:
                logger.warning(f"[Nightly] Scoring failed for {company.domain}: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

        db.commit()
        return {"scored": scored, "eligible": eligible}

    def _step_heatmap_regeneration(self, db: Session) -> dict:
        """Regenerate the friction heatmap data.

        The heatmap is computed on the fly by the frontend/API,
        but we update the pre-computed sector×function aggregates.
        """
        from app.services.sector_inference import infer_sector

        companies = db.query(Company).filter(
            Company.positioning_eligible == True  # noqa: E712
        ).all()

        sector_counts = {}
        for company in companies:
            if not company.inferred_sector:
                result = infer_sector(
                    industry=company.industry,
                    name=company.name,
                    domain=company.domain,
                    functional_areas=[],  # TODO: load from job roles
                )
                company.inferred_sector = result.sector
                company.inferred_sector_source = result.source
                company.inferred_sector_confidence = result.confidence

            sector = company.inferred_sector
            if sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

        db.commit()
        return {"sectors_updated": len(sector_counts), "companies_inferred": sum(sector_counts.values())}

    def _step_candidate_alignment(self, db: Session) -> dict:
        """Re-compute alignment for all users with intelligence profiles."""
        from app.models.candidate_intelligence import CandidateIntelligenceProfile

        profiles = db.query(CandidateIntelligenceProfile).all()
        aligned = 0

        for profile in profiles:
            try:
                # Re-extract intelligence (picks up new accomplishments)
                candidate = candidate_intelligence_extractor.extract(profile.user_id, db)

                # Align against eligible companies
                matches = alignment_engine.align_candidate_to_all(
                    candidate, db, min_score=0.15
                )
                aligned += len(matches)
            except Exception as e:
                logger.warning(f"[Nightly] Alignment failed for user {profile.user_id}: {e}")

        return {"profiles_processed": len(profiles), "total_matches": aligned}

    def _step_vip_regeneration(self, db: Session) -> dict:
        """Regenerate VIP opportunities for all VIP users."""
        # Get VIP users from Ascendia
        vip_users = self._get_vip_users(db)

        generated = 0
        for user_id in vip_users:
            try:
                opps = vip_positioning_engine.generate_opportunities(user_id, db)
                generated += len(opps)
            except Exception as e:
                logger.warning(f"[Nightly] VIP generation failed for user {user_id}: {e}")

        return {"vip_users": len(vip_users), "opportunities_generated": generated}

    def _step_snapshot_persistence(self, db: Session) -> dict:
        """Store temporal snapshots for all companies with scores."""
        companies_with_scores = (
            db.query(Company.id)
            .join(FrictionScore, Company.id == FrictionScore.company_id)
            .distinct()
            .all()
        )

        snapshots_created = 0
        now = datetime.now(timezone.utc)

        for (company_id,) in companies_with_scores:
            try:
                latest_score = (
                    db.query(FrictionScore)
                    .filter(FrictionScore.company_id == company_id)
                    .order_by(FrictionScore.computed_at.desc())
                    .first()
                )

                if not latest_score:
                    continue

                # Check if snapshot already exists for today
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                existing = (
                    db.query(FrictionTemporalSnapshot)
                    .filter(
                        FrictionTemporalSnapshot.company_id == company_id,
                        FrictionTemporalSnapshot.snapshot_date >= today_start,
                    )
                    .first()
                )

                if existing:
                    continue  # Already have today's snapshot

                # Count signals and roles
                signal_count = (
                    db.query(CompanySignal)
                    .filter(CompanySignal.company_id == company_id)
                    .count()
                )
                roles_count = (
                    db.query(CompanyJobRole)
                    .filter(
                        CompanyJobRole.company_id == company_id,
                        CompanyJobRole.functional_area.isnot(None),
                        ~CompanyJobRole.functional_area.in_(["junk", "unknown"]),
                    )
                    .count()
                )

                # Get evaluation KPIs
                try:
                    evaluation = company_evaluation_engine.evaluate(
                        company_id=company_id, db=db
                    )
                except Exception:
                    evaluation = {}

                snapshot = FrictionTemporalSnapshot(
                    company_id=company_id,
                    snapshot_date=now,
                    dominant_friction_type=latest_score.dominant_friction_type,
                    total_score=float(latest_score.total_score) if latest_score.total_score else None,
                    category_scores=latest_score.scoring_breakdown_json or {},
                    diagnostic_state=evaluation.get("diagnostic_state"),
                    pain_clarity=evaluation.get("kpis", {}).get("pain_clarity"),
                    hiring_pressure=evaluation.get("kpis", {}).get("hiring_pressure"),
                    signal_count=signal_count,
                    classified_roles_count=roles_count,
                    snapshot_run_id=self.run_id,
                )
                db.add(snapshot)
                snapshots_created += 1

            except Exception as e:
                logger.warning(f"[Nightly] Snapshot failed for company {company_id}: {e}")

        db.commit()
        return {"snapshots_created": snapshots_created}

    def _step_temporal_tracking(self, db: Session) -> dict:
        """Compute temporal trends using score delta and velocity engines."""
        tracked = 0
        try:
            from app.services.score_delta_engine import ScoreDeltaEngine
            from app.services.signal_velocity_tracker import SignalVelocityTracker

            companies = db.query(Company).limit(200).all()
            for company in companies:
                try:
                    delta_engine = ScoreDeltaEngine()
                    velocity_tracker = SignalVelocityTracker()

                    delta_engine.compute_deltas(db, company.id)
                    velocity_tracker.compute_velocity(db, company.id)
                    tracked += 1
                except Exception as e:
                    logger.debug(f"[Nightly] Temporal tracking skipped for {company.id}: {e}")
                    continue
        except ImportError as e:
            logger.warning(f"[Nightly] Temporal engines not available: {e}")

        return {"companies_tracked": tracked}

    def _step_delta_computation(self, db: Session) -> dict:
        """Compare current vs previous scores and compute deltas."""
        # Get companies with at least 2 score snapshots
        companies_with_history = (
            db.query(FrictionScore.company_id)
            .group_by(FrictionScore.company_id)
            .having(db.func.count(FrictionScore.id) >= 2)
            .all()
        )

        deltas_computed = 0
        for (company_id,) in companies_with_history:
            try:
                scores = (
                    db.query(FrictionScore)
                    .filter(FrictionScore.company_id == company_id)
                    .order_by(FrictionScore.computed_at.desc())
                    .limit(2)
                    .all()
                )

                if len(scores) >= 2:
                    current = float(scores[0].total_score or 0)
                    previous = float(scores[1].total_score or 0)
                    delta = round(current - previous, 2)

                    # Update the company's temporal snapshot if exists
                    snapshot = (
                        db.query(FrictionTemporalSnapshot)
                        .filter(
                            FrictionTemporalSnapshot.company_id == company_id,
                            FrictionTemporalSnapshot.snapshot_run_id == self.run_id,
                        )
                        .first()
                    )
                    if snapshot and snapshot.category_scores:
                        # Store delta in the snapshot's category_scores
                        cat_scores = snapshot.category_scores or {}
                        if isinstance(cat_scores, dict):
                            cat_scores["_delta_total"] = delta
                            snapshot.category_scores = cat_scores

                    deltas_computed += 1
            except Exception as e:
                logger.debug(f"[Nightly] Delta computation failed for {company_id}: {e}")

        db.commit()
        return {"deltas_computed": deltas_computed}

    # ── Helper methods ──────────────────────────────────────────────────────

    def _update_friction_company_profile(
        self,
        company: Company,
        score: FrictionScore,
        eligibility,
        db: Session,
    ) -> None:
        """Update the FrictionCompanyProfile enrichment table."""
        try:
            # Get verdict
            signals = (
                db.query(CompanySignal)
                .filter(CompanySignal.company_id == company.id)
                .all()
            )
            type_result = company_type_engine.analyze(signals, len(signals), False)
            verdict = final_verdict_engine.generate(
                company=company,
                signals=signals,
                score=score,
                hypothesis=None,
                company_type=type_result.get("company_type", "unclear"),
                db=db,
            )

            # Get positioning output
            positioning = positioning_engine.generate(company_id=company.id, db=db)

            # Upsert profile
            existing = (
                db.query(FrictionCompanyProfile)
                .filter(FrictionCompanyProfile.company_id == company.id)
                .first()
            )

            values = {
                "dominant_pain": verdict.get("main_pain"),
                "pain_dimensions": score.scoring_breakdown_json or {},
                "pain_clarity": verdict.get("pain_clarity"),
                "diagnostic_state": verdict.get("diagnosis_status"),
                "recommended_positioning": verdict.get("recommended_positioning"),
                "candidate_archetype": positioning.candidate_archetype if positioning else None,
                "positioning_angle": positioning.positioning_angle if positioning else None,
                "resume_emphasis": positioning.resume_emphasis if positioning else [],
                "networking_angle": positioning.networking_angle if positioning else None,
                "interview_themes": positioning.interview_themes if positioning else [],
                "confidence_band": eligibility.confidence_band,
                "evidence_depth": positioning.evidence_depth if positioning else {},
                "temporal_status": verdict.get("temporal_status"),
                "trend_direction": verdict.get("trend_direction"),
            }

            if existing:
                for key, val in values.items():
                    setattr(existing, key, val)
            else:
                profile = FrictionCompanyProfile(
                    company_id=company.id,
                    **values,
                )
                db.add(profile)

        except Exception as e:
            logger.debug(f"[Nightly] Company profile update failed for {company.domain}: {e}")

    def _get_vip_users(self, db: Session) -> list[UUID]:
        """Get VIP user IDs from Ascendia tables.

        Tries to read from Ascendia's user/subscriptions tables.
        Falls back to known VIP users from configuration.
        """
        vip_users = []

        # Try Ascendia subscriptions table
        try:
            result = db.execute(
                text(
                    "SELECT user_id FROM subscriptions WHERE plan = 'vip' AND status = 'active'"
                )
            )
            rows = result.fetchall()
            vip_users = [UUID(str(row[0])) for row in rows]
        except Exception:
            logger.debug("Subscriptions table not available")

        # Fallback: configured VIP users
        if not vip_users:
            vip_config = os.environ.get("ASCENDIA_VIP_USER_IDS", "")
            if vip_config:
                for uid_str in vip_config.split(","):
                    uid_str = uid_str.strip()
                    if uid_str:
                        try:
                            vip_users.append(UUID(uid_str))
                        except ValueError:
                            pass

        return vip_users


nightly_orchestrator = NightlyOrchestrator()