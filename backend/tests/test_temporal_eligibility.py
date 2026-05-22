"""
Temporal eligibility override boundary tests.

Verifies:
  1. Existing static eligibility gates are preserved unchanged.
  2. Temporal override promotes ineligible → conditional when:
     - temporal state is emerging_pain or accelerating_pain
     - confidence is moderate or high
     - evidence thresholds are met
  3. Temporal override is blocked when:
     - static ds is "insufficient_evidence" and temporal is insufficient
     - static ds is "no_signal" with low/none temporal confidence
     - temporal state is stable_low, stable_elevated, or volatile
     - temporal confidence is low or none
     - evidence counts are below thresholds
  4. Output fields: temporal_gate_passed, temporal_reason, temporal_opportunity_type
  5. Positioning implication examples for each opportunity type.
"""

import pytest
from uuid import uuid4

from app.services.positioning_engine import (
    check_eligibility,
    EligibilityResult,
    _apply_temporal_override,
    _TEMPORAL_MIN_SIGNALS,
    _TEMPORAL_MIN_SCORED,
    _TEMPORAL_MIN_SNAPSHOTS,
)
from app.schemas.temporal_diagnostic import (
    TemporalDiagnosticResult,
    TemporalDiagnosticState,
    TemporalConfidence,
    EvidenceStrength,
    TopChangingCategory,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_temporal(
    state: TemporalDiagnosticState,
    confidence: TemporalConfidence = TemporalConfidence.HIGH,
    signal_count: int = 10,
    scored_signal_count: int = 5,
    score_snapshot_count: int = 3,
    top_cat: TopChangingCategory | None = None,
) -> TemporalDiagnosticResult:
    """Build a TemporalDiagnosticResult with sensible defaults for testing."""
    return TemporalDiagnosticResult(
        company_id=uuid4(),
        temporal_state=state,
        confidence=confidence,
        evidence_strength=EvidenceStrength.STRONG,
        top_changing_category=top_cat,
        reasoning_trace=[],
        summary=state.value,
        score_delta_available=score_snapshot_count > 1,
        velocity_available=signal_count > 0,
        evaluation_available=True,
        score_snapshot_count=score_snapshot_count,
        signal_count=signal_count,
        scored_signal_count=scored_signal_count,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. BACKWARD COMPATIBILITY: static gates unchanged without temporal
# ═══════════════════════════════════════════════════════════════════════

class TestStaticGatesPreserved:
    """Passing temporal_diagnostic=None must produce identical results."""

    def test_insufficient_evidence_unchanged(self):
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
        )
        assert result.eligible is False
        assert result.gate_passed == "none"
        assert result.temporal_gate_passed is None

    def test_specific_pain_identified_unchanged(self):
        result = check_eligibility(
            diagnostic_state="specific_pain_identified",
            pain_clarity="high", function_concentration="high",
            positioning_readiness="high", classified_roles=5, jds_extracted=3,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.temporal_gate_passed is None

    def test_specific_pain_emerging_eligible_unchanged(self):
        result = check_eligibility(
            diagnostic_state="specific_pain_emerging",
            pain_clarity="moderate", function_concentration="moderate",
            positioning_readiness="moderate", classified_roles=3, jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_gate_passed is None

    def test_broad_pattern_eligible_unchanged(self):
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low", function_concentration="moderate",
            positioning_readiness="low", classified_roles=5, jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_gate_passed is None

    def test_ready_for_positioning_unchanged(self):
        result = check_eligibility(
            diagnostic_state="ready_for_positioning",
            pain_clarity="high", function_concentration="high",
            positioning_readiness="high", classified_roles=10, jds_extracted=5,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.temporal_gate_passed is None

    def test_new_fields_default_to_none_without_temporal(self):
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
        )
        assert result.temporal_gate_passed is None
        assert result.temporal_reason is None
        assert result.temporal_opportunity_type is None


# ═══════════════════════════════════════════════════════════════════════
# 2. TEMPORAL OVERRIDE: emerging_pain and accelerating_pain
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalOverrideEmergingPain:
    """emerging_pain with moderate+ confidence can promote ineligible."""

    def test_emerging_pain_moderate_confidence_promotes(self):
        """insufficient_evidence + emerging_pain + moderate → conditional."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.MODERATE,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.confidence_band == "moderate"
        assert result.temporal_gate_passed == "temporal_override"
        assert result.temporal_opportunity_type == "early_positioning"

    def test_emerging_pain_high_confidence_promotes(self):
        """insufficient_evidence + emerging_pain + high → conditional."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.HIGH,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_opportunity_type == "early_positioning"


class TestTemporalOverrideAcceleratingPain:
    """accelerating_pain with moderate+ confidence promotes ineligible."""

    def test_accelerating_pain_moderate_confidence_promotes(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.MODERATE,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_gate_passed == "temporal_override"
        assert result.temporal_opportunity_type == "accelerated_positioning"

    def test_accelerating_pain_high_confidence_promotes(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.HIGH,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_opportunity_type == "accelerated_positioning"

    def test_accelerating_pain_broad_pattern_promotes(self):
        """broad_hiring_pattern_detected with <5 roles + accelerating → override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.MODERATE,
        )
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=2, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.temporal_gate_passed == "temporal_override"


# ═══════════════════════════════════════════════════════════════════════
# 3. BLOCKED: temporal override must NOT fire
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalOverrideBlocked:
    """Cases where temporal override must NOT promote."""

    def test_insufficient_temporal_state_does_not_override(self):
        """insufficient_temporal_data → no override regardless of confidence."""
        td = _make_temporal(
            state=TemporalDiagnosticState.INSUFFICIENT,
            confidence=TemporalConfidence.HIGH,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False
        assert result.gate_passed == "none"
        assert result.temporal_gate_passed is None

    def test_stable_low_does_not_override(self):
        """stable_low_friction → no override (not an escalation signal)."""
        td = _make_temporal(state=TemporalDiagnosticState.STABLE_LOW)
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_stable_elevated_does_not_override(self):
        """stable_elevated_friction → no override (stable, not trending)."""
        td = _make_temporal(state=TemporalDiagnosticState.STABLE_ELEVATED)
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_volatile_does_not_override(self):
        """volatile_friction → no override (direction unclear)."""
        td = _make_temporal(state=TemporalDiagnosticState.VOLATILE)
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_declining_pain_does_not_override(self):
        """declining_pain → no override (pain is easing, not growing)."""
        td = _make_temporal(state=TemporalDiagnosticState.DECLINING_PAIN)
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_low_confidence_does_not_override(self):
        """emerging_pain + low confidence → no override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.LOW,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_none_confidence_does_not_override(self):
        """emerging_pain + none confidence → no override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.NONE,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_no_signal_with_low_temporal_confidence_blocked(self):
        """no_signal ds + low temporal confidence → blocked."""
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.LOW,
        )
        result = check_eligibility(
            diagnostic_state="no_signal",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_no_signal_with_none_temporal_confidence_blocked(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.NONE,
        )
        result = check_eligibility(
            diagnostic_state="no_signal",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False


class TestTemporalEvidenceThresholds:
    """Evidence count thresholds must be met for override."""

    def test_below_signal_count_threshold_blocked(self):
        """signal_count < 5 → no override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.HIGH,
            signal_count=_TEMPORAL_MIN_SIGNALS - 1,
            scored_signal_count=_TEMPORAL_MIN_SCORED,
            score_snapshot_count=_TEMPORAL_MIN_SNAPSHOTS,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_below_scored_signal_threshold_blocked(self):
        """scored_signal_count < 3 → no override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.HIGH,
            signal_count=_TEMPORAL_MIN_SIGNALS,
            scored_signal_count=_TEMPORAL_MIN_SCORED - 1,
            score_snapshot_count=_TEMPORAL_MIN_SNAPSHOTS,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_below_snapshot_threshold_blocked(self):
        """score_snapshot_count < 2 → no override."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.HIGH,
            signal_count=_TEMPORAL_MIN_SIGNALS,
            scored_signal_count=_TEMPORAL_MIN_SCORED,
            score_snapshot_count=_TEMPORAL_MIN_SNAPSHOTS - 1,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is False

    def test_exact_threshold_passes(self):
        """Exact minimum thresholds → override succeeds."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.MODERATE,
            signal_count=_TEMPORAL_MIN_SIGNALS,
            scored_signal_count=_TEMPORAL_MIN_SCORED,
            score_snapshot_count=_TEMPORAL_MIN_SNAPSHOTS,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.temporal_gate_passed == "temporal_override"


# ═══════════════════════════════════════════════════════════════════════
# 4. TEMPORAL DOES NOT DOWNGRADE: already-eligible stays eligible
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalNoDowngrade:
    """Temporal must never downgrade or replace an already-eligible result."""

    def test_specific_pain_identified_stays_full(self):
        """Full-eligible stays full, even with declining temporal."""
        td = _make_temporal(state=TemporalDiagnosticState.DECLINING_PAIN)
        result = check_eligibility(
            diagnostic_state="specific_pain_identified",
            pain_clarity="high", function_concentration="high",
            positioning_readiness="high", classified_roles=5, jds_extracted=3,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.temporal_gate_passed is None

    def test_ready_for_positioning_stays_full(self):
        td = _make_temporal(state=TemporalDiagnosticState.ACCELERATING_PAIN)
        result = check_eligibility(
            diagnostic_state="ready_for_positioning",
            pain_clarity="high", function_concentration="high",
            positioning_readiness="high", classified_roles=10, jds_extracted=5,
            temporal_diagnostic=td,
        )
        assert result.gate_passed == "full"
        assert result.temporal_gate_passed is None

    def test_specific_pain_emerging_stays_conditional(self):
        td = _make_temporal(state=TemporalDiagnosticState.ACCELERATING_PAIN)
        result = check_eligibility(
            diagnostic_state="specific_pain_emerging",
            pain_clarity="moderate", function_concentration="moderate",
            positioning_readiness="moderate", classified_roles=3, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.gate_passed == "conditional"
        assert result.temporal_gate_passed is None


# ═══════════════════════════════════════════════════════════════════════
# 5. OUTPUT FIELDS: temporal_gate_passed, temporal_reason, temporal_opportunity_type
# ═══════════════════════════════════════════════════════════════════════

class TestTemporalOutputFields:
    """Verify temporal fields are populated correctly on override."""

    def test_override_sets_all_temporal_fields(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.HIGH,
            signal_count=12, scored_signal_count=6, score_snapshot_count=4,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.temporal_gate_passed == "temporal_override"
        assert result.temporal_reason is not None
        assert "emerging_pain" in result.temporal_reason
        assert result.temporal_opportunity_type == "early_positioning"

    def test_accelerating_sets_opportunity_type(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.MODERATE,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.temporal_opportunity_type == "accelerated_positioning"

    def test_no_override_sets_temporal_fields_to_none(self):
        """When no override happens, temporal fields remain None."""
        td = _make_temporal(
            state=TemporalDiagnosticState.INSUFFICIENT,
            confidence=TemporalConfidence.HIGH,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.temporal_gate_passed is None
        assert result.temporal_reason is None
        assert result.temporal_opportunity_type is None

    def test_temporal_reason_contains_evidence_details(self):
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.HIGH,
            signal_count=15, scored_signal_count=8, score_snapshot_count=5,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert "signals=15" in result.temporal_reason
        assert "scored=8" in result.temporal_reason
        assert "snapshots=5" in result.temporal_reason
        assert "high" in result.temporal_reason


# ═══════════════════════════════════════════════════════════════════════
# 6. _apply_temporal_override UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestApplyTemporalOverrideDirect:
    """Direct tests on _apply_temporal_override for boundary precision.

    Note: _apply_temporal_override is a low-level function. It does NOT
    check whether the static ds is eligible — that's handled by
    check_eligibility which returns before calling this for eligible states.
    """

    def test_no_signal_with_moderate_confidence_allows_override(self):
        """no_signal + moderate temporal confidence → override allowed."""
        result = _apply_temporal_override(
            static_ds="no_signal",
            temporal_state=TemporalDiagnosticState.EMERGING_PAIN,
            temporal_confidence=TemporalConfidence.MODERATE,
            signal_count=10, scored_signal_count=5, score_snapshot_count=3,
        )
        assert result is not None
        assert result.eligible is True

    def test_no_signal_with_high_confidence_allows_override(self):
        result = _apply_temporal_override(
            static_ds="no_signal",
            temporal_state=TemporalDiagnosticState.ACCELERATING_PAIN,
            temporal_confidence=TemporalConfidence.HIGH,
            signal_count=10, scored_signal_count=5, score_snapshot_count=3,
        )
        assert result is not None
        assert result.eligible is True

    def test_insufficient_evidence_with_moderate_temporal_allows_override(self):
        result = _apply_temporal_override(
            static_ds="insufficient_evidence",
            temporal_state=TemporalDiagnosticState.EMERGING_PAIN,
            temporal_confidence=TemporalConfidence.MODERATE,
            signal_count=10, scored_signal_count=5, score_snapshot_count=3,
        )
        assert result is not None
        assert result.eligible is True

    def test_confidence_band_is_moderate_on_override(self):
        """All temporal overrides result in moderate confidence band."""
        result = _apply_temporal_override(
            static_ds="insufficient_evidence",
            temporal_state=TemporalDiagnosticState.ACCELERATING_PAIN,
            temporal_confidence=TemporalConfidence.HIGH,
            signal_count=10, scored_signal_count=5, score_snapshot_count=3,
        )
        assert result is not None
        assert result.confidence_band == "moderate"


# ═══════════════════════════════════════════════════════════════════════
# 7. POSITIONING IMPLICATION EXAMPLES
# ═══════════════════════════════════════════════════════════════════════

class TestPositioningImplications:
    """Examples of how temporal opportunity types map to positioning guidance.

    These tests verify the output fields are populated correctly so that
    downstream consumers (SmartMatchCache, PositioningOutput, NovaWork UI)
    can differentiate positioning implications.

    early_positioning:
      - For consultants/candidates: "Emerging opportunity — early mover advantage"
      - Assertiveness: exploratory (low confidence)
      - Attack angle: focus on discovery, validate pain direction

    accelerated_positioning:
      - For consultants/candidates: "Accelerating pain — urgent positioning"
      - Assertiveness: directional (moderate confidence)
      - Attack angle: proactive outreach, reference specific pain signals
    """

    def test_early_positioning_implication_fields(self):
        """emerging_pain → early_positioning with correct reason wording."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.MODERATE,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.temporal_opportunity_type == "early_positioning"
        assert "emerging" in result.reason.lower()
        assert "conditional" in result.reason.lower() or "early" in result.reason.lower()

    def test_accelerated_positioning_implication_fields(self):
        """accelerating_pain → accelerated_positioning with urgency wording."""
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.HIGH,
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=0, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.temporal_opportunity_type == "accelerated_positioning"
        assert "accelerat" in result.reason.lower()
        assert "conditional" in result.reason.lower()

    def test_b2b_consultant_use_case(self):
        """B2B consultant scenario: company with insufficient static evidence
        but accelerating temporal signals → eligible for early outreach."""
        td = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.MODERATE,
            top_cat=TopChangingCategory(
                category="reporting_fragmentation",
                delta=0.8,
                trend="worsening",
                velocity=2.1,
                evidence_strength=EvidenceStrength.MODERATE,
            ),
        )
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=2, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.confidence_band == "moderate"
        assert result.temporal_opportunity_type == "accelerated_positioning"
        # Downstream can use temporal_opportunity_type to:
        # - Set assertiveness to "directional" for accelerated_positioning
        # - Craft networking angle around the top_changing_category
        # - Prioritize this company in SmartMatch over static-only ineligible

    def test_candidate_use_case(self):
        """Candidate scenario: company with emerging pain → exploratory positioning."""
        td = _make_temporal(
            state=TemporalDiagnosticState.EMERGING_PAIN,
            confidence=TemporalConfidence.MODERATE,
            top_cat=TopChangingCategory(
                category="tooling_inconsistency",
                delta=0.3,
                trend="worsening",
                velocity=0.8,
                evidence_strength=EvidenceStrength.WEAK,
            ),
        )
        result = check_eligibility(
            diagnostic_state="no_signal",
            pain_clarity="low", function_concentration="low",
            positioning_readiness="low", classified_roles=1, jds_extracted=0,
            temporal_diagnostic=td,
        )
        assert result.eligible is True
        assert result.temporal_opportunity_type == "early_positioning"
        # Downstream can use this to:
        # - Set assertiveness to "exploratory"
        # - Suggest discovery conversations, not definitive positioning