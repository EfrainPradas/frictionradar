"""Company Site Collector — improved homepage scanner.

Now uses careers_url_finder to detect careers links and ATS embeds
from the homepage, instead of a simplistic keyword match.
"""

import re
import urllib3
from typing import List

import requests
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.collectors.careers_url_finder import (
    _detect_ats_in_html,
    _extract_careers_links_from_html,
    _has_job_elements,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.models.company import Company
from app.schemas.signal import SignalCreate

logger = get_logger(__name__)

urllib3.disable_warnings()

# Keywords that suggest operational friction / growth
FRICTION_KEYWORDS = {
    "revops": ("revops_language_detected", "Detected Revenue Operations language on the homepage."),
    "revenue operations": ("revops_language_detected", "Detected Revenue Operations language on the homepage."),
    "scaling": ("scaling_language_detected", "Detected scaling/growth language on the homepage."),
    "rapidly growing": ("scaling_language_detected", "Detected scaling/growth language on the homepage."),
    "growing fast": ("scaling_language_detected", "Detected scaling/growth language on the homepage."),
    "hiring": ("hiring_language_detected", "Detected hiring language on the homepage."),
    "we're hiring": ("hiring_language_detected", "Detected hiring language on the homepage."),
    "we are hiring": ("hiring_language_detected", "Detected hiring language on the homepage."),
    "open positions": ("hiring_language_detected", "Detected open positions language on the homepage."),
    "multiple teams": ("cross_team_language_detected", "Detected cross-team/multi-team language on the homepage."),
    "cross-functional": ("cross_team_language_detected", "Detected cross-functional language on the homepage."),
}


class CompanySiteCollector(BaseCollector):
    """Scans the company homepage for careers links, ATS patterns, and friction signals."""

    collector_type = "company_site"

    def collect(self, company: Company) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        if not company.domain:
            return signals

        protocol = "https://" if not company.domain.startswith("http") else ""
        target_url = f"{protocol}{company.domain}"

        try:
            headers = {"User-Agent": settings.DEFAULT_USER_AGENT}
            response = requests.get(
                target_url, headers=headers, timeout=5, verify=False
            )
            if response.status_code != 200:
                logger.info(f"[CompanySite] {company.domain}: homepage HTTP {response.status_code}")
                return signals
        except Exception as e:
            logger.warning(f"[CompanySite] {company.domain}: homepage fetch FAILED: {e}")
            return signals

        html = response.text
        text_lower = html.lower()
        final_url = response.url

        # ── Signal 1: Careers page link detected ─────────────────────
        careers_links = _extract_careers_links_from_html(html, final_url)
        if careers_links:
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=target_url,
                    signal_type="careers_page_found",
                    signal_text=f"Found careers link: {careers_links[0]}",
                    confidence=0.9,
                )
            )

        # ── Signal 2: ATS platform embed detected ────────────────────
        ats_platform = _detect_ats_in_html(html)
        if ats_platform:
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=target_url,
                    signal_type=f"ats_embed_detected_{ats_platform}",
                    signal_text=f"Detected {ats_platform} ATS embed on homepage.",
                    confidence=0.85,
                )
            )

        # ── Signal 3: Friction/growth keywords ──────────────────────
        seen_types = set()
        for keyword, (signal_type, signal_text) in FRICTION_KEYWORDS.items():
            if keyword in text_lower and signal_type not in seen_types:
                signals.append(
                    SignalCreate(
                        source_type=self.collector_type,
                        source_url=target_url,
                        signal_type=signal_type,
                        signal_text=signal_text,
                        confidence=0.6,
                    )
                )
                seen_types.add(signal_type)

        # ── Signal 4: Company size hints from homepage ───────────────
        size_match = re.search(
            r"(\d{3,4})\s*(?:employees?|people|team members?)",
            text_lower,
        )
        if size_match:
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=target_url,
                    signal_type="company_size_detected",
                    signal_text=f"Company size hint: ~{size_match.group(1)} employees",
                    numeric_value=int(size_match.group(1)),
                    confidence=0.5,
                )
            )

        return signals
