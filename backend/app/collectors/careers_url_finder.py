"""
Multi-strategy careers URL finder.

Tries multiple approaches to find a company's careers/job page:
  1. Scan homepage for careers links and ATS embed patterns
  2. Common URL paths (/careers, /jobs, /join-us, etc.)
  3. Subdomain patterns (careers.{domain}, jobs.{domain})
  4. ATS platform detection (Greenhouse, Lever, Workday, Ashby, etc.)
  5. Domain-slug guessing on known ATS platforms

Returns the best URL found with discovery strategy and confidence.
"""

import re
import urllib3
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from app.core.logging import get_logger

logger = get_logger(__name__)

urllib3.disable_warnings()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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
    "/people",
    "/team",
    "/talent",
]

CAREERS_SUBDOMAINS = ["careers", "jobs"]

# Signals that a page actually IS a careers page (not a random 200)
CAREERS_PAGE_INDICATORS = [
    "open positions",
    "current openings",
    "job openings",
    "join our team",
    "we're hiring",
    "we are hiring",
    "open roles",
    "career opportunities",
    "available positions",
    "view all jobs",
    "search jobs",
    "job listings",
    "all jobs",
    "all positions",
    "life at",
    "our culture",
    "benefits",
    "department",
]

# Weak indicators — present alone are not enough but help when combined
WEAK_INDICATORS = [
    "job",
    "position",
    "opening",
    "role",
    "apply",
    "location",
    "listing",
    "team",
    "engineering",
    "marketing",
    "sales",
    "operations",
    "finance",
    "design",
    "product",
]

ATS_PLATFORMS: Dict[str, Dict] = {
    "greenhouse": {
        "url_template": "https://boards.greenhouse.io/{slug}",
        "html_patterns": [r"boards\.greenhouse\.io", r"greenhouse\.io/embed"],
    },
    "lever": {
        "url_template": "https://jobs.lever.co/{slug}",
        "html_patterns": [r"jobs\.lever\.co", r"lever\.co/embed"],
    },
    "ashby": {
        "url_template": "https://jobs.ashbyhq.com/{slug}",
        "html_patterns": [r"ashbyhq\.com"],
    },
    "smartrecruiters": {
        "url_template": "https://careers.smartrecruiters.com/{slug}",
        "html_patterns": [r"smartrecruiters\.com"],
    },
    "jobvite": {
        "url_template": "https://jobs.jobvite.com/{slug}",
        "html_patterns": [r"jobvite\.com"],
    },
    "icims": {
        "url_template": None,  # ICIMS URLs are too company-specific to guess
        "html_patterns": [r"icims\.com"],
    },
    "workday": {
        "url_template": None,  # Workday URLs are too variable
        "html_patterns": [r"workday\.com", r"wd\d+\.myworkdayjobs\.com"],
    },
    "myworkdayjobs": {
        "url_template": None,
        "html_patterns": [r"myworkdayjobs\.com"],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify_company_name(name: str) -> List[str]:
    """Generate plausible URL slugs from a company name."""
    if not name:
        return []

    # Remove common suffixes and parenthetical content
    clean = re.sub(
        r"\s*(inc|llc|corp|corporation|ltd|company|co\.?|group|holdings|enterprises|solutions|technologies)\s*\.?\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\s*\(.*?\)\s*", "", clean)
    clean = clean.strip()

    slugs: List[str] = []

    # Standard hyphenated
    slug = re.sub(r"[^a-z0-9]+", "-", clean.lower()).strip("-")
    if slug:
        slugs.append(slug)

    # No separators
    slug_bare = re.sub(r"[^a-z0-9]", "", clean.lower())
    if slug_bare and slug_bare not in slugs:
        slugs.append(slug_bare)

    # Underscore
    slug_us = re.sub(r"[^a-z0-9]+", "_", clean.lower()).strip("_")
    if slug_us and slug_us not in slugs:
        slugs.append(slug_us)

    return slugs[:4]


def _has_careers_content(html: str) -> bool:
    """Check if HTML contains strong careers-page indicators."""
    text = html.lower()
    return any(kw in text for kw in CAREERS_PAGE_INDICATORS)


def _has_job_elements(html: str) -> bool:
    """Check if HTML contains weak but suggestive job-related terms."""
    text = html.lower()
    return any(kw in text for kw in WEAK_INDICATORS)


# Platforms that return HTTP 200 for any slug (empty SPA shell, or a
# silent redirect to a generic page). Observed behaviour:
#   - Ashby: 200 + 6.3KB shell, slug stays in URL → size threshold catches it
#     (real workspaces ≥30KB, smallest sampled Linear 37KB)
#   - SmartRecruiters: 200 + 302 to jobs.smartrecruiters.com when slug is
#     unknown → slug drops out of the final URL
#   - Jobvite: 200 + 302 to /support/job-seeker-support/?invalid=1 → slug
#     drops out of the final URL
# Greenhouse/Lever return 404 for bad slugs, so they don't need this.
ATS_SPA_SHELL_MIN_BYTES = {
    "ashby": 15000,
    "smartrecruiters": 40000,
}

# If True, require the slug to appear in the final (post-redirect) URL.
# Platforms that silently redirect away from the slug when it's invalid.
ATS_REQUIRE_SLUG_IN_FINAL_URL = {"smartrecruiters", "jobvite", "ashby"}


def _validate_ats_response(
    platform: str, html: str, final_url: Optional[str], slug: str
) -> bool:
    """Extra sanity check on top of _has_job_elements for SPA-heavy ATS.

    Returns False if the response is almost certainly a shell page or a
    redirect to a generic fallback.
    """
    threshold = ATS_SPA_SHELL_MIN_BYTES.get(platform)
    if threshold and len(html) < threshold:
        return False
    if platform in ATS_REQUIRE_SLUG_IN_FINAL_URL:
        if not final_url or slug.lower() not in final_url.lower():
            return False
    return True


def _detect_ats_in_html(html: str) -> Optional[str]:
    """Return the name of the ATS platform detected in HTML, or None."""
    for platform, config in ATS_PLATFORMS.items():
        for pattern in config["html_patterns"]:
            if re.search(pattern, html, re.IGNORECASE):
                return platform
    return None


def _extract_careers_links_from_html(html: str, base_url: str) -> List[str]:
    """Extract careers-related links from an HTML page."""
    links: List[str] = []
    parsed_base = urlparse(base_url)

    # Match href values containing careers/job keywords
    href_pattern = r'href=["\']([^"\']*(?:career|job|join|work|talent|opportunit|hiring|open-role|position)[^"\']*)["\']'
    matches = re.findall(href_pattern, html, re.IGNORECASE)

    exclude_words = ["login", "signin", "sign-in", "auth", "password", "register", "signup"]

    for href in matches:
        href_lower = href.lower()
        if any(w in href_lower for w in exclude_words):
            continue

        if href.startswith("/"):
            full = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
        elif href.startswith("http"):
            full = href
        else:
            continue

        links.append(full)

    return links


# ---------------------------------------------------------------------------
# Finder
# ---------------------------------------------------------------------------

class CareersURLFinder:
    """Multi-strategy careers URL finder.

    Thread-safe: creates a fresh requests.Session per find() call
    so multiple threads can use this concurrently without sharing
    connection pool state.
    """

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Size-bounded memo cache. Collectors run sequentially per company inside a
    # worker process, so several collectors (CareersCollector + DynamicCareers)
    # call find() with the same (domain, name). Without this cache we redo the
    # entire probe — on dead domains that's ~100s wasted per duplicate call.
    _MEMO_MAX = 128

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self._memo: Dict[Tuple[str, Optional[str]], Tuple[Optional[str], str, dict]] = {}
        self._memo_order: List[Tuple[str, Optional[str]]] = []

    def _make_session(self) -> requests.Session:
        """Create a fresh, short-lived session for one find() call."""
        s = requests.Session()
        s.headers.update(self.DEFAULT_HEADERS)
        return s

    def _memo_get(self, key):
        return self._memo.get(key)

    def _memo_put(self, key, value):
        self._memo[key] = value
        self._memo_order.append(key)
        if len(self._memo_order) > self._MEMO_MAX:
            old = self._memo_order.pop(0)
            self._memo.pop(old, None)

    def find(
        self, domain: str, company_name: Optional[str] = None
    ) -> Tuple[Optional[str], str, dict]:
        """Find the best careers URL for a company.

        Creates a fresh HTTP session per call — safe for concurrent use.

        Returns:
            (url | None, strategy, metadata)
        """
        if not domain:
            return None, "no_domain", {}

        domain = self._clean_domain(domain)

        # Memo short-circuit: same (domain, name) in this process → reuse.
        memo_key = (domain, company_name)
        cached = self._memo_get(memo_key)
        if cached is not None:
            url, strategy, meta = cached
            logger.debug(f"[CareersURLFinder] memo hit for {domain}: strategy={strategy}")
            return url, strategy, {**meta, "memo": True}

        session = self._make_session()
        log = {"domain": domain, "company_name": company_name, "steps": []}

        try:
            # ── Step 1: Scan homepage ────────────────────────────────────
            log["steps"].append("scan_homepage")
            homepage = f"https://{domain}"

            careers_url, ats_platform, ats_embed, homepage_dead = self._scan_homepage(
                session, homepage
            )

            if careers_url:
                log["steps"].append(f"homepage_link_found:{careers_url}")
                result = (careers_url, "homepage_link", {"log": log})
                self._memo_put(memo_key, result)
                return result

            if ats_platform:
                log["steps"].append(f"ats_detected:{ats_platform}")
                ats_url = self._try_ats_url(session, ats_platform, domain, company_name)
                if ats_url:
                    result = (ats_url, "ats_detected", {"platform": ats_platform, "log": log})
                    self._memo_put(memo_key, result)
                    return result

            # If the homepage was unreachable (DNS/connect timeout), don't waste
            # ~100s probing 15 paths + 2 subdomains + www on the same dead
            # domain. Skip straight to ATS guessing (which hits external
            # domains like boards.greenhouse.io that are typically reachable).
            if homepage_dead:
                log["steps"].append("homepage_dead_skip_path_probes")
                if company_name:
                    log["steps"].append("try_ats_guess")
                    ats_result = self._try_all_ats(session, domain, company_name)
                    if ats_result:
                        url, platform, slug = ats_result
                        result = (
                            url,
                            "ats_guess",
                            {"platform": platform, "slug": slug, "log": log},
                        )
                        self._memo_put(memo_key, result)
                        return result
                log["steps"].append("not_found_dead_domain")
                result = (None, "dead_domain", {"log": log})
                self._memo_put(memo_key, result)
                return result

            # ── Step 2: Common paths ─────────────────────────────────────
            log["steps"].append("try_paths")
            for path in CAREERS_PATHS:
                url = f"https://{domain}{path}"
                if self._is_careers_page(session, url):
                    result = (url, f"path:{path}", {"log": log})
                    self._memo_put(memo_key, result)
                    return result

            # ── Step 3: Subdomains ───────────────────────────────────────
            log["steps"].append("try_subdomains")
            for sub in CAREERS_SUBDOMAINS:
                url = f"https://{sub}.{domain}"
                if self._is_careers_page(session, url):
                    result = (url, f"subdomain:{sub}", {"log": log})
                    self._memo_put(memo_key, result)
                    return result

            # ── Step 4: ATS guessing by company name ─────────────────────
            if company_name:
                log["steps"].append("try_ats_guess")
                ats_result = self._try_all_ats(session, domain, company_name)
                if ats_result:
                    url, platform, slug = ats_result
                    result = (
                        url,
                        "ats_guess",
                        {"platform": platform, "slug": slug, "log": log},
                    )
                    self._memo_put(memo_key, result)
                    return result

            # ── Step 5: www prefix ───────────────────────────────────────
            if not domain.startswith("www."):
                log["steps"].append("try_www")
                for path in ["/careers", "/jobs"]:
                    url = f"https://www.{domain}{path}"
                    if self._is_careers_page(session, url):
                        result = (url, f"www_path:{path}", {"log": log})
                        self._memo_put(memo_key, result)
                        return result

            log["steps"].append("not_found")
            result = (None, "not_found", {"log": log})
            self._memo_put(memo_key, result)
            return result
        finally:
            session.close()

    # ── Internals ───────────────────────────────────────────────────

    def _clean_domain(self, domain: str) -> str:
        domain = domain.strip().lower()
        if domain.startswith("http"):
            parsed = urlparse(domain)
            domain = parsed.netloc or parsed.path.split("/")[0]
        return domain

    def _scan_homepage(
        self, session: requests.Session, url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
        """Scan homepage for careers links and ATS embeds.

        Returns (careers_url, ats_platform, ats_embed_url, dead).
        `dead` is True when the homepage is unreachable (ConnectionError /
        DNS failure / connect-timeout). Callers use it to skip path/subdomain
        probing on the same dead domain.
        """
        try:
            resp = session.get(
                url, timeout=self.timeout, allow_redirects=True, verify=False
            )
            if resp.status_code != 200:
                # Server responded but non-200 — domain is alive, just this
                # URL isn't useful. Don't mark dead.
                return None, None, None, False
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.debug(f"Homepage fetch failed (dead domain) for {url}: {e}")
            return None, None, None, True
        except Exception as e:
            logger.debug(f"Homepage fetch failed for {url}: {e}")
            return None, None, None, False

        html = resp.text
        final_url = resp.url

        # Detect ATS
        ats_platform = _detect_ats_in_html(html)
        ats_embed = None
        if ats_platform:
            config = ATS_PLATFORMS[ats_platform]
            for pattern in config["html_patterns"]:
                url_match = re.search(
                    rf'https?://[^\s\'"<>]*{re.escape(pattern[2:])}[^\s\'"<>]*',
                    html,
                    re.IGNORECASE,
                )
                if url_match:
                    ats_embed = url_match.group(0)
                    break

        # Extract careers links
        careers_links = _extract_careers_links_from_html(html, final_url)
        if careers_links:
            # Prefer the shortest/most direct link
            careers_links.sort(key=len)
            return careers_links[0], ats_platform, ats_embed, False

        return None, ats_platform, ats_embed, False

    def _is_careers_page(self, session: requests.Session, url: str) -> bool:
        """Probe a URL and determine if it's a real careers page."""
        try:
            resp = session.get(
                url, timeout=self.timeout, allow_redirects=True, verify=False
            )
            if resp.status_code != 200:
                return False

            html = resp.text

            # Strong signal
            if _has_careers_content(html):
                return True

            # Redirected to a careers-like URL
            if resp.url != url and any(
                kw in resp.url.lower() for kw in ["career", "job", "join", "work"]
            ):
                return True

            # Page is big enough and has job terms
            if len(html) > 2000 and _has_job_elements(html):
                weak_count = sum(1 for kw in WEAK_INDICATORS if kw in html.lower())
                if weak_count >= 4:
                    return True

            return False

        except Exception:
            return False

    def _try_ats_url(
        self, session: requests.Session, platform: str, domain: str, company_name: Optional[str]
    ) -> Optional[str]:
        config = ATS_PLATFORMS.get(platform)
        if not config or not config.get("url_template"):
            return None

        slugs = []
        if company_name:
            slugs.extend(_slugify_company_name(company_name))
        domain_slug = domain.split(".")[0]
        if domain_slug and domain_slug not in slugs:
            slugs.insert(0, domain_slug)

        for slug in slugs[:3]:
            url = config["url_template"].format(slug=slug)
            try:
                resp = session.get(
                    url, timeout=self.timeout, allow_redirects=True, verify=False
                )
                if (
                    resp.status_code == 200
                    and _has_job_elements(resp.text)
                    and _validate_ats_response(platform, resp.text, resp.url, slug)
                ):
                    logger.info(f"ATS URL found: {url} ({platform})")
                    return url
            except Exception:
                continue

        return None

    def _try_all_ats(
        self, session: requests.Session, domain: str, company_name: str
    ) -> Optional[Tuple[str, str, str]]:
        """Try all ATS platforms with company name / domain slug."""
        slugs = []
        if company_name:
            slugs.extend(_slugify_company_name(company_name))
        domain_slug = domain.split(".")[0]
        if domain_slug and domain_slug not in slugs:
            slugs.insert(0, domain_slug)

        for platform, config in ATS_PLATFORMS.items():
            if not config.get("url_template"):
                continue
            for slug in slugs[:2]:
                url = config["url_template"].format(slug=slug)
                try:
                    resp = session.get(
                        url, timeout=self.timeout, allow_redirects=True, verify=False
                    )
                    if (
                        resp.status_code == 200
                        and _has_job_elements(resp.text)
                        and _validate_ats_response(platform, resp.text, resp.url, slug)
                    ):
                        logger.info(
                            f"ATS guess hit: {url} ({platform}, slug={slug})"
                        )
                        return url, platform, slug
                except Exception:
                    continue

        return None


# Module-level singleton
careers_url_finder = CareersURLFinder()
