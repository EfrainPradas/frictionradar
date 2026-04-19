"""
Build a JSON list of Utah-based companies using the Wikipedia API.

Sources (in order):
    1. Category:Companies based in Utah   — direct category members
    2. Category:Companies based in <city>, Utah — for Salt Lake City, Provo,
       Lehi, Draper, Orem, South Jordan, Sandy, Ogden, Park City, Midvale
    3. For each company, the Wikipedia infobox is parsed to extract the
       official website (domain).

Output:
    tools/data/utah_companies.json

Usage:
    python tools/scrape_utah_companies.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

OUTPUT_PATH = Path(__file__).parent / "data" / "utah_companies.json"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_BASE = "https://en.wikipedia.org"

UA = {
    "User-Agent": (
        "FrictionRadar/0.3 (https://friction-radar.local; contact: internal) "
        "python-requests"
    )
}

UTAH_CATEGORIES = [
    "Category:Companies based in Utah",
    "Category:Companies based in Salt Lake City",
    "Category:Companies based in Provo, Utah",
    "Category:Companies based in Lehi, Utah",
    "Category:Companies based in Draper, Utah",
    "Category:Companies based in Orem, Utah",
    "Category:Companies based in South Jordan, Utah",
    "Category:Companies based in Sandy, Utah",
    "Category:Companies based in Ogden, Utah",
    "Category:Companies based in Park City, Utah",
    "Category:Companies based in Midvale, Utah",
    "Category:Technology companies based in Utah",
    "Category:Retail companies based in Utah",
]

# Wikipedia pages that are lists / meta, not real companies.
BLACKLIST_SUBSTRINGS = [
    "List of ",
    "Category:",
    "Template:",
    "Companies based in",
    "Economy of Utah",
]


def api_get(params: dict) -> dict:
    q = {"format": "json", "formatversion": "2", **params}
    r = requests.get(WIKI_API, params=q, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_category_members(category: str) -> list[str]:
    members: list[str] = []
    cmcontinue: Optional[str] = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
            "cmtype": "page",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params)
        for m in data.get("query", {}).get("categorymembers", []):
            members.append(m["title"])
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        cmcontinue = cont
    return members


def is_real_company(title: str) -> bool:
    for bad in BLACKLIST_SUBSTRINGS:
        if bad in title:
            return False
    return True


def fetch_infobox_domain_and_industry(title: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (domain, industry, headquarters) extracted from the Wikipedia infobox."""
    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "redirects": 1,
    }
    try:
        data = api_get(params)
    except requests.RequestException:
        return None, None, None

    html = data.get("parse", {}).get("text")
    if not html:
        return None, None, None

    soup = BeautifulSoup(html, "html.parser")
    infobox = soup.find("table", class_=re.compile(r"infobox"))
    if not infobox:
        return None, None, None

    domain: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None

    for row in infobox.find_all("tr"):
        header = row.find("th")
        if not header:
            continue
        label = header.get_text(strip=True).lower()
        value_cell = row.find("td")
        if not value_cell:
            continue

        if "website" in label or "url" in label:
            link = value_cell.find("a", href=True)
            if link:
                href = link["href"]
                parsed = urlparse(href)
                host = parsed.netloc or parsed.path
                host = host.lower()
                if host.startswith("www."):
                    host = host[4:]
                host = host.split("/")[0]
                if host and "." in host:
                    domain = host
            if not domain:
                text = value_cell.get_text(" ", strip=True)
                m = re.search(r"([a-z0-9-]+\.[a-z0-9.-]+)", text.lower())
                if m:
                    domain = m.group(1)

        elif "industry" in label or "type of business" in label:
            industry = value_cell.get_text(", ", strip=True)
            industry = re.sub(r"\[\d+\]", "", industry).strip(", ")

        elif "headquarters" in label or "location" in label or "area served" in label:
            if headquarters is None:
                headquarters = value_cell.get_text(", ", strip=True)
                headquarters = re.sub(r"\[\d+\]", "", headquarters).strip(", ")

    return domain, industry, headquarters


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_titles: set[str] = set()
    print("[1/3] Collecting category members from Wikipedia API…")
    for cat in UTAH_CATEGORIES:
        try:
            members = fetch_category_members(cat)
            real = [t for t in members if is_real_company(t)]
            print(f"  {cat:<55s} -> {len(real):3d} pages")
            all_titles.update(real)
        except requests.RequestException as e:
            print(f"  {cat:<55s} -> ERROR {e}")

    titles = sorted(all_titles)
    print(f"\n[2/3] {len(titles)} unique candidate pages. Extracting infoboxes…")

    companies: list[dict] = []
    for i, title in enumerate(titles, start=1):
        domain, industry, hq = fetch_infobox_domain_and_industry(title)
        status = domain or "—"
        print(f"  [{i:3d}/{len(titles)}] {title[:45]:<45s} {status}")
        companies.append(
            {
                "rank": i,
                "name": title,
                "domain": domain,
                "industry": industry,
                "hq": hq,
                "source": "wikipedia",
                "wiki_url": f"{WIKI_BASE}/wiki/{title.replace(' ', '_')}",
            }
        )
        time.sleep(0.12)  # be polite to Wikipedia

    resolved = [c for c in companies if c["domain"]]
    print(f"\n[3/3] Resolved {len(resolved)}/{len(companies)} domains.")

    # Keep companies with domains first, then re-rank by position.
    with_domain = [c for c in companies if c["domain"]]
    without_domain = [c for c in companies if not c["domain"]]
    for i, c in enumerate(with_domain, start=1):
        c["rank"] = i

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "wikipedia_categories",
        "total_candidates": len(companies),
        "resolved_domains": len(with_domain),
        "companies_with_domain": with_domain,
        "companies_without_domain": [c["name"] for c in without_domain],
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {OUTPUT_PATH}")
    print(
        f"  {len(with_domain)} companies with a resolved domain are in "
        f"'companies_with_domain'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
