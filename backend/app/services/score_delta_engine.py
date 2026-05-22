"""Score History Delta Engine — computes normalized score deltas over time.

Reads FrictionScore history for a company, compares consecutive snapshots,
and produces per-category + overall trend analysis.

Uses v2.0.0 normalized_score fields exclusively (never raw_score).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.friction_categories import FRICTION_CATEGORIES
from app.models.friction_score import FrictionScore
from app.schemas.score_delta import (
    CategoryDelta,
    LookbackWindow,
    Magnitude,
    OverallDelta,
    ScoreDeltaResult,
    TrendDirection,
)

# ── Constants ────────────────────────────────────────────────────────────

LOOKBACK_DAYS: dict[LookbackWindow, int] = {
    LookbackWindow.D7: 7,
    LookbackWindow.D30: 30,
    LookbackWindow.D90: 90,
    LookbackWindow.D180: 180,
}

# Minimum snapshots required to produce a delta (need at least 2).
MIN_SNAPSHOTS = 2

# Thresholds for magnitude classification (absolute delta on 0-1 scale).
MAGNITUDE_THRESHOLDS = {
    Magnitude.NEGLIGIBLE: 0.02,  # < 2% change
    Magnitude.MILD: 0.05,        # 2-5% change
    Magnitude.MODERATE: 0.15,    # 5-15% change
    # anything >= 0.15 is STRONG
}

# Trend classification thresholds.
STABLE_THRESHOLD = 0.02   # |delta| <= 2% → stable
VOLATILE_THRESHOLD = 2     # direction flips >= 2 times → volatile

# Overall score: sum of per-category normalized scores.
# Since there are 5 categories each 0-1, overall is 0-5.
OVERALL_MAGNITUDE_THRESHOLDS = {
    Magnitude.NEGLIGIBLE: 0.10,
    Magnitude.MILD: 0.25,
    Magnitude.MODERATE: 0.75,
}


# ── Helpers ──────────────────────────────────────────────────────────────

def _classify_magnitude(abs_delta: float, thresholds: dict | None = None) -> Magnitude:
    """Classify the absolute magnitude of a per-category delta (0-1 scale)."""
    limits = thresholds or MAGNITUDE_THRESHOLDS
    if abs_delta < limits[Magnitude.NEGLIGIBLE]:
        return Magnitude.NEGLIGIBLE
    if abs_delta < limits[Magnitude.MILD]:
        return Magnitude.MILD
    if abs_delta < limits[Magnitude.MODERATE]:
        return Magnitude.MODERATE
    return Magnitude.STRONG


def _classify_trend(deltas: list[float], current: float, previous: float) -> TrendDirection:
    """Classify trend direction from a series of per-category deltas.

    Uses consecutive normalized_score values to detect:
    - improving: friction decreasing (delta < 0)
    - declining: friction increasing (delta > 0)
    - stable: change within threshold
    - volatile: direction flips >= 2 times
    """
    if len(deltas) < 1:
        abs_change = abs(current - previous)
        if abs_change <= STABLE_THRESHOLD:
            return TrendDirection.STABLE
        return TrendDirection.IMPROVING if current < previous else TrendDirection.DECLINING

    # Count direction flips across consecutive deltas.
    flips = 0
    for i in range(1, len(deltas)):
        if (deltas[i] > 0) != (deltas[i - 1] > 0):
            flips += 1

    if flips >= VOLATILE_THRESHOLD:
        return TrendDirection.VOLATILE

    # No meaningful flips — classify by net direction.
    abs_change = abs(current - previous)
    if abs_change <= STABLE_THRESHOLD:
        return TrendDirection.STABLE
    return TrendDirection.IMPROVING if current < previous else TrendDirection.DECLINING


def _extract_normalized(breakdown_json: dict) -> dict[str, float]:
    """Extract per-category normalized_score from v2.0.0 breakdown JSON."""
    categories = breakdown_json.get("categories", {})
    return {
        cat: categories[cat].get("normalized_score", 0.0)
        for cat in FRICTION_CATEGORIES
        if cat in categories
    }


def _extract_matched_signals(breakdown_json: dict, category: str) -> list[str]:
    """Extract matched signal labels for a category from v2.0.0 breakdown."""
    categories = breakdown_json.get("categories", {})
    cat_data = categories.get(category, {})
    return cat_data.get("matched_signals", [])


def _build_evidence(
    category: str,
    current_signals: list[str],
    previous_signals: list[str],
    delta: float,
) -> str:
    """Build a human-readable evidence summary for a category delta."""
    gained = sorted(set(current_signals) - set(previous_signals))
    lost = sorted(set(previous_signals) - set(current_signals))
    kept = sorted(set(current_signals) & set(previous_signals))

    parts: list[str] = []

    if delta > STABLE_THRESHOLD:
        parts.append(f"{category.replace('_', ' ').title()} increased")
    elif delta < -STABLE_THRESHOLD:
        parts.append(f"{category.replace('_', ' ').title()} decreased")
    else:
        parts.append(f"{category.replace('_', ' ').title()} unchanged")

    if gained:
        parts.append(f"new signals: {', '.join(gained)}")
    if lost:
        parts.append(f"lost signals: {', '.join(lost)}")
    if kept and len(kept) <= 5:
        parts.append(f"persistent: {', '.join(kept)}")

    return "; ".join(parts)


# ── Engine ────────────────────────────────────────────────────────────────

class ScoreDeltaEngine:
    """Computes normalized score deltas between FrictionScore snapshots."""

    def compute_delta(
        self,
        db: Session,
        company_id: UUID,
        lookback: LookbackWindow = LookbackWindow.D30,
    ) -> ScoreDeltaResult:
        """Compute score delta for a company over the specified lookback window.

        Returns a ScoreDeltaResult with per-category deltas, overall delta,
        trend directions, magnitudes, and evidence summaries.
        """
        days = LOOKBACK_DAYS[lookback]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Fetch scores within window, ordered by computed_at ascending.
        scores = self._fetch_scores(db, company_id, cutoff)

        result = ScoreDeltaResult(
            company_id=company_id,
            lookback_window=lookback,
            lookback_days=days,
            snapshot_count=len(scores),
        )

        if len(scores) < MIN_SNAPSHOTS:
            result.overall = None
            return result

        # Use the latest and second-to-latest scores.
        current = scores[-1]
        previous = scores[-2]

        result.current_score_id = current.id
        result.previous_score_id = previous.id
        result.current_computed_at = current.computed_at
        result.previous_computed_at = previous.computed_at

        current_norms = _extract_normalized(current.scoring_breakdown_json)
        previous_norms = _extract_normalized(previous.scoring_breakdown_json)

        # Compute per-category deltas.
        # For multi-snapshot trend detection, collect intermediate deltas.
        category_deltas: list[CategoryDelta] = []
        intermediate_deltas: dict[str, list[float]] = {cat: [] for cat in FRICTION_CATEGORIES}

        # Build intermediate deltas if we have > 2 snapshots.
        if len(scores) > 2:
            for i in range(1, len(scores)):
                prev_n = _extract_normalized(scores[i - 1].scoring_breakdown_json)
                curr_n = _extract_normalized(scores[i].scoring_breakdown_json)
                for cat in FRICTION_CATEGORIES:
                    intermediate_deltas[cat].append(
                        curr_n.get(cat, 0.0) - prev_n.get(cat, 0.0)
                    )

        for cat in FRICTION_CATEGORIES:
            curr_val = current_norms.get(cat, 0.0)
            prev_val = previous_norms.get(cat, 0.0)
            delta = round(curr_val - prev_val, 4)

            trend = _classify_trend(
                intermediate_deltas.get(cat, []),
                curr_val,
                prev_val,
            )
            magnitude = _classify_magnitude(abs(delta))

            curr_signals = _extract_matched_signals(current.scoring_breakdown_json, cat)
            prev_signals = _extract_matched_signals(previous.scoring_breakdown_json, cat)
            evidence = _build_evidence(cat, curr_signals, prev_signals, delta)

            category_deltas.append(CategoryDelta(
                category=cat,
                current_normalized=round(curr_val, 4),
                previous_normalized=round(prev_val, 4),
                delta=delta,
                trend=trend,
                magnitude=magnitude,
                evidence=evidence,
            ))

        result.category_deltas = category_deltas

        # Overall delta.
        current_total = sum(current_norms.get(c, 0.0) for c in FRICTION_CATEGORIES)
        previous_total = sum(previous_norms.get(c, 0.0) for c in FRICTION_CATEGORIES)
        overall_delta = round(current_total - previous_total, 4)

        # Find the category that shifted the most (by absolute delta).
        biggest_shift_cat: Optional[str] = None
        biggest_shift = 0.0
        for cd in category_deltas:
            if abs(cd.delta) > biggest_shift:
                biggest_shift = abs(cd.delta)
                biggest_shift_cat = cd.category

        result.overall = OverallDelta(
            current_total=round(current_total, 4),
            previous_total=round(previous_total, 4),
            delta=overall_delta,
            trend=_classify_trend([], current_total, previous_total),
            magnitude=_classify_magnitude(abs(overall_delta), OVERALL_MAGNITUDE_THRESHOLDS),
            dominant_shift=biggest_shift_cat,
        )

        return result

    def compute_all_windows(
        self,
        db: Session,
        company_id: UUID,
    ) -> dict[LookbackWindow, ScoreDeltaResult]:
        """Compute deltas for all standard lookback windows."""
        return {
            window: self.compute_delta(db, company_id, window)
            for window in LookbackWindow
        }

    def _fetch_scores(
        self,
        db: Session,
        company_id: UUID,
        cutoff: datetime,
    ) -> list[FrictionScore]:
        """Fetch FrictionScore rows for a company within a time window."""
        stmt = (
            select(FrictionScore)
            .where(
                FrictionScore.company_id == company_id,
                FrictionScore.computed_at >= cutoff,
            )
            .order_by(FrictionScore.computed_at.asc())
        )
        return list(db.execute(stmt).scalars().all())


# ── Singleton ─────────────────────────────────────────────────────────────

score_delta_engine = ScoreDeltaEngine()