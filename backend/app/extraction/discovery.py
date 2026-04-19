"""Careers URL discovery.

Finds the best careers page URL for a company by probing:
  1. Homepage links (extract <a> tags with career keywords)
  2. Common paths (/careers, /jobs, /join-us, etc.)
  3. Subdomains (careers.domain, jobs.domain)
  4. www prefix fallback

Returns a DiscoveryResult with the URL, how it was found,
and a pre-fetched HTTP response for the classifier/extractor
to reuse (avoids double-fetching).
"""

from __future__ import annotations

import re
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import requests

from app.core.logging import get_logger

logger = get_logger(__name__)

urllib3.disable_warnings()

TIMEOUT = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CAREERS_PATHS = [
    "/careers",
    "/jobs",
    "/about/careers",
    "/company/careers",
    "/careers/jobs",
    "/work-with-us",
    "/join-us",
    "/join",
    "/work-here",
    "/hiring",
    "/opportunities",
    "/employment",
    "/talent",
    "/open-positions",
]

CAREERS_SUBDOMAINS = ["careers", "jobs"]

# Strong indicators that a page IS a careers/jobs page
STRONG_INDICATORS = [
    "open positions", "current openings", "job openings",
    "join our team", "we're hiring", "we are hiring",
    "open roles", "career opportunities", "available positions",
    "view all jobs", "search jobs", "job listings",
    "all jobs", "all positions", "apply now", "apply today",
]

# Link href patterns that suggest a careers page
CAREERS_LINK_PATTERN = re.compile(
    r'href=["\']([^"\']*(?:career|jobs?|join|work|talent|opportunit|hiring|open-role|position)[^"\']*)["\']',
    re.IGNORECASE,
)


@dataclass
class DiscoveryResult:
    """Result of careers URL discovery."""

    url: Optional[str] = None
    strategy: str = "not_found"  # homepage_link, path, subdomain, www_path
    status_code: Optional[int] = None
    content_length: int = 0
    has_job_indicators: bool = False
    html: str = ""  # Pre-fetched HTML for reuse
    final_url: str = ""  # After redirects


def discover_careers_url(
    domain: str, company_name: Optional[str] = None
) -> DiscoveryResult:
    """Find the best careers page URL for a domain.

    Tries homepage links first (quick), then probes all candidate
    URLs in parallel to minimize wall-clock time.
    """
    domain = _clean_domain(domain)

    # ── 1. Scan homepage for careers links (fast, single request) ──
    homepage_result = _try_homepage_links(domain)
    if homepage_result and homepage_result.url:
        return homepage_result

    # ── 2. Parallel probe: paths + subdomains + www ────────────────
    candidates = []
    # High-priority paths first
    for path in ["/careers", "/jobs"]:
        candidates.append((f"https://{domain}{path}", f"path:{path}"))
    # Subdomains
    for sub in CAREERS_SUBDOMAINS:
        candidates.append((f"https://{sub}.{domain}", f"subdomain:{sub}"))
    # Remaining paths
    for path in CAREERS_PATHS[2:]:  # skip /careers and /jobs already added
        candidates.append((f"https://{domain}{path}", f"path:{path}"))
    # www fallback
    if not domain.startswith("www."):
        for path in ["/careers", "/jobs"]:
            candidates.append((f"https://www.{domain}{path}", f"www:{path}"))

    best_fallback: Optional[DiscoveryResult] = None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_probe_url, url, strategy): (url, strategy)
            for url, strategy in candidates
        }
        for future in as_completed(futures):
            result = future.result()
            if result and result.has_job_indicators:
                # Cancel remaining futures (best-effort)
                for f in futures:
                    f.cancel()
                return result
            # Track best fallback (200 with content)
            if (
                result
                and result.status_code == 200
                and result.content_length > 500
                and best_fallback is None
            ):
                best_fallback = result

    if best_fallback:
        return best_fallback

    return DiscoveryResult()


def _clean_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if domain.startswith("http"):
        parsed = urlparse(domain)
        domain = parsed.netloc or parsed.path.split("/")[0]
    return domain


def _try_homepage_links(domain: str) -> Optional[DiscoveryResult]:
    """Scan homepage HTML for careers-related links."""
    try:
        resp = requests.get(
            f"https://{domain}",
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            verify=False,
        )
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    matches = CAREERS_LINK_PATTERN.findall(resp.text)
    exclude = {"login", "signin", "sign-in", "auth", "password", "register", "signup"}
    parsed_base = urlparse(resp.url)

    for href in matches:
        href_lower = href.lower()
        if any(w in href_lower for w in exclude):
            continue

        if href.startswith("/"):
            full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
        elif href.startswith("http"):
            full_url = href
        else:
            continue

        result = _probe_url(full_url, "homepage_link")
        if result and result.has_job_indicators:
            return result

    return None


def _probe_url(url: str, strategy: str) -> Optional[DiscoveryResult]:
    """Fetch a URL and check if it looks like a careers page."""
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            verify=False,
        )
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    html = resp.text
    text_lower = html.lower()
    has_indicators = any(kw in text_lower for kw in STRONG_INDICATORS)

    # Also check if URL looks like careers after redirects
    if not has_indicators:
        final_lower = resp.url.lower()
        if any(kw in final_lower for kw in ["career", "job", "hiring", "talent"]):
            # URL looks right — check for weaker indicators
            weak_count = sum(
                1 for kw in ["job", "position", "role", "apply", "team", "department"]
                if kw in text_lower
            )
            if weak_count >= 3:
                has_indicators = True

    return DiscoveryResult(
        url=resp.url,
        strategy=strategy,
        status_code=resp.status_code,
        content_length=len(html),
        has_job_indicators=has_indicators,
        html=html,
        final_url=resp.url,
    )
