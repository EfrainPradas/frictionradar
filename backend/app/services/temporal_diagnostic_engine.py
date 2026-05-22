"""Temporal Diagnostic Engine — combines score deltas, signal velocity,
and company evaluation to determine how friction is changing over time.

Decision rules:
  1. insufficient_temporal_data  — fewer than 2 score snapshots or <5 scored signals
  2. volatile_friction            — score delta shows volatile trend OR velocity shows signal_spike
  3. accelerating_pain            — friction increasing (delta > 0) AND velocity accelerating/spike
  4. emerging_pain                — friction increasing (delta > threshold) but signal pressure stable
  5. declining_pain               — friction decreasing (delta < 0) with signal deceleration/drought
  6. stable_elevated_friction      — friction > threshold but stable, no acceleration
  7. stable_low_friction           — friction low and stable

Confidence:
  - HIGH: 3+ score snapshots, 10+ scored signals, consistent direction across delta + velocity
  - MODERATE: 2 score snapshots, 5+ scored signals
  - LOW: 2 score snapshots, <5 scored signals
  - NONE: insufficient temporal data

Evidence strength:
  - STRONG: both delta and velocity agree on direction
  - MODERATE: only one input supports the direction
  - WEAK: direction inferred from limited data
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

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
    ReasoningStep,
    TemporalConfidence,
    TemporalDiagnosticResult,
    TemporalDiagnosticState,
    TopChangingCategory,
)

# ── Constants ────────────────────────────────────────────────────────────

# Minimum data thresholds.
MIN_SCORE_SNAPSHOTS = 2
MIN_SCORED_SIGNALS = 5
MIN_SCORED_SIGNALS_HIGH_CONF = 10
MIN_SCORE_SNAPSHOTS_HIGH_CONF = 3

# Friction level thresholds (on 0-5 scale — sum of 5 normalized categories).
ELEVATED_FRICTION_THRESHOLD = 1.0  # total normalized > 1.0 = elevated
LOW_FRICTION_THRESHOLD = 0.3      # total normalized < 0.3 = low

# Delta thresholds for "emerging" vs "accelerating".
# These are on the 0-5 scale (sum of 5 normalized categories).
EMERGING_DELTA_THRESHOLD = 0.25   # ~5% per-category average increase
ACCELERATING_DELTA_THRESHOLD = 0.75  # ~15% per-category average increase


class TemporalDiagnosticEngine:
    """Determines how a company's friction state is changing over time."""

    def diagnose(
        self,
        company_id: UUID,
        score_delta: Optional[ScoreDeltaResult] = None,
        velocity: Optional[SignalVelocityResult] = None,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> TemporalDiagnosticResult:
        """Produce a temporal diagnostic from available inputs.

        All inputs are optional — the engine degrades gracefully when data
        is missing. It never declares a trend from a single data point.
        """
        trace: List[ReasoningStep] = []

        # ── Step 0: Data availability ───────────────────────────────
        delta_available = score_delta is not None and score_delta.overall is not None
        velocity_available = velocity is not None and velocity.total_signals > 0
        evaluation_available = evaluation is not None

        snapshot_count = score_delta.snapshot_count if score_delta else 0
        signal_count = velocity.total_signals if velocity else 0
        scored_signal_count = velocity.scored_signals if velocity else 0

        trace.append(ReasoningStep(
            step="data_availability",
            condition=f"snapshots={snapshot_count}, signals={scored_signal_count}",
            result=f"delta={'yes' if delta_available else 'no'}, velocity={'yes' if velocity_available else 'no'}, eval={'yes' if evaluation_available else 'no'}",
        ))

        # ── Step 1: Insufficient data check ──────────────────────────
        if not delta_available and scored_signal_count < MIN_SCORED_SIGNALS:
            trace.append(ReasoningStep(
                step="insufficient_data",
                condition=f"snapshots={snapshot_count} < {MIN_SCORE_SNAPSHOTS} OR scored_signals={scored_signal_count} < {MIN_SCORED_SIGNALS}",
                result="insufficient_temporal_data",
            ))
            return self._build_result(
                company_id=company_id,
                state=TemporalDiagnosticState.INSUFFICIENT,
                confidence=TemporalConfidence.NONE,
                evidence_strength=EvidenceStrength.WEAK,
                trace=trace,
                delta_available=delta_available,
                velocity_available=velocity_available,
                evaluation_available=evaluation_available,
                snapshot_count=snapshot_count,
                signal_count=signal_count,
                scored_signal_count=scored_signal_count,
            )

        # ── Step 2: Extract key metrics ─────────────────────────────
        overall_delta: Optional[OverallDelta] = score_delta.overall if score_delta else None
        category_deltas: List[CategoryDelta] = score_delta.category_deltas if score_delta else []
        category_velocities: List[CategoryVelocity] = velocity.category_velocities if velocity else []

        delta_trend = overall_delta.trend if overall_delta else None
        delta_magnitude = abs(overall_delta.delta) if overall_delta else 0.0
        velocity_pressure = velocity.overall_pressure if velocity else PressureState.INSUFFICIENT

        # Current friction level from evaluation or delta.
        current_friction = self._current_friction_level(overall_delta, evaluation)
        trace.append(ReasoningStep(
            step="friction_level",
            condition=f"current_total={current_friction:.2f}",
            result=f"{'elevated' if current_friction >= ELEVATED_FRICTION_THRESHOLD else 'low' if current_friction < LOW_FRICTION_THRESHOLD else 'moderate'}",
        ))

        # ── Step 3: Volatile check ──────────────────────────────────
        if delta_trend == TrendDirection.VOLATILE or velocity_pressure == PressureState.SPIKE:
            reason = "volatile_delta" if delta_trend == TrendDirection.VOLATILE else "signal_spike"
            trace.append(ReasoningStep(
                step="volatile_check",
                condition=f"delta_trend={delta_trend}, velocity_pressure={velocity_pressure}",
                result=f"volatile_friction ({reason})",
            ))
            state = TemporalDiagnosticState.VOLATILE
            conf, ev_str = self._compute_confidence(
                snapshot_count, scored_signal_count, delta_available, velocity_available,
                delta_trend, velocity_pressure,
            )
            top_cat = self._find_top_changing(category_deltas, category_velocities, ev_str)
            return self._build_result(
                company_id=company_id, state=state, confidence=conf,
                evidence_strength=ev_str, trace=trace,
                delta_available=delta_available, velocity_available=velocity_available,
                evaluation_available=evaluation_available, top_cat=top_cat,
                snapshot_count=snapshot_count, signal_count=signal_count,
                scored_signal_count=scored_signal_count, current_friction=current_friction,
            )

        # ── Step 4: Accelerating pain ───────────────────────────────
        # Friction increasing + signal velocity accelerating or high magnitude.
        friction_increasing = (
            (delta_available and overall_delta.delta > EMERGING_DELTA_THRESHOLD)
            or (not delta_available and velocity_pressure == PressureState.ACCELERATING)
        )
        delta_str = f"{overall_delta.delta:.2f}" if overall_delta else "N/A"
        if friction_increasing:
            # Distinguish accelerating vs emerging based on magnitude and velocity.
            if (
                delta_available and delta_magnitude >= ACCELERATING_DELTA_THRESHOLD
            ) or velocity_pressure == PressureState.ACCELERATING:
                trace.append(ReasoningStep(
                    step="pain_direction",
                    condition=f"delta={delta_str}, velocity_pressure={velocity_pressure}",
                    result="accelerating_pain",
                ))
                state = TemporalDiagnosticState.ACCELERATING_PAIN
            else:
                trace.append(ReasoningStep(
                    step="pain_direction",
                    condition=f"delta={delta_str}, velocity_pressure={velocity_pressure}",
                    result="emerging_pain",
                ))
                state = TemporalDiagnosticState.EMERGING_PAIN

            conf, ev_str = self._compute_confidence(
                snapshot_count, scored_signal_count, delta_available, velocity_available,
                delta_trend, velocity_pressure,
            )
            top_cat = self._find_top_changing(category_deltas, category_velocities, ev_str)
            return self._build_result(
                company_id=company_id, state=state, confidence=conf,
                evidence_strength=ev_str, trace=trace,
                delta_available=delta_available, velocity_available=velocity_available,
                evaluation_available=evaluation_available, top_cat=top_cat,
                snapshot_count=snapshot_count, signal_count=signal_count,
                scored_signal_count=scored_signal_count, current_friction=current_friction,
            )

        # ── Step 5: Declining pain ──────────────────────────────────
        # Friction decreasing + signal deceleration or drought.
        friction_decreasing = (
            (delta_available and overall_delta.delta < -EMERGING_DELTA_THRESHOLD)
            or (velocity_pressure == PressureState.DECELERATING)
        )
        if friction_decreasing:
            trace.append(ReasoningStep(
                step="pain_direction",
                condition=f"delta={delta_str}, velocity_pressure={velocity_pressure}",
                result="declining_pain",
            ))
            state = TemporalDiagnosticState.DECLINING_PAIN
            conf, ev_str = self._compute_confidence(
                snapshot_count, scored_signal_count, delta_available, velocity_available,
                delta_trend, velocity_pressure,
            )
            top_cat = self._find_top_changing(category_deltas, category_velocities, ev_str)
            return self._build_result(
                company_id=company_id, state=state, confidence=conf,
                evidence_strength=ev_str, trace=trace,
                delta_available=delta_available, velocity_available=velocity_available,
                evaluation_available=evaluation_available, top_cat=top_cat,
                snapshot_count=snapshot_count, signal_count=signal_count,
                scored_signal_count=scored_signal_count, current_friction=current_friction,
            )

        # ── Step 6: Drought check ───────────────────────────────────
        if velocity_pressure == PressureState.DROUGHT:
            trace.append(ReasoningStep(
                step="drought_check",
                condition=f"velocity_pressure={velocity_pressure}",
                result="declining_pain (signal drought)",
            ))
            state = TemporalDiagnosticState.DECLINING_PAIN
            conf, ev_str = self._compute_confidence(
                snapshot_count, scored_signal_count, delta_available, velocity_available,
                delta_trend, velocity_pressure,
            )
            top_cat = self._find_top_changing(category_deltas, category_velocities, ev_str)
            return self._build_result(
                company_id=company_id, state=state, confidence=conf,
                evidence_strength=ev_str, trace=trace,
                delta_available=delta_available, velocity_available=velocity_available,
                evaluation_available=evaluation_available, top_cat=top_cat,
                snapshot_count=snapshot_count, signal_count=signal_count,
                scored_signal_count=scored_signal_count, current_friction=current_friction,
            )

        # ── Step 7: Stable states ───────────────────────────────────
        if current_friction >= ELEVATED_FRICTION_THRESHOLD:
            trace.append(ReasoningStep(
                step="stable_check",
                condition=f"friction={current_friction:.2f} >= {ELEVATED_FRICTION_THRESHOLD}",
                result="stable_elevated_friction",
            ))
            state = TemporalDiagnosticState.STABLE_ELEVATED
        else:
            trace.append(ReasoningStep(
                step="stable_check",
                condition=f"friction={current_friction:.2f} < {ELEVATED_FRICTION_THRESHOLD}",
                result="stable_low_friction",
            ))
            state = TemporalDiagnosticState.STABLE_LOW

        conf, ev_str = self._compute_confidence(
            snapshot_count, scored_signal_count, delta_available, velocity_available,
            delta_trend, velocity_pressure,
        )
        top_cat = self._find_top_changing(category_deltas, category_velocities, ev_str)
        return self._build_result(
            company_id=company_id, state=state, confidence=conf,
            evidence_strength=ev_str, trace=trace,
            delta_available=delta_available, velocity_available=velocity_available,
            evaluation_available=evaluation_available, top_cat=top_cat,
            snapshot_count=snapshot_count, signal_count=signal_count,
            scored_signal_count=scored_signal_count, current_friction=current_friction,
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _current_friction_level(
        self,
        overall_delta: Optional[OverallDelta],
        evaluation: Optional[Dict[str, Any]],
    ) -> float:
        """Get current total friction level (0-5 scale)."""
        if overall_delta is not None:
            return overall_delta.current_total
        # Fallback: try to infer from evaluation.
        if evaluation and "kpis" in evaluation:
            # Evaluation doesn't have a direct friction score, so default moderate.
            return 1.5
        return 0.0

    def _compute_confidence(
        self,
        snapshot_count: int,
        scored_signal_count: int,
        delta_available: bool,
        velocity_available: bool,
        delta_trend: Optional[TrendDirection],
        velocity_pressure: PressureState,
    ) -> tuple[TemporalConfidence, EvidenceStrength]:
        """Compute confidence and evidence strength for the diagnosis."""
        # Direction agreement: do delta and velocity point the same way?
        direction_agrees = False
        if delta_available and velocity_available:
            if delta_trend in (TrendDirection.DECLINING, TrendDirection.VOLATILE):
                direction_agrees = velocity_pressure in (
                    PressureState.DECELERATING, PressureState.SPIKE,
                )
            elif delta_trend == TrendDirection.IMPROVING:
                direction_agrees = velocity_pressure in (
                    PressureState.DECELERATING, PressureState.DROUGHT,
                )
            elif delta_trend == TrendDirection.STABLE:
                direction_agrees = velocity_pressure == PressureState.STABLE
            else:
                # No delta trend — check if velocity has direction.
                direction_agrees = velocity_pressure in (
                    PressureState.ACCELERATING, PressureState.DECELERATING,
                    PressureState.STABLE, PressureState.SPIKE, PressureState.DROUGHT,
                )

        inputs_count = sum([delta_available, velocity_available])

        # Confidence.
        if (
            snapshot_count >= MIN_SCORE_SNAPSHOTS_HIGH_CONF
            and scored_signal_count >= MIN_SCORED_SIGNALS_HIGH_CONF
            and inputs_count >= 2
            and direction_agrees
        ):
            conf = TemporalConfidence.HIGH
        elif (
            snapshot_count >= MIN_SCORE_SNAPSHOTS
            and scored_signal_count >= MIN_SCORED_SIGNALS
            and inputs_count >= 1
        ):
            conf = TemporalConfidence.MODERATE
        elif snapshot_count >= MIN_SCORE_SNAPSHOTS or scored_signal_count >= 3:
            conf = TemporalConfidence.LOW
        else:
            conf = TemporalConfidence.NONE

        # Evidence strength.
        if inputs_count >= 2 and direction_agrees:
            ev_str = EvidenceStrength.STRONG
        elif inputs_count >= 2:
            ev_str = EvidenceStrength.MODERATE
        elif inputs_count >= 1:
            ev_str = EvidenceStrength.MODERATE
        else:
            ev_str = EvidenceStrength.WEAK

        return conf, ev_str

    def _find_top_changing(
        self,
        category_deltas: List[CategoryDelta],
        category_velocities: List[CategoryVelocity],
        evidence_strength: EvidenceStrength,
    ) -> Optional[TopChangingCategory]:
        """Find the category with the largest absolute delta change."""
        if not category_deltas:
            return None

        # Sort by absolute delta, descending.
        sorted_deltas = sorted(category_deltas, key=lambda d: abs(d.delta), reverse=True)
        top = sorted_deltas[0]

        # If all deltas are zero, there's no top changing category.
        if abs(top.delta) < 0.001:
            return None

        # Find matching velocity for evidence strength.
        top_velocity = 0.0
        for cv in category_velocities:
            if cv.category == top.category:
                top_velocity = cv.velocity
                break

        return TopChangingCategory(
            category=top.category,
            delta=top.delta,
            trend=top.trend.value if hasattr(top.trend, "value") else str(top.trend),
            velocity=top_velocity,
            evidence_strength=evidence_strength,
        )

    def _build_result(
        self,
        company_id: UUID,
        state: TemporalDiagnosticState,
        confidence: TemporalConfidence,
        evidence_strength: EvidenceStrength,
        trace: List[ReasoningStep],
        delta_available: bool,
        velocity_available: bool,
        evaluation_available: bool,
        snapshot_count: int,
        signal_count: int,
        scored_signal_count: int,
        top_cat: Optional[TopChangingCategory] = None,
        current_friction: float = 0.0,
    ) -> TemporalDiagnosticResult:
        """Build a TemporalDiagnosticResult with a summary string."""
        summary = self._summary(state, confidence, evidence_strength, top_cat, current_friction)
        return TemporalDiagnosticResult(
            company_id=company_id,
            temporal_state=state,
            confidence=confidence,
            evidence_strength=evidence_strength,
            top_changing_category=top_cat,
            reasoning_trace=trace,
            summary=summary,
            score_delta_available=delta_available,
            velocity_available=velocity_available,
            evaluation_available=evaluation_available,
            score_snapshot_count=snapshot_count,
            signal_count=signal_count,
            scored_signal_count=scored_signal_count,
        )

    def _summary(
        self,
        state: TemporalDiagnosticState,
        confidence: TemporalConfidence,
        evidence_strength: EvidenceStrength,
        top_cat: Optional[TopChangingCategory],
        current_friction: float,
    ) -> str:
        """Generate a human-readable summary."""
        if state == TemporalDiagnosticState.INSUFFICIENT:
            return "Not enough temporal data to determine friction direction."
        if state == TemporalDiagnosticState.VOLATILE:
            return "Friction direction is volatile — score changes flip between increasing and decreasing."
        if state == TemporalDiagnosticState.ACCELERATING_PAIN:
            cat = top_cat.category.replace("_", " ").title() if top_cat else "unknown"
            return f"Friction is accelerating, driven by {cat} ({evidence_strength.value} evidence)."
        if state == TemporalDiagnosticState.EMERGING_PAIN:
            cat = top_cat.category.replace("_", " ").title() if top_cat else "unknown"
            return f"Friction is emerging, with {cat} starting to rise ({evidence_strength.value} evidence)."
        if state == TemporalDiagnosticState.DECLINING_PAIN:
            return f"Friction is declining ({evidence_strength.value} evidence)."
        if state == TemporalDiagnosticState.STABLE_ELEVATED:
            return f"Friction is elevated ({current_friction:.1f}/5.0) but stable ({evidence_strength.value} evidence)."
        if state == TemporalDiagnosticState.STABLE_LOW:
            return f"Friction is low ({current_friction:.1f}/5.0) and stable ({evidence_strength.value} evidence)."
        return f"Temporal state: {state.value}"


# ── Singleton ─────────────────────────────────────────────────────────────

temporal_diagnostic_engine = TemporalDiagnosticEngine()