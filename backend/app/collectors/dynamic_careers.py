"""Dynamic Careers Collector — fallback collector for category detection.

Activated in ACTIVE_COLLECTORS. Uses careers_url_finder to discover
the careers page, then extracts hiring categories and job count signals.
"""

import re
import urllib3
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.collectors.careers_url_finder import careers_url_finder
from app.models.company import Company
from app.schemas.signal import SignalCreate
from app.core.logging import get_logger

logger = get_logger(__name__)

urllib3.disable_warnings()

CATEGORY_KEYWORDS = {
    "retail": ["retail", "store", "cashier", "sales floor", "associate"],
    "distribution": ["distribution", "warehouse", "fulfillment", "logistics", "shipping"],
    "manufacturing": ["manufacturing", "production", "factory", "assembly"],
    "technology": ["technology", "tech", "engineering", "software", "it"],
    "supply_chain": ["supply chain", "procurement", "sourcing"],
    "marketing": ["marketing", "digital marketing", "brand"],
    "sales": ["sales", "account executive"],
    "finance": ["finance", "accounting", "financial"],
    "hr_people": ["hr", "human resources", "people"],
    "operations": ["operations", "ops", "program"],
    "customer_success": ["customer success", "support"],
}


class DynamicCareersCollector(BaseCollector):
    """Modern dynamic careers page collector."""

    collector_type = "dynamic_careers"

    def collect(self, company: Company) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        if not company.domain:
            return signals

        # Use the shared careers URL finder
        url, strategy, meta = careers_url_finder.find(company.domain, company.name)
        if not url:
            return signals

        page_data = self._extract_with_requests(url)
        if not page_data:
            return signals

        # Guard: if the page is NOT actually a careers page (no careers
        # indicators found), only emit signals we're confident about
        # (position count from structured data) — do NOT emit generic
        # category matches that would come from any company homepage.
        if not page_data.get("is_verified_careers_page", False):
            # Only emit open_positions if we found a clear count
            if page_data.get("open_positions_count"):
                count = page_data["open_positions_count"]
                signal_type = (
                    "high_open_positions_count_detected" if count > 100 else "open_positions_count_detected"
                )
                signals.append(
                    SignalCreate(
                        source_type=self.collector_type,
                        source_url=page_data.get("careers_url", ""),
                        signal_type=signal_type,
                        signal_text=f"Visible open positions: {count}",
                        numeric_value=count,
                        confidence=0.7,
                    )
                )
            return signals

        if page_data.get("open_positions_count"):
            count = page_data["open_positions_count"]
            signal_type = (
                "high_open_positions_count_detected" if count > 100 else "open_positions_count_detected"
            )
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=page_data.get("careers_url", ""),
                    signal_type=signal_type,
                    signal_text=f"Visible open positions: {count}",
                    numeric_value=count,
                    confidence=0.9,
                )
            )

        for category in page_data.get("visible_categories", []):
            category_lower = category.lower()
            for cat_key, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in category_lower for kw in keywords):
                    signals.append(
                        SignalCreate(
                            source_type=self.collector_type,
                            source_url=page_data.get("careers_url", ""),
                            signal_type=f"{cat_key}_hiring_detected",
                            signal_text=f"Visible hiring category: {category}",
                            confidence=0.8,
                        )
                    )
                    break

        if page_data.get("job_cards_count", 0) > 0:
            signals.append(
                SignalCreate(
                    source_type=self.collector_type,
                    source_url=page_data.get("careers_url", ""),
                    signal_type="job_cards_visible_detected",
                    signal_text=f"Visible job listings: {page_data['job_cards_count']} jobs",
                    numeric_value=page_data["job_cards_count"],
                    confidence=0.85,
                )
            )

        return signals

    # Indicators that confirm this is a real careers/jobs page
    CAREERS_INDICATORS = [
        "open positions", "current openings", "job openings",
        "join our team", "we're hiring", "we are hiring",
        "open roles", "career opportunities", "available positions",
        "view all jobs", "search jobs", "job listings",
        "all jobs", "all positions", "apply now",
    ]

    def _extract_with_requests(self, url: str) -> Optional[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        try:
            response = requests.get(url, headers=headers, timeout=5, allow_redirects=True, verify=False)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text()
            text_lower = page_text.lower()

            # Verify if this is actually a careers page
            is_careers = any(kw in text_lower for kw in self.CAREERS_INDICATORS)
            # Also check if URL itself suggests careers
            url_lower = response.url.lower()
            if any(kw in url_lower for kw in ["career", "job", "hiring", "join", "talent", "openings"]):
                is_careers = True

            open_positions = self._find_position_count(page_text)
            categories = self._find_categories(response.text) if is_careers else []
            job_links = self._find_job_links(soup, response.url)

            if open_positions or categories or job_links:
                return {
                    "careers_url": response.url,
                    "open_positions_count": open_positions,
                    "visible_categories": categories,
                    "job_cards_count": len(job_links),
                    "job_links": job_links,
                    "is_verified_careers_page": is_careers,
                }
        except Exception:
            pass

        return None

    def _find_position_count(self, text: str) -> int:
        patterns = [
            r"(\d{1,3}(?:,\d{3})*)\s*(?:open\s*)?positions?",
            r"(\d+)\s*(?:available|open)\s*(?:jobs|positions)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    num = int(m.replace(",", ""))
                    if 10 < num < 10000:
                        return num
                except (ValueError, TypeError):
                    continue
        return 0

    def _find_categories(self, text: str) -> List[str]:
        categories: List[str] = []
        text_lower = text.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    cat_name = category.replace("_", " ").title()
                    if cat_name not in categories:
                        categories.append(cat_name)
                    break
        return categories[:8]

    def _find_job_links(self, soup, base_url: str) -> List[str]:
        links: List[str] = []
        from urllib.parse import urlparse, urljoin

        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if any(kw in href.lower() or kw in text.lower() for kw in ["job", "position"]) and text and len(text) > 3:
                if href.startswith("http"):
                    links.append(href)
                elif href.startswith("/"):
                    links.append(f"{base}{href}")
        return list(set(links))[:20]


dynamic_careers_collector = DynamicCareersCollector()
