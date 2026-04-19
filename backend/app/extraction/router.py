"""Extraction strategy router.

Decides the cheapest viable extraction strategy for a given company
based on prior ATS detection, cached results, and homepage signals.

This module is PURELY DECISIONAL — it does not execute any extraction.
Extractors (Phase 2+) will call router.decide() and then dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.extraction.constants import (
    ATSPlatform,
    ATS_WITH_JSON_API,
    ExtractionStrategy,
    ReasonCode,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# How long a cached extraction is considered fresh.
CACHE_TTL = timedelta(hours=48)

# Minimum visible text length (chars) to consider an HTTP response
# as having real content (not a JS shell).
MIN_STATIC_CONTENT_LENGTH = 500


@dataclass
class RoutingDecision:
    """Output of the router — tells the dispatcher what to do."""

    strategy: ExtractionStrategy
    reason: ReasonCode
    careers_url: Optional[str] = None
    ats_platform: Optional[str] = None
    ats_api_url: Optional[str] = None
    fallback_chain: List[ExtractionStrategy] = field(default_factory=list)


@dataclass
class RoutingContext:
    """Inputs the router uses to make a decision.

    Built by the caller from whatever information is already available
    (homepage scan, prior ATS detection, cached results, etc.).
    """

    domain: str = ""
    company_name: Optional[str] = None
    company_id: Optional[UUID] = None

    # From prior ATS detection (company_site collector or DB)
    detected_ats_platform: Optional[str] = None
    detected_ats_url: Optional[str] = None

    # From careers_url_finder or prior collection
    careers_url: Optional[str] = None
    careers_url_strategy: Optional[str] = None  # e.g. "homepage_link", "path:/careers"

    # From a quick HTTP probe of the careers page (if available)
    careers_page_content_length: Optional[int] = None
    careers_page_has_job_indicators: bool = False

    # Cache state
    has_fresh_cache: bool = False
    cache_age_hours: Optional[float] = None


class ExtractionRouter:
    """Decides extraction strategy based on available context.

    Priority order:
    1. Cache (if fresh) → CACHE_FRESH
    2. ATS API (if platform detected with JSON template) → ATS_API
    3. HTTP Static (if careers page responds with rich content) → HTTP_STATIC
    4. Playwright (fallback) → PLAYWRIGHT
    """

    def decide(self, ctx: RoutingContext) -> RoutingDecision:
        """Return the best extraction strategy for the given context."""

        # ── 1. Cache check ──────────────────────────────────────────
        if ctx.has_fresh_cache:
            logger.info(
                f"[Router] {ctx.domain}: CACHE_FRESH "
                f"(age={ctx.cache_age_hours:.1f}h)"
            )
            return RoutingDecision(
                strategy=ExtractionStrategy.HTTP_STATIC,  # doesn't matter; caller uses cache
                reason=ReasonCode.CACHE_FRESH,
                careers_url=ctx.careers_url,
            )

        # ── 2. ATS API check ───────────────────────────────────────
        if ctx.detected_ats_platform:
            try:
                platform = ATSPlatform(ctx.detected_ats_platform)
            except ValueError:
                platform = None

            if platform and platform in ATS_WITH_JSON_API:
                logger.info(
                    f"[Router] {ctx.domain}: ATS_API "
                    f"(platform={platform.value}, url={ctx.detected_ats_url})"
                )
                return RoutingDecision(
                    strategy=ExtractionStrategy.ATS_API,
                    reason=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
                    careers_url=ctx.careers_url,
                    ats_platform=platform.value,
                    ats_api_url=ctx.detected_ats_url,
                    fallback_chain=[
                        ExtractionStrategy.HTTP_STATIC,
                        ExtractionStrategy.PLAYWRIGHT,
                    ],
                )
            else:
                # ATS detected but no JSON template (Workday, iCIMS)
                logger.info(
                    f"[Router] {ctx.domain}: PLAYWRIGHT "
                    f"(ats={ctx.detected_ats_platform}, no JSON template)"
                )
                return RoutingDecision(
                    strategy=ExtractionStrategy.PLAYWRIGHT,
                    reason=ReasonCode.ATS_DETECTED_NO_TEMPLATE,
                    careers_url=ctx.careers_url,
                    ats_platform=ctx.detected_ats_platform,
                )

        # ── 3. HTTP Static check ────────────────────────────────────
        if ctx.careers_url:
            if (
                ctx.careers_page_content_length is not None
                and ctx.careers_page_content_length >= MIN_STATIC_CONTENT_LENGTH
                and ctx.careers_page_has_job_indicators
            ):
                logger.info(
                    f"[Router] {ctx.domain}: HTTP_STATIC "
                    f"(url={ctx.careers_url}, "
                    f"content={ctx.careers_page_content_length} chars)"
                )
                return RoutingDecision(
                    strategy=ExtractionStrategy.HTTP_STATIC,
                    reason=ReasonCode.STATIC_CAREERS_PAGE_DETECTED,
                    careers_url=ctx.careers_url,
                    fallback_chain=[ExtractionStrategy.PLAYWRIGHT],
                )

            if ctx.careers_page_content_length is not None and ctx.careers_page_content_length < MIN_STATIC_CONTENT_LENGTH:
                logger.info(
                    f"[Router] {ctx.domain}: PLAYWRIGHT "
                    f"(SPA shell, content={ctx.careers_page_content_length} chars)"
                )
                return RoutingDecision(
                    strategy=ExtractionStrategy.PLAYWRIGHT,
                    reason=ReasonCode.SPA_CONTENT_EMPTY,
                    careers_url=ctx.careers_url,
                )

            # Careers URL found but not yet probed for content quality
            logger.info(
                f"[Router] {ctx.domain}: HTTP_STATIC "
                f"(url={ctx.careers_url}, untested)"
            )
            return RoutingDecision(
                strategy=ExtractionStrategy.HTTP_STATIC,
                reason=ReasonCode.CAREERS_URL_FOUND_UNTESTED,
                careers_url=ctx.careers_url,
                fallback_chain=[ExtractionStrategy.PLAYWRIGHT],
            )

        # ── 4. No careers URL found ─────────────────────────────────
        logger.info(
            f"[Router] {ctx.domain}: PLAYWRIGHT "
            f"(no careers URL found)"
        )
        return RoutingDecision(
            strategy=ExtractionStrategy.PLAYWRIGHT,
            reason=ReasonCode.NO_CAREERS_URL_FOUND,
            fallback_chain=[],
        )


# Module-level singleton
extraction_router = ExtractionRouter()
