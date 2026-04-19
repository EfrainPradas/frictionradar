"""
Business Read Engine - Separates Hiring Pressure from Pain Clarity

This service provides the top-level business interpretation for each company:
1. Hiring Pressure: How strong is the visible hiring demand?
2. Pain Clarity: How clearly can we identify the specific internal pain?
3. Diagnosis Status: What is our current diagnostic state?

These two dimensions must be kept separate to avoid misleading outputs.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company_signal import CompanySignal
from app.core.logging import logger

# Lazy import to handle missing tables gracefully
try:
    from app.models.company_job_role import CompanyJobRole, HiringPattern

    JOB_ROLES_AVAILABLE = True
except ImportError:
    JOB_ROLES_AVAILABLE = False
    CompanyJobRole = None
    HiringPattern = None


class BusinessReadEngine:
    """Separates hiring pressure from pain clarity for accurate business interpretation."""

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

    HIRING_AREA_SIGNAL_SUFFIX = "_hiring_detected"
    OPEN_COUNT_SIGNAL_TYPES = {
        "open_positions_count_detected",
        "high_open_positions_count_detected",
    }
    JOB_CARDS_SIGNAL_TYPE = "job_cards_visible_detected"

    def compute_reading(
        self,
        company_id: UUID,
        db: Session | None = None,
        signals: List[CompanySignal] | None = None,
        job_roles: List | None = None,
        hiring_pattern: Any = None,
    ) -> Dict[str, Any]:
        """Compute the business reading for a company."""

        # Load signals if not provided
        if signals is None and db:
            try:
                signals = (
                    db.query(CompanySignal)
                    .filter(CompanySignal.company_id == company_id)
                    .all()
                )
            except Exception as e:
                logger.warning(f"Could not query signals: {e}")
                signals = []

        # Try to load job_roles if available
        job_roles = job_roles or []
        hiring_pattern = hiring_pattern

        if db and JOB_ROLES_AVAILABLE:
            try:
                job_roles = (
                    db.query(CompanyJobRole)
                    .filter(CompanyJobRole.company_id == company_id)
                    .all()
                )
                hiring_pattern = (
                    db.query(HiringPattern)
                    .filter(HiringPattern.company_id == company_id)
                    .first()
                )
            except Exception as e:
                logger.warning(f"Could not query job_roles tables: {e}")
                job_roles = []
                hiring_pattern = None
                try:
                    db.rollback()
                except Exception:
                    pass

        # Calculate Hiring Pressure
        hiring_pressure = self._calculate_hiring_pressure(
            signals or [], job_roles, hiring_pattern
        )

        # Calculate Pain Clarity
        pain_clarity = self._calculate_pain_clarity(
            signals or [], job_roles, hiring_pattern
        )

        # Determine Diagnosis Status
        diagnosis = self._determine_diagnosis(
            hiring_pressure=hiring_pressure,
            pain_clarity=pain_clarity,
            signals=signals or [],
            job_roles=job_roles,
            hiring_pattern=hiring_pattern,
        )

        evidence = self._extract_evidence(signals or [], job_roles, hiring_pattern)

        # Generate the final reading
        return {
            "hiring_pressure": hiring_pressure,
            "pain_clarity": pain_clarity,
            "diagnosis_status": diagnosis["status"],
            "diagnosis_summary": diagnosis["summary"],
            "business_read_summary": diagnosis["business_read"],
            "next_best_step": diagnosis["next_step"],
            "metadata": {
                "total_signals": len(signals or []),
                "total_job_roles": len(job_roles),
                "unique_functional_areas": self._count_functional_areas(job_roles),
                "open_positions_count": evidence["open_positions_count"],
                "visible_hiring_areas": evidence["visible_hiring_areas"],
                "visible_job_cards": evidence["visible_job_cards"],
                "distinct_hiring_signals": evidence["distinct_hiring_signals"],
            },
        }

    def _extract_evidence(
        self,
        signals: List,
        job_roles: List,
        hiring_pattern: Any,
    ) -> Dict[str, int]:
        """Extract the concrete hiring evidence numbers already present in signals."""
        open_positions_count = 0
        visible_hiring_areas = 0
        visible_job_cards = 0
        has_job_cards_signal = False
        distinct_hiring_signals = set()

        for s in signals:
            stype = (getattr(s, "signal_type", "") or "").lower()
            if not stype:
                continue

            if stype in self.OPEN_COUNT_SIGNAL_TYPES:
                try:
                    value = int(getattr(s, "numeric_value", 0) or 0)
                    if value > open_positions_count:
                        open_positions_count = value
                except (TypeError, ValueError):
                    pass
                distinct_hiring_signals.add(stype)

            if stype.endswith(self.HIRING_AREA_SIGNAL_SUFFIX) and stype not in (
                "visible_hiring_area_detected",
            ):
                visible_hiring_areas += 1
                distinct_hiring_signals.add(stype)

            if stype == "visible_hiring_area_detected":
                distinct_hiring_signals.add(stype)

            if stype == self.JOB_CARDS_SIGNAL_TYPE:
                has_job_cards_signal = True
                distinct_hiring_signals.add(stype)

        # Visible job cards are persisted as job_roles via careers_v2 router.
        visible_job_cards = len(job_roles) if job_roles else (10 if has_job_cards_signal else 0)

        # Fall back to functional area count from job_roles if per-area signals were not stored.
        if visible_hiring_areas == 0:
            visible_hiring_areas = self._count_functional_areas(job_roles)

        # Use hiring_pattern breadth as another fallback.
        if hiring_pattern is not None:
            try:
                unique_functions = int(
                    getattr(hiring_pattern, "unique_functions_found", 0) or 0
                )
                if unique_functions > visible_hiring_areas:
                    visible_hiring_areas = unique_functions
            except Exception:
                pass

        return {
            "open_positions_count": open_positions_count,
            "visible_hiring_areas": visible_hiring_areas,
            "visible_job_cards": visible_job_cards,
            "distinct_hiring_signals": len(distinct_hiring_signals),
        }

    def _calculate_hiring_pressure(
        self,
        signals: List,
        job_roles: List,
        hiring_pattern: Any,
    ) -> str:
        """Deterministic Hiring Pressure using concrete visible hiring evidence."""
        ev = self._extract_evidence(signals, job_roles, hiring_pattern)

        open_positions = ev["open_positions_count"]
        hiring_areas = ev["visible_hiring_areas"]
        job_cards = ev["visible_job_cards"]
        distinct_signals = ev["distinct_hiring_signals"]

        # HIGH: any one of these is enough.
        if (
            open_positions >= 100
            or hiring_areas >= 5
            or (job_cards >= 5 and hiring_areas >= 2)
            or (job_cards >= 5 and distinct_signals >= 4)
        ):
            return "high"

        # MODERATE: visible demand without breadth.
        if (
            20 <= open_positions <= 99
            or 2 <= hiring_areas <= 4
            or 2 <= job_cards <= 4
            or distinct_signals >= 2
        ):
            return "moderate"

        return "low"

    def _calculate_pain_clarity(
        self,
        signals: List,
        job_roles: List,
        hiring_pattern: Any,
    ) -> str:
        """Pain Clarity reflects whether a dominant function can be isolated.

        It must NOT depend on hiring volume alone — broad demand without a
        dominant role family is Moderate, not Low.
        """
        roles_with_function = [r for r in job_roles if self._get_role_function(r)]
        roles_with_description = [r for r in job_roles if self._get_role_description(r)]

        function_counts: Dict[str, int] = {}
        for role in roles_with_function:
            func = self._get_role_function(role)
            if func:
                function_counts[func] = function_counts.get(func, 0) + 1

        total_classified = sum(function_counts.values())
        max_repeated = max(function_counts.values()) if function_counts else 0
        dominant_share = (max_repeated / total_classified) if total_classified else 0.0

        top_function = None
        unique_functions = 0
        if hiring_pattern is not None:
            try:
                top_function = getattr(hiring_pattern, "top_functional_areas", None)
                unique_functions = int(
                    getattr(hiring_pattern, "unique_functions_found", 0) or 0
                )
            except Exception:
                pass

        # HIGH: one function family clearly dominates.
        if (
            (max_repeated >= 3 and dominant_share >= 0.5)
            or (top_function and len(roles_with_description) >= 3 and dominant_share >= 0.5)
        ):
            return "high"

        # Derive breadth from evidence (same source used for hiring pressure).
        ev = self._extract_evidence(signals, job_roles, hiring_pattern)
        broad_evidence = (
            ev["visible_hiring_areas"] >= 2
            or ev["open_positions_count"] >= 20
            or ev["visible_job_cards"] >= 2
            or unique_functions >= 2
        )

        # MODERATE: meaningful breadth OR some directional signal, but not dominant.
        if (
            broad_evidence
            or max_repeated >= 2
            or top_function
            or len(roles_with_function) >= 3
        ):
            return "moderate"

        # LOW: only shallow evidence, no direction yet.
        return "low"

    def _get_role_function(self, role: Any) -> str | None:
        """Get functional area from role."""
        try:
            return getattr(role, "functional_area", None)
        except Exception:
            return None

    def _get_role_description(self, role: Any) -> str | None:
        """Get description from role."""
        try:
            return getattr(role, "role_description", None)
        except Exception:
            return None

    def _determine_diagnosis(
        self,
        hiring_pressure: str,
        pain_clarity: str,
        signals: List,
        job_roles: List,
        hiring_pattern: Any = None,
    ) -> Dict[str, str]:
        """Determine the diagnosis status from pressure, clarity, and raw evidence.

        Key rule: if broad hiring evidence exists, we NEVER return
        insufficient_evidence — at worst we return broad_hiring_pattern_detected.
        """
        ev = self._extract_evidence(signals, job_roles, hiring_pattern)
        has_broad_evidence = (
            ev["open_positions_count"] >= 20
            or ev["visible_hiring_areas"] >= 2
            or ev["visible_job_cards"] >= 2
            or hiring_pressure in ("moderate", "high")
        )

        # Specific pain isolated.
        if pain_clarity == "high":
            return self.DIAGNOSIS_STATUS["specific_pain_identified"]

        # A dominant direction is emerging: high pressure + moderate clarity
        # AND role-level evidence is actually present (not just breadth).
        roles_with_function = [r for r in job_roles if self._get_role_function(r)]
        if (
            hiring_pressure == "high"
            and pain_clarity == "moderate"
            and len(roles_with_function) >= 3
        ):
            return self.DIAGNOSIS_STATUS["specific_pain_emerging"]

        # Broad hiring evidence present but dominant pain not isolated.
        if has_broad_evidence:
            return self.DIAGNOSIS_STATUS["broad_hiring_pattern_detected"]

        # Truly nothing to work with.
        return self.DIAGNOSIS_STATUS["insufficient_evidence"]

    def _count_functional_areas(self, job_roles: List) -> int:
        """Count unique functional areas from job roles."""
        areas = set()
        for role in job_roles:
            try:
                func = self._get_role_function(role)
                if func:
                    areas.add(func)
            except Exception:
                pass
        return len(areas)


business_read_engine = BusinessReadEngine()
