"""Signal Velocity Tracker — measures signal arrival rate over time.

Aggregates CompanySignal records by time window, computes per-category
velocity (signals/period), acceleration (velocity change), and detects
pressure states: accelerating, decelerating, stable, spike, drought.

Separates scored signals (contribute to friction scoring) from discovery
signals (metadata like careers_page_found, company_size_detected).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.core.friction_categories import FRICTION_CATEGORIES
from app.core.scoring_rules import SCORING_RULES, INTENTIONALLY_UNSCORED_SIGNALS
from app.models.company_signal import CompanySignal
from app.schemas.signal_velocity import (
    CategoryVelocity,
    PressureState,
    SignalClass,
    SignalVelocityResult,
    SourceSummary,
    VelocityBucket,
    VelocityWindow,
)

# ── Constants ────────────────────────────────────────────────────────────

WINDOW_DAYS: dict[VelocityWindow, int] = {
    VelocityWindow.DAILY: 1,
    VelocityWindow.WEEKLY: 7,
    VelocityWindow.ROLLING_30D: 30,
    VelocityWindow.ROLLING_90D: 90,
}

# Spike threshold: bucket count > 3× the mean velocity.
SPIKE_MULTIPLIER = 3.0

# Drought threshold: consecutive days with 0 scored signals.
DROUGHT_MIN_DAYS = 7

# Acceleration thresholds.
ACCELERATING_THRESHOLD = 0.5   # velocity increase >= 0.5 signals/period
DECELERATING_THRESHOLD = -0.5  # velocity decrease <= -0.5 signals/period

# Build a set of all scored signal types from SCORING_RULES.
_SCORED_SIGNAL_TYPES: set[str] = set()
for _cat, _rules in SCORING_RULES.items():
    for _rule in _rules:
        for _st in _rule.get("signal_types", []):
            _SCORED_SIGNAL_TYPES.add(_st)

# Concentration signals are also scored (they appear in SCORING_RULES but
# are generated dynamically by hiring_pattern_service).

# Build category → signal_type mapping from SCORING_RULES.
_CATEGORY_SIGNAL_MAP: dict[str, set[str]] = {cat: set() for cat in FRICTION_CATEGORIES}
for _cat, _rules in SCORING_RULES.items():
    for _rule in _rules:
        for _st in _rule.get("signal_types", []):
            _CATEGORY_SIGNAL_MAP[_cat].add(_st)


# ── Helpers ──────────────────────────────────────────────────────────────

def _classify_signal(signal_type: str) -> SignalClass:
    """Classify a signal as scored or discovery."""
    if signal_type in INTENTIONALLY_UNSCORED_SIGNALS:
        return SignalClass.DISCOVERY
    if signal_type in _SCORED_SIGNAL_TYPES:
        return SignalClass.SCORED
    # Concentration signals like *_concentration_high are scored.
    if signal_type.endswith(("_high", "_moderate", "_low")):
        # Check if the base (without _high/_moderate/_low) maps to a category.
        for suffix in ("_high", "_moderate", "_low"):
            if signal_type.endswith(suffix):
                base = signal_type[: -len(suffix)]
                if base in _SCORED_SIGNAL_TYPES:
                    return SignalClass.SCORED
    # ATS board signals and hiring category signals are also scored.
    if signal_type.endswith("_board_detected"):
        return SignalClass.SCORED
    if signal_type.endswith("_hiring_detected"):
        return SignalClass.SCORED
    # Anything not in rules and not discovery is discovery-like metadata.
    return SignalClass.DISCOVERY


def _map_signal_to_category(signal_type: str) -> Optional[str]:
    """Map a signal_type to its friction category, if any."""
    for cat, types in _CATEGORY_SIGNAL_MAP.items():
        if signal_type in types:
            return cat
    # Concentration signals: strip _high/_moderate/_low and look up.
    for suffix in ("_high", "_moderate", "_low"):
        if signal_type.endswith(suffix):
            base = signal_type[: -len(suffix)]
            for cat, types in _CATEGORY_SIGNAL_MAP.items():
                if base in types:
                    return cat
    # ATS board signals map to scaling_strain (they indicate hiring platforms in use).
    if signal_type.endswith("_board_detected"):
        return "scaling_strain"
    # Hiring category signals → their respective categories.
    hiring_map = {
        "technology_hiring_detected": "tooling_inconsistency",
        "marketing_hiring_detected": "process_inefficiency",
        "finance_hiring_detected": "reporting_fragmentation",
        "operations_hiring_detected": "process_inefficiency",
        "sales_hiring_detected": "scaling_strain",
        "analytics_hiring_detected": "reporting_fragmentation",
        "design_hiring_detected": "tooling_inconsistency",
        "hr_people_hiring_detected": "process_inefficiency",
        "legal_hiring_detected": "process_inefficiency",
        "healthcare_hiring_detected": "customer_experience_friction",
        "manufacturing_hiring_detected": "scaling_strain",
        "retail_hiring_detected": "customer_experience_friction",
        "customer_success_hiring_detected": "customer_experience_friction",
        "recruiting_hiring_detected": "process_inefficiency",
        "it_hiring_detected": "tooling_inconsistency",
        "education_hiring_detected": "process_inefficiency",
        "trades_hiring_detected": "scaling_strain",
        "transportation_hiring_detected": "scaling_strain",
        "food_service_hiring_detected": "customer_experience_friction",
        "hospitality_hiring_detected": "customer_experience_friction",
        "supply_chain_hiring_detected": "process_inefficiency",
    }
    return hiring_map.get(signal_type)


def _classify_pressure(
    acceleration: float,
    spike: bool,
    drought: bool,
    total_signals: int,
) -> PressureState:
    """Classify overall signal pressure state."""
    if total_signals == 0:
        return PressureState.INSUFFICIENT
    if spike:
        return PressureState.SPIKE
    if drought:
        return PressureState.DROUGHT
    if acceleration >= ACCELERATING_THRESHOLD:
        return PressureState.ACCELERATING
    if acceleration <= DECELERATING_THRESHOLD:
        return PressureState.DECELERATING
    return PressureState.STABLE


def _build_evidence(
    overall_pressure: PressureState,
    spike: bool,
    drought: bool,
    drought_days: int,
    top_category: Optional[str],
    top_velocity: float,
    total_signals: int,
    scored_signals: int,
) -> str:
    """Build a human-readable evidence summary."""
    parts: list[str] = []

    if total_signals == 0:
        return "No signals in this period"

    parts.append(f"{scored_signals} scored / {total_signals} total signals")

    if spike:
        parts.append("signal spike detected (3× above mean)")
    if drought:
        parts.append(f"signal drought: {drought_days} consecutive days with 0 scored signals")

    if overall_pressure == PressureState.ACCELERATING:
        parts.append("signal pressure accelerating")
    elif overall_pressure == PressureState.DECELERATING:
        parts.append("signal pressure decelerating")
    elif overall_pressure == PressureState.STABLE:
        parts.append("signal pressure stable")

    if top_category:
        label = top_category.replace("_", " ").title()
        parts.append(f"highest velocity: {label} ({top_velocity:.1f}/period)")

    return "; ".join(parts)


# ── Engine ────────────────────────────────────────────────────────────────

class SignalVelocityTracker:
    """Tracks signal arrival velocity and detects pressure changes."""

    def compute_velocity(
        self,
        db: Session,
        company_id: UUID,
        window: VelocityWindow = VelocityWindow.ROLLING_30D,
    ) -> SignalVelocityResult:
        """Compute signal velocity for a company over the specified window."""
        days = WINDOW_DAYS[window]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        signals = self._fetch_signals(db, company_id, cutoff)

        if not signals:
            return SignalVelocityResult(
                company_id=company_id,
                window=window,
                window_days=days,
                total_signals=0,
                scored_signals=0,
                discovery_signals=0,
                overall_velocity=0.0,
                overall_acceleration=0.0,
                overall_pressure=PressureState.INSUFFICIENT,
            )

        # Classify and bucket signals.
        scored_count = 0
        discovery_count = 0
        category_signal_counts: dict[str, int] = defaultdict(int)
        source_counts: dict[str, int] = defaultdict(int)
        source_latest: dict[str, datetime] = {}

        for sig in signals:
            cls = _classify_signal(sig.signal_type)
            if cls == SignalClass.SCORED:
                scored_count += 1
            else:
                discovery_count += 1

            cat = _map_signal_to_category(sig.signal_type)
            if cat:
                category_signal_counts[cat] += 1

            source_counts[sig.source_type] += 1
            if sig.source_type not in source_latest or sig.captured_at > source_latest[sig.source_type]:
                source_latest[sig.source_type] = sig.captured_at

        total_count = len(signals)
        periods = max(days / 7, 1) if window != VelocityWindow.DAILY else 1
        velocity = total_count / periods

        # Compute buckets and detect spike/drought.
        buckets = self._compute_buckets(signals, days, window)
        acceleration = self._compute_acceleration(buckets)
        spike, spike_bucket = self._detect_spike(buckets)
        drought, drought_days = self._detect_drought(signals, days)

        # Per-category velocity.
        cat_velocities: list[CategoryVelocity] = []
        top_category: Optional[str] = None
        top_velocity = 0.0
        for cat in FRICTION_CATEGORIES:
            count = category_signal_counts.get(cat, 0)
            cat_scored = count  # All mapped signals are scored.
            cat_velocity = count / periods

            # Per-category acceleration: compare last half vs first half.
            cat_accel = self._compute_category_acceleration(
                cat, signals, periods
            )

            # Per-category pressure.
            if count == 0:
                pressure = PressureState.INSUFFICIENT
            elif spike:
                pressure = PressureState.SPIKE
            elif cat_accel >= ACCELERATING_THRESHOLD:
                pressure = PressureState.ACCELERATING
            elif cat_accel <= DECELERATING_THRESHOLD:
                pressure = PressureState.DECELERATING
            else:
                pressure = PressureState.STABLE

            cat_velocities.append(CategoryVelocity(
                category=cat,
                signal_count=count,
                scored_count=cat_scored,
                discovery_count=0,  # Mapped signals are all scored
                velocity=round(cat_velocity, 2),
                acceleration=round(cat_accel, 2),
                pressure=pressure,
            ))

            if cat_velocity > top_velocity:
                top_velocity = cat_velocity
                top_category = cat

        overall_pressure = _classify_pressure(
            acceleration, spike, drought, total_count
        )
        evidence = _build_evidence(
            overall_pressure, spike, drought, drought_days,
            top_category, top_velocity, total_count, scored_count,
        )

        # Source summary.
        source_summary = sorted(
            [
                SourceSummary(
                    source_type=src,
                    signal_count=cnt,
                    latest_signal_at=source_latest[src],
                )
                for src, cnt in source_counts.items()
            ],
            key=lambda s: s.signal_count,
            reverse=True,
        )

        return SignalVelocityResult(
            company_id=company_id,
            window=window,
            window_days=days,
            total_signals=total_count,
            scored_signals=scored_count,
            discovery_signals=discovery_count,
            overall_velocity=round(velocity, 2),
            overall_acceleration=round(acceleration, 2),
            overall_pressure=overall_pressure,
            category_velocities=cat_velocities,
            buckets=buckets,
            source_summary=source_summary,
            spike_detected=spike,
            spike_bucket=spike_bucket,
            drought_detected=drought,
            drought_days=drought_days,
            evidence=evidence,
        )

    def _fetch_signals(
        self,
        db: Session,
        company_id: UUID,
        cutoff: datetime,
    ) -> list[CompanySignal]:
        """Fetch CompanySignal rows for a company within a time window."""
        stmt = (
            select(CompanySignal)
            .where(
                CompanySignal.company_id == company_id,
                CompanySignal.captured_at >= cutoff,
            )
            .order_by(CompanySignal.captured_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def _compute_buckets(
        self,
        signals: list[CompanySignal],
        days: int,
        window: VelocityWindow,
    ) -> list[VelocityBucket]:
        """Bucket signals into time periods based on the window type."""
        if not signals:
            return []

        if window == VelocityWindow.DAILY:
            bucket_size = timedelta(days=1)
        elif window == VelocityWindow.WEEKLY:
            bucket_size = timedelta(weeks=1)
        else:
            # Rolling windows: use weekly buckets for granularity.
            bucket_size = timedelta(weeks=1)

        # Determine bucket boundaries.
        first = signals[0].captured_at
        buckets: list[VelocityBucket] = []
        bucket_start = first
        bucket_end = bucket_start + bucket_size

        current_bucket_signals: list[CompanySignal] = []
        for sig in signals:
            while sig.captured_at >= bucket_end:
                # Flush current bucket.
                buckets.append(self._make_bucket(
                    bucket_start, bucket_end, current_bucket_signals,
                ))
                current_bucket_signals = []
                bucket_start = bucket_end
                bucket_end = bucket_start + bucket_size

            current_bucket_signals.append(sig)

        # Flush last bucket.
        if current_bucket_signals:
            buckets.append(self._make_bucket(
                bucket_start, bucket_end, current_bucket_signals,
            ))

        return buckets

    def _make_bucket(
        self,
        start: datetime,
        end: datetime,
        signals: list[CompanySignal],
    ) -> VelocityBucket:
        """Create a VelocityBucket from a list of signals."""
        total = len(signals)
        scored = 0
        discovery = 0
        cat_counts: dict[str, int] = defaultdict(int)

        for sig in signals:
            cls = _classify_signal(sig.signal_type)
            if cls == SignalClass.SCORED:
                scored += 1
            else:
                discovery += 1
            cat = _map_signal_to_category(sig.signal_type)
            if cat:
                cat_counts[cat] += 1

        return VelocityBucket(
            bucket_start=start,
            bucket_end=end,
            total_count=total,
            scored_count=scored,
            discovery_count=discovery,
            category_counts=dict(cat_counts),
        )

    def _compute_acceleration(self, buckets: list[VelocityBucket]) -> float:
        """Compute overall acceleration as velocity change between halves.

        Compares the average velocity in the second half of buckets vs
        the first half.
        """
        if len(buckets) < 2:
            return 0.0

        mid = len(buckets) // 2
        first_half = buckets[:mid]
        second_half = buckets[mid:]

        first_vel = sum(b.scored_count for b in first_half) / len(first_half)
        second_vel = sum(b.scored_count for b in second_half) / len(second_half)

        return round(second_vel - first_vel, 2)

    def _compute_category_acceleration(
        self,
        category: str,
        signals: list[CompanySignal],
        periods: float,
    ) -> float:
        """Compute per-category acceleration.

        Compares scored signal count in the second half of the time range
        vs the first half.
        """
        if len(signals) < 2:
            return 0.0

        mid = len(signals) // 2
        first_half_count = 0
        second_half_count = 0

        for i, sig in enumerate(signals):
            cat = _map_signal_to_category(sig.signal_type)
            if cat != category:
                continue
            if _classify_signal(sig.signal_type) != SignalClass.SCORED:
                continue
            if i < mid:
                first_half_count += 1
            else:
                second_half_count += 1

        if periods <= 0:
            return 0.0

        half_periods = periods / 2
        if half_periods <= 0:
            return 0.0

        first_vel = first_half_count / half_periods
        second_vel = second_half_count / half_periods
        return round(second_vel - first_vel, 2)

    def _detect_spike(
        self,
        buckets: list[VelocityBucket],
    ) -> tuple[bool, Optional[datetime]]:
        """Detect if any bucket has 3× the mean scored count."""
        if not buckets:
            return False, None

        scored_counts = [b.scored_count for b in buckets]
        mean_count = sum(scored_counts) / len(scored_counts)

        if mean_count == 0:
            # If all buckets are 0, any non-zero bucket is a spike.
            for b in buckets:
                if b.scored_count > 0:
                    return True, b.bucket_start
            return False, None

        threshold = mean_count * SPIKE_MULTIPLIER
        for b in buckets:
            if b.scored_count > threshold:
                return True, b.bucket_start

        return False, None

    def _detect_drought(
        self,
        signals: list[CompanySignal],
        window_days: int,
    ) -> tuple[bool, int]:
        """Detect consecutive days with zero scored signals.

        Returns (drought_detected, max_consecutive_drought_days).
        """
        if not signals:
            return True, window_days

        # Build a set of days that had scored signals.
        scored_days: set[str] = set()
        for sig in signals:
            if _classify_signal(sig.signal_type) == SignalClass.SCORED:
                scored_days.add(sig.captured_at.strftime("%Y-%m-%d"))

        if not scored_days:
            return True, window_days

        # Count max consecutive days without scored signals.
        first = min(signals, key=lambda s: s.captured_at).captured_at.date()
        last = max(signals, key=lambda s: s.captured_at).captured_at.date()

        max_drought = 0
        current_drought = 0
        day = first
        while day <= last:
            if day.strftime("%Y-%m-%d") not in scored_days:
                current_drought += 1
                max_drought = max(max_drought, current_drought)
            else:
                current_drought = 0
            day += timedelta(days=1)

        return max_drought >= DROUGHT_MIN_DAYS, max_drought


# ── Singleton ─────────────────────────────────────────────────────────────

signal_velocity_tracker = SignalVelocityTracker()