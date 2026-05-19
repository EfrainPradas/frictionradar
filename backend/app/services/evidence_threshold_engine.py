"""
Evidence Threshold Engine — Delegates to CompanyEvaluationEngine.

This engine is now a thin adapter. All threshold logic is computed by
CompanyEvaluationEngine (the single source of truth). The old API shape
is preserved for backward compatibility with FinalVerdictEngine.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.collection_run import CollectionRun
from app.core.logging import logger


class EvidenceThresholdEngine:
    """Determines evidence quality and thresholds.

    DELEGATES to CompanyEvaluationEngine for all KPI and diagnostic computations.
    The old threshold logic has been removed — this engine now maps the canonical
    output to the legacy API shape.
    """

    def evaluate_evidence(
        self,
        signals: list[CompanySignal],
        score: FrictionScore | None,
        collection_runs: list[CollectionRun] | None,
        company_id: UUID | None = None,
        db=None,
    ) -> dict:
        """Evaluate evidence quality using the canonical CompanyEvaluationEngine.

        Maps the canonical output to the legacy EvidenceThresholdEngine API shape.
        """
        from app.services.company_evaluation import company_evaluation_engine

        # Delegate to the canonical engine
        evaluation = company_evaluation_engine.evaluate(
            company_id=company_id or UUID("00000000-0000-0000-0000-000000000000"),
            db=db,
            signals=signals,
        )

        kpis = evaluation["kpis"]
        evidence = evaluation["evidence"]

        # Map canonical diagnostic_state to legacy confidence
        diagnostic_state = evaluation["diagnostic_state"]
        if diagnostic_state in ("ready_for_positioning", "specific_pain_identified"):
            confidence = "high"
        elif diagnostic_state in ("specific_pain_emerging", "broad_hiring_pattern_detected"):
            confidence = "moderate"
        else:
            confidence = "low"

        # Map canonical extraction_coverage to legacy evidence_quality
        evidence_quality = kpis["extraction_coverage"]

        # Map canonical allow_specific_pain_output to legacy is_strong_enough
        is_strong_enough = evaluation["allow_specific_pain_output"]

        # Compute signal_diversity using the canonical threshold (>=4 high, >=2 medium)
        distinct_signal_types = evidence.get("distinct_signal_types", 0)
        if distinct_signal_types >= 4:
            signal_diversity = "high"
        elif distinct_signal_types >= 2:
            signal_diversity = "medium"
        elif distinct_signal_types > 0:
            signal_diversity = "low"
        else:
            signal_diversity = "none"

        # Build the legacy output shape
        return {
            "evidence_quality": evidence_quality,
            "confidence": confidence,
            "is_strong_enough": is_strong_enough,
            "unique_signal_count": evidence.get("distinct_signal_types", 0),
            "total_signal_count": len(signals) if signals else 0,
            "source_type_count": len(set(
                s.source_type for s in signals if s.source_type
            )) if signals else 0,
            "friction_score": float(score.total_score) if score and score.total_score is not None else 0.0,
            "function_type": evidence.get("function_type"),
            "signal_diversity": signal_diversity,
            "has_repeated_signals": False,  # Not available from canonical engine
            "function_specific_signals": {
                "has_function_specific": evidence.get("function_type") is not None,
                "function_type": evidence.get("function_type"),
                "details": [],
                "confidence": "high" if evidence.get("function_type") else None,
            },
            "visible_job_count": evidence.get("visible_job_cards", 0),
            "visible_categories_count": evidence.get("visible_hiring_areas", 0),
            "has_high_volume": evidence.get("open_positions_count", 0) >= 100,
        }


evidence_threshold_engine = EvidenceThresholdEngine()