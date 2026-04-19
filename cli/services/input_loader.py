"""Load and validate the input JSON company list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .domain_utils import normalize_domain, is_valid_domain


def load_companies(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        raw = raw.get("companies_with_domain") or raw.get("companies") or []
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON array or object with 'companies'")

    companies: list[dict[str, Any]] = []
    seen_domains: set[str] = set()

    for i, entry in enumerate(raw):
        name = (
            entry.get("company_name")
            or entry.get("name")
            or ""
        ).strip()
        raw_domain = (entry.get("domain") or "").strip()

        if not name and not raw_domain:
            continue

        domain = normalize_domain(raw_domain) if raw_domain else ""
        valid, reason = is_valid_domain(domain) if domain else (False, "missing domain")

        if not valid:
            companies.append({
                "company_name": name or raw_domain,
                "domain": raw_domain,
                "industry": entry.get("industry"),
                "location": entry.get("location") or entry.get("hq"),
                "source": entry.get("source", "cli_import"),
                "_exclude_reason": reason,
            })
            continue

        if domain in seen_domains:
            companies.append({
                "company_name": name,
                "domain": domain,
                "industry": entry.get("industry"),
                "location": entry.get("location") or entry.get("hq"),
                "source": entry.get("source", "cli_import"),
                "_exclude_reason": f"duplicate domain: {domain}",
            })
            continue

        seen_domains.add(domain)
        companies.append({
            "company_name": name or domain,
            "domain": domain,
            "industry": entry.get("industry"),
            "location": entry.get("location") or entry.get("hq"),
            "source": entry.get("source", "cli_import"),
        })

    return companies
