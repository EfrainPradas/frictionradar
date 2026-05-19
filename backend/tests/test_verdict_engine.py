"""
Verdict engine tests.

Verifies:
  1. Zero signals → preliminary verdict, no specific pain.
  2. High hiring + low pain clarity → preliminary, not definitive.
  3. Strong evidence → final verdict with all pain fields populated.
  4. Company type switch (operating vs intermediary) changes pain map.
  5. Friction inference from signal text matches known types.
  6. Verdict always includes hiring_pressure, pain_clarity, diagnosis_status.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tests.conftest import (
    make_signal, make_signals, make_company, make_friction_score,
    make_mock_db, make_v2_breakdown,
)
from app.services.final_verdict_engine import FinalVerdictEngine


def _make_verdict_inputs(
    hiring_pressure="moderate",
    pain_clarity="moderate",
    extraction_coverage="moderate",
    function_concentration="moderate",
    diagnostic_state="specific_pain_emerging",
    allow_specific_pain=True,
):
    """Create mock evaluation output for verdict engine tests.

    Note: The evaluation engine uses 'diagnostic_state' as the key,
    while the verdict engine output uses 'diagnosis_status'.
    """
    return {
        "kpis": {
            "extraction_coverage": extraction_coverage,
            "hiring_pressure": hiring_pressure,
            "function_concentration": function_concentration,
            "pain_clarity": pain_clarity,
            "company_type_confidence": "moderate",
            "positioning_readiness": "moderate",
        },
        "diagnostic_state": diagnostic_state,
        "allow_specific_pain_output": allow_specific_pain,
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


class TestVerdictZeroSignals:
    """Zero signals should produce a preliminary verdict with no specific pain."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_zero_signals_preliminary_verdict(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="low",
            pain_clarity="low",
            extraction_coverage="low",
            diagnostic_state="insufficient_evidence",
            allow_specific_pain=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low",
            "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "No evidence yet.",
            "next_best_step": "Run collection.",
            "metadata": {"total_signals": 0, "total_job_roles": 0},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low",
            "confidence": "low",
            "is_strong_enough": False,
        }

        engine = FinalVerdictEngine()
        company = make_company()
        result = engine.generate(
            company=company,
            signals=[],
            score=None,
            hypothesis=None,
            db=make_mock_db(),
        )

        assert result["verdict_type"] == "preliminary"
        assert result["main_pain"] is None
        assert result["where_pain_lives"] is None
        assert result["diagnosis_status"] == "insufficient_evidence"


class TestVerdictHighHiringLowPain:
    """High hiring pressure + low pain clarity → preliminary, no definitive pain."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_high_hiring_low_pain_no_definitive(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high",
            pain_clarity="low",
            diagnostic_state="broad_hiring_pattern_detected",
            allow_specific_pain=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high",
            "pain_clarity": "low",
            "diagnosis_status": "broad_hiring_pattern_detected",
            "business_read_summary": "Hiring activity but no specific pain.",
            "next_best_step": "Parse role details.",
            "metadata": {"total_signals": 5, "total_job_roles": 0},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "moderate",
            "confidence": "moderate",
            "is_strong_enough": False,
        }

        engine = FinalVerdictEngine()
        company = make_company()
        result = engine.generate(
            company=company,
            signals=make_signals([("high_hiring_volume", None)]),
            score=None,
            hypothesis=None,
            db=make_mock_db(),
        )

        assert result["verdict_type"] == "preliminary"
        assert result["main_pain"] is None
        assert result["diagnosis_status"] == "broad_hiring_pattern_detected"


class TestVerdictStrongEvidence:
    """Strong evidence → final verdict with pain fields populated."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_strong_evidence_final_verdict(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high",
            pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high",
            "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong hiring signals with clear pain.",
            "next_best_step": "Use this insight for positioning.",
            "metadata": {"total_signals": 10, "total_job_roles": 5},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high",
            "confidence": "high",
            "is_strong_enough": True,
        }

        engine = FinalVerdictEngine()
        company = make_company()
        score = make_friction_score(dominant_friction_type="scaling_strain")

        result = engine.generate(
            company=company,
            signals=make_signals([("scaling_language_detected", None)]),
            score=score,
            hypothesis=None,
            company_type="operating_company",
            db=make_mock_db(),
        )

        assert result["verdict_type"] == "final"
        assert result["main_pain"] is not None
        assert result["where_pain_lives"] is not None
        assert result["diagnosis_status"] == "specific_pain_identified"


class TestVerdictCompanyTypeSwitch:
    """Operating company vs job_market_intermediary should use different pain maps."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_operating_company_pain_map(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high",
            "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.",
            "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high",
            "confidence": "high",
            "is_strong_enough": True,
        }

        engine = FinalVerdictEngine()
        company = make_company()
        score = make_friction_score(dominant_friction_type="scaling_strain")

        result = engine.generate(
            company=company,
            signals=[],
            score=score,
            hypothesis=None,
            company_type="operating_company",
            db=make_mock_db(),
        )

        assert result["verdict_type"] == "final"
        # Operating company pain map should talk about coordination/alignment
        assert "coordination" in result["main_pain"] or "scale" in result["main_pain"].lower()

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_intermediary_pain_map(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high",
            "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.",
            "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high",
            "confidence": "high",
            "is_strong_enough": True,
        }

        engine = FinalVerdictEngine()
        company = make_company()
        score = make_friction_score(dominant_friction_type="scaling_strain")

        result = engine.generate(
            company=company,
            signals=[],
            score=score,
            hypothesis=None,
            company_type="job_market_intermediary",
            db=make_mock_db(),
        )

        assert result["verdict_type"] == "final"
        # Intermediary pain map should talk about recruiting/placement
        assert "recruiting" in result["main_pain"].lower() or "placement" in result["main_pain"].lower()


class TestVerdictFrictionInference:
    """Signal text should infer dominant friction type when score doesn't specify."""

    def test_infer_reporting_from_signals(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="analytics_hiring_detected", signal_text="needs better data reporting"),
        ]
        result = engine._infer_friction_from_signals(signals)
        assert result == "reporting_fragmentation"

    def test_infer_tooling_from_signals(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="hiring_language_detected", signal_text="hiring for their software platform"),
        ]
        result = engine._infer_friction_from_signals(signals)
        assert result == "tooling_inconsistency"

    def test_infer_scaling_from_signals(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="scaling_language_detected", signal_text="scaling rapidly and hiring"),
        ]
        result = engine._infer_friction_from_signals(signals)
        assert result == "scaling_strain"

    def test_infer_process_from_signals(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="company_size_detected", signal_text="manual processes slow them down"),
        ]
        result = engine._infer_friction_from_signals(signals)
        assert result == "process_inefficiency"

    def test_infer_customer_from_signals(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="hiring_news_detected", signal_text="improving customer experience"),
        ]
        result = engine._infer_friction_from_signals(signals)
        assert result == "customer_experience_friction"

    def test_infer_default_when_no_match(self):
        engine = FinalVerdictEngine()
        signals = [
            make_signal(signal_type="careers_page_found", signal_text="found careers page"),
        ]
        result = engine._infer_friction_from_signals(signals)
        # No keyword match → None
        assert result is None


class TestVerdictAlwaysIncludesKeyFields:
    """Every verdict should include required key fields."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_preliminary_includes_all_fields(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            diagnostic_state="insufficient_evidence",
            allow_specific_pain=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low",
            "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "Not enough evidence.",
            "next_best_step": "Run collection.",
            "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low",
            "confidence": "low",
            "is_strong_enough": False,
        }

        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(),
            signals=[],
            score=None,
            hypothesis=None,
            db=make_mock_db(),
        )

        required_fields = [
            "verdict_type", "hiring_pressure", "pain_clarity",
            "diagnosis_status", "confidence",
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"