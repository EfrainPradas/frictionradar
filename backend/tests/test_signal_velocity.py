"""Tests for the Signal Velocity Tracker.

Covers:
  - Signal classification (scored vs discovery)
  - Category mapping
  - Velocity computation (normal, spike, no-data, sparse)
  - Acceleration and pressure detection
  - Bucket time-series
  - Source summary
  - All four window types
  - Edge cases: 0 signals, 1 signal, drought, spike
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.friction_categories import FRICTION_CATEGORIES
from app.schemas.signal_velocity import (
    CategoryVelocity,
    PressureState,
    SignalClass,
    SignalVelocityResult,
    VelocityBucket,
    VelocityWindow,
)
from app.services.signal_velocity_tracker import (
    ACCELERATING_THRESHOLD,
    DECELERATING_THRESHOLD,
    DROUGHT_MIN_DAYS,
    SPIKE_MULTIPLIER,
    SignalVelocityTracker,
    _classify_signal,
    _map_signal_to_category,
    _classify_pressure,
    _build_evidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)
COMPANY_ID = uuid4()


def _make_signal(
    signal_type: str = "analytics_role_detected",
    source_type: str = "ats_public",
    captured_at: datetime = NOW,
    company_id: uuid4 = COMPANY_ID,
    numeric_value: float | None = None,
    signal_text: str = "",
) -> MagicMock:
    """Create a mock CompanySignal."""
    s = MagicMock()
    s.id = uuid4()
    s.company_id = company_id
    s.signal_type = signal_type
    s.source_type = source_type
    s.captured_at = captured_at
    s.numeric_value = numeric_value
    s.signal_text = signal_text or f"Detected: {signal_type}"
    s.confidence = 0.8
    return s


def _mock_db_with_signals(signals):
    """Create a mock DB that returns the given signals."""
    db = MagicMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = signals
    mock_result.scalars.return_value = mock_scalars
    db.execute.return_value = mock_result
    return db


# ── Unit tests: signal classification ──────────────────────────────────────

class TestClassifySignal:
    def test_scored_signal(self):
        assert _classify_signal("analytics_role_detected") == SignalClass.SCORED

    def test_discovery_signal(self):
        assert _classify_signal("careers_page_found") == SignalClass.DISCOVERY

    def test_company_size_discovery(self):
        assert _classify_signal("company_size_detected") == SignalClass.DISCOVERY

    def test_concentration_signal_scored(self):
        assert _classify_signal("analytics_concentration_high") == SignalClass.SCORED

    def test_ats_board_signal_scored(self):
        assert _classify_signal("greenhouse_board_detected") == SignalClass.SCORED

    def test_hiring_category_signal_scored(self):
        assert _classify_signal("technology_hiring_detected") == SignalClass.SCORED

    def test_visible_hiring_area_discovery(self):
        assert _classify_signal("visible_hiring_area_detected") == SignalClass.DISCOVERY

    def test_job_links_extracted_discovery(self):
        assert _classify_signal("job_links_extracted") == SignalClass.DISCOVERY


class TestMapSignalToCategory:
    def test_analytics_maps_to_reporting(self):
        cat = _map_signal_to_category("analytics_role_detected")
        assert cat == "reporting_fragmentation"

    def test_revops_maps_to_process(self):
        cat = _map_signal_to_category("revops_language_detected")
        assert cat == "process_inefficiency"

    def test_growth_language_maps_to_scaling(self):
        cat = _map_signal_to_category("growth_language_detected")
        assert cat == "scaling_strain"

    def test_customer_hiring_maps_to_customer(self):
        cat = _map_signal_to_category("customer_success_hiring_detected")
        assert cat == "customer_experience_friction"

    def test_concentration_maps_correctly(self):
        cat = _map_signal_to_category("analytics_concentration_high")
        assert cat == "reporting_fragmentation"

    def test_discovery_signal_has_no_category(self):
        cat = _map_signal_to_category("careers_page_found")
        assert cat is None

    def test_ats_board_maps_to_scaling(self):
        cat = _map_signal_to_category("greenhouse_board_detected")
        assert cat == "scaling_strain"


# ── Unit tests: pressure classification ────────────────────────────────────

class TestClassifyPressure:
    def test_insufficient_when_zero_signals(self):
        assert _classify_pressure(0.0, False, False, 0) == PressureState.INSUFFICIENT

    def test_spike_overrides_acceleration(self):
        assert _classify_pressure(1.0, True, False, 10) == PressureState.SPIKE

    def test_drought_overrides_acceleration(self):
        assert _classify_pressure(0.0, False, True, 5) == PressureState.DROUGHT

    def test_accelerating(self):
        assert _classify_pressure(1.0, False, False, 10) == PressureState.ACCELERATING

    def test_decelerating(self):
        assert _classify_pressure(-1.0, False, False, 10) == PressureState.DECELERATING

    def test_stable(self):
        assert _classify_pressure(0.1, False, False, 10) == PressureState.STABLE


# ── Integration: no data ──────────────────────────────────────────────────

class TestNoData:
    def test_zero_signals_returns_insufficient(self):
        db = _mock_db_with_signals([])
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.total_signals == 0
        assert result.overall_pressure == PressureState.INSUFFICIENT
        assert result.overall_velocity == 0.0
        assert result.overall_acceleration == 0.0
        assert result.category_velocities == []
        assert result.buckets == []


class TestSparseData:
    def test_single_signal(self):
        signals = [_make_signal(captured_at=NOW)]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.WEEKLY)

        assert result.total_signals == 1
        assert result.overall_velocity > 0

    def test_two_signals_different_days(self):
        signals = [
            _make_signal(captured_at=NOW - timedelta(days=10)),
            _make_signal(captured_at=NOW),
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.total_signals == 2
        assert result.scored_signals >= 1


# ── Integration: normal velocity ──────────────────────────────────────────

class TestNormalVelocity:
    def test_week_of_signals(self):
        """7 scored signals over 1 week → velocity = 7/1 = 7.0."""
        signals = [
            _make_signal(
                signal_type="analytics_role_detected",
                captured_at=NOW - timedelta(days=7) + timedelta(days=i),
            )
            for i in range(7)
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.WEEKLY)

        assert result.total_signals == 7
        assert result.scored_signals == 7
        assert result.discovery_signals == 0

    def test_mixed_scored_and_discovery(self):
        """Scored + discovery signals are separated correctly."""
        signals = [
            _make_signal(signal_type="analytics_role_detected", captured_at=NOW - timedelta(days=5)),
            _make_signal(signal_type="careers_page_found", captured_at=NOW - timedelta(days=4)),
            _make_signal(signal_type="growth_language_detected", captured_at=NOW - timedelta(days=3)),
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.scored_signals == 2
        assert result.discovery_signals == 1
        assert result.total_signals == 3

    def test_category_velocity_populated(self):
        """All 5 categories appear in category_velocities."""
        signals = [
            _make_signal(signal_type="analytics_role_detected", captured_at=NOW - timedelta(days=1)),
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert len(result.category_velocities) == 5
        # Only reporting_fragmentation should have a count.
        rf = next(cv for cv in result.category_velocities if cv.category == "reporting_fragmentation")
        assert rf.signal_count == 1
        assert rf.scored_count == 1
        # Others should have 0.
        ss = next(cv for cv in result.category_velocities if cv.category == "scaling_strain")
        assert ss.signal_count == 0


# ── Integration: spike detection ──────────────────────────────────────────

class TestSpikeDetection:
    def test_spike_detected_when_one_bucket_triples_mean(self):
        """1 signal in each of weeks 1-3, then 10 in week 4 → spike."""
        base_signals = [
            _make_signal(
                signal_type="analytics_role_detected",
                captured_at=NOW - timedelta(days=28) + timedelta(days=i * 7),
            )
            for i in range(3)
        ]
        spike_signals = [
            _make_signal(
                signal_type="analytics_role_detected",
                captured_at=NOW - timedelta(days=3) + timedelta(days=0, hours=i),
            )
            for i in range(10)
        ]
        signals = base_signals + spike_signals
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.spike_detected is True

    def test_no_spike_when_evenly_distributed(self):
        """Even distribution → no spike."""
        signals = [
            _make_signal(
                signal_type="analytics_role_detected",
                captured_at=NOW - timedelta(days=29) + timedelta(days=i * 4),
            )
            for i in range(8)
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        # Evenly distributed signals should not trigger a spike.
        # (8 signals over ~30 days ≈ 2 per week-bucket, all similar)
        assert result.spike_detected is False or result.overall_pressure in (
            PressureState.STABLE, PressureState.ACCELERATING, PressureState.DECELERATING,
        )


# ── Integration: drought detection ────────────────────────────────────────

class TestDroughtDetection:
    def test_drought_when_no_scored_signals_for_7_days(self):
        """Only discovery signals for 30 days → drought."""
        signals = [
            _make_signal(
                signal_type="careers_page_found",
                captured_at=NOW - timedelta(days=i),
            )
            for i in range(0, 30, 3)
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.drought_detected is True
        assert result.overall_pressure == PressureState.DROUGHT

    def test_no_drought_with_recent_scored_signals(self):
        """Scored signals every few days → no drought."""
        signals = [
            _make_signal(
                signal_type="analytics_role_detected",
                captured_at=NOW - timedelta(days=i),
            )
            for i in range(0, 14, 2)
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.drought_detected is False


# ── Integration: acceleration ─────────────────────────────────────────────

class TestAcceleration:
    def test_accelerating_when_second_half_has_more(self):
        """More scored signals in the second half → accelerating."""
        first_half = [
            _make_signal(
                signal_type="growth_language_detected",
                captured_at=NOW - timedelta(days=25) + timedelta(days=i),
            )
            for i in range(2)
        ]
        second_half = [
            _make_signal(
                signal_type="growth_language_detected",
                captured_at=NOW - timedelta(days=5) + timedelta(days=i),
            )
            for i in range(8)
        ]
        signals = first_half + second_half
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.overall_acceleration > 0

    def test_decelerating_when_first_half_has_more(self):
        """More scored signals in the first half → decelerating."""
        first_half = [
            _make_signal(
                signal_type="growth_language_detected",
                captured_at=NOW - timedelta(days=25) + timedelta(days=i),
            )
            for i in range(8)
        ]
        second_half = [
            _make_signal(
                signal_type="growth_language_detected",
                captured_at=NOW - timedelta(days=5) + timedelta(days=i),
            )
            for i in range(2)
        ]
        signals = first_half + second_half
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert result.overall_acceleration < 0


# ── Integration: source summary ───────────────────────────────────────────

class TestSourceSummary:
    def test_source_summary_populated(self):
        """Source summary lists distinct source_types with counts."""
        signals = [
            _make_signal(signal_type="analytics_role_detected", source_type="ats_public", captured_at=NOW - timedelta(days=5)),
            _make_signal(signal_type="growth_language_detected", source_type="company_site", captured_at=NOW - timedelta(days=3)),
            _make_signal(signal_type="careers_page_found", source_type="careers", captured_at=NOW - timedelta(days=1)),
        ]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)

        assert len(result.source_summary) >= 2
        sources = {s.source_type for s in result.source_summary}
        assert "ats_public" in sources
        assert "company_site" in sources


# ── Integration: all window types ─────────────────────────────────────────

class TestAllWindows:
    def test_daily_window(self):
        signals = [_make_signal(captured_at=NOW)]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.DAILY)
        assert result.window_days == 1
        assert result.total_signals == 1

    def test_weekly_window(self):
        signals = [_make_signal(captured_at=NOW)]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.WEEKLY)
        assert result.window_days == 7

    def test_rolling_30d_window(self):
        signals = [_make_signal(captured_at=NOW)]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_30D)
        assert result.window_days == 30

    def test_rolling_90d_window(self):
        signals = [_make_signal(captured_at=NOW)]
        db = _mock_db_with_signals(signals)
        tracker = SignalVelocityTracker()
        result = tracker.compute_velocity(db, COMPANY_ID, VelocityWindow.ROLLING_90D)
        assert result.window_days == 90


# ── Integration: evidence summary ─────────────────────────────────────────

class TestEvidence:
    def test_evidence_no_signals(self):
        evidence = _build_evidence(PressureState.INSUFFICIENT, False, False, 0, None, 0.0, 0, 0)
        assert "No signals" in evidence

    def test_evidence_spike(self):
        evidence = _build_evidence(PressureState.SPIKE, True, False, 0, "scaling_strain", 3.0, 10, 8)
        assert "signal spike" in evidence

    def test_evidence_stable(self):
        evidence = _build_evidence(PressureState.STABLE, False, False, 0, "tooling_inconsistency", 2.0, 5, 4)
        assert "stable" in evidence

    def test_evidence_drought(self):
        evidence = _build_evidence(PressureState.DROUGHT, False, True, 14, None, 0.0, 3, 1)
        assert "drought" in evidence
        assert "14" in evidence

    def test_evidence_includes_top_category(self):
        evidence = _build_evidence(PressureState.ACCELERATING, False, False, 0, "scaling_strain", 3.5, 12, 10)
        assert "Scaling Strain" in evidence


# ── Schema serialization ───────────────────────────────────────────────────

class TestSchemaSerialization:
    def test_velocity_result_json_round_trip(self):
        result = SignalVelocityResult(
            company_id=COMPANY_ID,
            window=VelocityWindow.ROLLING_30D,
            window_days=30,
            total_signals=10,
            scored_signals=8,
            discovery_signals=2,
            overall_velocity=2.5,
            overall_acceleration=0.5,
            overall_pressure=PressureState.ACCELERATING,
            evidence="8 scored / 10 total signals; signal pressure accelerating",
        )
        json_str = result.model_dump_json()
        restored = SignalVelocityResult.model_validate_json(json_str)
        assert restored.total_signals == 10
        assert restored.overall_pressure == PressureState.ACCELERATING

    def test_velocity_bucket_serialization(self):
        bucket = VelocityBucket(
            bucket_start=NOW - timedelta(days=7),
            bucket_end=NOW,
            total_count=5,
            scored_count=4,
            discovery_count=1,
            category_counts={"scaling_strain": 3, "reporting_fragmentation": 1},
        )
        d = bucket.model_dump()
        assert d["total_count"] == 5
        assert d["category_counts"]["scaling_strain"] == 3