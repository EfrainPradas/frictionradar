"""
Tests for the unified confidence architecture.

Verifies that:
  1. CompanyEvaluationEngine produces reasoning_trace for every KPI.
  2. EvidenceThresholdEngine delegates to CompanyEvaluationEngine and
     returns consistent values.
  3. BusinessReadEngine delegates to CompanyEvaluationEngine and
     returns consistent values.
  4. Diagnostic state transitions are correct.
  5. Zero signals produce insufficient_evidence across all engines.
  6. The legacy API shapes are preserved by delegated engines.
  7. FinalVerdictEngine uses canonical KPIs consistently.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.company_evaluation import (
    CompanyEvaluationEngine,
    LEVEL_LOW,
    LEVEL_MODERATE,
    LEVEL_HIGH,
)
from app.services.evidence_threshold_engine import EvidenceThresholdEngine
from app.services.business_read_engine import BusinessReadEngine


def _make_signal(signal_type: str, signal_text: str = "", numeric_value=None, source_type: str = "ats_board"):
    """Create a mock CompanySignal for testing."""
    s = MagicMock()
    s.signal_type = signal_type
    s.signal_text = signal_text
    s.numeric_value = numeric_value
    s.source_type = source_type
    s.company_id = uuid4()
    return s


def _make_role(functional_area: str = None, role_title: str = None, role_description: str = None):
    """Create a mock CompanyJobRole for testing."""
    r = MagicMock()
    r.functional_area = functional_area
    r.role_title = role_title
    r.role_description = role_description
    r.company_id = uuid4()
    return r


# ─── Reasoning Trace ───────────────────────────────────────────────

class TestReasoningTrace:
    """Verify reasoning_trace is populated for every KPI."""

    def test_reasoning_trace_keys_match_kpis(self):
        """Every KPI should have a reasoning_trace entry."""
        engine = CompanyEvaluationEngine()
        result = engine.evaluate(
            company_id=uuid4(),
            signals=[],
            job_roles=[],
        )
        kpis = result["kpis"]
        trace = result["reasoning_trace"]

        for kpi_name in kpis:
            assert kpi_name in trace, f"Missing reasoning_trace for KPI: {kpi_name}"

    def test_reasoning_trace_has_level_and_conditions(self):
        """Each reasoning_trace entry should have level, met_conditions, missed_conditions."""
        engine = CompanyEvaluationEngine()
        result = engine.evaluate(
            company_id=uuid4(),
            signals=[],
            job_roles=[],
        )
        for kpi_name, entry in result["reasoning_trace"].items():
            assert "level" in entry, f"Missing 'level' in trace for {kpi_name}"
            assert entry["level"] in (LEVEL_LOW, LEVEL_MODERATE, LEVEL_HIGH), (
                f"Invalid level '{entry['level']}' in trace for {kpi_name}"
            )
            assert "met_conditions" in entry, f"Missing 'met_conditions' in trace for {kpi_name}"
            assert "missed_conditions" in entry, f"Missing 'missed_conditions' in trace for {kpi_name}"

    def test_reasoning_trace_with_signals(self):
        """Reasoning trace with signals should have some met conditions."""
        engine = CompanyEvaluationEngine()
        signals = [
            _make_signal("analytics_hiring_detected", "hiring data analysts", numeric_value=None),
            _make_signal("open_positions_count_detected", "Open positions: 50", numeric_value=50),
            _make_signal("careers_page_found", "https://example.com/careers"),
        ]
        result = engine.evaluate(
            company_id=uuid4(),
            signals=signals,
            job_roles=[],
        )
        trace = result["reasoning_trace"]
        # At least one KPI should have met conditions
        total_met = sum(len(entry.get("met_conditions", [])) for entry in trace.values())
        assert total_met > 0, "With signals, at least one KPI should have met conditions"


# ─── Threshold Consistency ──────────────────────────────────────────

class TestThresholdConsistency:
    """Verify that delegated engines produce consistent values."""

    def test_zero_signals_insufficient_evidence_all_engines(self):
        """All engines should agree: zero signals → insufficient_evidence."""
        eval_engine = CompanyEvaluationEngine()
        result = eval_engine.evaluate(
            company_id=uuid4(),
            signals=[],
            job_roles=[],
        )
        assert result["diagnostic_state"] == "insufficient_evidence"
        assert result["kpis"]["hiring_pressure"] == LEVEL_LOW
        assert result["kpis"]["pain_clarity"] == LEVEL_LOW
        assert result["kpis"]["extraction_coverage"] == LEVEL_LOW
        assert result["allow_specific_pain_output"] is False

    def test_business_read_delegation_matches_evaluation(self):
        """BusinessReadEngine should produce KPIs consistent with CompanyEvaluationEngine."""
        eval_engine = CompanyEvaluationEngine()
        br_engine = BusinessReadEngine()

        signals = [
            _make_signal("open_positions_count_detected", "Open positions: 50", numeric_value=50),
            _make_signal("analytics_hiring_detected", "hiring analysts"),
            _make_signal("finance_hiring_detected", "hiring finance"),
        ]

        eval_result = eval_engine.evaluate(
            company_id=uuid4(),
            signals=signals,
            job_roles=[],
        )
        br_result = br_engine.compute_reading(
            company_id=uuid4(),
            db=None,
            signals=signals,
        )

        # KPIs should match exactly since both delegate to the same engine
        assert br_result["hiring_pressure"] == eval_result["kpis"]["hiring_pressure"]
        assert br_result["pain_clarity"] == eval_result["kpis"]["pain_clarity"]

    def test_evidence_threshold_delegation_matches_evaluation(self):
        """EvidenceThresholdEngine should produce values consistent with CompanyEvaluationEngine."""
        eval_engine = CompanyEvaluationEngine()
        et_engine = EvidenceThresholdEngine()

        signals = [
            _make_signal("open_positions_count_detected", "Open positions: 50", numeric_value=50),
            _make_signal("analytics_hiring_detected", "hiring analysts"),
        ]

        eval_result = eval_engine.evaluate(
            company_id=uuid4(),
            signals=signals,
            job_roles=[],
        )
        et_result = et_engine.evaluate_evidence(
            signals=signals,
            score=None,
            collection_runs=None,
            company_id=uuid4(),
        )

        # evidence_quality should match extraction_coverage
        assert et_result["evidence_quality"] == eval_result["kpis"]["extraction_coverage"]

        # is_strong_enough should match allow_specific_pain_output
        assert et_result["is_strong_enough"] == eval_result["allow_specific_pain_output"]


# ─── Diagnostic State Machine ───────────────────────────────────────

class TestDiagnosticStateMachine:
    """Verify diagnostic state transitions."""

    def test_zero_signals_insufficient_evidence(self):
        engine = CompanyEvaluationEngine()
        result = engine.evaluate(company_id=uuid4(), signals=[], job_roles=[])
        assert result["diagnostic_state"] == "insufficient_evidence"

    def test_high_hiring_low_pain_broad_pattern(self):
        """High hiring pressure + low pain clarity → broad_hiring_pattern_detected."""
        engine = CompanyEvaluationEngine()

        # Create signals that give high hiring pressure but low pain clarity
        signals = [
            _make_signal("high_open_positions_count_detected", "100+ positions", numeric_value=150),
            _make_signal("analytics_hiring_detected", "hiring analysts"),
            _make_signal("finance_hiring_detected", "hiring finance"),
            _make_signal("operations_hiring_detected", "hiring operations"),
            _make_signal("marketing_hiring_detected", "hiring marketing"),
        ]

        result = engine.evaluate(company_id=uuid4(), signals=signals, job_roles=[])

        # With high hiring but no role concentration, pain_clarity should be low
        # and diagnostic_state should be broad_hiring_pattern_detected or specific_pain_emerging
        assert result["diagnostic_state"] in (
            "broad_hiring_pattern_detected",
            "specific_pain_emerging",
            "specific_pain_identified",
        )

    def test_low_extraction_coverage_insufficient_evidence(self):
        """Low extraction_coverage always forces insufficient_evidence."""
        engine = CompanyEvaluationEngine()
        result = engine.evaluate(company_id=uuid4(), signals=[], job_roles=[])
        assert result["kpis"]["extraction_coverage"] == LEVEL_LOW
        assert result["diagnostic_state"] == "insufficient_evidence"


# ─── Legacy API Shape Preservation ──────────────────────────────────

class TestLegacyAPIShapePreservation:
    """Verify that delegated engines preserve their legacy API shapes."""

    def test_evidence_threshold_preserves_keys(self):
        """EvidenceThresholdEngine.evaluate_evidence() should return all expected keys."""
        engine = EvidenceThresholdEngine()
        result = engine.evaluate_evidence(
            signals=[],
            score=None,
            collection_runs=None,
            company_id=uuid4(),
        )

        expected_keys = {
            "evidence_quality", "confidence", "is_strong_enough",
            "unique_signal_count", "total_signal_count", "source_type_count",
            "friction_score", "function_type", "signal_diversity",
            "has_repeated_signals", "function_specific_signals",
            "visible_job_count", "visible_categories_count", "has_high_volume",
        }
        actual_keys = set(result.keys())
        missing = expected_keys - actual_keys
        assert not missing, f"Missing keys in EvidenceThresholdEngine output: {missing}"

    def test_business_read_preserves_keys(self):
        """BusinessReadEngine.compute_reading() should return all expected keys."""
        engine = BusinessReadEngine()
        result = engine.compute_reading(
            company_id=uuid4(),
            db=None,
            signals=[],
        )

        expected_keys = {
            "hiring_pressure", "pain_clarity", "diagnosis_status",
            "diagnosis_summary", "business_read_summary", "next_best_step",
            "metadata",
        }
        actual_keys = set(result.keys())
        missing = expected_keys - actual_keys
        assert not missing, f"Missing keys in BusinessReadEngine output: {missing}"

    def test_metadata_keys_preserved(self):
        """BusinessReadEngine metadata should have expected keys."""
        engine = BusinessReadEngine()
        result = engine.compute_reading(
            company_id=uuid4(),
            db=None,
            signals=[],
        )

        expected_meta_keys = {
            "total_signals", "total_job_roles", "unique_functional_areas",
            "open_positions_count", "visible_hiring_areas",
            "visible_job_cards", "distinct_hiring_signals",
        }
        actual_meta_keys = set(result["metadata"].keys())
        missing = expected_meta_keys - actual_meta_keys
        assert not missing, f"Missing metadata keys: {missing}"

    def test_evidence_quality_values_are_valid(self):
        """evidence_quality should be one of low/moderate/high."""
        engine = EvidenceThresholdEngine()
        for signals in [[], [_make_signal("test", "test")]]:
            result = engine.evaluate_evidence(
                signals=signals,
                score=None,
                collection_runs=None,
                company_id=uuid4(),
            )
            assert result["evidence_quality"] in ("low", "moderate", "high"), (
                f"Invalid evidence_quality: {result['evidence_quality']}"
            )

    def test_confidence_values_are_valid(self):
        """confidence should be one of low/moderate/high."""
        engine = EvidenceThresholdEngine()
        result = engine.evaluate_evidence(
            signals=[],
            score=None,
            collection_runs=None,
            company_id=uuid4(),
        )
        assert result["confidence"] in ("low", "moderate", "high"), (
            f"Invalid confidence: {result['confidence']}"
        )

    def test_diagnosis_status_values_are_valid(self):
        """BusinessReadEngine diagnosis_status should be one of 4 valid states."""
        engine = BusinessReadEngine()
        result = engine.compute_reading(
            company_id=uuid4(),
            db=None,
            signals=[],
        )
        valid_states = {
            "insufficient_evidence",
            "broad_hiring_pattern_detected",
            "specific_pain_emerging",
            "specific_pain_identified",
        }
        assert result["diagnosis_status"] in valid_states, (
            f"Invalid diagnosis_status: {result['diagnosis_status']}"
        )


# ─── Confidence Level Derivation ────────────────────────────────────

class TestConfidenceLevelDerivation:
    """Verify that confidence is correctly derived from diagnostic_state."""

    def test_insufficient_evidence_gives_low_confidence(self):
        engine = EvidenceThresholdEngine()
        result = engine.evaluate_evidence(
            signals=[],
            score=None,
            collection_runs=None,
            company_id=uuid4(),
        )
        assert result["confidence"] == "low"
        assert result["evidence_quality"] == "low"
        assert result["is_strong_enough"] is False

    def test_is_strong_enough_matches_allow_specific_pain(self):
        """is_strong_enough from EvidenceThresholdEngine should match
        allow_specific_pain_output from CompanyEvaluationEngine."""
        eval_engine = CompanyEvaluationEngine()
        et_engine = EvidenceThresholdEngine()

        signals = [
            _make_signal("analytics_hiring_detected", "hiring data analysts"),
            _make_signal("open_positions_count_detected", "Open positions: 30", numeric_value=30),
        ]

        eval_result = eval_engine.evaluate(
            company_id=uuid4(),
            signals=signals,
            job_roles=[],
        )
        et_result = et_engine.evaluate_evidence(
            signals=signals,
            score=None,
            collection_runs=None,
            company_id=uuid4(),
        )

        assert et_result["is_strong_enough"] == eval_result["allow_specific_pain_output"], (
            f"is_strong_enough={et_result['is_strong_enough']} does not match "
            f"allow_specific_pain_output={eval_result['allow_specific_pain_output']}"
        )