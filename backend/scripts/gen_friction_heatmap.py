"""Generate a self-contained HTML friction heatmap: sector x functional_area.

Each cell = companies that (a) belong to the sector and (b) hire in that function.
Color intensity = composite pain_score.

pain_score = 0.35 * pct_specific_pain        (% diag in {specific_pain_identified, ready_for_positioning})
           + 0.25 * function_dominance      (mean roles_in_F / total_classified_roles of the company)
           + 0.20 * pct_eligible            (% passing full or conditional gate)
           + 0.10 * velocity_30d            (recent roles in F / total roles in F)
           + 0.10 * concentration_signal    (HIGH=1, MODERATE=0.5, LOW=0)

Output: output/friction_heatmap_{YYYYMMDD}.html (portable, no external deps).
Usage:  python scripts/gen_friction_heatmap.py [--min-companies 3] [--output PATH]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole

EXCLUDED_AREAS = {None, "", "junk", "unknown", "Technology"}

# Display order for functional areas (columns)
FUNCTION_DISPLAY_ORDER = [
    "engineering",
    "product",
    "data_analytics",
    "analytics",
    "it",
    "sales",
    "marketing",
    "customer_support",
    "customer_success",
    "operations",
    "supply_chain",
    "finance",
    "hr",
    "hr_people",
    "recruiting",
    "recruiting_talent",
    "legal",
    "legal_compliance",
    "manufacturing",
    "retail",
    "healthcare",
    "hospitality",
    "education",
    "trades",
    "transportation",
    "food_service",
]

STATE_LABELS = {
    "ready_for_positioning": "Listo para posicionar",
    "specific_pain_identified": "Dolor específico identificado",
    "specific_pain_emerging": "Dolor emergiendo",
    "broad_hiring_pattern_detected": "Hiring amplio / sin foco",
    "insufficient_evidence": "Evidencia insuficiente",
}

FUNCTION_LABELS = {
    "engineering": "Engineering",
    "product": "Product",
    "data_analytics": "Data/Analytics",
    "analytics": "Analytics",
    "it": "IT",
    "sales": "Sales",
    "marketing": "Marketing",
    "customer_support": "Customer Support",
    "customer_success": "Customer Success",
    "operations": "Operations",
    "supply_chain": "Supply Chain",
    "finance": "Finance",
    "hr": "HR / People",
    "hr_people": "HR / People",
    "recruiting": "Recruiting",
    "recruiting_talent": "Recruiting",
    "legal": "Legal",
    "legal_compliance": "Legal",
    "manufacturing": "Manufacturing",
    "retail": "Retail Ops",
    "healthcare": "Healthcare",
    "hospitality": "Hospitality",
    "education": "Education",
    "trades": "Trades",
    "transportation": "Transport",
    "food_service": "Food Service",
}

SECTOR_DISPLAY_ORDER = [
    "Software & SaaS",
    "AI & Machine Learning",
    "Fintech & Financial Services",
    "Healthcare & Biotech",
    "Ecommerce & Consumer",
    "Retail & Hospitality",
    "Media & Entertainment",
    "Gaming",
    "Manufacturing & Industrial",
    "Logistics & Transportation",
    "Telco & Internet Infra",
    "Energy & Utilities",
    "Professional Services",
    "Real Estate & Construction",
    "Education",
    "Other",
]


# ─── Per-company derived metrics ────────────────────────────────────────────

def compute_concentration(fn_counts: Counter) -> str:
    total = sum(fn_counts.values())
    if total == 0:
        return "low"
    top = max(fn_counts.values())
    areas = len(fn_counts)
    share = top / total
    if total >= 3 and share >= 0.50 and areas <= 3:
        return "high"
    if total >= 2 and share >= 0.35 and areas <= 4:
        return "moderate"
    return "low"


def compute_eligibility(state: str, fn_counts: Counter) -> str:
    classified = sum(fn_counts.values())
    top_share = (max(fn_counts.values()) / classified) if classified else 0.0
    if state in ("ready_for_positioning", "specific_pain_identified"):
        return "full"
    if state == "specific_pain_emerging" and classified >= 3 and top_share >= 0.35:
        return "conditional"
    if state == "broad_hiring_pattern_detected":
        if classified >= 5 and top_share >= 0.35:
            return "conditional"
        if classified >= 15:
            return "conditional"
    return "none"


CONCENTRATION_VALUE = {"high": 1.0, "moderate": 0.5, "low": 0.0}


# ─── Main aggregation ───────────────────────────────────────────────────────

def aggregate(db, min_companies: int):
    companies = db.query(Company).all()
    company_by_id = {c.id: c for c in companies}

    roles_by_company: dict = defaultdict(list)
    fn_counts_by_company: dict = defaultdict(Counter)
    recent_roles_by_company_fn: dict = defaultdict(int)

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    for r in db.query(CompanyJobRole).all():
        roles_by_company[r.company_id].append(r)
        if r.functional_area not in EXCLUDED_AREAS:
            fn_counts_by_company[r.company_id][r.functional_area] += 1
            if r.discovered_at and r.discovered_at >= cutoff_30d:
                recent_roles_by_company_fn[(r.company_id, r.functional_area)] += 1

    # company-level derived state
    derived = {}
    for c in companies:
        fn_counts = fn_counts_by_company.get(c.id, Counter())
        derived[c.id] = {
            "fn_counts": fn_counts,
            "total_classified": sum(fn_counts.values()),
            "concentration": compute_concentration(fn_counts),
            "eligibility": compute_eligibility(c.latest_diagnostic_state or "", fn_counts),
            "specific_pain": (c.latest_diagnostic_state or "") in (
                "ready_for_positioning", "specific_pain_identified"
            ),
        }

    # Build cells: (sector, function) → aggregation
    cells: dict = defaultdict(lambda: {
        "companies": [],
        "sum_dominance": 0.0,
        "sum_concentration": 0.0,
        "sum_pain": 0,
        "sum_eligible": 0,
        "sum_recent": 0,
        "sum_roles_in_f": 0,
    })

    for c in companies:
        sector = c.inferred_sector or "Other"
        d = derived[c.id]
        if d["total_classified"] == 0:
            continue

        # Company-level dominant area (for pain context in the tooltip)
        top_area, top_count = (d["fn_counts"].most_common(1) or [(None, 0)])[0]
        top_area_share = top_count / d["total_classified"] if d["total_classified"] else 0.0
        top_area_label = FUNCTION_LABELS.get(top_area, top_area or "—")

        state_label = STATE_LABELS.get(
            c.latest_diagnostic_state or "",
            c.latest_diagnostic_state or "sin señal",
        )

        # Interpretive 1-liner about the company's pain shape
        if c.latest_diagnostic_state in ("ready_for_positioning", "specific_pain_identified"):
            pain_summary = (
                f"Dolor concentrado en {top_area_label} ({int(top_area_share*100)}% del hiring)"
            )
        elif c.latest_diagnostic_state == "specific_pain_emerging":
            pain_summary = f"Dolor emergente — foco en {top_area_label}"
        elif c.latest_diagnostic_state == "broad_hiring_pattern_detected":
            n_areas = len(d["fn_counts"])
            areas_word = "área" if n_areas == 1 else "áreas"
            pain_summary = (
                f"Contratando en {n_areas} {areas_word} — top: {top_area_label} ({int(top_area_share*100)}%)"
            )
        else:
            pain_summary = "Sin patrón de dolor claro"

        for fn, cnt in d["fn_counts"].items():
            key = (sector, fn)
            cell = cells[key]
            dominance = cnt / d["total_classified"]
            cell["companies"].append({
                "name": c.name,
                "domain": c.domain,
                "state": c.latest_diagnostic_state,
                "state_label": state_label,
                "eligibility": d["eligibility"],
                "roles_in_f": cnt,
                "total_roles": d["total_classified"],
                "dominance": round(dominance, 3),
                "concentration": d["concentration"],
                "top_area": top_area,
                "top_area_label": top_area_label,
                "top_area_share": round(top_area_share, 3),
                "pain_summary": pain_summary,
            })
            cell["sum_dominance"] += dominance
            cell["sum_concentration"] += CONCENTRATION_VALUE[d["concentration"]]
            cell["sum_pain"] += 1 if d["specific_pain"] else 0
            cell["sum_eligible"] += 1 if d["eligibility"] in ("full", "conditional") else 0
            cell["sum_recent"] += recent_roles_by_company_fn.get((c.id, fn), 0)
            cell["sum_roles_in_f"] += cnt

    # compute pain_score per cell
    for key, cell in cells.items():
        n = len(cell["companies"])
        if n == 0:
            cell["pain_score"] = 0.0
            continue
        pct_pain = cell["sum_pain"] / n
        mean_dom = cell["sum_dominance"] / n
        pct_elig = cell["sum_eligible"] / n
        velocity = (
            cell["sum_recent"] / cell["sum_roles_in_f"]
            if cell["sum_roles_in_f"] else 0.0
        )
        mean_conc = cell["sum_concentration"] / n
        pain = (
            0.35 * pct_pain
            + 0.25 * mean_dom
            + 0.20 * pct_elig
            + 0.10 * velocity
            + 0.10 * mean_conc
        )
        cell["pain_score"] = round(pain, 3)
        cell["pct_pain"] = round(pct_pain, 3)
        cell["pct_eligible"] = round(pct_elig, 3)
        cell["mean_dominance"] = round(mean_dom, 3)
        cell["velocity"] = round(velocity, 3)
        cell["mean_concentration"] = round(mean_conc, 3)
        cell["n"] = n

    # collect present sectors and functions, ordered
    present_sectors = {s for (s, _) in cells.keys()}
    sectors = [s for s in SECTOR_DISPLAY_ORDER if s in present_sectors]
    extras = sorted(present_sectors - set(sectors))
    sectors.extend(extras)

    present_functions = {f for (_, f) in cells.keys()}
    functions = []
    seen = set()
    for f in FUNCTION_DISPLAY_ORDER:
        if f in present_functions and f not in seen:
            functions.append(f)
            seen.add(f)
    for f in sorted(present_functions - seen):
        functions.append(f)

    # Filter: keep only cells with >= min_companies; mark others as sparse
    for key, cell in cells.items():
        cell["sparse"] = cell["n"] < min_companies

    return {
        "cells": cells,
        "sectors": sectors,
        "functions": functions,
        "total_companies": len(companies),
        "classified_companies": sum(1 for d in derived.values() if d["total_classified"] > 0),
    }


# ─── Public helper: single-cell companies (reused by /internal/v1/heatmap/cell) ─

def compute_cell_companies(
    db, sector: str, function: str, *, min_companies: int = 1
) -> dict:
    """Return the heatmap payload for one (sector, function) cell.

    Shape mirrors what the HTML renderer consumes:

        {
          "sector": str,
          "function": str,
          "n": int,
          "pain_score": float,
          "pct_pain": float, "pct_eligible": float,
          "mean_dominance": float, "velocity": float,
          "mean_concentration": float,
          "sparse": bool,
          "companies": [sorted by eligibility gate, then roles_in_f],
        }

    Empty cell returns n=0 and empty companies list.
    """
    agg = aggregate(db, min_companies=min_companies)
    cell = agg["cells"].get((sector, function))
    if cell is None:
        return {
            "sector": sector,
            "function": function,
            "n": 0,
            "pain_score": 0.0,
            "pct_pain": 0.0,
            "pct_eligible": 0.0,
            "mean_dominance": 0.0,
            "velocity": 0.0,
            "mean_concentration": 0.0,
            "sparse": True,
            "companies": [],
        }

    sorted_companies = sorted(
        cell["companies"],
        key=lambda c: (
            0 if c["eligibility"] == "full" else
            1 if c["eligibility"] == "conditional" else 2,
            -c["roles_in_f"],
        ),
    )
    return {
        "sector": sector,
        "function": function,
        "n": cell.get("n", len(cell["companies"])),
        "pain_score": cell.get("pain_score", 0.0),
        "pct_pain": cell.get("pct_pain", 0.0),
        "pct_eligible": cell.get("pct_eligible", 0.0),
        "mean_dominance": cell.get("mean_dominance", 0.0),
        "velocity": cell.get("velocity", 0.0),
        "mean_concentration": cell.get("mean_concentration", 0.0),
        "sparse": cell.get("sparse", False),
        "companies": sorted_companies,
    }


# ─── HTML rendering ─────────────────────────────────────────────────────────

def render_html(agg: dict, min_companies: int) -> str:
    cells = agg["cells"]
    sectors = agg["sectors"]
    functions = agg["functions"]

    # top cells by pain (excluding sparse)
    strong_cells = [
        ((s, f), cell) for (s, f), cell in cells.items()
        if not cell["sparse"]
    ]
    strong_cells.sort(key=lambda x: -x[1]["pain_score"])
    top10 = strong_cells[:10]

    # prepare JSON-safe cell data
    cell_data_for_js = {}
    for (s, f), cell in cells.items():
        cell_data_for_js[f"{s}||{f}"] = {
            "n": cell["n"],
            "pain": cell["pain_score"],
            "pct_pain": cell.get("pct_pain", 0),
            "pct_eligible": cell.get("pct_eligible", 0),
            "mean_dominance": cell.get("mean_dominance", 0),
            "velocity": cell.get("velocity", 0),
            "sparse": cell["sparse"],
            "companies": sorted(
                cell["companies"],
                key=lambda c: (
                    0 if c["eligibility"] == "full" else
                    1 if c["eligibility"] == "conditional" else 2,
                    -c["roles_in_f"],
                ),
            ),
            "total_companies": len(cell["companies"]),
        }

    today = datetime.now().strftime("%Y-%m-%d")

    # Build top narrative
    narrative_rows = []
    for (s, f), cell in top10:
        narrative_rows.append(
            f'<li><b>{html.escape(s)} × {html.escape(FUNCTION_LABELS.get(f, f))}</b> '
            f'— score <span class="score">{cell["pain_score"]:.2f}</span> '
            f'({cell["n"]} empresas, '
            f'{int(cell.get("pct_pain", 0)*100)}% en dolor específico, '
            f'{int(cell.get("pct_eligible", 0)*100)}% eligible)</li>'
        )
    narrative_html = "\n".join(narrative_rows) if narrative_rows else "<li>No high-density cells yet.</li>"

    # Build table rows
    def pain_color(p: float, sparse: bool) -> str:
        if sparse:
            return "#f5f5f5"
        # Red scale, 0 -> #fff3e0 (very pale), 1 -> #b71c1c (deep red)
        # but cap effective range at 0.6 (few cells get above that)
        t = min(p / 0.6, 1.0)
        r = int(255 - (255 - 183) * t)
        g = int(243 - (243 - 28) * t)
        b = int(224 - (224 - 28) * t)
        return f"rgb({r},{g},{b})"

    def text_color(p: float, sparse: bool) -> str:
        if sparse:
            return "#999"
        return "#fff" if p / 0.6 > 0.5 else "#222"

    rows_html = []
    header_cells = '<th class="sector-head"></th>' + "".join(
        f'<th class="func-head"><div>{html.escape(FUNCTION_LABELS.get(f, f))}</div></th>'
        for f in functions
    )
    rows_html.append(f"<thead><tr>{header_cells}</tr></thead>")
    rows_html.append("<tbody>")

    for s in sectors:
        cells_in_row = []
        for f in functions:
            cell = cells.get((s, f))
            if cell is None:
                cells_in_row.append('<td class="empty"></td>')
                continue
            p = cell["pain_score"]
            n = cell["n"]
            bg = pain_color(p, cell["sparse"])
            fg = text_color(p, cell["sparse"])
            sparse_class = " sparse" if cell["sparse"] else ""
            cells_in_row.append(
                f'<td class="cell{sparse_class}" '
                f'style="background:{bg};color:{fg};" '
                f'data-key="{html.escape(s)}||{f}">'
                f'<div class="score-big">{p:.2f}</div>'
                f'<div class="n-small">n={n}</div>'
                f'</td>'
            )
        sector_label = html.escape(s)
        if s == "Other":
            sector_label = "Unclassified"
        rows_html.append(
            f'<tr><th class="sector-row">{sector_label}</th>{"".join(cells_in_row)}</tr>'
        )
    rows_html.append("</tbody>")
    table_html = "<table>" + "\n".join(rows_html) + "</table>"

    cell_data_json = json.dumps(cell_data_for_js, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>FrictionRadar — Sector × Función Heatmap ({today})</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    margin: 0; padding: 28px;
    background: #fafafa;
    color: #1a1a1a;
  }}
  h1 {{ margin: 0 0 6px 0; font-size: 26px; letter-spacing: -0.5px; }}
  .subtitle {{ color: #666; margin-bottom: 26px; font-size: 14px; }}
  .meta {{
    display: flex; gap: 24px; margin-bottom: 22px; font-size: 13px;
    padding: 12px 16px; background: #fff; border: 1px solid #eee; border-radius: 6px;
  }}
  .meta b {{ color: #111; }}
  .legend {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: #555; }}
  .legend-bar {{
    width: 240px; height: 14px; border-radius: 3px;
    background: linear-gradient(to right, rgb(255,243,224), rgb(183,28,28));
  }}
  details.narrative {{
    background: #fff; border: 1px solid #eee; border-radius: 6px;
    padding: 0; margin-bottom: 20px; font-size: 14px;
  }}
  details.narrative summary {{
    cursor: pointer; padding: 12px 20px; list-style: none;
    display: flex; align-items: center; gap: 10px;
  }}
  details.narrative summary::-webkit-details-marker {{ display: none; }}
  details.narrative summary::before {{
    content: "▸"; color: #999; font-size: 12px; transition: transform 0.15s ease;
    display: inline-block;
  }}
  details.narrative[open] summary::before {{ transform: rotate(90deg); }}
  details.narrative summary h3 {{
    display: inline; margin: 0; font-size: 13px; text-transform: uppercase;
    letter-spacing: 1px; color: #666; font-weight: 600;
  }}
  details.narrative summary .hint {{
    margin-left: 8px; font-size: 11px; color: #aaa; text-transform: none;
    letter-spacing: normal; font-weight: 400;
  }}
  details.narrative[open] summary .hint {{ display: none; }}
  details.narrative > ol {{ margin: 4px 20px 12px 38px; padding: 0; line-height: 1.7; }}
  details.narrative .score {{
    font-family: ui-monospace, monospace; background: #fff3e0; padding: 1px 6px; border-radius: 3px;
    font-weight: 600;
  }}
  table {{
    border-collapse: separate; border-spacing: 2px;
    background: #fff; padding: 8px;
    border-radius: 6px; border: 1px solid #eee;
  }}
  th.sector-head {{ background: transparent; }}
  th.func-head {{
    font-size: 11px; color: #555; text-align: center;
    padding: 6px 4px; min-width: 90px; max-width: 90px;
    font-weight: 500;
    vertical-align: bottom;
  }}
  th.func-head div {{
    writing-mode: vertical-rl; transform: rotate(180deg);
    white-space: nowrap; height: 90px;
  }}
  th.sector-row {{
    text-align: right; padding: 0 10px; font-weight: 500; font-size: 13px;
    color: #222; background: transparent;
    min-width: 220px; max-width: 240px;
  }}
  td.cell {{
    width: 90px; height: 60px;
    text-align: center; vertical-align: middle;
    font-family: ui-monospace, monospace;
    border-radius: 4px; cursor: pointer;
    transition: transform 0.08s ease, box-shadow 0.08s ease;
    user-select: none;
    position: relative;
  }}
  td.cell:hover {{ transform: scale(1.08); box-shadow: 0 4px 14px rgba(0,0,0,0.25); z-index: 10; }}
  td.cell .score-big {{ font-size: 15px; font-weight: 700; line-height: 1.1; }}
  td.cell .n-small {{ font-size: 10px; opacity: 0.85; margin-top: 2px; }}
  td.cell.sparse {{
    background: repeating-linear-gradient(45deg, #f7f7f7, #f7f7f7 6px, #efefef 6px, #efefef 12px) !important;
    color: #aaa !important;
  }}
  td.empty {{ background: #fff; width: 90px; height: 60px; }}
  #tooltip {{
    position: fixed;
    background: #111; color: #fff;
    padding: 12px 14px; border-radius: 6px;
    font-size: 12px; line-height: 1.5;
    max-width: 400px; min-width: 280px;
    max-height: 70vh;
    display: flex; flex-direction: column;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    pointer-events: auto;
    opacity: 0; visibility: hidden;
    transition: opacity 0.12s ease, visibility 0s linear 0.12s;
    z-index: 1000;
  }}
  #tooltip.visible {{
    opacity: 1; visibility: visible;
    transition: opacity 0.12s ease, visibility 0s linear 0s;
  }}
  #tooltip .title {{ font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #fff; flex: 0 0 auto; }}
  #tooltip .stats {{ color: #bbb; margin-bottom: 4px; font-family: ui-monospace, monospace; flex: 0 0 auto; }}
  #tooltip .stats span {{ color: #fff; }}
  #tooltip .stats .metric {{ border-bottom: 1px dotted #666; cursor: help; }}
  #tooltip details.glossary {{
    flex: 0 0 auto; margin: 0 0 8px 0; font-size: 10.5px; color: #888;
  }}
  #tooltip details.glossary summary {{
    cursor: pointer; list-style: none; color: #7aa7ff;
    font-size: 10.5px; padding: 2px 0;
  }}
  #tooltip details.glossary summary::-webkit-details-marker {{ display: none; }}
  #tooltip details.glossary summary::before {{
    content: "ⓘ "; color: #7aa7ff;
  }}
  #tooltip details.glossary[open] summary::before {{ content: "▾ "; }}
  #tooltip details.glossary dl {{
    margin: 4px 0 0 0; padding: 6px 10px; background: #1a1a1a;
    border-radius: 4px; line-height: 1.45;
  }}
  #tooltip details.glossary dt {{
    display: inline; color: #ffb74d; font-family: ui-monospace, monospace;
    font-weight: 600;
  }}
  #tooltip details.glossary dd {{
    display: inline; margin: 0 0 0 4px; color: #bbb;
  }}
  #tooltip details.glossary dd::after {{ content: ""; display: block; margin-bottom: 3px; }}
  #tooltip .companies {{
    border-top: 1px solid #333; padding-top: 8px;
    overflow-y: auto; overflow-x: hidden;
    flex: 1 1 auto;
    scrollbar-width: thin; scrollbar-color: #444 #1a1a1a;
  }}
  #tooltip .companies::-webkit-scrollbar {{ width: 8px; }}
  #tooltip .companies::-webkit-scrollbar-track {{ background: #1a1a1a; border-radius: 4px; }}
  #tooltip .companies::-webkit-scrollbar-thumb {{ background: #444; border-radius: 4px; }}
  #tooltip .companies::-webkit-scrollbar-thumb:hover {{ background: #555; }}
  #tooltip .company {{ margin-bottom: 10px; }}
  #tooltip .company:last-child {{ margin-bottom: 0; }}
  #tooltip .company .eligible-full {{ color: #ff7043; font-weight: 700; }}
  #tooltip .company .eligible-cond {{ color: #ffb300; font-weight: 600; }}
  #tooltip .company .eligible-none {{ color: #888; }}
  #tooltip .company .pain {{
    color: #ffd7b5; font-size: 11px; margin: 2px 0 1px 18px; line-height: 1.35;
  }}
  #tooltip .company .meta {{
    color: #888; font-family: ui-monospace, monospace; font-size: 10px;
    margin-left: 18px; line-height: 1.3;
  }}
  .formula {{
    font-family: ui-monospace, monospace;
    background: #f0f0f0; padding: 8px 12px; border-radius: 4px;
    font-size: 11px; color: #444; margin: 6px 20px 14px 20px; line-height: 1.6;
  }}
  .footer-note {{ color: #888; font-size: 11px; margin-top: 18px; line-height: 1.6; }}
</style>
</head>
<body>
<h1>FrictionRadar — Mapa de dolor por sector × función</h1>
<div class="subtitle">Generado {today} · Pasa el mouse sobre una celda para ver las empresas.</div>

<div class="meta">
  <div><b>{agg["classified_companies"]}</b> empresas con señal / {agg["total_companies"]} en corpus</div>
  <div><b>{len(agg["sectors"])}</b> sectores</div>
  <div><b>{len(agg["functions"])}</b> funciones</div>
  <div><b>{len([c for c in cells.values() if not c["sparse"]])}</b> celdas densas (≥{min_companies} empresas)</div>
  <div class="legend">Pain score <div class="legend-bar"></div> <span>0.0</span>→<span>0.6+</span></div>
</div>

<details class="narrative">
  <summary><h3>Top 10 celdas de mayor dolor <span class="hint">(click para expandir)</span></h3></summary>
  <ol>{narrative_html}</ol>
  <div class="formula">
    pain = 0.35·(% dolor específico) + 0.25·(dominancia de función) + 0.20·(% eligible)
         + 0.10·(velocidad 30d) + 0.10·(concentración funcional)
  </div>
</details>

{table_html}

<div class="footer-note">
  Las celdas con patrón diagonal tienen n&lt;{min_companies} empresas — muestra insuficiente, interpretar con cautela.<br/>
  "Unclassified" = empresas sin industry declarada y sin señales fuertes en nombre/dominio/hiring.
</div>

<div id="tooltip"></div>

<script>
const CELL_DATA = {cell_data_json};
const tooltip = document.getElementById("tooltip");

function eligibleClass(e) {{
  if (e === "full") return "eligible-full";
  if (e === "conditional") return "eligible-cond";
  return "eligible-none";
}}

function eligibleTag(e) {{
  if (e === "full") return "★ full";
  if (e === "conditional") return "◯ cond";
  return "·";
}}

let hideTimer = null;

function scheduleHide() {{
  if (hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(() => tooltip.classList.remove("visible"), 180);
}}

function cancelHide() {{
  if (hideTimer) {{ clearTimeout(hideTimer); hideTimer = null; }}
}}

function positionTooltip(cellEl) {{
  const rect = cellEl.getBoundingClientRect();
  const pad = 10;
  // Try right side first
  let x = rect.right + pad;
  let y = rect.top;
  const tw = tooltip.offsetWidth;
  const th = tooltip.offsetHeight;
  if (x + tw > window.innerWidth - 8) {{
    // Flip to left side
    x = rect.left - tw - pad;
  }}
  if (x < 8) x = 8;
  if (y + th > window.innerHeight - 8) {{
    y = Math.max(8, window.innerHeight - th - 8);
  }}
  if (y < 8) y = 8;
  tooltip.style.left = x + "px";
  tooltip.style.top = y + "px";
}}

document.querySelectorAll("td.cell").forEach(cell => {{
  cell.addEventListener("mouseenter", () => {{
    cancelHide();
    const key = cell.dataset.key;
    const data = CELL_DATA[key];
    if (!data) return;
    const [sector, fn] = key.split("||");
    let html = `<div class="title">${{sector}} × ${{fn.replace(/_/g, " ")}}</div>`;
    html += `<div class="stats">`;
    html += `<span class="metric" title="Empresas en esta celda (sector × función)">n</span>=<span>${{data.n}}</span> · `;
    html += `<span class="metric" title="Pain score compuesto 0-1. Fórmula: 0.35·pain% + 0.25·dom + 0.20·elig% + 0.10·vel30d + 0.10·concentración">pain</span>=<span>${{data.pain.toFixed(2)}}</span> · `;
    html += `<span class="metric" title="% de empresas con diagnóstico 'specific_pain_identified' o 'ready_for_positioning' (dolor concreto y accionable)">pain%</span>=<span>${{Math.round(data.pct_pain * 100)}}%</span> · `;
    html += `<span class="metric" title="% de empresas que pasan el gate de elegibilidad (full + conditional) para acción comercial">elig%</span>=<span>${{Math.round(data.pct_eligible * 100)}}%</span><br/>`;
    html += `<span class="metric" title="Dominancia funcional media: qué tan concentrado está el hiring en esta función (roles en función / total roles clasificados)">dom</span>=<span>${{(data.mean_dominance*100).toFixed(0)}}%</span> · `;
    html += `<span class="metric" title="Velocidad últimos 30 días: % de roles de esta función descubiertos en los últimos 30d (señal de momentum reciente)">vel30d</span>=<span>${{(data.velocity*100).toFixed(0)}}%</span>`;
    html += `</div>`;
    html += `<details class="glossary"><summary>¿Qué significan estos valores?</summary>`;
    html += `<dl>`;
    html += `<dt>n</dt><dd>= empresas dentro de esta celda (sector × función).</dd>`;
    html += `<dt>pain</dt><dd>= score compuesto 0-1 que resume el dolor agregado. Fórmula: 0.35·pain% + 0.25·dom + 0.20·elig% + 0.10·vel30d + 0.10·concentración.</dd>`;
    html += `<dt>pain%</dt><dd>= % de empresas con diagnóstico de <b>dolor específico</b> (listas para posicionar o con dolor concreto identificado).</dd>`;
    html += `<dt>elig%</dt><dd>= % que pasan el gate de elegibilidad (full + conditional) — las que serían accionables comercialmente.</dd>`;
    html += `<dt>dom</dt><dd>= dominancia funcional media — qué tan concentrado está el hiring en esta función vs. el total de roles clasificados de la empresa.</dd>`;
    html += `<dt>vel30d</dt><dd>= velocidad: % de roles de esta función descubiertos en los últimos 30 días (indica momentum).</dd>`;
    html += `</dl></details>`;
    if (data.sparse) {{
      html += `<div style="color:#ffb300;margin-bottom:6px;">⚠ muestra pequeña (n&lt;${{ {min_companies} }})</div>`;
    }}
    html += `<div class="companies">`;
    data.companies.forEach(c => {{
      const cls = eligibleClass(c.eligibility);
      const tag = eligibleTag(c.eligibility);
      html += `<div class="company"><span class="${{cls}}">${{tag}}</span> `;
      html += `<b>${{c.name}}</b>`;
      html += `<div class="pain">${{c.pain_summary}}</div>`;
      html += `<div class="meta">${{c.state_label}} · ${{c.roles_in_f}}/${{c.total_roles}} en esta celda · dom ${{(c.dominance*100).toFixed(0)}}%</div>`;
      html += `</div>`;
    }});
    html += `</div>`;
    tooltip.innerHTML = html;
    tooltip.classList.add("visible");
    // Position after content is rendered (so offsetWidth/Height are accurate)
    requestAnimationFrame(() => positionTooltip(cell));
  }});
  cell.addEventListener("mouseleave", scheduleHide);
}});

tooltip.addEventListener("mouseenter", cancelHide);
tooltip.addEventListener("mouseleave", scheduleHide);
</script>
</body>
</html>
"""


# ─── Entrypoint ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-companies", type=int, default=3,
                    help="Cells with fewer companies are marked sparse")
    ap.add_argument("--output", type=str, default=None)
    args = ap.parse_args()

    db = SessionLocal()
    agg = aggregate(db, min_companies=args.min_companies)
    db.close()

    out_path = args.output or os.path.join(
        "output", f"friction_heatmap_{datetime.now().strftime('%Y%m%d')}.html"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    html_out = render_html(agg, min_companies=args.min_companies)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    dense = sum(1 for c in agg["cells"].values() if not c["sparse"])
    sparse = sum(1 for c in agg["cells"].values() if c["sparse"])
    print(f"Heatmap written: {out_path}")
    print(f"  sectors: {len(agg['sectors'])}  functions: {len(agg['functions'])}")
    print(f"  dense cells: {dense}   sparse cells: {sparse}")
    print(f"  classified companies: {agg['classified_companies']} / {agg['total_companies']}")

    # Echo top 5 to console
    cells = agg["cells"]
    top5 = sorted(
        [((s, f), c) for (s, f), c in cells.items() if not c["sparse"]],
        key=lambda x: -x[1]["pain_score"]
    )[:5]
    print(f"\nTop 5 celdas densas:")
    for (s, f), c in top5:
        print(f"  {c['pain_score']:.2f}  {s[:25]:25s} × {f:22s}  n={c['n']}")


if __name__ == "__main__":
    main()
