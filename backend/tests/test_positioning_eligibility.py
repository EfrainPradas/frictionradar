"""
Positioning eligibility boundary tests.

Verifies:
  1. insufficient_evidence → not eligible
  2. broad_hiring_pattern_detected with < 5 classified roles → not eligible
  3. broad_hiring_pattern_detected with >= 15 classified roles → eligible (conditional)
  4. specific_pain_emerging with >= 3 classified → eligible (conditional)
  5. specific_pain_emerging with < 3 classified → not eligible
  6. specific_pain_identified with JDs → eligible (full)
  7. ready_for_positioning → eligible (full, high confidence)
  8. Company not found → not eligible
  9. Zero job roles → classified = 0 → affects eligibility
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tests.conftest import make_signal, make_company, make_mock_db
from app.services.positioning_engine import (
    check_eligibility,
    EligibilityResult,
)


class TestEligibilityInsufficientEvidence:
    """insufficient_evidence → never eligible."""

    def test_insufficient_evidence_not_eligible(self):
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low",
            function_concentration="low",
            positioning_readiness="low",
            classified_roles=0,
            jds_extracted=0,
        )
        assert result.eligible is False
        assert result.gate_passed == "none"

    def test_insufficient_evidence_even_with_roles(self):
        """Even with roles, insufficient_evidence blocks eligibility."""
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low",
            function_concentration="moderate",
            positioning_readiness="low",
            classified_roles=10,
            jds_extracted=5,
        )
        assert result.eligible is False


class TestEligibilityBroadHiringPattern:
    """broad_hiring_pattern_detected eligibility boundaries."""

    def test_broad_low_roles_not_eligible(self):
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low",
            function_concentration="low",
            positioning_readiness="low",
            classified_roles=2,
            jds_extracted=0,
        )
        assert result.eligible is False

    def test_broad_15_roles_eligible(self):
        """classified >= 15 makes broad eligible (conditional, low confidence)."""
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low",
            function_concentration="low",
            positioning_readiness="low",
            classified_roles=15,
            jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.confidence_band == "low"

    def test_broad_5_roles_moderate_concentration_eligible(self):
        """classified >= 5 AND function_concentration != 'low' → eligible."""
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low",
            function_concentration="moderate",
            positioning_readiness="low",
            classified_roles=5,
            jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"

    def test_broad_5_roles_low_concentration_not_eligible(self):
        """classified >= 5 but function_concentration='low' → not eligible."""
        result = check_eligibility(
            diagnostic_state="broad_hiring_pattern_detected",
            pain_clarity="low",
            function_concentration="low",
            positioning_readiness="low",
            classified_roles=5,
            jds_extracted=0,
        )
        assert result.eligible is False


class TestEligibilitySpecificPainEmerging:
    """specific_pain_emerging eligibility boundaries."""

    def test_emerging_3_classified_eligible(self):
        result = check_eligibility(
            diagnostic_state="specific_pain_emerging",
            pain_clarity="moderate",
            function_concentration="moderate",
            positioning_readiness="moderate",
            classified_roles=3,
            jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "conditional"
        assert result.confidence_band == "moderate"

    def test_emerging_2_classified_not_eligible(self):
        result = check_eligibility(
            diagnostic_state="specific_pain_emerging",
            pain_clarity="moderate",
            function_concentration="moderate",
            positioning_readiness="moderate",
            classified_roles=2,
            jds_extracted=0,
        )
        assert result.eligible is False

    def test_emerging_1_classified_not_eligible(self):
        result = check_eligibility(
            diagnostic_state="specific_pain_emerging",
            pain_clarity="moderate",
            function_concentration="moderate",
            positioning_readiness="moderate",
            classified_roles=1,
            jds_extracted=0,
        )
        assert result.eligible is False


class TestEligibilitySpecificPainIdentified:
    """specific_pain_identified eligibility boundaries."""

    def test_identified_3_jds_eligible_high(self):
        """3+ JDs → eligible (full, high confidence)."""
        result = check_eligibility(
            diagnostic_state="specific_pain_identified",
            pain_clarity="high",
            function_concentration="high",
            positioning_readiness="high",
            classified_roles=5,
            jds_extracted=3,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.confidence_band == "high"

    def test_identified_0_jds_still_eligible_moderate(self):
        """identified with 0 JDs → eligible (full, moderate confidence)."""
        result = check_eligibility(
            diagnostic_state="specific_pain_identified",
            pain_clarity="high",
            function_concentration="moderate",
            positioning_readiness="moderate",
            classified_roles=5,
            jds_extracted=0,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.confidence_band == "moderate"


class TestEligibilityReadyForPositioning:
    """ready_for_positioning → always eligible (full, high)."""

    def test_ready_for_positioning_eligible(self):
        result = check_eligibility(
            diagnostic_state="ready_for_positioning",
            pain_clarity="high",
            function_concentration="high",
            positioning_readiness="high",
            classified_roles=10,
            jds_extracted=5,
        )
        assert result.eligible is True
        assert result.gate_passed == "full"
        assert result.confidence_band == "high"


class TestEligibilityEdgeCases:
    """Boundary conditions and edge cases."""

    def test_zero_classified_roles(self):
        """Zero classified roles should generally make eligibility harder."""
        for state in ["broad_hiring_pattern_detected", "specific_pain_emerging"]:
            result = check_eligibility(
                diagnostic_state=state,
                pain_clarity="moderate",
                function_concentration="moderate",
                positioning_readiness="moderate",
                classified_roles=0,
                jds_extracted=0,
            )
            assert result.eligible is False, f"state={state} with 0 roles should not be eligible"

    def test_eligibility_result_fields(self):
        result = check_eligibility(
            diagnostic_state="insufficient_evidence",
            pain_clarity="low",
            function_concentration="low",
            positioning_readiness="low",
            classified_roles=0,
            jds_extracted=0,
        )
        assert hasattr(result, "eligible")
        assert hasattr(result, "gate_passed")
        assert hasattr(result, "reason")
        assert hasattr(result, "diagnostic_state")
        assert hasattr(result, "confidence_band")

    def test_unknown_diagnostic_state(self):
        """Unknown diagnostic states should not be eligible."""
        result = check_eligibility(
            diagnostic_state="unknown_state",
            pain_clarity="moderate",
            function_concentration="moderate",
            positioning_readiness="moderate",
            classified_roles=5,
            jds_extracted=3,
        )
        assert result.eligible is False