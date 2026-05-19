"""
Shared test fixtures and factories for FrictionRadar.

Provides mock object factories for:
  - CompanySignal (all valid signal_type values)
  - Company (minimal valid company)
  - FrictionScore (with v2.0.0 breakdown)
  - CompanyJobRole (with functional_area)
  - CollectionRun (with valid status)
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.core.friction_categories import FRICTION_CATEGORIES


# ─── Signal Factory ─────────────────────────────────────────────────────

# Canonical signal types from the emitter registry
SIGNAL_TYPES = {
    "static": [
        "careers_page_found",
        "high_open_positions_count_detected",
        "open_positions_count_detected",
        "multiple_open_roles",
        "analytics_role_detected",
        "company_size_detected",
        "revops_language_detected",
        "scaling_language_detected",
        "hiring_language_detected",
        "cross_team_language_detected",
        "newsroom_found",
        "expansion_language_detected",
        "funding_detected",
        "acquisition_detected",
        "reporting_language_detected",
        "partnership_detected",
        "growth_language_detected",
        "hiring_news_detected",
        "job_cards_visible_detected",
        "job_links_extracted",
        "visible_hiring_area_detected",
        "high_hiring_volume",
        "broad_hiring_pattern",
        "narrow_hiring_focus",
    ],
    "ats_board": [
        "greenhouse_board_detected",
        "lever_board_detected",
        "ashby_board_detected",
    ],
    "hiring_category": [
        "technology_hiring_detected",
        "marketing_hiring_detected",
        "finance_hiring_detected",
        "operations_hiring_detected",
        "sales_hiring_detected",
        "analytics_hiring_detected",
    ],
}

SOURCE_TYPES = [
    "company_site", "careers", "ats_public", "newsroom",
    "dynamic_careers", "playwright_careers", "browser_capture_v2",
]


def make_signal(
    signal_type: str = "open_positions_count_detected",
    signal_text: str = "",
    numeric_value: float | None = None,
    source_type: str = "ats_public",
    company_id: object = None,
) -> MagicMock:
    """Create a mock CompanySignal for testing."""
    s = MagicMock()
    s.id = uuid4()
    s.signal_type = signal_type
    s.signal_text = signal_text or f"Detected: {signal_type}"
    s.numeric_value = numeric_value
    s.source_type = source_type
    s.company_id = company_id or uuid4()
    s.captured_at = datetime.now(timezone.utc)
    s.confidence = 0.8
    return s


def make_signals(types_and_values: list[tuple[str, float | None]]) -> list[MagicMock]:
    """Create multiple signals from a list of (signal_type, numeric_value) tuples."""
    return [make_signal(t, numeric_value=v) for t, v in types_and_values]


# ─── Company Factory ────────────────────────────────────────────────────

def make_company(
    name: str = "TestCorp",
    domain: str = "testcorp.com",
    industry: str = "Technology",
    company_id: object = None,
) -> MagicMock:
    """Create a mock Company for testing."""
    c = MagicMock()
    c.id = company_id or uuid4()
    c.name = name
    c.domain = domain
    c.industry = industry
    c.company_size = None
    c.source_added_from = "test"
    c.created_at = datetime.now(timezone.utc)
    c.updated_at = datetime.now(timezone.utc)
    c.inferred_sector = None
    c.inferred_sector_confidence = None
    return c


# ─── FrictionScore Factory ──────────────────────────────────────────────

def make_v2_breakdown(
    dominant: str = "scaling_strain",
    total_score: float = 15.0,
    matched_signals: list[str] | None = None,
) -> dict:
    """Create a v2.0.0 scoring breakdown dict."""
    categories = {}
    per_cat_score = total_score / len(FRICTION_CATEGORIES) if FRICTION_CATEGORIES else 0
    for cat in FRICTION_CATEGORIES:
        cat_signals = matched_signals if matched_signals else [f"test_{cat}"]
        categories[cat] = {
            "raw_score": per_cat_score if cat == dominant else 0,
            "max_possible": 10.0,
            "normalized_score": per_cat_score / 10.0 if cat == dominant else 0.0,
            "matched_signals": cat_signals if cat == dominant else [],
        }
    return {
        "categories": categories,
        "confidence": {
            "signal_diversity": 3,
            "contributing_signal_count": 5,
            "evidence_breadth": 2,
            "confidence_level": "medium",
        },
        "scoring_version": "2.0.0",
    }


def make_friction_score(
    dominant_friction_type: str = "scaling_strain",
    total_score: float = 15.0,
    company_id: object = None,
    breakdown: dict | None = None,
) -> MagicMock:
    """Create a mock FrictionScore for testing."""
    s = MagicMock()
    s.id = uuid4()
    s.company_id = company_id or uuid4()
    s.total_score = total_score
    s.dominant_friction_type = dominant_friction_type
    s.scoring_breakdown_json = breakdown or make_v2_breakdown(
        dominant=dominant_friction_type, total_score=total_score,
    )
    s.scoring_version = "2.0.0"
    s.computed_at = datetime.now(timezone.utc)
    s.created_at = datetime.now(timezone.utc)
    s.open_positions_count = None
    return s


# ─── JobRole Factory ────────────────────────────────────────────────────

FUNCTIONAL_AREAS = [
    "analytics", "finance", "operations", "marketing", "sales",
    "engineering", "product", "hr", "recruiting", "legal",
    "customer_support", "supply_chain", "it",
]


def make_role(
    functional_area: str | None = "analytics",
    role_title: str = "Data Analyst",
    role_description: str | None = None,
    company_id: object = None,
) -> MagicMock:
    """Create a mock CompanyJobRole for testing."""
    r = MagicMock()
    r.id = uuid4()
    r.functional_area = functional_area
    r.role_title = role_title
    r.role_description = role_description or f"Responsible for {functional_area} operations"
    r.company_id = company_id or uuid4()
    return r


def make_roles(areas_and_titles: list[tuple[str, str]]) -> list[MagicMock]:
    """Create multiple roles from a list of (functional_area, role_title) tuples."""
    return [make_role(area, title) for area, title in areas_and_titles]


# ─── CollectionRun Factory ──────────────────────────────────────────────

COLLECTION_RUN_STATUSES = ["pending", "running", "completed", "failed"]


def make_collection_run(
    company_id: object = None,
    status: str = "completed",
) -> MagicMock:
    """Create a mock CollectionRun for testing."""
    r = MagicMock()
    r.id = uuid4()
    r.company_id = company_id or uuid4()
    r.collector_type = "orchestrator"
    r.status = status
    r.started_at = datetime.now(timezone.utc)
    r.finished_at = datetime.now(timezone.utc) if status in ("completed", "failed") else None
    r.error_message = "Test error" if status == "failed" else None
    r.metadata_json = {"signals_extracted": 5} if status == "completed" else None
    return r


# ─── Mock DB Session ────────────────────────────────────────────────────

def make_mock_db() -> MagicMock:
    """Create a mock SQLAlchemy Session suitable for engine tests.

    Supports chain mocking: db.query(X).filter(Y).first()
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.refresh = MagicMock()
    db.close = MagicMock()
    return db