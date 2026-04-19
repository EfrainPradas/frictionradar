"""Extraction instrumentation — structured logging and attempt persistence.

Records every extraction attempt with strategy, duration, outcome, and
reason codes. Used for observability and debugging extraction routing.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.extraction.constants import ExtractionStrategy, ReasonCode
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionAttemptRecord:
    """Immutable record of a single extraction attempt."""

    domain: str = ""
    company_id: Optional[UUID] = None
    strategy: ExtractionStrategy = ExtractionStrategy.PLAYWRIGHT
    reason_code: ReasonCode = ReasonCode.PLAYWRIGHT_REQUIRED
    fallback_from: Optional[ExtractionStrategy] = None

    # Outcome
    success: bool = False
    error: Optional[str] = None
    jobs_found: int = 0
    positions_count: Optional[int] = None
    evidence_quality: str = "none"

    # Timing
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    duration_ms: int = 0
    used_cache: bool = False

    # Source
    careers_url: Optional[str] = None
    ats_platform: Optional[str] = None


@contextmanager
def track_extraction(
    domain: str,
    strategy: ExtractionStrategy,
    reason_code: ReasonCode,
    company_id: Optional[UUID] = None,
    fallback_from: Optional[ExtractionStrategy] = None,
):
    """Context manager that times an extraction and logs the result.

    Usage:
        with track_extraction("stripe.com", strategy, reason) as attempt:
            result = do_extraction(...)
            attempt.success = result.success
            attempt.jobs_found = result.jobs_count
            attempt.positions_count = result.open_positions_count
            attempt.evidence_quality = result.evidence_quality

    On exit, the attempt is logged with duration. The caller can also
    persist it to company_extraction_attempts via persist_attempt().
    """
    attempt = ExtractionAttemptRecord(
        domain=domain,
        company_id=company_id,
        strategy=strategy,
        reason_code=reason_code,
        fallback_from=fallback_from,
    )
    t0 = time.monotonic()

    try:
        yield attempt
    except Exception as exc:
        attempt.success = False
        attempt.error = str(exc)[:500]
        raise
    finally:
        attempt.duration_ms = int((time.monotonic() - t0) * 1000)
        _log_attempt(attempt)


def _log_attempt(attempt: ExtractionAttemptRecord) -> None:
    """Emit a structured log line for the extraction attempt."""
    status = "OK" if attempt.success else "FAIL"
    fallback = f" fallback_from={attempt.fallback_from.value}" if attempt.fallback_from else ""

    logger.info(
        f"[Extraction] {attempt.domain} "
        f"strategy={attempt.strategy.value} "
        f"reason={attempt.reason_code.value} "
        f"status={status} "
        f"duration={attempt.duration_ms}ms "
        f"jobs={attempt.jobs_found} "
        f"positions={attempt.positions_count} "
        f"quality={attempt.evidence_quality} "
        f"cache={attempt.used_cache}"
        f"{fallback}"
    )
    if attempt.error:
        logger.warning(
            f"[Extraction] {attempt.domain} error: {attempt.error}"
        )


def persist_attempt(db, attempt: ExtractionAttemptRecord) -> None:
    """Save an extraction attempt to the database.

    Requires the CompanyExtractionAttempt model and table to exist.
    Fails silently if the table doesn't exist yet (safe for incremental rollout).
    """
    try:
        from app.models.extraction import CompanyExtractionAttempt

        record = CompanyExtractionAttempt(
            company_id=attempt.company_id,
            domain=attempt.domain,
            strategy=attempt.strategy.value,
            reason_code=attempt.reason_code.value,
            fallback_from=attempt.fallback_from.value if attempt.fallback_from else None,
            success=attempt.success,
            error=attempt.error,
            jobs_found=attempt.jobs_found,
            positions_count=attempt.positions_count,
            evidence_quality=attempt.evidence_quality,
            duration_ms=attempt.duration_ms,
            used_cache=attempt.used_cache,
            careers_url=attempt.careers_url,
            ats_platform=attempt.ats_platform,
        )
        db.add(record)
        db.commit()
    except Exception as exc:
        logger.debug(f"[Extraction] Could not persist attempt: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
