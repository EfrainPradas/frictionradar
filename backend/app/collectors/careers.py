"""Careers Collector — improved with multi-path URL discovery.

Uses careers_url_finder to find the careers page, then extracts
hiring category signals and job count indicators.
"""

import re
from typing import List

import requests
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.collectors.careers_url_finder import careers_url_finder
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_ssl_verify
from app.models.company import Company
from app.schemas.signal import SignalCreate

logger = get_logger(__name__)

CATEGORY_KEYWORDS = {
    "retail": ["retail", "store", "cashier", "sales floor", "associate"],
    "distribution": ["distribution", "warehouse", "fulfillment", "logistics", "shipping"],
    "manufacturing": ["manufacturing", "production", "factory", "assembly"],
    "technology": ["technology", "tech", "engineering", "software", "it", "data"],
    "supply_chain": ["supply chain", "procurement", "sourcing"],
    "marketing": ["marketing", "digital marketing", "brand", "content"],
    "sales": ["sales", "account executive", "business development", "bd"],
    "finance": ["finance", "accounting", "financial", "fp&a"],
    "hr_people": ["hr", "human resources", "people", "people ops"],
    "operations": ["operations", "ops", "program management"],
    "customer_success": ["customer success", "support", "customer experience"],
    "product": ["product", "product management", "pm"],
    "design": ["design", "ux", "ui", "user experience"],
    "legal": ["legal", "compliance", "regulatory"],
    "healthcare": ["healthcare", "medical", "clinical", "nursing"],
}


class CareersCollector(BaseCollector):
    """Finds the careers page and extracts hiring signals."""

    collector_type = "careers"

    def collect(self, company: Company) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        if not company.domain:
            return signals

        # ── Step 1: Find careers URL ─────────────────────────────────
        url, strategy, meta = careers_url_finder.find(
            company.domain, company.name
        )

        if not url:
            logger.info(f"[CareersCollector] {company.domain}: no careers URL found (strategy: not_found)")
            return signals

        logger.info(
            f"Careers URL found for {company.name}: {url} (strategy: {strategy})"
        )

        # ── Step 2: Fetch the careers page ──────────────────────────
        try:
            headers = {"User-Agent": settings.DEFAULT_USER_AGENT}
            response = requests.get(url, headers=headers, timeout=5, verify=get_ssl_verify())
            if response.status_code != 200:
                return signals
        except Exception as e:
            logger.warning(f"[CareersCollector] {company.domain}: careers page fetch FAILED for {url}: {e}")
            return signals

        html = response.text
        text_content = html.lower()
        final_url = response.url

        # ── Signal: Careers page found ───────────────────────────────
        signals.append(
            SignalCreate(
                source_type=self.collector_type,
                source_url=final_url,
                signal_type="careers_page_found",
                signal_text=f"Careers page found at {final_url} (strategy: {strategy})",
                confidence=0.95,
            )
        )

        # ── Signal: Open positions count ────────────────────────────
        count = self._extract_position_count(text_content)
        if count and count > 0:
            signal_type = (
                "high_open_positions_count_detected"
                if count >= 100
                else "open_positions_count_detected"
            )
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=final_url,
                    signal_type=signal_type,
                    signal_text=f"Open positions count: {count}",
                    numeric_value=count,
                    confidence=0.85,
                )
            )

        # ── Signal: Multiple open roles phrasing ────────────────────
        if any(kw in text_content for kw in ["open roles", "open positions", "current openings"]):
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=final_url,
                    signal_type="multiple_open_roles",
                    signal_text="Found multiple open roles phrasing on careers page.",
                    confidence=0.8,
                )
            )

        # ── Signals: Hiring categories ───────────────────────────────
        seen_categories = set()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_content and category not in seen_categories:
                    signals.append(
                        SignalCreate(
                            source_type=self.collector_type,
                            source_url=final_url,
                            signal_type=f"{category}_hiring_detected",
                            signal_text=f"Detected {category.title()} hiring area.",
                            confidence=0.75,
                        )
                    )
                    seen_categories.add(category)
                    break

        # ── Signal: Job links count ─────────────────────────────────
        job_links = self._find_job_links(html, company.domain)
        if job_links:
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=final_url,
                    signal_type="job_links_extracted",
                    signal_text=f"Extracted {len(job_links)} job links from careers page.",
                    numeric_value=len(job_links),
                    confidence=0.8,
                )
            )

        # ── Signal: Analytics/data roles ────────────────────────────
        if any(kw in text_content for kw in ["data analyst", "analytics", "business intelligence", "bi analyst"]):
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=final_url,
                    signal_type="analytics_role_detected",
                    signal_text="Detected Analytics/Data roles on the careers page.",
                    confidence=0.85,
                )
            )

        return signals

    def _extract_position_count(self, text: str) -> int:
        """Try to extract an open positions count from page text."""
        patterns = [
            r"(\d{1,3}(?:,\d{3})*)\s*(?:open\s*)?(?:positions?|jobs?|roles?|openings?)",
            r"(?:open\s*)?(?:positions?|jobs?|roles?|openings?)\s*:?\s*(\d{1,3}(?:,\d{3})*)",
            r'"(?:open|available)(?:Jobs|Positions|Roles)":\s*(\d+)',
            r'"total":\s*(\d+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    num = int(m.replace(",", ""))
                    if 5 <= num <= 10000:
                        return num
                except (ValueError, TypeError):
                    continue
        return 0

    def _find_job_links(self, html: str, domain: str) -> List[str]:
        """Find job listing links in the page."""
        links = []
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()
            if any(kw in href.lower() or kw in text for kw in ["job", "role", "position", "careers"]):
                if href and 3 < len(text) < 150:
                    if href.startswith("http"):
                        links.append(href)
                    elif href.startswith("/"):
                        links.append(f"https://{domain}{href}")
        return list(set(links))[:20]


careers_collector = CareersCollector()
