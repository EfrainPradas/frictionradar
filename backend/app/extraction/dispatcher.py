"""Extraction dispatcher — routes to the correct strategy and executes.

Entry points:
  - try_ats_extraction()         → ATS API only
  - try_http_static_extraction() → HTTP static parsing
  - try_playwright_extraction()  → Playwright fallback (budgeted)
  - extract_company()            → Full chain: ATS → HTTP → Playwright

The caller (batch_processor) uses extract_company() as the single
entry point. It returns a NormalizedJobsResult from whichever strategy
succeeds first.
"""

from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.instrumentation import track_extraction
from app.extraction.router import ExtractionRouter, RoutingContext, RoutingDecision
from app.extraction.schemas import NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── ATS API extraction (Phase 2) ───────────────────────────────────

def try_ats_extraction(
    domain: str,
    company_name: Optional[str] = None,
    company_id: Optional[UUID] = None,
    detected_ats_platform: Optional[str] = None,
    detected_ats_url: Optional[str] = None,
) -> Optional[NormalizedJobsResult]:
    """Attempt ATS API extraction for a company.

    Returns:
        NormalizedJobsResult if ATS extraction was attempted (check .success)
        None if ATS_API strategy was not selected (no ATS detected)
    """
    ctx = RoutingContext(
        domain=domain,
        company_name=company_name,
        company_id=company_id,
        detected_ats_platform=detected_ats_platform,
        detected_ats_url=detected_ats_url,
    )

    router = ExtractionRouter()
    decision = router.decide(ctx)

    if decision.strategy != ExtractionStrategy.ATS_API:
        return None

    from app.extraction.adapters import ATS_ADAPTERS

    try:
        platform = ATSPlatform(decision.ats_platform)
    except (ValueError, TypeError):
        return None

    adapter = ATS_ADAPTERS.get(platform)
    if adapter is None:
        return None

    with track_extraction(
        domain=domain,
        strategy=ExtractionStrategy.ATS_API,
        reason_code=decision.reason,
        company_id=company_id,
    ) as attempt:
        result = adapter.extract(domain, company_name)
        attempt.success = result.success
        attempt.jobs_found = result.jobs_count
        attempt.positions_count = result.open_positions_count
        attempt.evidence_quality = result.evidence_quality
        attempt.careers_url = result.careers_url
        attempt.ats_platform = platform.value

    return result


# ── HTTP Static extraction (Phase 3) ───────────────────────────────

def try_http_static_extraction(
    domain: str,
    company_name: Optional[str] = None,
    company_id: Optional[UUID] = None,
) -> Optional[NormalizedJobsResult]:
    """Attempt HTTP static extraction for a company.

    Steps:
      1. Discover careers URL
      2. Classify page (static vs SPA)
      3. If static, extract jobs from HTML
      4. If confidence too low, return result with low confidence
         (caller decides to fall back to Playwright)

    Returns:
        NormalizedJobsResult if extraction was attempted (check .success and .confidence)
        None if no careers URL was found at all
    """
    from app.extraction.discovery import discover_careers_url
    from app.extraction.classifier import classify_page
    from app.extraction.http_static import extract_from_html, MIN_ACCEPTANCE_CONFIDENCE

    # ── 1. Discover careers URL ─────────────────────────────────
    discovery = discover_careers_url(domain, company_name)
    if not discovery.url:
        logger.info(f"[HTTPStatic] {domain}: no careers URL found")
        return None

    # ── 2. Classify page ────────────────────────────────────────
    classification = classify_page(discovery.html)

    logger.info(
        f"[HTTPStatic] {domain}: classified as {classification.page_type} "
        f"(confidence={classification.confidence:.2f}, "
        f"reason={classification.reason})"
    )

    # If it's clearly a SPA shell, don't bother extracting
    if classification.page_type == "spa_shell" and classification.confidence > 0.5:
        logger.info(f"[HTTPStatic] {domain}: SPA shell detected, skipping HTTP extraction")
        return NormalizedJobsResult(
            domain=domain,
            careers_url=discovery.url,
            strategy_used=ExtractionStrategy.HTTP_STATIC,
            reason_code=ReasonCode.SPA_CONTENT_EMPTY,
            error="SPA shell — requires Playwright",
        )

    # ── 3. Extract from HTML ────────────────────────────────────
    with track_extraction(
        domain=domain,
        strategy=ExtractionStrategy.HTTP_STATIC,
        reason_code=ReasonCode.STATIC_CAREERS_PAGE_DETECTED,
        company_id=company_id,
    ) as attempt:
        result = extract_from_html(
            html=discovery.html,
            url=discovery.final_url or discovery.url,
            domain=domain,
        )

        attempt.success = result.success
        attempt.jobs_found = result.jobs_count
        attempt.positions_count = result.open_positions_count
        attempt.evidence_quality = result.evidence_quality
        attempt.careers_url = result.careers_url

    # ── 4. Check confidence threshold ───────────────────────────
    if result.confidence < MIN_ACCEPTANCE_CONFIDENCE and result.success:
        result.reason_code = ReasonCode.HTTP_PARSE_LOW_CONFIDENCE
        logger.info(
            f"[HTTPStatic] {domain}: low confidence ({result.confidence:.2f}), "
            f"caller should consider Playwright fallback"
        )

    return result


# ── Playwright extraction (Phase 5) ────────────────────────────────

def try_playwright_extraction(
    domain: str,
    careers_url: Optional[str] = None,
    company_name: Optional[str] = None,
    company_id: Optional[UUID] = None,
    fallback_from: Optional[ExtractionStrategy] = None,
    fallback_reason: Optional[ReasonCode] = None,
) -> NormalizedJobsResult:
    """Execute Playwright extraction with budget controls.

    This is synchronous — it manages the async event loop internally.
    Always returns a NormalizedJobsResult (check .success and .error).
    """
    from app.extraction.playwright_fallback import run_playwright_extraction

    with track_extraction(
        domain=domain,
        strategy=ExtractionStrategy.PLAYWRIGHT,
        reason_code=fallback_reason or ReasonCode.PLAYWRIGHT_REQUIRED,
        company_id=company_id,
        fallback_from=fallback_from,
    ) as attempt:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                run_playwright_extraction(
                    domain=domain,
                    careers_url=careers_url,
                    company_name=company_name,
                    company_id=company_id,
                    fallback_from=fallback_from,
                    fallback_reason=fallback_reason,
                )
            )
        except Exception as exc:
            result = NormalizedJobsResult(
                domain=domain,
                careers_url=careers_url,
                strategy_used=ExtractionStrategy.PLAYWRIGHT,
                reason_code=ReasonCode.PLAYWRIGHT_CAPTURE_FAILED,
                fallback_from=fallback_from,
                error=f"Playwright failed: {str(exc)[:300]}",
            )
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

        attempt.success = result.success
        attempt.jobs_found = result.jobs_count
        attempt.positions_count = result.open_positions_count
        attempt.evidence_quality = result.evidence_quality
        attempt.careers_url = result.careers_url

    return result


# ── Unified extraction chain ───────────────────────────────────────

def extract_company(
    domain: str,
    company_name: Optional[str] = None,
    company_id: Optional[UUID] = None,
    detected_ats_platform: Optional[str] = None,
    detected_ats_url: Optional[str] = None,
    skip_playwright: bool = False,
) -> NormalizedJobsResult:
    """Full extraction chain: ATS → HTTP → Playwright.

    This is THE entry point for the extraction layer. It tries every
    strategy in order and returns the first successful result.

    If all strategies fail, returns a NormalizedJobsResult with
    .success=False and .error describing what happened.

    Args:
        skip_playwright: If True, stops after HTTP static (for testing
            or when Playwright is not installed).

    Returns:
        NormalizedJobsResult — always. Check .success.
    """
    careers_url_hint: Optional[str] = None
    prior_fallback_from: Optional[ExtractionStrategy] = None
    prior_reason: Optional[ReasonCode] = None

    # ── 1. Try ATS API ──────────────────────────────────────────
    if detected_ats_platform:
        ats_result = try_ats_extraction(
            domain=domain,
            company_name=company_name,
            company_id=company_id,
            detected_ats_platform=detected_ats_platform,
            detected_ats_url=detected_ats_url,
        )
        if ats_result and ats_result.success:
            logger.info(
                f"[Dispatcher] {domain}: RESOLVED via ATS_API "
                f"({ats_result.jobs_count} jobs)"
            )
            return ats_result

        if ats_result:
            prior_fallback_from = ExtractionStrategy.ATS_API
            prior_reason = ReasonCode.FALLBACK_FROM_ATS_API
            careers_url_hint = ats_result.careers_url

    # ── 2. Try HTTP Static ──────────────────────────────────────
    http_result = try_http_static_extraction(
        domain=domain,
        company_name=company_name,
        company_id=company_id,
    )

    if http_result and http_result.success and http_result.confidence >= 0.4:
        logger.info(
            f"[Dispatcher] {domain}: RESOLVED via HTTP_STATIC "
            f"({http_result.jobs_count} jobs, "
            f"confidence={http_result.confidence:.2f})"
        )
        return http_result

    # Capture context for Playwright
    if http_result:
        careers_url_hint = http_result.careers_url or careers_url_hint
        if http_result.reason_code == ReasonCode.SPA_CONTENT_EMPTY:
            prior_fallback_from = ExtractionStrategy.HTTP_STATIC
            prior_reason = ReasonCode.SPA_CONTENT_EMPTY
        elif http_result.success and http_result.confidence < 0.4:
            prior_fallback_from = ExtractionStrategy.HTTP_STATIC
            prior_reason = ReasonCode.HTTP_PARSE_LOW_CONFIDENCE
        else:
            prior_fallback_from = prior_fallback_from or ExtractionStrategy.HTTP_STATIC
            prior_reason = prior_reason or ReasonCode.FALLBACK_FROM_HTTP_STATIC

    # ── 3. Playwright fallback ──────────────────────────────────
    if skip_playwright:
        logger.info(
            f"[Dispatcher] {domain}: Playwright skipped (skip_playwright=True)"
        )
        # Return best partial result or empty
        if http_result and http_result.success:
            return http_result
        return NormalizedJobsResult(
            domain=domain,
            strategy_used=ExtractionStrategy.PLAYWRIGHT,
            reason_code=prior_reason or ReasonCode.PLAYWRIGHT_REQUIRED,
            error="Playwright skipped by caller",
        )

    logger.info(
        f"[Dispatcher] {domain}: escalating to PLAYWRIGHT "
        f"(fallback_from={prior_fallback_from.value if prior_fallback_from else 'none'}, "
        f"reason={prior_reason.value if prior_reason else 'none'})"
    )

    pw_result = try_playwright_extraction(
        domain=domain,
        careers_url=careers_url_hint,
        company_name=company_name,
        company_id=company_id,
        fallback_from=prior_fallback_from,
        fallback_reason=prior_reason or ReasonCode.PLAYWRIGHT_REQUIRED,
    )

    if pw_result.success:
        logger.info(
            f"[Dispatcher] {domain}: RESOLVED via PLAYWRIGHT "
            f"({pw_result.jobs_count} jobs, "
            f"quality={pw_result.evidence_quality})"
        )
    else:
        logger.warning(
            f"[Dispatcher] {domain}: ALL STRATEGIES FAILED — "
            f"error={pw_result.error}"
        )

    return pw_result


# ── Utility ─────────────────────────────────────────────────────────

def detect_ats_from_html(html: str) -> Optional[str]:
    """Scan HTML for ATS embed markers. Returns platform name or None."""
    from app.extraction.adapters import ATS_ADAPTERS

    for platform, adapter in ATS_ADAPTERS.items():
        if adapter.detect(html):
            return platform.value
    return None
