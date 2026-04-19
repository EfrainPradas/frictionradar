"""Extraction strategies and reason codes.

These enums are the shared vocabulary between the router, extractors,
instrumentation, and persistence layers.
"""

from enum import Enum


class ExtractionStrategy(str, Enum):
    """How we extract careers data from a company."""

    ATS_API = "ats_api"
    """Direct HTTP call to a known ATS JSON endpoint (Greenhouse, Lever, etc.)."""

    HTTP_STATIC = "http_static"
    """Standard HTTP GET + HTML parsing on a static or server-rendered careers page."""

    PLAYWRIGHT = "playwright"
    """Full browser rendering for JS-heavy / SPA careers pages."""


class ReasonCode(str, Enum):
    """Why the router chose a particular strategy."""

    # ── ATS_API reasons ─────────────────────────────────────────────
    KNOWN_ATS_JSON_AVAILABLE = "known_ats_json_available"
    """ATS platform detected with a guessable JSON endpoint (e.g. Greenhouse boards API)."""

    ATS_DETECTED_NO_TEMPLATE = "ats_detected_no_template"
    """ATS platform detected in HTML but no URL template available (e.g. Workday, iCIMS)."""

    # ── HTTP_STATIC reasons ─────────────────────────────────────────
    STATIC_CAREERS_PAGE_DETECTED = "static_careers_page_detected"
    """Careers page found and responds with rich HTML (not a JS shell)."""

    CAREERS_URL_FOUND_UNTESTED = "careers_url_found_untested"
    """Careers URL discovered but not yet verified for content quality."""

    # ── PLAYWRIGHT reasons ──────────────────────────────────────────
    SPA_CONTENT_EMPTY = "spa_content_empty"
    """HTTP response was a JS shell with little visible text — needs browser rendering."""

    HTTP_PARSE_LOW_CONFIDENCE = "http_parse_low_confidence"
    """HTTP extraction ran but produced very few or low-confidence signals."""

    PLAYWRIGHT_REQUIRED = "playwright_required"
    """No ATS detected, no static page found, or all cheaper strategies failed."""

    NO_CAREERS_URL_FOUND = "no_careers_url_found"
    """Could not discover any careers URL — Playwright will attempt path probing."""

    # ── Cache reasons ───────────────────────────────────────────────
    CACHE_FRESH = "cache_fresh"
    """Valid cached extraction exists and is within TTL."""

    # ── Fallback reasons ────────────────────────────────────────────
    FALLBACK_FROM_ATS_API = "fallback_from_ats_api"
    """ATS API extraction failed or returned empty — falling back."""

    FALLBACK_FROM_HTTP_STATIC = "fallback_from_http_static"
    """HTTP static extraction was insufficient — falling back."""

    # ── Playwright-specific reasons ─────────────────────────────────
    PLAYWRIGHT_BUDGET_EXCEEDED = "playwright_budget_exceeded"
    """Playwright was needed but budget (max attempts or timeout) was exhausted."""

    PLAYWRIGHT_CAPTURE_FAILED = "playwright_capture_failed"
    """Browser launched but page capture failed (timeout, crash, navigation error)."""

    PLAYWRIGHT_EMPTY_RESULT = "playwright_empty_result"
    """Page captured but hybrid extractor found no usable evidence."""

    PLAYWRIGHT_NOT_AVAILABLE = "playwright_not_available"
    """Playwright browser not installed or failed to launch."""


class ATSPlatform(str, Enum):
    """Known ATS platforms with potential direct API access."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    JOBVITE = "jobvite"
    ICIMS = "icims"
    WORKDAY = "workday"
    MYWORKDAYJOBS = "myworkdayjobs"


# Platforms where we can build a JSON API URL from a slug.
# Others (workday, icims) require Playwright because URLs are too variable.
ATS_WITH_JSON_API = {
    ATSPlatform.GREENHOUSE,
    ATSPlatform.LEVER,
    ATSPlatform.ASHBY,
    ATSPlatform.SMARTRECRUITERS,
    ATSPlatform.JOBVITE,
}
