"""Tests for temporal enrichment in FinalVerdictEngine.

Covers:
  - Backward compatibility: existing verdicts unchanged when no temporal data
  - Temporal fields are None/absent when no temporal data provided
  - Temporal fields populated when temporal data is provided
  - Each temporal state produces correct trend_direction
  - Top accelerating/declining pain extracted from score delta
  - Temporal confidence high → verdict wording enhanced
  - Temporal confidence low → verdict wording unchanged
  - Temporal enrichment works across all verdict paths (preliminary, final, default)
"""
import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import make_company, make_signals, make_friction_score, make_mock_db
from app.services.final_verdict_engine import FinalVerdictEngine
from app.schemas.score_delta import (
    CategoryDelta, LookbackWindow, Magnitude, OverallDelta,
    ScoreDeltaResult, TrendDirection,
)
from app.schemas.signal_velocity import (
    CategoryVelocity, PressureState, SignalVelocityResult, VelocityWindow,
)
from app.schemas.temporal_diagnostic import (
    EvidenceStrength, ReasoningStep, TemporalConfidence,
    TemporalDiagnosticResult, TemporalDiagnosticState, TopChangingCategory,
)

from app.core.friction_categories import FRICTION_CATEGORIES


def _make_verdict_inputs(**overrides):
    """Create mock evaluation output."""
    defaults = {
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
        },
        "reasoning_trace": {},
    }
    defaults.update(overrides)
    return defaults


def _make_temporal(
    state: TemporalDiagnosticState = TemporalDiagnosticState.STABLE_LOW,
    confidence: TemporalConfidence = TemporalConfidence.MODERATE,
    top_cat: TopChangingCategory | None = None,
) -> TemporalDiagnosticResult:
    """Create a TemporalDiagnosticResult."""
    return TemporalDiagnosticResult(
        company_id=uuid4(),
        temporal_state=state,
        confidence=confidence,
        evidence_strength=EvidenceStrength.MODERATE,
        top_changing_category=top_cat,
        reasoning_trace=[
            ReasoningStep(step="data_availability", condition="snapshots=2, signals=10", result="sufficient"),
        ],
        summary=f"Temporal state: {state.value}",
    )


def _make_delta(
    delta_val: float = 0.0,
    trend: TrendDirection = TrendDirection.STABLE,
    categories: list[CategoryDelta] | None = None,
) -> ScoreDeltaResult:
    """Create a ScoreDeltaResult."""
    if categories is None:
        categories = [
            CategoryDelta(
                category=cat,
                current_normalized=0.1,
                previous_normalized=0.1,
                delta=0.0,
                trend=TrendDirection.STABLE,
                magnitude=Magnitude.NEGLIGIBLE,
                evidence=f"{cat} stable",
            )
            for cat in FRICTION_CATEGORIES
        ]
    overall = OverallDelta(
        current_total=0.5, previous_total=0.5, delta=delta_val,
        trend=trend, magnitude=Magnitude.NEGLIGIBLE,
    )
    return ScoreDeltaResult(
        company_id=uuid4(), lookback_window=LookbackWindow.D30,
        lookback_days=30, snapshot_count=2, category_deltas=categories, overall=overall,
    )


COMPANY_ID = uuid4()


# ── Backward compatibility ───────────────────────────────────────────────

class TestBackwardCompatibility:
    """Existing verdicts must not change when no temporal data is provided."""

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_preliminary_verdict_unchanged_without_temporal(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="low", pain_clarity="low",
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low", "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "No evidence.",
            "next_best_step": "Run collection.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low", "confidence": "low", "is_strong_enough": False,
        }
        engine = FinalVerdictEngine()
        result = engine.generate(company=make_company(), signals=[], score=None, hypothesis=None, db=make_mock_db())

        assert result["verdict_type"] == "preliminary"
        assert result["main_pain"] is None
        # Temporal fields should be None
        assert result["temporal_status"] is None
        assert result["trend_direction"] is None
        assert result["top_accelerating_pain"] is None
        assert result["top_declining_pain"] is None

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_final_verdict_unchanged_without_temporal(self, mock_eval, mock_br, mock_et):
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high", pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high", "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high", "confidence": "high", "is_strong_enough": True,
        }
        engine = FinalVerdictEngine()
        score = make_friction_score(dominant_friction_type="scaling_strain")
        result = engine.generate(
            company=make_company(), signals=make_signals([("scaling_language_detected", None)]),
            score=score, hypothesis=None, company_type="operating_company", db=make_mock_db(),
        )

        assert result["verdict_type"] == "final"
        assert result["main_pain"] is not None
        assert result["temporal_status"] is None


# ── Temporal enrichment states ──────────────────────────────────────────

class TestTemporalEnrichmentStates:

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_accelerating_pain_enrichment(self, mock_eval, mock_br, mock_et):
        """Temporal accelerating pain → trend_direction='worsening', wording enhanced."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high", pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high", "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high", "confidence": "high", "is_strong_enough": True,
        }

        temporal = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.HIGH,
            top_cat=TopChangingCategory(
                category="reporting_fragmentation", delta=0.3,
                trend="declining", velocity=1.5, evidence_strength=EvidenceStrength.STRONG,
            ),
        )
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=make_signals([("analytics_role_detected", None)]),
            score=make_friction_score(), hypothesis=None, temporal_diagnostic=temporal,
            db=make_mock_db(),
        )

        assert result["temporal_status"] == "accelerating_pain"
        assert result["trend_direction"] == "worsening"
        assert result["top_accelerating_pain"] is not None
        assert result["top_accelerating_pain"]["category"] == "reporting_fragmentation"
        # Wording should be enhanced
        assert "accelerating" in result["what_we_know"].lower() or "reporting" in result["what_we_know"].lower()

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_declining_pain_enrichment(self, mock_eval, mock_br, mock_et):
        """Temporal declining pain → trend_direction='improving'."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high", pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high", "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high", "confidence": "high", "is_strong_enough": True,
        }

        temporal = _make_temporal(
            state=TemporalDiagnosticState.DECLINING_PAIN,
            confidence=TemporalConfidence.MODERATE,
            top_cat=TopChangingCategory(
                category="tooling_inconsistency", delta=-0.2,
                trend="improving", velocity=0.8, evidence_strength=EvidenceStrength.MODERATE,
            ),
        )
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=make_signals([("technology_hiring_detected", None)]),
            score=make_friction_score(), hypothesis=None, temporal_diagnostic=temporal,
            db=make_mock_db(),
        )

        assert result["temporal_status"] == "declining_pain"
        assert result["trend_direction"] == "improving"
        assert result["top_declining_pain"] is not None
        assert "easing" in result["what_we_know"].lower()

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_stable_low_enrichment(self, mock_eval, mock_br, mock_et):
        """Stable low friction → trend_direction='stable'."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="low", pain_clarity="low",
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low", "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "No evidence.", "next_best_step": "Run collection.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low", "confidence": "low", "is_strong_enough": False,
        }

        temporal = _make_temporal(state=TemporalDiagnosticState.STABLE_LOW)
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=[], score=None, hypothesis=None,
            temporal_diagnostic=temporal, db=make_mock_db(),
        )

        assert result["temporal_status"] == "stable_low_friction"
        assert result["trend_direction"] == "stable"

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_volatile_enrichment(self, mock_eval, mock_br, mock_et):
        """Volatile friction → trend_direction='volatile'."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="low", pain_clarity="low",
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low", "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "No evidence.", "next_best_step": "Run collection.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low", "confidence": "low", "is_strong_enough": False,
        }

        temporal = _make_temporal(state=TemporalDiagnosticState.VOLATILE)
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=[], score=None, hypothesis=None,
            temporal_diagnostic=temporal, db=make_mock_db(),
        )

        assert result["temporal_status"] == "volatile_friction"
        assert result["trend_direction"] == "volatile"

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_insufficient_temporal_data(self, mock_eval, mock_br, mock_et):
        """Insufficient temporal data → temporal_status='insufficient_temporal_data'."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="low", pain_clarity="low",
            diagnostic_state="insufficient_evidence",
            allow_specific_pain_output=False,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "low", "pain_clarity": "low",
            "diagnosis_status": "insufficient_evidence",
            "business_read_summary": "No evidence.", "next_best_step": "Run collection.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "low", "confidence": "low", "is_strong_enough": False,
        }

        temporal = _make_temporal(state=TemporalDiagnosticState.INSUFFICIENT)
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=[], score=None, hypothesis=None,
            temporal_diagnostic=temporal, db=make_mock_db(),
        )

        assert result["temporal_status"] == "insufficient_temporal_data"
        assert result["trend_direction"] is None


# ── Top accelerating/declining pain from delta ──────────────────────────

class TestTopAcceleratingDeclining:

    def test_top_accelerating_from_delta(self):
        """Top accelerating pain extracted from score delta categories."""
        engine = FinalVerdictEngine()
        categories = [
            CategoryDelta(
                category="scaling_strain",
                current_normalized=0.5, previous_normalized=0.2,
                delta=0.3, trend=TrendDirection.DECLINING,
                magnitude=Magnitude.STRONG, evidence="Scaling increased",
            ),
            CategoryDelta(
                category="reporting_fragmentation",
                current_normalized=0.15, previous_normalized=0.1,
                delta=0.05, trend=TrendDirection.DECLINING,
                magnitude=Magnitude.MILD, evidence="Reporting increased",
            ),
        ]
        delta = _make_delta(delta_val=0.35, trend=TrendDirection.DECLINING, categories=categories)

        temporal = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            top_cat=TopChangingCategory(
                category="scaling_strain", delta=0.3,
                trend="declining", velocity=1.5, evidence_strength=EvidenceStrength.STRONG,
            ),
        )
        enrichment = engine._enrich_temporal(temporal_diagnostic=temporal, score_delta=delta, velocity=None)

        assert enrichment["top_accelerating_pain"] is not None
        assert enrichment["top_accelerating_pain"]["category"] == "scaling_strain"
        assert enrichment["top_accelerating_pain"]["delta"] == pytest.approx(0.3, abs=0.01)

    def test_top_declining_from_delta(self):
        """Top declining pain extracted when all deltas are negative."""
        engine = FinalVerdictEngine()
        categories = [
            CategoryDelta(
                category="scaling_strain",
                current_normalized=0.1, previous_normalized=0.4,
                delta=-0.3, trend=TrendDirection.IMPROVING,
                magnitude=Magnitude.STRONG, evidence="Scaling decreased",
            ),
        ]
        delta = _make_delta(delta_val=-0.3, trend=TrendDirection.IMPROVING, categories=categories)

        temporal = _make_temporal(
            state=TemporalDiagnosticState.DECLINING_PAIN,
            top_cat=TopChangingCategory(
                category="scaling_strain", delta=-0.3,
                trend="improving", velocity=0.5, evidence_strength=EvidenceStrength.STRONG,
            ),
        )
        enrichment = engine._enrich_temporal(temporal_diagnostic=temporal, score_delta=delta, velocity=None)

        assert enrichment["top_declining_pain"] is not None
        assert enrichment["top_declining_pain"]["category"] == "scaling_strain"

    def test_no_accelerating_when_all_stable(self):
        """No top_accelerating_pain when all deltas are zero."""
        engine = FinalVerdictEngine()
        delta = _make_delta(delta_val=0.0, trend=TrendDirection.STABLE)
        temporal = _make_temporal(state=TemporalDiagnosticState.STABLE_LOW)
        enrichment = engine._enrich_temporal(temporal_diagnostic=temporal, score_delta=delta, velocity=None)

        assert enrichment["top_accelerating_pain"] is None
        assert enrichment["top_declining_pain"] is None


# ── Confidence-based wording ─────────────────────────────────────────────

class TestConfidenceBasedWording:

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_low_confidence_does_not_override_wording(self, mock_eval, mock_br, mock_et):
        """Temporal confidence=low should not change static verdict wording."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high", pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high", "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high", "confidence": "high", "is_strong_enough": True,
        }

        temporal = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.LOW,
        )
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=make_signals([("scaling_language_detected", None)]),
            score=make_friction_score(), hypothesis=None, temporal_diagnostic=temporal,
            db=make_mock_db(),
        )

        # Low confidence → wording NOT overridden
        assert result["verdict_type"] == "final"
        assert result["temporal_status"] == "accelerating_pain"
        # what_we_know should be the ORIGINAL static wording, not temporal
        assert "enough evidence" in result["what_we_know"]

    @patch("app.services.final_verdict_engine.evidence_threshold_engine")
    @patch("app.services.final_verdict_engine.business_read_engine")
    @patch("app.services.final_verdict_engine.company_evaluation_engine")
    def test_high_confidence_enhances_wording(self, mock_eval, mock_br, mock_et):
        """Temporal confidence=high should enhance verdict wording."""
        mock_eval.evaluate.return_value = _make_verdict_inputs(
            hiring_pressure="high", pain_clarity="high",
            diagnostic_state="specific_pain_identified",
            allow_specific_pain_output=True,
        )
        mock_br.compute_reading.return_value = {
            "hiring_pressure": "high", "pain_clarity": "high",
            "diagnosis_status": "specific_pain_identified",
            "business_read_summary": "Strong signals.",
            "next_best_step": "Position now.", "metadata": {},
        }
        mock_et.evaluate_evidence.return_value = {
            "evidence_quality": "high", "confidence": "high", "is_strong_enough": True,
        }

        temporal = _make_temporal(
            state=TemporalDiagnosticState.ACCELERATING_PAIN,
            confidence=TemporalConfidence.HIGH,
            top_cat=TopChangingCategory(
                category="reporting_fragmentation", delta=0.3,
                trend="declining", velocity=1.5, evidence_strength=EvidenceStrength.STRONG,
            ),
        )
        engine = FinalVerdictEngine()
        result = engine.generate(
            company=make_company(), signals=make_signals([("analytics_role_detected", None)]),
            score=make_friction_score(), hypothesis=None, temporal_diagnostic=temporal,
            db=make_mock_db(),
        )

        # High confidence → wording enhanced
        assert "accelerating" in result["what_we_know"].lower() or "Reporting" in result["what_we_know"]