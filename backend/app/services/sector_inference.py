"""Sector inference for companies.

Assigns each company to one of ~15 sector buckets using a waterfall of signals:

  1. Explicit `industry` text (if present) → map via INDUSTRY_TEXT_MAP
  2. Name keywords                          → NAME_KEYWORDS
  3. Domain TLD / suffix                    → DOMAIN_KEYWORDS
  4. Functional signature of their hiring   → FUNCTIONAL_HEURISTICS

Higher-priority signals win. Each inference carries a source + confidence
string so downstream consumers (the heatmap) can flag low-confidence cells.

No DB access here — pure functions. Callers wire the inputs.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

SECTORS = [
    "Software & SaaS",
    "AI & Machine Learning",
    "Semiconductors & Hardware",
    "Fintech & Financial Services",
    "Ecommerce & Consumer",
    "Healthcare & Biotech",
    "Media & Entertainment",
    "Gaming",
    "Retail & Hospitality",
    "Manufacturing & Industrial",
    "Logistics & Transportation",
    "Telco & Internet Infra",
    "Education",
    "Real Estate & Construction",
    "Energy & Utilities",
    "Professional Services",
    "Other",
]

# ─── Industry free-text → sector ────────────────────────────────────────────
# Order matters: more specific patterns first.
INDUSTRY_TEXT_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bsemiconductors?\b|\bsemiconductor manufactur\b|\bchip(?:sets?)?\b|\bfoundry\b|\bgpu\b|\bcpu\b|\bhardware\b|\bhome automation\b|\bcomputer hardware\b|\belectronic components?\b|\bembedded\b", re.I), "Semiconductors & Hardware"),
    (re.compile(r"\bartificial intelligence\b|\bmachine learning\b|\bml\b|\bai\b", re.I), "AI & Machine Learning"),
    (re.compile(r"\bfintech\b|\bbanking\b|\binsurance\b|\bfinancial\b|\bpayments?\b|\bpayment processing\b|\bcapital markets\b", re.I), "Fintech & Financial Services"),
    (re.compile(r"\bhealth\b|\bbiotech\b|\bpharma\b|\bmedical\b|\bdiagnostics\b|\bhospital\b|\bclinic", re.I), "Healthcare & Biotech"),
    (re.compile(r"\bvideo games?\b|\bgame developer\b|\bgaming\b|\besports\b", re.I), "Gaming"),
    (re.compile(r"\bretail\b|\bhospitality\b|\brestaurant\b|\bhotel\b|\btourism\b|\btravel\b", re.I), "Retail & Hospitality"),
    (re.compile(r"\becommerce\b|\be-commerce\b|\bmarketplace\b|\bconsumer goods\b|\bpersonal care\b", re.I), "Ecommerce & Consumer"),
    (re.compile(r"\bmedia\b|\bentertainment\b|\bmusic\b|\bfilm\b|\btelevision\b|\bbroadcast", re.I), "Media & Entertainment"),
    (re.compile(r"\bmanufactur\b|\bindustrial\b|\bchemicals?\b|\bmaterials\b|\bnuclear\b|\baerospace\b|\barmored", re.I), "Manufacturing & Industrial"),
    (re.compile(r"\blogistics\b|\bfreight\b|\btransport\b|\baviation\b|\bshipping\b|\bsupply chain\b", re.I), "Logistics & Transportation"),
    (re.compile(r"\btelecom\b|\binternet service\b|\bisp\b|\bcable\b|\bmobile network\b|\bfiber\b|\binternet industry\b|\bweb hosting\b", re.I), "Telco & Internet Infra"),
    (re.compile(r"\beducation\b|\bupskilling\b|\bschool\b|\blearning\b|\bedtech\b", re.I), "Education"),
    (re.compile(r"\bconstruction\b|\breal estate\b|\bproperty\b|\bhousing\b", re.I), "Real Estate & Construction"),
    (re.compile(r"\benergy\b|\butilit\b|\boil\b|\bgas\b|\bpower\b|\bsolar\b|\brenewable\b", re.I), "Energy & Utilities"),
    (re.compile(r"\bconsulting\b|\blegal\b|\blaw\b|\baccounting\b|\badvertising\b|\bagency\b|\bstaffing\b|\brecruiting\b|\bhuman resources?\b|\bhr services?\b", re.I), "Professional Services"),
    # Keep generic tech buckets last so they don't swallow specific ones
    (re.compile(r"\bsoftware\b|\bsaas\b|\bapplication software\b|\bcloud computing\b|\bcomputers\b|\btechnology industry\b|\btechnology\b|\binternet\b|\bit\b|\binformation technology\b", re.I), "Software & SaaS"),
]


# ─── Company name keywords → sector ────────────────────────────────────────
NAME_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(nvidia|amd|intel|qualcomm|cypress|tsmc|micron|broadcom|marvell|analog\s?devices|texas\s?instruments|arm|mediatek|semiconductor|semiconductors?|silicon)\b", re.I), "Semiconductors & Hardware"),
    (re.compile(r"\b(bank|banco|capital|financial|finance|invest|credit|lending|insurance|mortgage|fintech|pay(?:ments?)?|trading)\b", re.I), "Fintech & Financial Services"),
    (re.compile(r"\b(health|medical|clinic|hospital|pharma|bio|genomics?|therapeutics?|diagnostics?|dental)\b", re.I), "Healthcare & Biotech"),
    (re.compile(r"\b(games?|gaming|studio|playst|entertainment)\b", re.I), "Gaming"),
    (re.compile(r"\b(retail|store|shop|market|grocery|boutique|restaurant|food|hotel|resort|hospitality|cafe)\b", re.I), "Retail & Hospitality"),
    (re.compile(r"\b(ecommerce|commerce|shopify|marketplace|brand)\b", re.I), "Ecommerce & Consumer"),
    (re.compile(r"\b(media|studios?|film|music|broadcast|news|publishing|entertainment)\b", re.I), "Media & Entertainment"),
    (re.compile(r"\b(manufactur|industries|chemical|materials|factory|aerospace|defense|metals?)\b", re.I), "Manufacturing & Industrial"),
    (re.compile(r"\b(logistics|freight|shipping|transport|aviation|airlines?|trucking|cargo|delivery)\b", re.I), "Logistics & Transportation"),
    (re.compile(r"\b(telecom|wireless|broadband|network|fiber|isp|cable)\b", re.I), "Telco & Internet Infra"),
    (re.compile(r"\b(education|academy|learning|university|school|edtech|tutor|upskilling)\b", re.I), "Education"),
    (re.compile(r"\b(construction|realty|realestate|real\s?estate|property|homes?|builders?|architects?)\b", re.I), "Real Estate & Construction"),
    (re.compile(r"\b(energy|solar|power|electric|oil|gas|renewable|utilit)\b", re.I), "Energy & Utilities"),
    (re.compile(r"\b(consulting|advisors?|legal|law(?:yer)?|accounting|agency|partners?|staffing|recruit(?:ing|ers?)?|robert\s?half|randstad|adecco|manpower|kelly\s?services|allegis)\b", re.I), "Professional Services"),
    (re.compile(r"\b(ai|\.ai|artificialintelligence|intelligence|neural|llm|gpt)\b", re.I), "AI & Machine Learning"),
    (re.compile(r"\b(software|tech|systems|cloud|platform|labs?|app|digital)\b", re.I), "Software & SaaS"),
]


# ─── Domain patterns → sector ──────────────────────────────────────────────
DOMAIN_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\.ai$", re.I), "AI & Machine Learning"),
    (re.compile(r"\.edu$|\.ac\.[a-z]{2}$", re.I), "Education"),
    (re.compile(r"\.bank$|\.insurance$", re.I), "Fintech & Financial Services"),
    (re.compile(r"\.health$|\.clinic$", re.I), "Healthcare & Biotech"),
    (re.compile(r"\.shop$|\.store$", re.I), "Retail & Hospitality"),
    (re.compile(r"\.games?$|\.gg$", re.I), "Gaming"),
    (re.compile(r"\.media$|\.tv$|\.fm$", re.I), "Media & Entertainment"),
]


# ─── Functional signature heuristic ────────────────────────────────────────
# When we have no declarative signal, infer from how the company hires.
# Input: Counter of {functional_area: count}, excluding junk/unknown.

def infer_from_functions(fn_counts: Counter) -> Optional[Tuple[str, str]]:
    """Return (sector, confidence) or None if signal too weak.

    Confidence is "medium" (clear dominance) or "low" (mixed).
    """
    total = sum(fn_counts.values())
    if total < 2:
        return None  # not enough signal

    def share(*areas: str) -> float:
        return sum(fn_counts.get(a, 0) for a in areas) / total if total else 0.0

    # Dominance thresholds: one pattern must clearly dominate.
    signals = [
        (share("engineering", "product", "data_analytics", "analytics", "it"),          "Software & SaaS"),
        (share("manufacturing", "supply_chain", "operations"),                          "Manufacturing & Industrial"),
        (share("retail", "customer_support", "customer_success", "hospitality"),        "Retail & Hospitality"),
        (share("transportation", "supply_chain"),                                       "Logistics & Transportation"),
        (share("healthcare"),                                                           "Healthcare & Biotech"),
        (share("education"),                                                            "Education"),
        (share("food_service", "hospitality"),                                          "Retail & Hospitality"),
        (share("trades"),                                                               "Real Estate & Construction"),
    ]
    signals.sort(reverse=True)
    top_share, top_sector = signals[0]

    if top_share >= 1.0 and total >= 2:
        return top_sector, "medium"
    if top_share >= 0.60:
        return top_sector, "medium"
    if top_share >= 0.40:
        return top_sector, "low"
    return None


# ─── Main waterfall ─────────────────────────────────────────────────────────

@dataclass
class InferredSector:
    sector: str
    source: str          # "industry_text" | "name" | "domain" | "functional" | "fallback"
    confidence: str      # "high" | "medium" | "low"


def _match_regex_list(text: str, pairs: Iterable[Tuple[re.Pattern, str]]) -> Optional[str]:
    for pat, sector in pairs:
        if pat.search(text):
            return sector
    return None


def infer_sector(
    name: str,
    domain: Optional[str],
    industry_text: Optional[str],
    fn_counts: Optional[Counter] = None,
) -> InferredSector:
    """Run the waterfall and return best sector."""
    # 1. Industry text (declarative, highest-confidence)
    if industry_text:
        match = _match_regex_list(industry_text, INDUSTRY_TEXT_MAP)
        if match:
            return InferredSector(match, "industry_text", "high")

    # 2. Name keywords
    if name:
        match = _match_regex_list(name, NAME_KEYWORDS)
        if match:
            return InferredSector(match, "name", "medium")

    # 3. Domain keywords
    if domain:
        match = _match_regex_list(domain, DOMAIN_KEYWORDS)
        if match:
            return InferredSector(match, "domain", "medium")

    # 4. Functional signature (behavioral)
    if fn_counts:
        fn_match = infer_from_functions(fn_counts)
        if fn_match:
            return InferredSector(fn_match[0], "functional", fn_match[1])

    return InferredSector("Other", "fallback", "low")
