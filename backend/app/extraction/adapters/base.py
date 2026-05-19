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
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.extraction.constants import ATSPlatform, ExtractionStrategy, ReasonCode
from app.extraction.schemas import NormalizedJob, NormalizedJobsResult
from app.core.logging import get_logger
from app.core.security import get_ssl_verify

logger = get_logger(__name__)

# Shared HTTP session config
DEFAULT_TIMEOUT = 12
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds — doubles each attempt (1s, 2s, 4s)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


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

    # ── Shared HTTP helpers (with retry) ──────────────────────────────

    def _request_with_retry(
        self,
        method: str,
        url: str,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs,
    ) -> Optional[requests.Response]:
        """Make an HTTP request with exponential backoff on transient errors.

        Retries on: 429, 500, 502, 503, 504 status codes, timeouts, and
        connection errors. Non-transient errors (4xx except 429) return
        the response immediately without retry.

        Returns the Response on success, or None after exhausting retries.
        """
        headers = kwargs.pop("headers", DEFAULT_HEADERS)
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.request(
                    method, url, headers=headers, timeout=timeout, **kwargs
                )
                if resp.status_code in TRANSIENT_STATUS_CODES:
                    if attempt < MAX_RETRIES - 1:
                        backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.debug(
                            f"[{self.platform.value}] {method} {url} got "
                            f"{resp.status_code}, retrying in {backoff}s "
                            f"(attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        time.sleep(backoff)
                        continue
                    # Final attempt failed with transient error
                    return None
                return resp
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.debug(
                        f"[{self.platform.value}] {method} {url} timed out, "
                        f"retrying in {backoff}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(backoff)
                    continue
                return None
            except requests.exceptions.ConnectionError:
                if attempt < MAX_RETRIES - 1:
                    backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.debug(
                        f"[{self.platform.value}] {method} {url} connection error, "
                        f"retrying in {backoff}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(backoff)
                    continue
                return None
            except requests.exceptions.RequestException:
                return None  # Non-retryable error
        return None

    def _get_json(
        self, url: str, timeout: int = DEFAULT_TIMEOUT
    ) -> Optional[Any]:
        """GET a URL and return parsed JSON, or None on any failure."""
        resp = self._request_with_retry("GET", url, timeout=timeout, verify=get_ssl_verify())
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            return None

    def _head_ok(self, url: str, timeout: int = 8) -> bool:
        """Quick HEAD check to see if a URL responds with 200."""
        resp = self._request_with_retry(
            "HEAD",
            url,
            timeout=timeout,
            verify=get_ssl_verify(),
            allow_redirects=True,
            headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]},
        )
        return resp is not None and resp.status_code == 200

    def _post_json(
        self,
        url: str,
        payload: dict,
        timeout: int = DEFAULT_TIMEOUT,
        headers: Optional[dict] = None,
    ) -> Optional[dict]:
        """POST JSON to a URL with retry, return parsed response or None."""
        post_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if headers:
            post_headers.update(headers)
        resp = self._request_with_retry(
            "POST", url, timeout=timeout, json=payload,
            headers=post_headers, verify=get_ssl_verify(),
        )
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            return None
