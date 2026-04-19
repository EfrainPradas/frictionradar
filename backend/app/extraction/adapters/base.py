"""Base ATS adapter contract.

Every vendor adapter (Greenhouse, Lever, Ashby, …) implements this
interface. The dispatcher calls these methods in order:

    1. resolve_endpoint(domain, company_name) → API URL or None
    2. fetch_jobs(api_url)                    → raw JSON response
    3. parse_jobs(raw_data)                   → NormalizedJobsResult

detect() is a class-level utility for checking whether a given HTML
page contains embed markers for this ATS.
"""

from __future__ import annotations

import re
import urllib3
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger

logger = get_logger(__name__)

urllib3.disable_warnings()

# Shared HTTP session config
DEFAULT_TIMEOUT = 12
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def slugify_company(name: str, domain: str) -> List[str]:
    """Generate plausible ATS slugs from company name and domain.

    Returns up to 5 candidates, most likely first.
    Reuses the same logic as careers_url_finder._slugify_company_name
    but adds the domain-prefix variant which is often the winner.
    """
    slugs: List[str] = []

    # Domain prefix is often the slug (e.g. stripe.com → "stripe")
    domain_slug = domain.split(".")[0].lower()
    if domain_slug and len(domain_slug) > 1:
        slugs.append(domain_slug)

    if not name:
        return slugs

    # Clean company name
    clean = re.sub(
        r"\s*(inc|llc|corp|corporation|ltd|company|co\.?|group|holdings|"
        r"enterprises|solutions|technologies)\s*\.?\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\s*\(.*?\)\s*", "", clean).strip()

    # Hyphenated
    slug = re.sub(r"[^a-z0-9]+", "-", clean.lower()).strip("-")
    if slug and slug not in slugs:
        slugs.append(slug)

    # Bare (no separators)
    slug_bare = re.sub(r"[^a-z0-9]", "", clean.lower())
    if slug_bare and slug_bare not in slugs:
        slugs.append(slug_bare)

    # Underscore
    slug_us = re.sub(r"[^a-z0-9]+", "_", clean.lower()).strip("_")
    if slug_us and slug_us not in slugs:
        slugs.append(slug_us)

    return slugs[:5]


class BaseATSAdapter(ABC):
    """Contract for vendor-specific ATS API adapters."""

    platform: ATSPlatform

    # ── Detection ───────────────────────────────────────────────────

    @abstractmethod
    def detect(self, html: str) -> bool:
        """Return True if the HTML contains embed/reference markers for this ATS."""

    # ── Endpoint resolution ─────────────────────────────────────────

    @abstractmethod
    def resolve_endpoint(
        self, domain: str, company_name: Optional[str] = None
    ) -> Optional[str]:
        """Build and validate the API URL for this company.

        Returns the working API URL, or None if no valid endpoint found.
        This method MAY make HTTP HEAD/GET requests to validate.
        """

    # ── Data fetch ──────────────────────────────────────────────────

    @abstractmethod
    def fetch_jobs(self, api_url: str) -> Optional[Dict[str, Any]]:
        """Fetch the raw JSON response from the ATS API.

        Returns the parsed JSON dict/list, or None on failure.
        """

    # ── Parsing ─────────────────────────────────────────────────────

    @abstractmethod
    def parse_jobs(
        self, raw_data: Any, api_url: str, domain: str
    ) -> NormalizedJobsResult:
        """Convert raw ATS API response into NormalizedJobsResult."""

    # ── Convenience: full pipeline ──────────────────────────────────

    def extract(
        self, domain: str, company_name: Optional[str] = None
    ) -> NormalizedJobsResult:
        """Run the full adapter pipeline: resolve → fetch → parse.

        Returns a NormalizedJobsResult with error set on failure.
        """
        api_url = self.resolve_endpoint(domain, company_name)
        if not api_url:
            return NormalizedJobsResult(
                domain=domain,
                ats_platform=self.platform.value,
                strategy_used=ExtractionStrategy.ATS_API,
                reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
                error=f"No valid {self.platform.value} endpoint found for {domain}",
            )

        raw = self.fetch_jobs(api_url)
        if raw is None:
            return NormalizedJobsResult(
                domain=domain,
                careers_url=api_url,
                ats_platform=self.platform.value,
                strategy_used=ExtractionStrategy.ATS_API,
                reason_code=ReasonCode.KNOWN_ATS_JSON_AVAILABLE,
                error=f"{self.platform.value} API returned no data from {api_url}",
            )

        result = self.parse_jobs(raw, api_url, domain)
        return result

    # ── Shared HTTP helper ──────────────────────────────────────────

    def _get_json(
        self, url: str, timeout: int = DEFAULT_TIMEOUT
    ) -> Optional[Any]:
        """GET a URL and return parsed JSON, or None on any failure."""
        try:
            resp = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=timeout,
                verify=False,
            )
            if resp.status_code != 200:
                logger.debug(
                    f"[{self.platform.value}] HTTP {resp.status_code} for {url}"
                )
                return None
            return resp.json()
        except Exception as exc:
            logger.debug(f"[{self.platform.value}] Request failed for {url}: {exc}")
            return None

    def _head_ok(self, url: str, timeout: int = 8) -> bool:
        """Quick HEAD check to see if a URL responds with 200."""
        try:
            resp = requests.head(
                url,
                headers={
                    "User-Agent": DEFAULT_HEADERS["User-Agent"],
                },
                timeout=timeout,
                allow_redirects=True,
                verify=False,
            )
            return resp.status_code == 200
        except Exception:
            return False
