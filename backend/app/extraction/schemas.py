"""Unified extraction output contract.

Every extractor (ats_api, http_static, playwright) MUST return a
NormalizedJobsResult. This is the single schema that the rest of
the pipeline consumes — scoring, evaluation, and signal persistence
never see extractor internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.extraction.constants import ExtractionStrategy, ReasonCode


@dataclass
class NormalizedJob:
    """A single job extracted from any source."""

    title: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None
    functional_area: Optional[str] = None
    job_url: Optional[str] = None
    description_snippet: Optional[str] = None


@dataclass
class NormalizedJobsResult:
    """Unified output from any extraction strategy.

    Every extractor fills this contract. Downstream code (signal
    persistence, scoring, evaluation) only depends on this shape.
    """

    # ── Identity ────────────────────────────────────────────────────
    domain: str = ""
    careers_url: Optional[str] = None
    ats_platform: Optional[str] = None

    # ── Strategy metadata ───────────────────────────────────────────
    strategy_used: ExtractionStrategy = ExtractionStrategy.PLAYWRIGHT
    reason_code: ReasonCode = ReasonCode.PLAYWRIGHT_REQUIRED
    fallback_from: Optional[ExtractionStrategy] = None

    # ── Extracted data ──────────────────────────────────────────────
    open_positions_count: Optional[int] = None
    jobs: List[NormalizedJob] = field(default_factory=list)
    hiring_areas: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

    # ── Quality indicators ──────────────────────────────────────────
    evidence_quality: str = "none"  # high | moderate | limited | none
    confidence: float = 0.0  # 0.0–1.0

    # ── Instrumentation ─────────────────────────────────────────────
    duration_ms: int = 0
    used_cache: bool = False
    error: Optional[str] = None
    extracted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def success(self) -> bool:
        return self.error is None and (
            self.open_positions_count is not None
            or len(self.jobs) > 0
            or len(self.hiring_areas) > 0
        )

    @property
    def jobs_count(self) -> int:
        return len(self.jobs)
