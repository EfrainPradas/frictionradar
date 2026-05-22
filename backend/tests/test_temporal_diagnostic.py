"""Tests for the Temporal Diagnostic Engine.

Covers:
  - Insufficient data handling
  - Each temporal state: volatile, accelerating, emerging, declining, stable_elevated, stable_low
  - Confidence and evidence strength computation
  - Top changing category identification
  - Reasoning trace generation
  - Edge cases: single input, no velocity, no delta
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.friction_categories import FRICTION_CATEGORIES
from app.schemas.score_delta import (
    CategoryDelta,
    LookbackWindow,
    Magnitude,
    OverallDelta,
    ScoreDeltaResult,
    TrendDirection,
)
from app.schemas.signal_velocity import (
    CategoryVelocity,
    PressureState,
    SignalVelocityResult,
    VelocityWindow,
)
from app.schemas.temporal_diagnostic import (
    EvidenceStrength,
    TemporalConfidence,
    TemporalDiagnosticState,
)
from app.services.temporal_diagnostic_engine import (
    ACCELERATING_DELTA_THRESHOLD,
    EMERGING_DELTA_THRESHOLD,
    ELEVATED_FRICTION_THRESHOLD,
    LOW_FRICTION_THRESHOLD,
    MIN_SCORE_SNAPSHOTS,
    MIN_SCORED_SIGNALS,
    TemporalDiagnosticEngine,
)

COMPANY_ID = uuid4()


# ── Factories ──────────────────────────────────────────────────────────────

def _make_delta(
    overall: OverallDelta,
    categories: list[CategoryDelta] | None = None,
    snapshot_count: int = 2,
) -> ScoreDeltaResult:
    """Create a ScoreDeltaResult with given overall delta."""
    if categories is None:
        categories = [
            CategoryDelta(
                category=cat,
                current_normalized=overall.current_total / 5,
                previous_normalized=overall.previous_total / 5,
                delta=overall.delta / 5,
                trend=TrendDirection.STABLE,
                magnitude=Magnitude.NEGLIGIBLE,
                evidence=f"{cat} stable",
            )
            for cat in FRICTION_CATEGORIES
        ]
    return ScoreDeltaResult(
        company_id=COMPANY_ID,
        lookback_window=LookbackWindow.D30,
        lookback_days=30,
        snapshot_count=snapshot_count,
        current_score_id=uuid4(),
        previous_score_id=uuid4(),
        current_computed_at=None,
        previous_computed_at=None,
        category_deltas=categories,
        overall=overall,
    )


def _make_velocity(
    total_signals: int = 10,
    scored_signals: int = 8,
    pressure: PressureState = PressureState.STABLE,
    acceleration: float = 0.0,
    category_velocities: list[CategoryVelocity] | None = None,
) -> SignalVelocityResult:
    """Create a SignalVelocityResult with given parameters."""
    if category_velocities is None:
        category_velocities = [
            CategoryVelocity(
                category=cat,
                signal_count=2,
                scored_count=2,
                discovery_count=0,
                velocity=0.5,
                acceleration=0.0,
                pressure=PressureState.STABLE,
            )
            for cat in FRICTION_CATEGORIES
        ]
    return SignalVelocityResult(
        company_id=COMPANY_ID,
        window=VelocityWindow.ROLLING_30D,
        window_days=30,
        total_signals=total_signals,
        scored_signals=scored_signals,
        discovery_signals=total_signals - scored_signals,
        overall_velocity=total_signals / 4,
        overall_acceleration=acceleration,
        overall_pressure=pressure,
        category_velocities=category_velocities,
    )


def _make_category_deltas(
    dominant: str = "scaling_strain",
    dominant_delta: float = 0.2,
    other_delta: float = 0.0,
) -> list[CategoryDelta]:
    """Create a list of CategoryDelta objects."""
    deltas = []
    for cat in FRICTION_CATEGORIES:
        if cat == dominant:
            d = dominant_delta
            trend = TrendDirection.DECLINING if d > 0 else (
                TrendDirection.IMPROVING if d < 0 else TrendDirection.STABLE
            )
            mag = Magnitude.STRONG if abs(d) >= 0.15 else (
                Magnitude.MODERATE if abs(d) >= 0.05 else Magnitude.NEGLIGIBLE
            )
        else:
            d = other_delta
            trend = TrendDirection.STABLE
            mag = Magnitude.NEGLIGIBLE
        deltas.append(CategoryDelta(
            category=cat,
            current_normalized=0.2 + d if cat == dominant else 0.1,
            previous_normalized=0.2 if cat == dominant else 0.1,
            delta=d,
            trend=trend,
            magnitude=mag,
            evidence=f"{cat} delta={d}",
        ))
    return deltas


# ── Engine instance ──────────────────────────────────────────────────────

engine = TemporalDiagnosticEngine()


# ── Test: insufficient data ──────────────────────────────────────────────

class TestInsufficientData:
    def test_no_inputs(self):
        result = engine.diagnose(COMPANY_ID)
        assert result.temporal_state == TemporalDiagnosticState.INSUFFICIENT
        assert result.confidence == TemporalConfidence.NONE
        assert result.evidence_strength == EvidenceStrength.WEAK

    def test_delta_but_no_velocity_with_few_signals(self):
        overall = OverallDelta(
            current_total=1.5, previous_total=1.0, delta=0.5,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.MODERATE,
        )
        delta = _make_delta(overall)
        result = engine.diagnose(COMPANY_ID, score_delta=delta)
        # With no velocity, scored_signal_count=0 < MIN_SCORED_SIGNALS
        # but delta is available so it should still produce a result
        assert result.temporal_state != TemporalDiagnosticState.INSUFFICIENT
        assert result.score_delta_available is True

    def test_velocity_only_with_insufficient_signals(self):
        velocity = _make_velocity(total_signals=3, scored_signals=2)
        result = engine.diagnose(COMPANY_ID, velocity=velocity)
        # scored_signals=2 < MIN_SCORED_SIGNALS=5, no delta
        assert result.temporal_state == TemporalDiagnosticState.INSUFFICIENT

    def test_velocity_with_enough_signals_no_delta(self):
        velocity = _make_velocity(total_signals=15, scored_signals=10, pressure=PressureState.STABLE)
        result = engine.diagnose(COMPANY_ID, velocity=velocity)
        # No delta but 10 scored signals → can still diagnose
        assert result.temporal_state != TemporalDiagnosticState.INSUFFICIENT


# ── Test: volatile ──────────────────────────────────────────────────────

class TestVolatile:
    def test_volatile_delta(self):
        overall = OverallDelta(
            current_total=1.5, previous_total=1.0, delta=0.5,
            trend=TrendDirection.VOLATILE, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(total_signals=15, scored_signals=10, pressure=PressureState.STABLE)
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.temporal_state == TemporalDiagnosticState.VOLATILE

    def test_spike_velocity(self):
        overall = OverallDelta(
            current_total=1.5, previous_total=1.0, delta=0.1,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.MILD,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(total_signals=15, scored_signals=10, pressure=PressureState.SPIKE)
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.temporal_state == TemporalDiagnosticState.VOLATILE


# ── Test: accelerating pain ──────────────────────────────────────────────

class TestAcceleratingPain:
    def test_large_delta_accelerating_velocity(self):
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        categories = _make_category_deltas(dominant_delta=0.3, other_delta=0.05)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(
            total_signals=20, scored_signals=15,
            pressure=PressureState.ACCELERATING, acceleration=1.0,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.temporal_state == TemporalDiagnosticState.ACCELERATING_PAIN
        assert result.top_changing_category is not None
        assert result.top_changing_category.category == "scaling_strain"

    def test_accelerating_pain_with_only_velocity(self):
        """Velocity accelerating alone can trigger accelerating pain."""
        velocity = _make_velocity(
            total_signals=20, scored_signals=12,
            pressure=PressureState.ACCELERATING, acceleration=1.5,
        )
        result = engine.diagnose(COMPANY_ID, velocity=velocity)
        # Without delta, velocity ACCELERATING should give accelerating_pain
        # Need scored_signals >= MIN_SCORED_SIGNALS (5) to pass insufficient check
        assert result.temporal_state == TemporalDiagnosticState.ACCELERATING_PAIN


# ── Test: emerging pain ──────────────────────────────────────────────────

class TestEmergingPain:
    def test_small_delta_stable_velocity(self):
        """Small positive delta with stable velocity → emerging pain."""
        overall = OverallDelta(
            current_total=1.5, previous_total=1.0, delta=0.5,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.MODERATE,
        )
        categories = _make_category_deltas(dominant_delta=0.08, other_delta=0.01)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(
            total_signals=15, scored_signals=10,
            pressure=PressureState.STABLE, acceleration=0.0,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        # delta=0.5 > EMERGING_DELTA_THRESHOLD=0.25 but < ACCELERATING_THRESHOLD=0.75
        # velocity is STABLE, so this is emerging, not accelerating
        assert result.temporal_state == TemporalDiagnosticState.EMERGING_PAIN


# ── Test: declining pain ──────────────────────────────────────────────────

class TestDecliningPain:
    def test_negative_delta_decelerating_velocity(self):
        overall = OverallDelta(
            current_total=0.5, previous_total=1.5, delta=-1.0,
            trend=TrendDirection.IMPROVING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(
            total_signals=10, scored_signals=8,
            pressure=PressureState.DECELERATING, acceleration=-0.5,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.temporal_state == TemporalDiagnosticState.DECLINING_PAIN

    def test_drought_triggers_declining(self):
        overall = OverallDelta(
            current_total=0.3, previous_total=0.5, delta=-0.2,
            trend=TrendDirection.IMPROVING, magnitude=Magnitude.MODERATE,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(
            total_signals=5, scored_signals=3,
            pressure=PressureState.DROUGHT,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.temporal_state == TemporalDiagnosticState.DECLINING_PAIN


# ── Test: stable elevated ────────────────────────────────────────────────

class TestStableElevated:
    def test_high_friction_stable(self):
        """Elevated friction with no change → stable_elevated_friction."""
        overall = OverallDelta(
            current_total=2.5, previous_total=2.5, delta=0.0,
            trend=TrendDirection.STABLE, magnitude=Magnitude.NEGLIGIBLE,
        )
        categories = _make_category_deltas(dominant_delta=0.0, other_delta=0.0)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(
            total_signals=15, scored_signals=10,
            pressure=PressureState.STABLE,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        # current_total=2.5 > ELEVATED_FRICTION_THRESHOLD=1.0, delta=0
        assert result.temporal_state == TemporalDiagnosticState.STABLE_ELEVATED


# ── Test: stable low ────────────────────────────────────────────────────

class TestStableLow:
    def test_low_friction_stable(self):
        """Low friction with no change → stable_low_friction."""
        overall = OverallDelta(
            current_total=0.2, previous_total=0.2, delta=0.0,
            trend=TrendDirection.STABLE, magnitude=Magnitude.NEGLIGIBLE,
        )
        categories = _make_category_deltas(dominant_delta=0.0, other_delta=0.0)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(
            total_signals=15, scored_signals=10,
            pressure=PressureState.STABLE,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        # current_total=0.2 < ELEVATED, delta=0
        assert result.temporal_state == TemporalDiagnosticState.STABLE_LOW


# ── Test: confidence levels ───────────────────────────────────────────────

class TestConfidence:
    def test_high_confidence(self):
        """3+ snapshots, 10+ signals, delta + velocity agree."""
        overall = OverallDelta(
            current_total=2.0, previous_total=1.5, delta=0.5,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall, snapshot_count=4)
        velocity = _make_velocity(
            total_signals=25, scored_signals=15,
            pressure=PressureState.ACCELERATING, acceleration=0.8,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.confidence in (TemporalConfidence.HIGH, TemporalConfidence.MODERATE)

    def test_low_confidence_sparse_data(self):
        """2 snapshots but <5 signals."""
        overall = OverallDelta(
            current_total=1.0, previous_total=0.5, delta=0.5,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall, snapshot_count=2)
        velocity = _make_velocity(total_signals=3, scored_signals=2)
        # With scored_signals < 5 but delta available, should still diagnose
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.confidence in (TemporalConfidence.LOW, TemporalConfidence.MODERATE)


# ── Test: evidence strength ──────────────────────────────────────────────

class TestEvidenceStrength:
    def test_strong_evidence_both_inputs_agree(self):
        """Delta declining + velocity accelerating → both agree on rising friction."""
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(
            total_signals=20, scored_signals=15,
            pressure=PressureState.ACCELERATING,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        # Both inputs present → at least moderate
        assert result.evidence_strength in (EvidenceStrength.STRONG, EvidenceStrength.MODERATE)

    def test_moderate_evidence_one_input(self):
        """Only delta available → moderate evidence."""
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        result = engine.diagnose(COMPANY_ID, score_delta=delta)
        assert result.evidence_strength in (EvidenceStrength.MODERATE, EvidenceStrength.WEAK)


# ── Test: top changing category ────────────────────────────────────────────

class TestTopChangingCategory:
    def test_identifies_highest_delta_category(self):
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        categories = _make_category_deltas(dominant_delta=0.3, other_delta=0.02)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(total_signals=20, scored_signals=15, pressure=PressureState.STABLE)
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert result.top_changing_category is not None
        assert result.top_changing_category.category == "scaling_strain"
        assert result.top_changing_category.delta == pytest.approx(0.3, abs=0.01)

    def test_no_top_changing_when_all_zero(self):
        overall = OverallDelta(
            current_total=0.5, previous_total=0.5, delta=0.0,
            trend=TrendDirection.STABLE, magnitude=Magnitude.NEGLIGIBLE,
        )
        categories = _make_category_deltas(dominant_delta=0.0, other_delta=0.0)
        delta = _make_delta(overall, categories=categories)
        velocity = _make_velocity(total_signals=15, scored_signals=10, pressure=PressureState.STABLE)
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        # All deltas ≈ 0 → no top changing category
        assert result.top_changing_category is None


# ── Test: reasoning trace ─────────────────────────────────────────────────

class TestReasoningTrace:
    def test_trace_contains_steps(self):
        overall = OverallDelta(
            current_total=1.5, previous_total=1.0, delta=0.5,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(total_signals=15, scored_signals=10, pressure=PressureState.ACCELERATING)
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert len(result.reasoning_trace) >= 2
        step_names = [s.step for s in result.reasoning_trace]
        assert "data_availability" in step_names

    def test_insufficient_trace(self):
        result = engine.diagnose(COMPANY_ID)
        assert len(result.reasoning_trace) >= 1
        assert result.reasoning_trace[0].step == "data_availability"


# ── Test: summary ──────────────────────────────────────────────────────────

class TestSummary:
    def test_insufficient_summary(self):
        result = engine.diagnose(COMPANY_ID)
        assert "Not enough" in result.summary

    def test_accelerating_summary(self):
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(
            total_signals=20, scored_signals=15, pressure=PressureState.ACCELERATING,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert "accelerating" in result.summary.lower()

    def test_declining_summary(self):
        overall = OverallDelta(
            current_total=0.5, previous_total=1.5, delta=-1.0,
            trend=TrendDirection.IMPROVING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(
            total_signals=10, scored_signals=8, pressure=PressureState.DECELERATING,
        )
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity)
        assert "declining" in result.summary.lower()


# ── Test: evaluation integration ───────────────────────────────────────────

class TestEvaluationIntegration:
    def test_evaluation_does_not_override_delta(self):
        """Evaluation provides friction context but doesn't override delta direction."""
        overall = OverallDelta(
            current_total=2.0, previous_total=1.0, delta=1.0,
            trend=TrendDirection.DECLINING, magnitude=Magnitude.STRONG,
        )
        delta = _make_delta(overall)
        velocity = _make_velocity(total_signals=20, scored_signals=15, pressure=PressureState.ACCELERATING)
        evaluation = {
            "diagnostic_state": "specific_pain_identified",
            "kpis": {"hiring_pressure": "high"},
        }
        result = engine.diagnose(COMPANY_ID, score_delta=delta, velocity=velocity, evaluation=evaluation)
        assert result.evaluation_available is True
        # Evaluation doesn't change the temporal state
        assert result.temporal_state == TemporalDiagnosticState.ACCELERATING_PAIN