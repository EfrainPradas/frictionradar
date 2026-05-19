"""
Confidence Reading — Single Source of Truth Schema.

All confidence/evidence/diagnosis concepts unified into one canonical output.
CompanyEvaluationEngine produces this; other engines delegate to it.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, ConfigDict


class KPILevels(BaseModel):
    """The 6 canonical KPI levels."""
    extraction_coverage: str       # low | moderate | high
    hiring_pressure: str           # low | moderate | high
    function_concentration: str    # low | moderate | high
    pain_clarity: str              # low | moderate | high
    company_type_confidence: str    # low | moderate | high
    positioning_readiness: str     # low | moderate | high


class KPIReasoning(BaseModel):
    """Reasoning trace for a single KPI: why was this level assigned?"""
    level: str
    met_conditions: List[str] = []
    missed_conditions: List[str] = []


class ConfidenceReading(BaseModel):
    """Single source of truth for company confidence and diagnosis.

    Produced by CompanyEvaluationEngine. Other engines (EvidenceThresholdEngine,
    BusinessReadEngine) delegate to it and map their legacy output from this.
    """
    model_config = ConfigDict(from_attributes=True)

    # The 6 canonical KPIs
    kpis: KPILevels

    # Diagnostic state (canonical state machine)
    diagnostic_state: str  # insufficient_evidence | broad_hiring_pattern_detected
                           # | specific_pain_emerging | specific_pain_identified
                           # | ready_for_positioning

    # Derived flags
    is_strong_enough: bool          # pain_clarity >= moderate AND function_concentration >= moderate
    allow_specific_pain_output: bool  # Same as is_strong_enough (unified)

    # Evidence metadata
    evidence: Dict[str, Any]

    # Human-readable summaries
    summary: str
    next_best_step: str

    # Reasoning trace: why each KPI was assigned its level
    reasoning_trace: Dict[str, Dict[str, Any]]

    # Convenience: the diagnostic state as a 4-state value
    # (maps ready_for_positioning → specific_pain_identified for backward compat)
    @property
    def diagnosis_status_4state(self) -> str:
        """4-state diagnosis for BusinessReadEngine backward compatibility."""
        if self.diagnostic_state == "ready_for_positioning":
            return "specific_pain_identified"
        return self.diagnostic_state

    # Convenience: confidence level derived from diagnostic state
    @property
    def confidence_level(self) -> str:
        """Derive confidence from diagnostic state.

        ready_for_positioning → high
        specific_pain_identified → high
        specific_pain_emerging → moderate
        broad_hiring_pattern_detected → moderate
        insufficient_evidence → low
        """
        if self.diagnostic_state in ("ready_for_positioning", "specific_pain_identified"):
            return "high"
        if self.diagnostic_state in ("specific_pain_emerging", "broad_hiring_pattern_detected"):
            return "moderate"
        return "low"