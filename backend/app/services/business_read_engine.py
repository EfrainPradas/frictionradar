"""
Business Read Engine — Delegates to CompanyEvaluationEngine.

This engine is now a thin adapter. All threshold logic is computed by
CompanyEvaluationEngine (the single source of truth). The old API shape
is preserved for backward compatibility with FinalVerdictEngine.
"""

from typing import Dict, Any, List
from uuid import UUID

from app.models.company_signal import CompanySignal
from app.core.logging import logger

try:
    from app.models.company_job_role import CompanyJobRole, HiringPattern

    JOB_ROLES_AVAILABLE = True
except ImportError:
    JOB_ROLES_AVAILABLE = False
    CompanyJobRole = None
    HiringPattern = None


class BusinessReadEngine:
    """Separates hiring pressure from pain clarity for accurate business interpretation.

    DELEGATES to CompanyEvaluationEngine for all KPI and diagnostic computations.
    The old threshold logic has been removed — this engine now maps the canonical
    output to the legacy BusinessReadEngine API shape.
    """

    DIAGNOSIS_STATUS = {
        "insufficient_evidence": {
            "status": "insufficient_evidence",
            "summary": "No meaningful hiring evidence has been captured yet.",
            "business_read": "The system has not yet captured visible hiring indicators for this company.",
            "next_step": "Run a careers-page capture to gather visible hiring evidence.",
        },
        "broad_hiring_pattern_detected": {
            "status": "broad_hiring_pattern_detected",
            "summary": "Strong hiring activity detected, but the dominant pain is not yet isolated.",
            "business_read": "The company shows strong visible hiring demand across multiple business functions, but the system has not yet isolated the single dominant pain area.",
            "next_step": "Parse role titles and descriptions to identify repeated role families and isolate the strongest business pressure.",
        },
        "specific_pain_emerging": {
            "status": "specific_pain_emerging",
            "summary": "A specific functional pressure is beginning to emerge.",
            "business_read": "Hiring patterns are starting to cluster around one functional area, but the dominant pain is not yet fully confirmed.",
            "next_step": "More role-level detail is needed to confirm the strongest functional pressure.",
        },
        "specific_pain_identified": {
            "status": "specific_pain_identified",
            "summary": "A dominant pain area has been identified with confidence.",
            "business_read": "The hiring pattern clearly concentrates in one functional area, indicating a specific internal pressure.",
            "next_step": "Use this insight for targeted positioning.",
        },
    }

    def compute_reading(
        self,
        company_id: UUID,
        db=None,
        signals: List[CompanySignal] | None = None,
        job_roles: List | None = None,
        hiring_pattern: Any = None,
    ) -> Dict[str, Any]:
        """Compute the business reading for a company.

        Delegates to CompanyEvaluationEngine and maps canonical output
        to the legacy BusinessReadEngine API shape.
        """
        from app.services.company_evaluation import company_evaluation_engine

        evaluation = company_evaluation_engine.evaluate(
            company_id=company_id,
            db=db,
            signals=signals,
            job_roles=job_roles,
            hiring_pattern=hiring_pattern,
        )

        kpis = evaluation["kpis"]
        evidence = evaluation["evidence"]

        # Map canonical diagnostic_state to 4-state diagnosis_status
        # (ready_for_positioning maps to specific_pain_identified)
        diagnostic_state = evaluation["diagnostic_state"]
        diagnosis_status = diagnostic_state
        if diagnostic_state == "ready_for_positioning":
            diagnosis_status = "specific_pain_identified"

        diagnosis_info = self.DIAGNOSIS_STATUS.get(
            diagnosis_status,
            self.DIAGNOSIS_STATUS["insufficient_evidence"],
        )

        return {
            "hiring_pressure": kpis["hiring_pressure"],
            "pain_clarity": kpis["pain_clarity"],
            "diagnosis_status": diagnosis_status,
            "diagnosis_summary": diagnosis_info["summary"],
            "business_read_summary": evaluation["summary"],
            "next_best_step": evaluation["next_best_step"],
            "metadata": {
                "total_signals": evidence.get("distinct_signal_types", 0),
                "total_job_roles": evidence.get("parsed_titles", 0) + evidence.get("parsed_descriptions", 0),
                "unique_functional_areas": evidence.get("visible_hiring_areas", 0),
                "open_positions_count": evidence.get("open_positions_count", 0),
                "visible_hiring_areas": evidence.get("visible_hiring_areas", 0),
                "visible_job_cards": evidence.get("visible_job_cards", 0),
                "distinct_hiring_signals": evidence.get("distinct_signal_types", 0),
            },
        }


business_read_engine = BusinessReadEngine()