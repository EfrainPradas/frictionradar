"""Domain normalization and validation utilities.

Enhanced to detect and flag truncated domains (Wikipedia formatting artifacts).
"""

from __future__ import annotations

import re


_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}$"
)


def normalize_domain(raw: str) -> str:
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.lstrip("www.")
    d = d.split("/")[0].split("?")[0].split("#")[0]
    return d


def is_valid_domain(domain: str) -> tuple[bool, str]:
    if not domain:
        return False, "empty domain"
    if len(domain) > 253:
        return False, "domain too long"
    if not _DOMAIN_RE.match(domain):
        return False, f"invalid domain format: {domain}"
    if _looks_truncated(domain):
        return False, f"likely truncated domain: {domain}"
    return True, ""


def _looks_truncated(domain: str) -> bool:
    """Detect domains that look like they were cut off (Wikipedia formatting).

    Examples of truncated domains:
      - aho.com (should be wahoo.com)
      - ilworks.com (should be wildworks.com)
      - akeupnow.com (should be wakeupnow.com)
    """
    # Very short domains without www are suspicious
    parts = domain.split(".")
    name_part = parts[0]

    # If the name part is < 4 chars, it's likely truncated
    # (unless it's a known short brand like ibm.com, hp.com, etc.)
    known_short = {"ibm", "hp", "3m", "ge", "bp", "pg", "si", "bt", "vw", "de", "go", "io", "tv", "me"}
    if len(name_part) < 4 and name_part not in known_short:
        # Check if it starts with a lowercase letter that looks like it lost a capital
        # (Wikipedia often strips leading uppercase when extracting URLs)
        return True

    # Check for archive.org partial URLs
    if "archive.org" in domain and domain.count("/") < 3:
        return True

    return False
