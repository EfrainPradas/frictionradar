"""Core batch processor — orchestrates per-company analysis using backend services directly.

Changes from original:
  - Collection result from run_collection_for_company is now logged.
  - Playwright extraction runs inline (was already the case, but now we surface errors).
  - Per-company metadata includes collector results and discovery strategy.
  - QA + tiering + operational state mapping applied post-pipeline.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

# Add backend to path so we can import its internals.
_BACKEND = str(Path(__file__).resolve().parent.parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.db.session import SessionLocal
from app.models.collection_run import CollectionRun
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.opportunity_hypothesis import OpportunityHypothesis
from app.schemas.company import CompanyCreate
from app.services import company_service
from app.services.collection_orchestrator import run_collection_for_company
from app.services.company_evaluation import company_evaluation_engine
from app.services.company_type_engine import company_type_engine
from app.services.final_verdict_engine import final_verdict_engine
from app.services.hypothesis_engine import generate_and_persist_hypothesis
from app.services.scoring_engine import compute_and_persist_score
from app.services.qa_engine import evaluate_qa
from app.services.tiering_engine import assign_tier, safe_tier_summary
from app.services.operational_state_mapper import attach_qa_fields

from .status_engine import assign_status, EXCLUDED


def _get_db():
    return SessionLocal()


def _safe_rollback(db):
    try:
        db.rollback()
    except Exception:
        pass


def process_company(
    entry: dict[str, Any],
    all_companies_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze a single company end-to-end. Returns a result dict.

    Args:
        entry: company input data
        all_companies_snapshot: optional list of all company results for QA cross-checks
            (e.g., detecting repeated open_positions_count patterns)
    """
    name = entry["company_name"]
    domain = entry.get("domain", "")

    # Pre-excluded by input_loader (invalid domain, duplicate)
    if entry.get("_exclude_reason"):
        return _excluded_result(entry, entry["_exclude_reason"])

    db = _get_db()
    try:
        return _run_pipeline(db, entry, all_companies_snapshot)
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            db.rollback()
        except Exception:
            pass
        return _error_result(entry, str(exc), tb)
    finally:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass


def _run_pipeline(db, entry: dict[str, Any], all_companies_snapshot: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    name = entry["company_name"]
    domain = entry["domain"]

    pipeline_log: list[str] = []
    collection_meta: dict = {}

    # ── Step 1: create or load company ──────────────────────────────
    company = company_service.find_by_domain(db, domain)
    if company is None:
        company = company_service.create_company(
            db,
            CompanyCreate(
                name=name,
                domain=domain,
                industry=entry.get("industry"),
                company_size=None,
                source_added_from="cli_batch",
            ),
        )
        pipeline_log.append(f"Created new company: {company.id}")
    else:
        pipeline_log.append(f"Loaded existing company: {company.id}")

    company_id = company.id

    # ── Step 2: collection (sync collectors) ────────────────────────
    run = CollectionRun(
        company_id=company_id,
        collector_type="cli_batch",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = run_collection_for_company(db, company_id, run.id)
        collection_meta = result
        pipeline_log.append(f"Collection: {result.get('status', 'unknown')}")
        if result.get("signals_persisted") is not None:
            pipeline_log.append(f"  signals_persisted: {result['signals_persisted']}")
        if result.get("collectors"):
            for c in result["collectors"]:
                pipeline_log.append(f"  collector {c['collector']}: {c['signals']} signals ({c['status']})")
    except Exception as e:
        pipeline_log.append(f"Collection ERROR: {e}")
        _safe_rollback(db)

    # ── Step 3: smart extraction (ATS API → HTTP static → Playwright) ─
    open_positions = None
    extraction_meta: dict = {}
    try:
        from app.extraction.dispatcher import extract_company
        from app.extraction.schemas import NormalizedJobsResult

        # Detect ATS platform from sync collector signals
        detected_ats = None
        for sig in (
            db.query(CompanySignal)
            .filter(
                CompanySignal.company_id == company_id,
                CompanySignal.signal_type.like("%_board_detected"),
            )
            .all()
        ):
            # Extract platform from signal_type like "greenhouse_board_detected"
            detected_ats = sig.signal_type.replace("_board_detected", "")
            break

        # Run the extraction chain: ATS API → HTTP static → Playwright
        ext_result = extract_company(
            domain=domain,
            company_name=name,
            company_id=company_id,
            detected_ats_platform=detected_ats,
        )

        # Log extraction outcome
        pipeline_log.append(
            f"Extraction: strategy={ext_result.strategy_used.value} "
            f"reason={ext_result.reason_code.value} "
            f"success={ext_result.success} "
            f"jobs={ext_result.jobs_count} "
            f"positions={ext_result.open_positions_count} "
            f"quality={ext_result.evidence_quality} "
            f"duration={ext_result.duration_ms}ms"
        )
        if ext_result.fallback_from:
            pipeline_log.append(f"  fallback_from={ext_result.fallback_from.value}")
        if ext_result.error:
            pipeline_log.append(f"  error={ext_result.error}")

        extraction_meta = {
            "strategy": ext_result.strategy_used.value,
            "reason": ext_result.reason_code.value,
            "success": ext_result.success,
            "jobs_count": ext_result.jobs_count,
            "duration_ms": ext_result.duration_ms,
        }

        # Convert NormalizedJobsResult → signals for the scoring pipeline
        if ext_result.success:
            open_positions = ext_result.open_positions_count
            _persist_extraction_signals(db, company_id, ext_result, pipeline_log)

    except Exception as e:
        pipeline_log.append(f"Extraction ERROR: {e}")
        _safe_rollback(db)

    # ── Step 4: scoring ─────────────────────────────────────────────
    _safe_rollback(db)
    score = None
    try:
        score = compute_and_persist_score(
            db, company_id, open_positions_count=open_positions
        )
        pipeline_log.append(f"Scoring: {score.total_score} ({score.dominant_friction_type})")
    except Exception as e:
        pipeline_log.append(f"Scoring ERROR: {e}")
        _safe_rollback(db)

    # ── Step 5: hypothesis ──────────────────────────────────────────
    hypothesis = None
    if score is not None:
        try:
            hypothesis = generate_and_persist_hypothesis(db, company_id, score)
            pipeline_log.append("Hypothesis: generated")
        except Exception as e:
            pipeline_log.append(f"Hypothesis ERROR: {e}")
            _safe_rollback(db)

    # ── Step 6: company type ────────────────────────────────────────
    _safe_rollback(db)
    signals = (
        db.query(CompanySignal)
        .filter(CompanySignal.company_id == company_id)
        .all()
    )
    type_result = company_type_engine.analyze(
        signals, len(signals), hypothesis is not None
    )
    pipeline_log.append(f"Company type: {type_result.get('company_type')} (confidence: {type_result.get('company_type_confidence')})")

    # ── Step 7: evaluation scorecard ────────────────────────────────
    _safe_rollback(db)
    evaluation = company_evaluation_engine.evaluate(
        company_id=company_id,
        db=db,
        signals=signals,
        company_type_confidence=type_result.get("company_type_confidence"),
    )

    # ── Step 8: status assignment ───────────────────────────────────
    status, notes = assign_status(
        signals_count=len(signals),
        evaluation=evaluation,
        company_type=type_result.get("company_type"),
    )

    kpis = evaluation.get("kpis", {})
    evidence = evaluation.get("evidence", {})

    pipeline_log.append(f"Final status: {status} ({len(signals)} signals)")

    # ── Build raw result dict (pre-QA) ──────────────────────────────
    result_raw = {
        "company_name": company.name,
        "domain": company.domain,
        "company_id": str(company_id),
        "industry": entry.get("industry"),
        "location": entry.get("location"),
        "source": entry.get("source"),
        "status": status,
        "company_type": type_result.get("company_type"),
        "company_type_confidence": type_result.get("company_type_confidence"),
        "hiring_pressure": kpis.get("hiring_pressure"),
        "pain_clarity": kpis.get("pain_clarity"),
        "function_concentration": kpis.get("function_concentration"),
        "extraction_coverage": kpis.get("extraction_coverage"),
        "positioning_readiness": kpis.get("positioning_readiness"),
        "diagnosis_status": evaluation.get("diagnostic_state"),
        "signals_count": len(signals),
        "distinct_signals_count": evidence.get("distinct_signal_types", 0),
        "open_positions_count": evidence.get("open_positions_count", 0),
        "friction_score": float(score.total_score) if score else None,
        "dominant_friction_type": score.dominant_friction_type if score else None,
        "summary": evaluation.get("summary", ""),
        "notes": notes,
        "pipeline_log": pipeline_log,
        "collection_meta": collection_meta,
        "extraction_meta": extraction_meta,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── Step 9: QA evaluation ───────────────────────────────────────
    qa_snapshot = all_companies_snapshot or []
    qa_result = evaluate_qa(result_raw, qa_snapshot)
    pipeline_log.append(f"QA: pass={qa_result['qa_pass']} score={qa_result['qa_score']} flags={qa_result['qa_flags']}")

    # ── Step 10: Tier assignment ────────────────────────────────────
    target_tier, tier_rationale = assign_tier(result_raw, qa_result)
    pipeline_log.append(f"Tier: {target_tier}")

    # ── Build final result with all fields ──────────────────────────
    final = attach_qa_fields(result_raw, qa_result, target_tier, tier_rationale)

    # Override summary with tier-safe wording
    final["summary"] = safe_tier_summary(target_tier, result_raw)
    final["pipeline_log"] = pipeline_log
    final["updated_at"] = datetime.now(timezone.utc).isoformat()

    return final


def _persist_extraction_signals(db, company_id, ext_result, pipeline_log):
    """Convert NormalizedJobsResult into CompanySignal records.

    Maps extraction output to the signal types that the scoring and
    evaluation engines already understand.
    """
    from app.services.collection_orchestrator import _persist_signals_deduped

    source_type = f"extraction_{ext_result.strategy_used.value}"
    url = ext_result.careers_url or ""
    new_signals = []

    # Position count
    if ext_result.open_positions_count and ext_result.open_positions_count > 0:
        sig_type = (
            "high_open_positions_count_detected"
            if ext_result.open_positions_count >= 100
            else "open_positions_count_detected"
        )
        new_signals.append(CompanySignal(
            company_id=company_id,
            source_type=source_type,
            source_url=url,
            signal_type=sig_type,
            signal_text=f"Open positions: {ext_result.open_positions_count}",
            numeric_value=ext_result.open_positions_count,
            confidence=ext_result.confidence,
        ))

    # Job cards count
    if ext_result.jobs_count > 0:
        new_signals.append(CompanySignal(
            company_id=company_id,
            source_type=source_type,
            source_url=url,
            signal_type="job_cards_visible_detected",
            signal_text=f"Job listings found: {ext_result.jobs_count}",
            numeric_value=ext_result.jobs_count,
            confidence=ext_result.confidence,
        ))

    # Hiring areas
    area_to_signal = {
        "retail": "retail", "distribution": "distribution",
        "manufacturing": "manufacturing", "technology": "technology",
        "finance": "finance", "operations": "operations",
        "marketing": "marketing", "sales": "sales",
        "customer_success": "customer_success", "supply_chain": "supply_chain",
        "hr_people": "hr_people", "design": "design",
        "legal": "legal", "healthcare": "healthcare",
        "engineering": "technology", "product": "technology",
        "data": "technology", "it": "technology",
    }
    seen_areas = set()
    for area in ext_result.hiring_areas:
        area_key = area.lower().replace(" ", "_").replace("&", "and")
        mapped = area_to_signal.get(area_key, area_key)
        if mapped in seen_areas:
            continue
        seen_areas.add(mapped)
        new_signals.append(CompanySignal(
            company_id=company_id,
            source_type=source_type,
            source_url=url,
            signal_type=f"{mapped}_hiring_detected",
            signal_text=f"Hiring area: {area}",
            confidence=0.8,
        ))

    # Careers page found
    if ext_result.careers_url:
        new_signals.append(CompanySignal(
            company_id=company_id,
            source_type=source_type,
            source_url=ext_result.careers_url,
            signal_type="careers_page_found",
            signal_text=f"Careers page: {ext_result.careers_url}",
            confidence=0.95,
        ))

    if new_signals:
        count = _persist_signals_deduped(db, company_id, new_signals)
        pipeline_log.append(f"  extraction_signals_persisted: {count}")


def _excluded_result(entry: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "company_name": entry.get("company_name", ""),
        "domain": entry.get("domain", ""),
        "company_id": None,
        "industry": entry.get("industry"),
        "location": entry.get("location"),
        "source": entry.get("source"),
        "status": EXCLUDED,
        "company_type": None,
        "company_type_confidence": None,
        "hiring_pressure": None,
        "pain_clarity": None,
        "function_concentration": None,
        "extraction_coverage": None,
        "positioning_readiness": None,
        "diagnosis_status": None,
        "signals_count": 0,
        "distinct_signals_count": 0,
        "open_positions_count": 0,
        "friction_score": None,
        "dominant_friction_type": None,
        "summary": "",
        "notes": [f"Excluded: {reason}"],
        "pipeline_log": [f"Excluded: {reason}"],
        "collection_meta": {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _error_result(
    entry: dict[str, Any], error: str, tb: str = ""
) -> dict[str, Any]:
    result = _excluded_result(entry, "")
    result["status"] = "needs_recollection"
    result["notes"] = [f"Error during processing: {error}"]
    result["error"] = error
    result["pipeline_log"] = [f"ERROR: {error}"]
    return result
