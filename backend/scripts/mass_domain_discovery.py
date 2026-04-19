"""Mass domain discovery for Florida companies using concurrent HTTP probing."""
import re
import sys
import os
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import app.models
from app.db.session import SessionLocal
from app.master.models import CompanyMaster
from app.master.domain_models import CompanyDomain

GENERIC_DOMAINS = {
    "palm.com", "google.com", "faith.com", "eagle.com", "vision.com",
    "summit.com", "trust.com", "legacy.com", "global.com", "elite.com",
    "premier.com", "apex.com", "prime.com", "alpha.com", "atlas.com",
    "core.com", "edge.com", "next.com", "spark.com", "swift.com",
    "pure.com", "first.com", "fresh.com", "bright.com", "clear.com",
    "light.com", "smart.com", "safe.com", "star.com", "sun.com",
    "sky.com", "sea.com", "bay.com", "oak.com", "ivy.com",
    "ace.com", "fox.com", "bee.com", "one.com", "pro.com",
    "united.com", "liberty.com", "patriot.com", "pioneer.com",
    "horizon.com", "bridge.com", "shield.com", "crown.com",
    "diamond.com", "golden.com", "silver.com", "national.com",
    "american.com", "coastal.com", "island.com", "tropical.com",
    "pacific.com", "atlantic.com", "gulf.com", "southern.com",
    "western.com", "northern.com", "eastern.com", "central.com",
    "metro.com", "urban.com", "royal.com", "noble.com",
    "garden.com", "paradise.com", "crystal.com", "magic.com",
    "phoenix.com", "titan.com", "omega.com", "delta.com",
    "sigma.com", "venture.com", "fortune.com", "dream.com",
    "power.com", "force.com", "flow.com", "wave.com", "rise.com",
    "rocket.com", "hero.com", "sage.com", "luna.com", "nova.com",
    "bolt.com", "zeus.com", "mars.com", "crest.com", "peak.com",
    "arch.com", "link.com", "base.com", "point.com", "node.com",
    "grid.com", "mesh.com", "haven.com", "nest.com", "hive.com",
    "fleet.com", "relay.com", "care.com", "home.com", "build.com",
    "craft.com", "works.com", "labs.com", "studio.com", "group.com",
    "solutions.com", "services.com", "systems.com", "partners.com",
    "holdings.com", "capital.com", "properties.com", "construction.com",
    "consulting.com", "management.com", "enterprise.com", "industries.com",
    "investments.com", "development.com", "technologies.com",
    "ironwood.com", "radiant.com", "everglades.com", "sunshine.com",
    "guardian.com", "pinnacle.com", "keystone.com", "landmark.com",
    "beacon.com", "harbor.com", "compass.com", "catalyst.com",
    "prestige.com", "integrity.com", "heritage.com", "infinity.com",
    "matrix.com", "quantum.com", "sterling.com", "vanguard.com",
    "summit.com", "element.com", "fusion.com", "impact.com",
    "nexus.com", "synergy.com", "velocity.com", "zenith.com",
}

PARKED_INDICATORS = [
    "domain is for sale", "buy this domain", "parked free",
    "godaddy", "sedoparking", "hugedomains", "afternic",
    "dan.com", "undeveloped", "this domain", "coming soon",
    "under construction", "page not found", "default web page",
    "welcome to nginx", "apache2 default", "it works!",
    "website is under construction", "site is under maintenance",
    "domain for sale", "this page is parked", "domainlane",
    "namecheap", "register.com", "domain parking",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FrictionRadar/1.0",
    "Accept": "text/html",
})


def name_to_slug(normalized_name):
    name = normalized_name.strip()
    name = re.sub(
        r"\b(group|services|solutions|consulting|management|holdings|"
        r"enterprises?|industries|investments?|construction|properties|"
        r"technologies|corporation|incorporated|company|associates?|"
        r"repair|cleaning|manufacturing|property|nonprofits?|homes?)\b",
        "", name,
    ).strip()

    slugs = []
    words = name.split()
    if not words:
        return []

    full = "".join(words)
    if len(full) >= 3:
        slugs.append(full)

    if len(words) > 1:
        slugs.append("-".join(words))

    if len(words[0]) >= 5:
        slugs.append(words[0])

    if len(words) >= 2:
        two = "".join(words[:2])
        if len(two) >= 5:
            slugs.append(two)

    return list(dict.fromkeys(slugs))


def probe_domain(domain, timeout=4):
    for scheme in ("https", "http"):
        try:
            r = session.get(f"{scheme}://{domain}", timeout=timeout, allow_redirects=True)
            title = ""
            if r.status_code < 500:
                m = re.search(r"<title[^>]*>([^<]+)</title>", r.text[:5000], re.IGNORECASE)
                if m:
                    title = m.group(1).strip()[:200]
            final_domain = r.url.split("//")[-1].split("/")[0].lower().replace("www.", "")
            redirect = final_domain if final_domain != domain.replace("www.", "") else None
            return {
                "domain": domain,
                "status": r.status_code,
                "title": title,
                "redirect": redirect,
            }
        except Exception:
            continue
    return None


def is_parked(title):
    title_lower = (title or "").lower()
    return any(ind in title_lower for ind in PARKED_INDICATORS)


def discover_domain(company_id, normalized_name):
    slugs = name_to_slug(normalized_name)
    for slug in slugs:
        domain = f"{slug}.com"
        if domain in GENERIC_DOMAINS or len(slug) <= 2:
            continue
        result = probe_domain(domain)
        if not result:
            continue
        if result["status"] < 400:
            if is_parked(result["title"]):
                continue
            if result.get("redirect") and result["redirect"] in GENERIC_DOMAINS:
                continue
            return {"company_id": company_id, "domain": domain, **result}
        elif result["status"] in (403, 429):
            return {"company_id": company_id, "domain": domain, **result}
    return None


def main():
    db = SessionLocal()
    subq = db.query(CompanyDomain.company_master_id).distinct()
    companies = (
        db.query(CompanyMaster.id, CompanyMaster.normalized_name, CompanyMaster.legal_name)
        .filter(
            CompanyMaster.source_confidence == 0.80,
            CompanyMaster.jurisdiction_state == "FL",
            ~CompanyMaster.id.in_(subq),
        )
        .all()
    )
    db.close()

    print(f"Probing domains for {len(companies)} companies (20 threads)...")

    found = []
    checked = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(discover_domain, str(c.id), c.normalized_name): c
            for c in companies
        }
        for future in as_completed(futures):
            checked += 1
            result = future.result()
            if result:
                found.append(result)
            if checked % 200 == 0:
                print(f"  Checked {checked}/{len(companies)}, found {len(found)} so far...")

    print(f"\nDone! Checked {checked}, found {len(found)} domains")

    if found:
        db = SessionLocal()
        saved = 0
        for r in found:
            try:
                exists = db.query(CompanyDomain).filter(
                    CompanyDomain.company_master_id == r["company_id"],
                    CompanyDomain.domain == r["domain"],
                ).first()
                if not exists:
                    db.add(CompanyDomain(
                        company_master_id=r["company_id"],
                        domain=r["domain"],
                        is_primary=True,
                        domain_status="resolved",
                        confidence=0.70,
                        source="auto_discovery_name_probe",
                        http_status=r["status"],
                        title_tag=r.get("title", "")[:200] if r.get("title") else None,
                        redirects_to=r.get("redirect"),
                        last_checked_at=datetime.now(timezone.utc),
                        last_verified_at=datetime.now(timezone.utc),
                    ))
                    saved += 1
            except Exception as e:
                print(f"  Error saving {r['domain']}: {e}")

        db.commit()
        db.close()
        print(f"Saved {saved} new domains to company_domains")

    print(f"\nSample found domains:")
    for r in found[:30]:
        print(f"  {r['domain']:40s} HTTP {r['status']}  {(r.get('title') or '')[:50]}")


if __name__ == "__main__":
    main()
