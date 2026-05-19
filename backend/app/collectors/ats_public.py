"""ATS Platform Detector — replaces the stub AtsPublicCollector.

Checks known ATS platforms (Greenhouse, Lever, Workday, Ashby, etc.)
by probing their public job board URLs derived from the company name
or domain slug.

This is a real detector, not a placeholder.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.collectors.base import BaseCollector
from app.collectors.careers_url_finder import (
    ATS_PLATFORMS,
    _slugify_company_name,
    careers_url_finder,
)
from app.core.logging import get_logger
from app.core.security import get_ssl_verify
from app.models.company import Company
from app.schemas.signal import SignalCreate

logger = get_logger(__name__)

# Map ATS platforms to signal types we emit
ATS_SIGNAL_MAP = {
    "greenhouse": ("greenhouse_board_detected", "ATS platform detected"),
    "lever": ("lever_board_detected", "ATS platform detected"),
    "ashby": ("ashby_board_detected", "ATS platform detected"),
    "smartrecruiters": ("smartrecruiters_board_detected", "ATS platform detected"),
    "jobvite": ("jobvite_board_detected", "ATS platform detected"),
    "icims": ("icims_board_detected", "ATS platform detected"),
    "workday": ("workday_board_detected", "ATS platform detected"),
    "myworkdayjobs": ("myworkdayjobs_board_detected", "ATS platform detected"),
}


class AtsPublicCollector(BaseCollector):
    """Detects and probes known ATS public job boards."""

    collector_type = "ats_public"

    def collect(self, company: Company) -> List[SignalCreate]:
        signals: List[SignalCreate] = []
        if not company.domain:
            return signals

        domain = company.domain.strip().lower()
        if domain.startswith("http"):
            parsed = urlparse(domain)
            domain = parsed.netloc or parsed.path.split("/")[0]

        # Strategy 1: Use the careers_url_finder (it already scans homepage for ATS embeds)
        url, strategy, meta = careers_url_finder.find(domain, company.name)

        if strategy == "ats_detected" or strategy == "ats_guess":
            platform = meta.get("platform", "unknown")
            signal_info = ATS_SIGNAL_MAP.get(platform)
            if signal_info:
                signals.append(
                    SignalCreate(
                        source_type=self.collector_type,
                        source_url=url or "",
                        signal_type=signal_info[0],
                        signal_text=f"{signal_info[1]}: {platform} ({strategy})",
                        confidence=0.85 if strategy == "ats_detected" else 0.6,
                    )
                )

            # If we got an ATS URL, we can also check for job count hints
            if url:
                count = self._extract_job_count_from_ats(url, platform)
                if count and count > 0:
                    signals.append(
                        SignalCreate(
                            source_type=self.collector_type,
                            source_url=url,
                            signal_type="open_positions_count_detected",
                            signal_text=f"ATS reports {count} open positions",
                            numeric_value=count,
                            confidence=0.8,
                        )
                    )

        # Strategy 2: Also try homepage HTML for ATS embed patterns (belt and suspenders)
        if not signals:
            homepage_ats = self._check_homepage_for_ats(domain, company.name)
            if homepage_ats:
                platform, confidence = homepage_ats
                signal_info = ATS_SIGNAL_MAP.get(platform)
                if signal_info:
                    signals.append(
                        SignalCreate(
                            source_type=self.collector_type,
                            source_url=f"https://{domain}",
                            signal_type=signal_info[0],
                            signal_text=f"{signal_info[1]}: {platform} (homepage embed)",
                            confidence=confidence,
                        )
                    )

        return signals

    def _check_homepage_for_ats(
        self, domain: str, company_name: str
    ) -> Optional[tuple]:
        """Fetch homepage HTML and look for ATS platform indicators."""
        try:
            resp = requests.get(
                f"https://{domain}",
                timeout=8,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                verify=get_ssl_verify(),
            )
            if resp.status_code != 200:
                return None

            for platform, config in ATS_PLATFORMS.items():
                for pattern in config["html_patterns"]:
                    if re.search(pattern, resp.text, re.IGNORECASE):
                        return platform, 0.75

        except Exception:
            pass

        return None

    def _extract_job_count_from_ats(
        self, url: str, platform: str
    ) -> Optional[int]:
        """Try to extract a job count from a known ATS job board page."""
        try:
            resp = requests.get(
                url,
                timeout=8,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                verify=get_ssl_verify(),
            )
            if resp.status_code != 200:
                return None

            text = resp.text

            # Greenhouse often has: "All Open Positions" or a count in structured data
            # Lever often has a count in the page
            # Generic: look for number patterns near "open" / "position" / "job"
            patterns = [
                r"(\d{1,3}(?:,\d{3})*)\s*(?:open\s*)?(?:positions?|jobs?|roles?|openings?)",
                r"(?:open\s*)?(?:positions?|jobs?|roles?|openings?)\s*:?\s*(\d{1,3}(?:,\d{3})*)",
                r'"(?:open|available)(?:Jobs|Positions|Roles)":\s*(\d+)',
                r'"count":\s*(\d+)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for m in matches:
                    try:
                        num = int(m.replace(",", ""))
                        if 1 <= num <= 5000:
                            return num
                    except (ValueError, TypeError):
                        continue

        except Exception:
            pass

        return None
