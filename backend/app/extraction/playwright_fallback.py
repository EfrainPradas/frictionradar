"""Playwright fallback — hardened, budgeted browser extraction.

This is the LAST resort in the extraction chain:
    ATS API  →  HTTP Static  →  **Playwright**

It wraps the existing BrowserCaptureService + hybrid_careers_extractor
with budget controls, timeout enforcement, and structured reason codes.

The wrapper does NOT modify the capture or extraction internals.
It adds:
  - Hard timeout (per-company budget)
  - Max redirect / retry awareness
  - Clean error categorization
  - NormalizedJobsResult output (same contract as ATS and HTTP)
  - Reason code for WHY Playwright was invoked
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from app.extraction.constants import ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Budget defaults ─────────────────────────────────────────────────

@dataclass(frozen=True)
class PlaywrightBudget:
    """Per-company resource limits for Playwright extraction."""

    timeout_s: int = 45
    """Hard wall-clock timeout for the entire Playwright operation.
    Raised 20s→45s to accommodate heavy SPAs (F3a-Bug-A)."""

    capture_timeout_ms: int = 35000
    """Timeout passed to BrowserCaptureService.capture_page().
    Raised 15s→35s so SPAs actually have time to hydrate within the wall clock."""

    retry_capture_timeout_ms: int = 25000
    """Timeout for the retry attempt when initial capture is short."""

    max_attempts: int = 1
    """How many Playwright capture attempts per company (1 = no retry loop)."""

    min_html_chars: int = 200
    """Minimum rendered HTML length to consider capture successful."""


DEFAULT_BUDGET = PlaywrightBudget()


async def run_playwright_extraction(
    domain: str,
    careers_url: Optional[str] = None,
    company_name: Optional[str] = None,
    company_id: Optional[UUID] = None,
    fallback_from: Optional[ExtractionStrategy] = None,
    fallback_reason: Optional[ReasonCode] = None,
    budget: PlaywrightBudget = DEFAULT_BUDGET,
) -> NormalizedJobsResult:
    """Execute Playwright extraction with budget controls.

    This is an async function. The caller (dispatcher) handles
    the async→sync bridge.

    Args:
        domain: Company domain.
        careers_url: Pre-discovered careers URL (skip URL discovery if provided).
        company_name: For logging and slug generation.
        company_id: For logging.
        fallback_from: Which strategy failed before this.
        fallback_reason: Why the previous strategy failed.
        budget: Resource limits.

    Returns:
        NormalizedJobsResult — always. Check .success and .error.
    """
    t0 = time.monotonic()

    # ── Build the base result shell ─────────────────────────────
    result = NormalizedJobsResult(
        domain=domain,
        careers_url=careers_url,
        strategy_used=ExtractionStrategy.PLAYWRIGHT,
        reason_code=fallback_reason or ReasonCode.PLAYWRIGHT_REQUIRED,
        fallback_from=fallback_from,
    )

    # ── Import heavy dependencies lazily ────────────────────────
    try:
        from app.services.browser_capture_service import BrowserCaptureService
        from app.services.hybrid_careers_extractor import hybrid_careers_extractor
    except ImportError as exc:
        result.error = f"Playwright not available: {exc}"
        result.reason_code = ReasonCode.PLAYWRIGHT_NOT_AVAILABLE
        result.duration_ms = _elapsed_ms(t0)
        logger.warning(f"[Playwright] {domain}: {result.error}")
        return result

    # ── Step 1: Discover careers URL if not provided ────────────
    if not careers_url:
        try:
            from app.services.collection_orchestrator import find_careers_url
            careers_url = await asyncio.wait_for(
                find_careers_url(domain),
                timeout=budget.timeout_s / 2,
            )
        except asyncio.TimeoutError:
            result.error = "Timeout during careers URL discovery"
            result.reason_code = ReasonCode.PLAYWRIGHT_CAPTURE_FAILED
            result.duration_ms = _elapsed_ms(t0)
            return result
        except Exception as exc:
            result.error = f"URL discovery failed: {str(exc)[:200]}"
            result.reason_code = ReasonCode.PLAYWRIGHT_CAPTURE_FAILED
            result.duration_ms = _elapsed_ms(t0)
            return result

    if not careers_url:
        result.error = "No careers URL found"
        result.reason_code = ReasonCode.NO_CAREERS_URL_FOUND
        result.duration_ms = _elapsed_ms(t0)
        return result

    result.careers_url = careers_url

    # ── Step 2: Capture with budget enforcement ─────────────────
    service = BrowserCaptureService()

    try:
        await asyncio.wait_for(
            service.initialize(),
            timeout=15,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        result.error = f"Browser launch failed: {str(exc)[:200]}"
        result.reason_code = ReasonCode.PLAYWRIGHT_NOT_AVAILABLE
        result.duration_ms = _elapsed_ms(t0)
        logger.warning(f"[Playwright] {domain}: {result.error}")
        return result

    try:
        # Check wall-clock budget before capture
        remaining_s = budget.timeout_s - (time.monotonic() - t0)
        if remaining_s < 5:
            result.error = "Budget exhausted before capture"
            result.reason_code = ReasonCode.PLAYWRIGHT_BUDGET_EXCEEDED
            result.duration_ms = _elapsed_ms(t0)
            return result

        # Primary capture
        capture_timeout = min(budget.capture_timeout_ms, int(remaining_s * 1000))
        capture = await asyncio.wait_for(
            service.capture_page(
                url=careers_url,
                timeout_ms=capture_timeout,
                intercept_network=True,
            ),
            timeout=remaining_s,
        )

        if capture.error:
            result.error = f"Capture error: {capture.error[:200]}"
            result.reason_code = ReasonCode.PLAYWRIGHT_CAPTURE_FAILED
            result.duration_ms = _elapsed_ms(t0)
            return result

        # ── Retry if initial capture is too short ───────────────
        if not capture.rendered_html or len(capture.rendered_html) < budget.min_html_chars:
            remaining_s = budget.timeout_s - (time.monotonic() - t0)
            if remaining_s > 8 and budget.max_attempts > 0:
                logger.info(
                    f"[Playwright] {domain}: short HTML "
                    f"({len(capture.rendered_html or '')} chars), "
                    f"retrying with networkidle"
                )
                try:
                    retry_timeout = min(
                        budget.retry_capture_timeout_ms,
                        int(remaining_s * 1000) - 2000,
                    )
                    page = await service._context.new_page()
                    await page.goto(
                        careers_url,
                        wait_until="networkidle",
                        timeout=retry_timeout,
                    )
                    # Wait for job selectors
                    for selector in [
                        "[data-testid='job']", ".job-card", ".posting",
                        ".job-listing", "[class*='job']", "[class*='posting']",
                    ]:
                        try:
                            await page.wait_for_selector(selector, timeout=5000)
                            break
                        except Exception:
                            continue

                    retry_html = await page.content()
                    retry_text = await page.evaluate(
                        "document.body?.innerText || ''"
                    )
                    if len(retry_html) > len(capture.rendered_html or ""):
                        capture.rendered_html = retry_html
                        capture.visible_text = retry_text
                    await page.close()
                except Exception as retry_err:
                    logger.debug(
                        f"[Playwright] {domain}: retry failed: {retry_err}"
                    )

        # ── Final HTML check ────────────────────────────────────
        if not capture.rendered_html or len(capture.rendered_html) < budget.min_html_chars:
            result.error = (
                f"Empty page after capture "
                f"({len(capture.rendered_html or '')} chars)"
            )
            result.reason_code = ReasonCode.PLAYWRIGHT_EMPTY_RESULT
            result.duration_ms = _elapsed_ms(t0)
            return result

        # ── Step 3: Hybrid extraction ───────────────────────────
        remaining_s = budget.timeout_s - (time.monotonic() - t0)
        if remaining_s < 2:
            result.error = "Budget exhausted before extraction"
            result.reason_code = ReasonCode.PLAYWRIGHT_BUDGET_EXCEEDED
            result.duration_ms = _elapsed_ms(t0)
            return result

        extraction = await asyncio.wait_for(
            hybrid_careers_extractor.extract(
                rendered_html=capture.rendered_html,
                visible_text=capture.visible_text,
                visible_links=capture.visible_links,
                network_requests=capture.network_requests,
                network_responses=capture.network_responses,
                embedded_json=capture.embedded_json,
                page_state=capture.page_state,
                source_url=capture.final_url or careers_url,
                preload_state=capture.preload_state,
            ),
            timeout=remaining_s,
        )

        # ── Step 4: Convert to NormalizedJobsResult ─────────────
        result = _convert_extraction(
            extraction=extraction,
            capture=capture,
            domain=domain,
            careers_url=careers_url,
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
        )
        result.duration_ms = _elapsed_ms(t0)

        logger.info(
            f"[Playwright] {domain}: complete — "
            f"jobs={result.jobs_count}, "
            f"positions={result.open_positions_count}, "
            f"quality={result.evidence_quality}, "
            f"duration={result.duration_ms}ms"
        )

        return result

    except asyncio.TimeoutError:
        result.error = f"Hard timeout ({budget.timeout_s}s) exceeded"
        result.reason_code = ReasonCode.PLAYWRIGHT_BUDGET_EXCEEDED
        result.duration_ms = _elapsed_ms(t0)
        logger.warning(f"[Playwright] {domain}: {result.error}")
        return result

    except Exception as exc:
        result.error = f"Unexpected error: {str(exc)[:300]}"
        result.reason_code = ReasonCode.PLAYWRIGHT_CAPTURE_FAILED
        result.duration_ms = _elapsed_ms(t0)
        logger.error(f"[Playwright] {domain}: {result.error}")
        return result

    finally:
        try:
            await service.cleanup()
        except Exception:
            pass


# ── Helpers ─────────────────────────────────────────────────────────

def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _convert_extraction(
    extraction,
    capture,
    domain: str,
    careers_url: str,
    fallback_from: Optional[ExtractionStrategy],
    fallback_reason: Optional[ReasonCode],
) -> NormalizedJobsResult:
    """Convert a HybridExtractionResult into NormalizedJobsResult."""

    jobs: List[NormalizedJob] = []
    hiring_areas: List[str] = []
    locations: List[str] = set()

    if extraction.visible_role_cards:
        for card in extraction.visible_role_cards:
            jobs.append(NormalizedJob(
                title=card.title,
                location=card.location,
                department=card.area,
                job_url=card.job_url,
            ))
            if card.location:
                locations.add(card.location)

    if extraction.visible_hiring_areas:
        hiring_areas = list(extraction.visible_hiring_areas)

    positions = extraction.open_positions_count

    # Assess quality
    if len(jobs) >= 5 or (positions and positions >= 10):
        quality = "high"
        confidence = 0.9
    elif len(jobs) >= 1 or (positions and positions > 0):
        quality = "moderate"
        confidence = 0.7
    elif hiring_areas:
        quality = "limited"
        confidence = 0.4
    else:
        quality = "none"
        confidence = 0.0

    success = positions is not None or len(jobs) > 0 or len(hiring_areas) > 0

    return NormalizedJobsResult(
        domain=domain,
        careers_url=capture.final_url or careers_url,
        strategy_used=ExtractionStrategy.PLAYWRIGHT,
        reason_code=fallback_reason or ReasonCode.PLAYWRIGHT_REQUIRED,
        fallback_from=fallback_from,
        open_positions_count=positions,
        jobs=jobs,
        hiring_areas=hiring_areas,
        locations=sorted(locations),
        evidence_quality=quality,
        confidence=confidence,
        error=None if success else "No evidence extracted",
    )
