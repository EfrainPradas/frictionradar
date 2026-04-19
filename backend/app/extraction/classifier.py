"""Static vs SPA page classifier.

Analyzes raw HTML to determine if a careers page can be meaningfully
parsed without JavaScript rendering.

Classification levels:
  - static_rich:   Lots of visible job content in HTML. Parse with HTTP.
  - static_sparse: Some content but thin. Parse with HTTP, expect low confidence.
  - spa_shell:     Empty shell, hydration markers. Needs Playwright.
  - unknown:       Can't determine. Default to Playwright.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PageClassification:
    """Result of classifying a page as static vs SPA."""

    page_type: str  # static_rich, static_sparse, spa_shell, unknown
    confidence: float  # 0.0–1.0
    reason: str  # Human-readable explanation

    # Evidence
    visible_text_length: int = 0
    job_card_anchors: int = 0
    has_json_ld: bool = False
    has_empty_root: bool = False
    has_hydration_markers: bool = False
    script_ratio: float = 0.0  # % of page that is <script> tags


# ── SPA detection patterns ──────────────────────────────────────────

# Common SPA shell indicators
SPA_ROOT_PATTERNS = [
    r'<div\s+id=["\'](?:root|app|__next|__nuxt|main-app)["\']>\s*</div>',
    r'<div\s+id=["\'](?:root|app|__next|__nuxt)["\']>\s*\n?\s*</div>',
]

HYDRATION_MARKERS = [
    "window.__NEXT_DATA__",
    "window.__NUXT__",
    "__INITIAL_STATE__",
    "window.__APP_DATA__",
    "data-reactroot",
    "data-server-rendered",
    "ng-app",
    "ng-version",
    "data-v-",  # Vue scoped CSS
]

# ── Job content patterns ────────────────────────────────────────────

# Anchors that look like job listing links
JOB_ANCHOR_PATTERN = re.compile(
    r'<a\s[^>]*href=["\'][^"\']*["\'][^>]*>[^<]{5,120}</a>',
    re.IGNORECASE,
)

# Patterns suggesting real job cards in HTML
JOB_CARD_PATTERNS = [
    r'class="[^"]*(?:job-card|job-listing|job-item|posting-item|position-card|career-item)[^"]*"',
    r"class='[^']*(?:job-card|job-listing|job-item|posting-item|position-card|career-item)[^']*'",
    r'data-testid="(?:job|posting|position)"',
    r'itemtype="https?://schema\.org/JobPosting"',
]

JSON_LD_JOB_PATTERN = re.compile(
    r'<script\s+type=["\']application/ld\+json["\'][^>]*>.*?JobPosting.*?</script>',
    re.IGNORECASE | re.DOTALL,
)


def classify_page(html: str) -> PageClassification:
    """Classify a careers page as static-parseable or SPA-shell.

    Args:
        html: Raw HTML response from an HTTP GET.

    Returns:
        PageClassification with type, confidence, and evidence.
    """
    if not html or len(html) < 100:
        return PageClassification(
            page_type="unknown",
            confidence=0.0,
            reason="Empty or near-empty HTML response",
            visible_text_length=len(html),
        )

    html_lower = html.lower()

    # ── Measure evidence ────────────────────────────────────────
    visible_text = _estimate_visible_text(html)
    visible_len = len(visible_text)

    # Count job-related anchors
    job_anchors = _count_job_anchors(html)

    # Check for structured job data
    has_json_ld = bool(JSON_LD_JOB_PATTERN.search(html))
    job_card_count = sum(
        1 for p in JOB_CARD_PATTERNS if re.search(p, html, re.I)
    )

    # Check for SPA indicators
    has_empty_root = any(
        re.search(p, html, re.I) for p in SPA_ROOT_PATTERNS
    )
    hydration_count = sum(
        1 for m in HYDRATION_MARKERS if m.lower() in html_lower
    )
    has_hydration = hydration_count >= 1

    # Script ratio
    script_content = re.findall(r'<script[^>]*>.*?</script>', html, re.I | re.DOTALL)
    script_len = sum(len(s) for s in script_content)
    script_ratio = script_len / max(len(html), 1)

    # ── Score ───────────────────────────────────────────────────
    static_score = 0.0
    spa_score = 0.0

    # Static evidence
    if visible_len > 2000:
        static_score += 0.25
    elif visible_len > 500:
        static_score += 0.1

    if job_anchors >= 10:
        static_score += 0.4
    elif job_anchors >= 5:
        static_score += 0.35
    elif job_anchors >= 2:
        static_score += 0.2

    if has_json_ld:
        static_score += 0.2

    if job_card_count >= 2:
        static_score += 0.15
    elif job_card_count >= 1:
        static_score += 0.1

    # SPA evidence
    if has_empty_root:
        spa_score += 0.4

    if hydration_count >= 2:
        spa_score += 0.3
    elif has_hydration:
        spa_score += 0.15

    if script_ratio > 0.6:
        spa_score += 0.2
    elif script_ratio > 0.4:
        spa_score += 0.1

    if visible_len < 200 and len(html) > 5000:
        # Lots of HTML but very little visible text → JS shell
        spa_score += 0.3

    # ── Decide ──────────────────────────────────────────────────
    if spa_score > 0.5 and static_score < 0.3:
        return PageClassification(
            page_type="spa_shell",
            confidence=min(spa_score, 1.0),
            reason=f"SPA shell detected (empty_root={has_empty_root}, hydration={hydration_count}, script_ratio={script_ratio:.0%})",
            visible_text_length=visible_len,
            job_card_anchors=job_anchors,
            has_json_ld=has_json_ld,
            has_empty_root=has_empty_root,
            has_hydration_markers=has_hydration,
            script_ratio=script_ratio,
        )

    if static_score >= 0.44:
        return PageClassification(
            page_type="static_rich",
            confidence=min(static_score, 1.0),
            reason=f"Rich static content (text={visible_len}, anchors={job_anchors}, json_ld={has_json_ld}, cards={job_card_count})",
            visible_text_length=visible_len,
            job_card_anchors=job_anchors,
            has_json_ld=has_json_ld,
            has_empty_root=has_empty_root,
            has_hydration_markers=has_hydration,
            script_ratio=script_ratio,
        )

    if static_score >= 0.2:
        return PageClassification(
            page_type="static_sparse",
            confidence=min(static_score, 1.0),
            reason=f"Sparse static content (text={visible_len}, anchors={job_anchors})",
            visible_text_length=visible_len,
            job_card_anchors=job_anchors,
            has_json_ld=has_json_ld,
            has_empty_root=has_empty_root,
            has_hydration_markers=has_hydration,
            script_ratio=script_ratio,
        )

    return PageClassification(
        page_type="unknown",
        confidence=0.0,
        reason=f"Indeterminate (static_score={static_score:.2f}, spa_score={spa_score:.2f})",
        visible_text_length=visible_len,
        job_card_anchors=job_anchors,
        has_json_ld=has_json_ld,
        has_empty_root=has_empty_root,
        has_hydration_markers=has_hydration,
        script_ratio=script_ratio,
    )


def _estimate_visible_text(html: str) -> str:
    """Rough estimate of visible text by stripping tags and scripts."""
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.I | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.I | re.DOTALL)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _count_job_anchors(html: str) -> int:
    """Count anchor tags that look like job listing links."""
    anchors = JOB_ANCHOR_PATTERN.findall(html)
    job_keywords = {"engineer", "manager", "analyst", "developer", "designer",
                    "coordinator", "director", "specialist", "associate",
                    "lead", "senior", "junior", "intern", "apply"}
    count = 0
    for a in anchors:
        a_lower = a.lower()
        if any(kw in a_lower for kw in job_keywords):
            count += 1
    return count
