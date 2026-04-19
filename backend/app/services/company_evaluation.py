"""
Company Evaluation Engine — Universal KPI Scorecard.

Computes 6 orthogonal KPIs and a top-level Diagnostic State that works
for any company (not just Nike). All thresholds are deterministic and
driven by evidence already present in signals / job_roles.

KPIs:
  1. extraction_coverage   — how much structured evidence was captured
  2. hiring_pressure       — visible strength of hiring demand
  3. function_concentration — concentrated vs. broadly distributed
  4. pain_clarity          — isolability of the dominant internal pain
  5. company_type_confidence — operating_company vs. job_market_intermediary
  6. positioning_readiness — is NovaWork able to recommend a strong angle

Plus:
  diagnostic_state ∈ {
    insufficient_evidence,
    broad_hiring_pattern_detected,
    specific_pain_emerging,
    specific_pain_identified,
    ready_for_positioning,
  }
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.company_signal import CompanySignal
from app.core.logging import logger

try:
    from app.models.company_job_role import CompanyJobRole, HiringPattern

    JOB_ROLES_AVAILABLE = True
except ImportError:
    JOB_ROLES_AVAILABLE = False
    CompanyJobRole = None
    HiringPattern = None


LEVEL_LOW = "low"
LEVEL_MODERATE = "moderate"
LEVEL_HIGH = "high"
LEVEL_ORDER = {LEVEL_LOW: 0, LEVEL_MODERATE: 1, LEVEL_HIGH: 2}


def _gte(level: str, floor: str) -> bool:
    return LEVEL_ORDER.get(level, 0) >= LEVEL_ORDER.get(floor, 0)


class CompanyEvaluationEngine:
    """Produces the universal evaluation scorecard for any company."""

    OPEN_COUNT_TYPES = {
        "open_positions_count_detected",
        "high_open_positions_count_detected",
    }
    HIRING_AREA_SUFFIX = "_hiring_detected"
    CAREER_SIGNAL_HINTS = ("careers", "career_page", "career_url")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        company_id: UUID,
        db: Optional[Session] = None,
        signals: Optional[List[CompanySignal]] = None,
        job_roles: Optional[List[Any]] = None,
        hiring_pattern: Any = None,
        company_type_confidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute the scorecard for a company.

        All inputs are optional — if `db` is provided, the engine will
        load signals and job_roles itself.
        """
        if signals is None and db is not None:
            try:
                signals = (
                    db.query(CompanySignal)
                    .filter(CompanySignal.company_id == company_id)
                    .all()
                )
            except Exception as e:
                logger.warning(f"company_evaluation: signals query failed: {e}")
                signals = []

        if job_roles is None and db is not None and JOB_ROLES_AVAILABLE:
            try:
                job_roles = (
                    db.query(CompanyJobRole)
                    .filter(CompanyJobRole.company_id == company_id)
                    .all()
                )
                if hiring_pattern is None:
                    hiring_pattern = (
                        db.query(HiringPattern)
                        .filter(HiringPattern.company_id == company_id)
                        .first()
                    )
            except Exception as e:
                logger.warning(f"company_evaluation: job_roles query failed: {e}")
                job_roles = []
                hiring_pattern = None
                try:
                    db.rollback()
                except Exception:
                    pass

        signals = signals or []
        job_roles = job_roles or []

        evidence = self._extract_evidence(signals, job_roles, hiring_pattern)

        extraction_coverage = self._score_extraction_coverage(
            signals, job_roles, evidence
        )
        hiring_pressure = self._score_hiring_pressure(evidence)
        function_concentration = self._score_function_concentration(
            job_roles, evidence
        )
        pain_clarity = self._score_pain_clarity(
            job_roles, hiring_pattern, evidence
        )
        # Default MODERATE when the caller didn't provide confidence.
        # Why: batch_runner.process_company never invokes company_type_engine,
        # so unprovided → LOW → positioning_readiness never HIGH →
        # ready_for_positioning is structurally unreachable. The working dataset
        # is curated operating-companies, so MODERATE is the safer default.
        # Callers with strict requirements must pass explicitly.
        type_confidence = self._normalize_level(company_type_confidence) or LEVEL_MODERATE
        positioning_readiness = self._score_positioning_readiness(
            hiring_pressure=hiring_pressure,
            pain_clarity=pain_clarity,
            function_concentration=function_concentration,
            company_type_confidence=type_confidence,
        )

        diagnostic_state = self._determine_diagnostic_state(
            extraction_coverage=extraction_coverage,
            hiring_pressure=hiring_pressure,
            pain_clarity=pain_clarity,
            function_concentration=function_concentration,
            positioning_readiness=positioning_readiness,
        )

        summary = self._summary_text(
            diagnostic_state=diagnostic_state,
            hiring_pressure=hiring_pressure,
            pain_clarity=pain_clarity,
            function_concentration=function_concentration,
        )

        return {
            "kpis": {
                "extraction_coverage": extraction_coverage,
                "hiring_pressure": hiring_pressure,
                "function_concentration": function_concentration,
                "pain_clarity": pain_clarity,
                "company_type_confidence": type_confidence,
                "positioning_readiness": positioning_readiness,
            },
            "diagnostic_state": diagnostic_state,
            "summary": summary["summary"],
            "next_best_step": summary["next_best_step"],
            "allow_specific_pain_output": self._allow_specific_pain(
                pain_clarity=pain_clarity,
                function_concentration=function_concentration,
            ),
            "evidence": evidence,
        }

    # ------------------------------------------------------------------ #
    # Evidence extraction (single source of truth for numeric inputs)
    # ------------------------------------------------------------------ #

    def _extract_evidence(
        self,
        signals: List[Any],
        job_roles: List[Any],
        hiring_pattern: Any,
    ) -> Dict[str, Any]:
        open_positions_count = 0
        visible_hiring_areas = 0
        has_job_cards_signal = False
        has_job_links_signal = False
        has_careers_page_signal = False
        has_structured_api_signal = False
        distinct_signal_types = set()

        for s in signals:
            stype = (getattr(s, "signal_type", "") or "").lower()
            if not stype:
                continue
            distinct_signal_types.add(stype)

            if stype in self.OPEN_COUNT_TYPES:
                try:
                    value = int(getattr(s, "numeric_value", 0) or 0)
                    if value > open_positions_count:
                        open_positions_count = value
                except (TypeError, ValueError):
                    pass

            if stype.endswith(self.HIRING_AREA_SUFFIX) and stype not in (
                "visible_hiring_area_detected",
            ):
                visible_hiring_areas += 1

            if stype == "job_cards_visible_detected":
                has_job_cards_signal = True

            if stype == "job_links_extracted":
                has_job_links_signal = True

            if any(hint in stype for hint in self.CAREER_SIGNAL_HINTS):
                has_careers_page_signal = True

            if "structured" in stype or "embedded_json" in stype or "api_detected" in stype:
                has_structured_api_signal = True

        # job_roles are persisted from visible_role_cards
        visible_job_cards = len(job_roles)
        parsed_titles = sum(1 for r in job_roles if getattr(r, "role_title", None))
        parsed_descriptions = sum(
            1 for r in job_roles if getattr(r, "role_description", None)
        )

        if visible_hiring_areas == 0 and job_roles:
            areas = set()
            for r in job_roles:
                area = getattr(r, "functional_area", None)
                if area:
                    areas.add(area)
            visible_hiring_areas = len(areas)

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
            "parsed_titles": parsed_titles,
            "parsed_descriptions": parsed_descriptions,
            "has_job_cards_signal": has_job_cards_signal,
            "has_job_links_signal": has_job_links_signal,
            "has_careers_page_signal": has_careers_page_signal,
            "has_structured_api_signal": has_structured_api_signal,
            "distinct_signal_types": len(distinct_signal_types),
        }

    # ------------------------------------------------------------------ #
    # KPI scoring functions
    # ------------------------------------------------------------------ #

    def _score_extraction_coverage(
        self,
        signals: List[Any],
        job_roles: List[Any],
        ev: Dict[str, Any],
    ) -> str:
        has_any_hiring_evidence = (
            ev["has_careers_page_signal"]
            or ev["visible_hiring_areas"] >= 1
            or ev["visible_job_cards"] >= 1
            or ev["open_positions_count"] > 0
            or any(
                "career" in (getattr(s, "source_type", "") or "").lower()
                or "hiring" in (getattr(s, "signal_type", "") or "").lower()
                for s in signals
            )
        )

        checks = [
            has_any_hiring_evidence,
            ev["open_positions_count"] > 0,
            ev["visible_hiring_areas"] >= 2,
            ev["visible_hiring_areas"] >= 5,
            ev["visible_job_cards"] >= 1 or ev["has_job_cards_signal"],
            ev["parsed_titles"] >= 1,
            ev["parsed_descriptions"] >= 1,
            ev["distinct_signal_types"] >= 5 or ev["has_structured_api_signal"],
        ]
        passed = sum(1 for c in checks if c)

        # HIGH requires role-level parsing, not just breadth.
        if passed >= 6 and ev["parsed_titles"] >= 1:
            return LEVEL_HIGH
        if passed >= 3:
            return LEVEL_MODERATE
        return LEVEL_LOW

    def _score_hiring_pressure(self, ev: Dict[str, Any]) -> str:
        open_positions = ev["open_positions_count"]
        hiring_areas = ev["visible_hiring_areas"]
        job_cards = ev["visible_job_cards"]
        distinct_signals = ev["distinct_signal_types"]

        if (
            open_positions >= 100
            or hiring_areas >= 5
            or (job_cards >= 5 and hiring_areas >= 2)
            or (job_cards >= 5 and distinct_signals >= 6)
        ):
            return LEVEL_HIGH

        if (
            20 <= open_positions <= 99
            or 2 <= hiring_areas <= 4
            or 2 <= job_cards <= 4
            or distinct_signals >= 3
        ):
            return LEVEL_MODERATE

        return LEVEL_LOW

    _EXCLUDED_AREAS = {"junk", "unknown", "Technology"}

    def _clean_role_counts(self, job_roles: List[Any]) -> Dict[str, int]:
        """Count roles by function, excluding junk/unknown/noise."""
        counts: Dict[str, int] = {}
        for r in job_roles:
            area = getattr(r, "functional_area", None)
            if not area or area in self._EXCLUDED_AREAS:
                continue
            counts[area] = counts.get(area, 0) + 1
        return counts

    def _score_function_concentration(
        self,
        job_roles: List[Any],
        ev: Dict[str, Any],
    ) -> str:
        """High = one function dominates; Low = broadly distributed.

        Only counts roles with valid functional_area (excludes junk/unknown).
        Uses unique_areas from classified roles when available.
        """
        function_counts = self._clean_role_counts(job_roles)
        total = sum(function_counts.values())

        if total > 0:
            areas = len(function_counts)
        else:
            areas = ev["visible_hiring_areas"]

        if areas >= 5 and total < 3:
            return LEVEL_LOW

        if total == 0:
            return LEVEL_LOW

        top = max(function_counts.values())
        share = top / total

        if top >= 3 and share >= 0.5 and areas <= 3:
            return LEVEL_HIGH
        if top >= 2 and share >= 0.35 and areas <= 4:
            return LEVEL_MODERATE
        return LEVEL_LOW

    def _score_pain_clarity(
        self,
        job_roles: List[Any],
        hiring_pattern: Any,
        ev: Dict[str, Any],
    ) -> str:
        """Pain Clarity — can we isolate a dominant internal pain?

        Requires real classified roles (excludes junk/unknown).
        Descriptions boost confidence but aren't required.
        """
        function_counts = self._clean_role_counts(job_roles)
        total = sum(function_counts.values())
        top = max(function_counts.values()) if function_counts else 0
        share = (top / total) if total else 0.0

        with_desc = sum(
            1 for r in job_roles
            if getattr(r, "role_description", None)
            and getattr(r, "functional_area", None) not in self._EXCLUDED_AREAS
        )

        has_pattern = hiring_pattern is not None

        # HIGH: strong concentration with evidence depth
        if (top >= 3 and share >= 0.5) or (
            has_pattern and with_desc >= 3 and share >= 0.5
        ):
            return LEVEL_HIGH

        # MODERATE: requires real clustering, not just any 3 classified roles.
        # At least 2 roles in the top function AND some evidence of a pattern.
        if top >= 2 and (has_pattern or total >= 5 or with_desc >= 2):
            return LEVEL_MODERATE

        # Fallback: if we have some classified roles at all
        if total >= 3:
            return LEVEL_MODERATE

        return LEVEL_LOW

    def _score_positioning_readiness(
        self,
        hiring_pressure: str,
        pain_clarity: str,
        function_concentration: str,
        company_type_confidence: str,
    ) -> str:
        # Rule E: cannot be high if Pain Clarity is low.
        if pain_clarity == LEVEL_LOW:
            return LEVEL_LOW

        if (
            pain_clarity == LEVEL_HIGH
            and _gte(function_concentration, LEVEL_MODERATE)
            and _gte(company_type_confidence, LEVEL_MODERATE)
            and _gte(hiring_pressure, LEVEL_MODERATE)
        ):
            return LEVEL_HIGH

        if (
            _gte(pain_clarity, LEVEL_MODERATE)
            and _gte(function_concentration, LEVEL_MODERATE)
            and _gte(hiring_pressure, LEVEL_MODERATE)
        ):
            return LEVEL_MODERATE

        return LEVEL_LOW

    # ------------------------------------------------------------------ #
    # Diagnostic state + summaries
    # ------------------------------------------------------------------ #

    def _determine_diagnostic_state(
        self,
        extraction_coverage: str,
        hiring_pressure: str,
        pain_clarity: str,
        function_concentration: str,
        positioning_readiness: str,
    ) -> str:
        # Rule A
        if extraction_coverage == LEVEL_LOW:
            return "insufficient_evidence"

        # Rule D upgraded — full readiness
        if positioning_readiness == LEVEL_HIGH:
            return "ready_for_positioning"

        # Rule D — specific pain identified
        if _gte(pain_clarity, LEVEL_MODERATE) and _gte(
            function_concentration, LEVEL_MODERATE
        ):
            if pain_clarity == LEVEL_HIGH:
                return "specific_pain_identified"
            return "specific_pain_emerging"

        # Rule C
        if pain_clarity == LEVEL_MODERATE and function_concentration == LEVEL_LOW:
            if hiring_pressure == LEVEL_HIGH:
                return "broad_hiring_pattern_detected"
            return "specific_pain_emerging"

        # Rule B
        if hiring_pressure == LEVEL_HIGH and pain_clarity == LEVEL_LOW:
            return "broad_hiring_pattern_detected"

        if _gte(hiring_pressure, LEVEL_MODERATE):
            return "broad_hiring_pattern_detected"

        return "insufficient_evidence"

    def _allow_specific_pain(
        self,
        pain_clarity: str,
        function_concentration: str,
    ) -> bool:
        """Rule D gate: block pain-specific outputs unless supported."""
        return _gte(pain_clarity, LEVEL_MODERATE) and _gte(
            function_concentration, LEVEL_MODERATE
        )

    def _summary_text(
        self,
        diagnostic_state: str,
        hiring_pressure: str,
        pain_clarity: str,
        function_concentration: str,
    ) -> Dict[str, str]:
        if diagnostic_state == "insufficient_evidence":
            return {
                "summary": "The system has not captured enough structured evidence to evaluate this company yet.",
                "next_best_step": "Run a careers-page capture to gather visible hiring evidence.",
            }
        if diagnostic_state == "broad_hiring_pattern_detected":
            return {
                "summary": "This company shows strong visible hiring demand across multiple functions, but the system has not yet isolated the dominant internal pain.",
                "next_best_step": "Parse role titles and descriptions to identify repeated role families and isolate the strongest functional pressure.",
            }
        if diagnostic_state == "specific_pain_emerging":
            return {
                "summary": "A specific functional pressure is beginning to emerge, but the dominant pain is not yet fully confirmed.",
                "next_best_step": "Collect more role-level detail to confirm the strongest functional pressure.",
            }
        if diagnostic_state == "specific_pain_identified":
            return {
                "summary": "A dominant functional pain has been identified, concentrated in one business area.",
                "next_best_step": "Build a tailored positioning angle around the dominant pain.",
            }
        if diagnostic_state == "ready_for_positioning":
            return {
                "summary": "Evidence is strong and concentrated — NovaWork can move to tailored positioning.",
                "next_best_step": "Generate the attack angle for the dominant pain area.",
            }
        return {
            "summary": "",
            "next_best_step": "",
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _normalize_level(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        v = str(value).strip().lower()
        if v in LEVEL_ORDER:
            return v
        if v in ("strong", "confident", "yes"):
            return LEVEL_HIGH
        if v in ("weak", "unknown", "no"):
            return LEVEL_LOW
        if v in ("medium", "mid"):
            return LEVEL_MODERATE
        return None


company_evaluation_engine = CompanyEvaluationEngine()
