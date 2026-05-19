"""Newsroom Collector — improved with homepage link discovery and multi-path fallback."""

import re
from typing import List, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_ssl_verify
from app.models.company import Company
from app.schemas.signal import SignalCreate

logger = get_logger(__name__)

NEWS_PATHS = ["/news", "/newsroom", "/press", "/about/news", "/blog", "/insights",
              "/media", "/press-releases", "/about/newsroom", "/company/news"]

GROWTH_KEYWORDS = [
    ("expanding", "expansion_language_detected", "Expansion/growth language detected in news."),
    ("new office", "expansion_language_detected", "New office announcement detected."),
    ("opening", "expansion_language_detected", "Opening/expansion language detected."),
    ("funding", "funding_detected", "Funding language detected in news."),
    ("investment", "funding_detected", "Investment language detected in news."),
    ("raised", "funding_detected", "Fundraising announcement detected."),
    ("acquired", "acquisition_detected", "Acquisition language detected."),
    ("acquisition", "acquisition_detected", "Acquisition language detected."),
    ("reporting", "reporting_language_detected", "Reporting language detected in news."),
    ("quarterly", "reporting_language_detected", "Quarterly reporting language detected."),
    ("partnership", "partnership_detected", "Partnership language detected."),
    ("strategic", "partnership_detected", "Strategic language detected."),
    ("growing", "growth_language_detected", "Growth language detected in news."),
    ("hiring", "hiring_news_detected", "Hiring mentioned in news."),
    ("scale", "growth_language_detected", "Scaling language detected in news."),
]


class NewsroomCollector(BaseCollector):
    """Scans news/blog pages for growth, funding, and operational signals."""

    collector_type = "newsroom"

    def collect(self, company: Company) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        if not company.domain:
            return signals

        domain = company.domain.strip().lower()
        if domain.startswith("http"):
            domain = urlparse(domain).netloc or domain.split("/")[0]

        # Strategy 1: Discover news/blog links from homepage
        discovered_url = self._discover_from_homepage(domain)
        if discovered_url:
            page_signals = self._scan_page(discovered_url)
            if page_signals:
                return page_signals

        # Strategy 2: Try known paths
        for path in NEWS_PATHS:
            url = f"https://{domain}{path}"
            page_signals = self._scan_page(url)
            if page_signals:
                signals.extend(page_signals)
                break

        return signals

    def _discover_from_homepage(self, domain: str) -> Optional[str]:
        """Scan homepage HTML for links to news/blog/press pages."""
        try:
            resp = requests.get(
                f"https://{domain}",
                headers={"User-Agent": settings.DEFAULT_USER_AGENT},
                timeout=5, verify=get_ssl_verify(),
            )
            if resp.status_code != 200:
                return None

            # Look for links containing news/blog/press keywords
            pattern = r'href=["\']([^"\']*(?:news|blog|press|media|insight|article)[^"\']*)["\']'
            matches = re.findall(pattern, resp.text, re.IGNORECASE)

            exclude = ["newsletter", "login", "signin", "subscribe", "cookie", "privacy"]
            base = f"https://{domain}"

            for href in matches:
                href_lower = href.lower()
                if any(w in href_lower for w in exclude):
                    continue
                if href.startswith("/"):
                    return urljoin(base, href)
                elif href.startswith("http"):
                    return href
        except Exception:
            pass
        return None

    def _scan_page(self, url: str) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        try:
            headers = {"User-Agent": settings.DEFAULT_USER_AGENT}
            response = requests.get(url, headers=headers, timeout=5, verify=get_ssl_verify())
            if response.status_code != 200:
                return signals
        except Exception:
            return signals

        html = response.text
        text_lower = html.lower()

        # Signal: Newsroom/blog page found
        if any(kw in text_lower for kw in ["press release", "news", "blog post", "article"]):
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=url,
                    signal_type="newsroom_found",
                    signal_text=f"News/Blog page found: {url}",
                    confidence=0.9,
                )
            )

        # Growth/funding/operational signals
        seen_types = set()
        for keyword, signal_type, signal_text in GROWTH_KEYWORDS:
            if keyword in text_lower and signal_type not in seen_types:
                signals.append(
                    SignalCreate(
                        source_type=self.collector_type,
                        source_url=url,
                        signal_type=signal_type,
                        signal_text=signal_text,
                        confidence=0.6,
                    )
                )
                seen_types.add(signal_type)

        return signals
