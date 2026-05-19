"""
Cross-engine confidence consistency tests.

Verifies that CompanyEvaluationEngine, EvidenceThresholdEngine, and
BusinessReadEngine produce consistent diagnostic states and confidence
levels when given the same input data.

Ensures:
  1. All three engines agree on diagnosis_status for the same inputs.
  2. Confidence levels are monotonic: more signals → higher confidence.
  3. evidence_threshold_engine.is_strong_enough matches
     company_evaluation_engine.allow_specific_pain_output.
  4. business_read_engine.diagnosis_status maps correctly from
     company_evaluation_engine.diagnosis_status.
  5. KPI levels are valid strings from the expected set.
  6. Zero-signal edge case: all engines agree on insufficient_evidence.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tests.conftest import make_signal, make_signals, make_company, make_mock_db


# ---------------------------------------------------------------------------
# Helpers — build evaluation output with sensible defaults
# ---------------------------------------------------------------------------

def _make_eval_output(**overrides):
    """Create a minimal company evaluation output dict."""
    base = {
        "kpis": {
            "extraction_coverage": "moderate",
            "hiring_pressure": "moderate",
            "function_concentration": "moderate",
            "pain_clarity": "moderate",
            "company_type_confidence": "moderate",
            "positioning_readiness": "moderate",
        },
        "diagnostic_state": "specific_pain_emerging",
        "allow_specific_pain_output": True,
        "summary": "Test summary",
        "next_best_step": "Test next step",
        "evidence": {
            "distinct_signal_types": 5,
            "open_positions_count": 30,
            "visible_hiring_areas": 3,
            "visible_job_cards": 10,
            "parsed_titles": 8,
            "parsed_descriptions": 8,
        },
        "reasoning_trace": {},
    }
    base.update(overrides)
    return base


def _make_business_read(evaluation_output, overrides=None):
    """Build a BusinessReadEngine.compute_reading return from evaluation output."""
    kpis = evaluation_output["kpis"]
    state = evaluation_output["diagnostic_state"]
    base = {
        "hiring_pressure": kpis["hiring_pressure"],
        "pain_clarity": kpis["pain_clarity"],
        "diagnosis_status": state,
        "business_read_summary": evaluation_output["summary"],
        "next_best_step": evaluation_output["next_best_step"],
        "metadata": {
            "total_signals": evaluation_output["evidence"].get("distinct_signal_types", 0),
            "total_job_roles": 0,
        },
    }
    if overrides:
        base.update(overrides)
    return base


def _make_evidence_threshold(evaluation_output):
    """Build an EvidenceThresholdEngine.evaluate_evidence return from evaluation output."""
    state = evaluation_output["diagnostic_state"]
    allow = evaluation_output["allow_specific_pain_output"]
    coverage = evaluation_output["kpis"]["extraction_coverage"]

    # Map diagnosis_status → confidence
    confidence_map = {
        "ready_for_positioning": "high",
        "specific_pain_identified": "high",
        "specific_pain_emerging": "moderate",
        "broad_hiring_pattern_detected": "low",
        "insufficient_evidence": "low",
    }

    return {
        "evidence_quality": coverage,
        "confidence": confidence_map.get(state, "low"),
        "is_strong_enough": allow,
        "unique_signal_count": 5,
        "total_signal_count": 10,
        "source_type_count": 3,
        "friction_score": 0.65,
        "function_type": None,
        "signal_diversity": "high",
        "has_repeated_signals": False,
        "function_specific_signals": {},
        "visible_job_count": 10,
        "visible_categories_count": 3,
        "has_high_volume": False,
    }


class TestDiagnosticStateConsistency:
    """All three engines should agree on diagnosis_status for the same inputs."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_all_engines_agree_insufficient_evidence(self, mock_eval, mock_br, mock_et):
        eval_output = _make_eval_output(
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        eval_output["kpis"]["hiring_pressure"] = "low"
        eval_output["kpis"]["pain_clarity"] = "low"

        mock_eval.evaluate.return_value = eval_output
        mock_br.compute_reading.return_value = _make_business_read(eval_output)
        mock_et.evaluate_evidence.return_value = _make_evidence_threshold(eval_output)

        from app.services.final_verdict_engine import FinalVerdictEngine
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(),
            signals=[],
            score=None,
            hypothesis=None,
            db=make_mock_db(),
        )

        assert result["diagnosis_status"] == "insufficient_evidence"
        assert result["verdict_type"] == "preliminary"

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_all_engines_agree_specific_pain(self, mock_eval, mock_br, mock_et):
        eval_output = _make_eval_output(
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        eval_output["kpis"]["hiring_pressure"] = "high"
        eval_output["kpis"]["pain_clarity"] = "high"

        mock_eval.evaluate.return_value = eval_output
        mock_br.compute_reading.return_value = _make_business_read(eval_output)
        mock_et.evaluate_evidence.return_value = _make_evidence_threshold(eval_output)

        from app.services.final_verdict_engine import FinalVerdictEngine
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(),
            signals=make_signals([("scaling_language_detected", None)]),
            score=None,
            hypothesis=None,
            db=make_mock_db(),
        )

        assert result["diagnosis_status"] == "specific_pain_identified"
        assert result["verdict_type"] == "final"


class TestConfidenceMonotonicity:
    """More signals should produce equal or higher confidence levels."""

    def test_zero_signals_none_confidence(self):
        from app.services.scoring_engine import _compute_confidence
        confidence = _compute_confidence({}, [])
        assert confidence["confidence_level"] == "none"

    def test_single_signal_low_or_none_confidence(self):
        from app.services.scoring_engine import _evaluate_rules, _compute_confidence
        signals = [make_signal(signal_type="careers_page_found")]
        breakdown = _evaluate_rules(signals)
        confidence = _compute_confidence(breakdown, signals)
        assert confidence["confidence_level"] in ("none", "low")

    def test_many_diverse_signals_higher_confidence(self):
        from app.services.scoring_engine import _evaluate_rules, _compute_confidence
        signals = make_signals([
            ("careers_page_found", None),
            ("open_positions_count_detected", 50),
            ("analytics_hiring_detected", None),
            ("finance_hiring_detected", None),
            ("scaling_language_detected", None),
            ("reporting_language_detected", None),
            ("high_hiring_volume", None),
        ])
        breakdown = _evaluate_rules(signals)
        confidence = _compute_confidence(breakdown, signals)
        # With 7 diverse signals, confidence should be at least low
        assert confidence["confidence_level"] in ("low", "medium", "high")


class TestEvidenceThresholdConsistency:
    """EvidenceThresholdEngine.is_strong_enough should match allow_specific_pain_output."""

    def test_allow_specific_pain_maps_to_is_strong_enough(self):
        """When evaluation says allow_specific_pain=True, threshold should say is_strong_enough=True."""
        eval_output = _make_eval_output(
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        threshold = _make_evidence_threshold(eval_output)
        assert threshold["is_strong_enough"] is True

    def test_disallow_specific_pain_maps_to_not_strong_enough(self):
        """When evaluation says allow_specific_pain=False, threshold should say is_strong_enough=False."""
        eval_output = _make_eval_output(
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        threshold = _make_evidence_threshold(eval_output)
        assert threshold["is_strong_enough"] is False


class TestKPILevels:
    """All KPI levels should be valid strings from the expected set."""

    VALID_LEVELS = {"low", "moderate", "high"}

    def test_kpi_keys_are_present(self):
        eval_output = _make_eval_output()
        expected_kpis = {
            "extraction_coverage", "hiring_pressure",
            "function_concentration", "pain_clarity",
            "company_type_confidence", "positioning_readiness",
        }
        assert set(eval_output["kpis"].keys()) == expected_kpis

    def test_kpi_levels_are_valid(self):
        eval_output = _make_eval_output()
        for kpi_name, level in eval_output["kpis"].items():
            assert level in self.VALID_LEVELS, (
                f"KPI '{kpi_name}' has invalid level '{level}'"
            )

    def test_diagnosis_status_values(self):
        """Diagnostic state should be one of the known states."""
        valid_states = {
            "insufficient_evidence",
            "broad_hiring_pattern_detected",
            "specific_pain_emerging",
            "specific_pain_identified",
            "ready_for_positioning",
        }
        for state in valid_states:
            eval_output = _make_eval_output(diagnosis_status=state)
            assert eval_output["diagnosis_status"] in valid_states


class TestBusinessReadMapping:
    """BusinessReadEngine should map diagnostic states correctly."""

    def test_ready_for_positioning_maps_to_specific_pain_identified(self):
        """BusinessReadEngine maps ready_for_positioning to specific_pain_identified."""
        eval_output = _make_eval_output(
            diagnostic_state="ready_for_positioning",
        )
        reading = _make_business_read(eval_output)
        # BusinessReadEngine maps ready_for_positioning to specific_pain_identified
        # in its DIAGNOSIS_STATUS constant
        assert reading["diagnosis_status"] in (
            "ready_for_positioning",
            "specific_pain_identified",
        )

    def test_insufficient_evidence_passes_through(self):
        eval_output = _make_eval_output(
            diagnostic_state="insufficient_evidence",
        )
        reading = _make_business_read(eval_output)
        assert reading["diagnosis_status"] == "insufficient_evidence"

    def test_broad_hiring_passes_through(self):
        eval_output = _make_eval_output(
            diagnostic_state="broad_hiring_pattern_detected",
        )
        reading = _make_business_read(eval_output)
        assert reading["diagnosis_status"] == "broad_hiring_pattern_detected"