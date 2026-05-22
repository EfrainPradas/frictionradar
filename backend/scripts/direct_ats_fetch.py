"""Direct ATS API fetcher for the literature cohort.

Bypasses the dynamic-scraping extractor by calling ATS JSON APIs
(Greenhouse / Workday / Lever) directly. Produces real job listings
for publishers, media, and EdTech companies that ship SPA careers
pages the generic Playwright extractor cannot parse.

Outputs:
  1. Writes clean rows into `company_job_roles` (for the heatmap).
  2. Generates `output/daughter_lit_jobs_<date>.html` — a ranked
     report sorted by relevance for an American Literature graduate.

Usage:
    python scripts/direct_ats_fetch.py                # write + report
    python scripts/direct_ats_fetch.py --dry-run      # no DB writes
    python scripts/direct_ats_fetch.py --append       # keep prior noisy rows

Add a new target by editing TARGETS below. Each adapter is self-contained.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole


# ── Target config ────────────────────────────────────────────────────
# Map domain -> adapter + params. Only domains present in `companies`
# table will be processed; missing ones are skipped silently.
TARGETS: dict[str, dict] = {
    "duolingo.com":    {"adapter": "greenhouse", "slug": "duolingo"},
    "khanacademy.org": {"adapter": "greenhouse", "slug": "khanacademy"},
    "newsela.com":     {"adapter": "greenhouse", "slug": "newsela"},
    "theatlantic.com": {"adapter": "workday", "host": "atlanticmedia.wd1.myworkdayjobs.com",
                         "tenant": "atlanticmedia", "site": "Careers"},
    "scholastic.com":  {"adapter": "workday", "host": "scholastic.wd5.myworkdayjobs.com",
                         "tenant": "scholastic", "site": "External"},
    "commonlit.org":   {"adapter": "lever", "slug": "commonlit"},
}


# ── Classifier + relevance ───────────────────────────────────────────
FUNCTIONAL_AREA_PATTERNS = [
    ("editorial",       r"(editor|editorial|copy\s*edit|proofread|manuscript|publishing)"),
    ("content",         r"(content|writer|writing|author)"),
    ("communications",  r"(communicat|press|public relations|\bpr\b)"),
    ("marketing",       r"(marketing|brand|publicist|publicity|growth)"),
    ("product",         r"(product manager|product designer|product owner)"),
    ("design",          r"(designer|graphic|art direct|ux\b|ui\b)"),
    ("engineering",     r"(engineer|developer|software|sre|devops|sdet)"),
    ("data_analytics",  r"(data scien|data engineer|analyst|analytics|\bbi\b)"),
    ("sales",           r"(sales|account executive|business development|\bbdr\b|\bsdr\b)"),
    ("operations",      r"(operations|coordinator|program manager|project manager|\bops\b)"),
    ("hr",              r"(human resources|recruit|talent|people ops)"),
    ("finance",         r"(finance|accountant|controller|treasur)"),
    ("legal",           r"(legal|attorney|counsel|paralegal)"),
    ("customer_success",r"(customer success|customer experience)"),
    ("education",       r"(curriculum|instructor|teacher|learning design|instructional)"),
]
_COMPILED_AREAS = [(n, re.compile(p, re.I)) for n, p in FUNCTIONAL_AREA_PATTERNS]

LIT_STRONG = [
    "editor", "editorial", "copyedit", "copy editor", "proofread",
    "publicist", "publicity", "writer", "writing", "copywriter",
    "content strategist", "content manager", "author", "books", "book",
    "fiction", "literary", "poet", "poetry", "manuscript",
    "storytelling", "narrative", "journalist", "reporter", "newsroom",
]
LIT_OK = [
    "communications", "communication", "media", "magazine", "press",
    "curriculum", "learning", "instructional", "english",
    "grant", "programs", "coordinator", "assistant", "fellow", "intern",
    "marketing", "brand", "social media", "newsletter", "audience", "community",
]
LIT_KILL = [
    "engineer", "developer", "software", "devops", "machine learning",
    "data scien", "sales", "account executive", "security", "finance",
    "accountant", "sre", "sdet", "infrastructure",
]


def classify_area(title: str, description: str = "") -> str:
    text = f"{title}\n{description or ''}"
    for name, pat in _COMPILED_AREAS:
        if pat.search(text):
            return name
    return "unknown"


def relevance_score(title: str, description: str = "") -> int:
    text = (title + " " + (description or "")).lower()
    score = 0
    for kw in LIT_STRONG:
        if kw in text:
            score += 20
    for kw in LIT_OK:
        if kw in text:
            score += 5
    for kw in LIT_KILL:
        if kw in text:
            score -= 25
    if re.search(r"\b(entry|junior|jr\.?|associate|assistant|coordinator|fellow|intern)\b", text):
        score += 15
    if re.search(r"\b(senior|sr\.?|staff|principal|director|head|\bvp\b|vice president|chief|lead)\b",
                 title, re.I):
        score -= 10
    return max(0, score)


# ── Adapters ─────────────────────────────────────────────────────────
def _html_to_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_greenhouse(cfg: dict) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{cfg['slug']}/jobs?content=true"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    out = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title"),
            "location": (j.get("location") or {}).get("name"),
            "department": (j.get("departments") or [{}])[0].get("name"),
            "description": _html_to_text(j.get("content") or ""),
            "url": j.get("absolute_url"),
        })
    return out


def fetch_workday(cfg: dict) -> list[dict]:
    url = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}/jobs"
    out, offset = [], 0
    while True:
        r = requests.post(
            url,
            json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""},
            timeout=20,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        postings = data.get("jobPostings") or []
        if not postings:
            break
        for j in postings:
            ext = j.get("externalPath") or ""
            out.append({
                "title": j.get("title"),
                "location": j.get("locationsText"),
                "department": None,
                "description": j.get("postingSiteDescription") or "",
                "url": f"https://{cfg['host']}{ext}" if ext else None,
            })
        offset += len(postings)
        if offset >= (data.get("total") or 0):
            break
        time.sleep(0.3)
    return out


def fetch_lever(cfg: dict) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{cfg['slug']}?mode=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    out = []
    for j in r.json():
        cats = j.get("categories") or {}
        out.append({
            "title": j.get("text"),
            "location": cats.get("location"),
            "department": cats.get("team"),
            "description": j.get("descriptionPlain") or _html_to_text(j.get("description", "")),
            "url": j.get("hostedUrl"),
        })
    return out


ADAPTERS = {
    "greenhouse": fetch_greenhouse,
    "workday":    fetch_workday,
    "lever":      fetch_lever,
}


# ── HTML report ──────────────────────────────────────────────────────
def write_html(jobs: list[dict], path: Path) -> None:
    rows = []
    for j in jobs:
        rel = j["relevance"]
        cls = "high" if rel >= 30 else "mid" if rel >= 15 else "low"
        title = html.escape(j.get("title") or "")
        loc = html.escape(j.get("location") or "—")
        dept = html.escape(j.get("department") or "—")
        area = html.escape(j.get("functional_area") or "—")
        company = html.escape(j.get("company") or "—")
        url = j.get("url") or "#"
        rows.append(
            f'<tr class="{cls}">'
            f'<td class="rel">{rel}</td>'
            f'<td>{company}</td>'
            f'<td><a href="{url}" target="_blank">{title}</a></td>'
            f'<td>{area}</td>'
            f'<td>{loc}</td>'
            f'<td>{dept}</td>'
            f'</tr>'
        )
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Jobs - Cohorte Literatura Americana</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; padding: 24px; color: #222; }}
  h1 {{ margin-bottom: 4px; }}
  .summary {{ color: #666; margin-bottom: 20px; font-size: 14px; }}
  .legend span {{ display: inline-block; padding: 2px 8px; margin-right: 8px; border-radius: 3px; font-size: 12px; }}
  .legend .high {{ background: #c8ecc4; }}
  .legend .mid {{ background: #ffefc2; }}
  .legend .low {{ background: #eee; color: #777; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; vertical-align: top; }}
  th {{ background: #f4f4f4; text-align: left; position: sticky; top: 0; }}
  td.rel {{ text-align: center; font-weight: 600; }}
  tr.high td {{ background: #e3f9e0; }}
  tr.mid  td {{ background: #fff9e0; }}
  tr.low  td {{ color: #888; }}
  a {{ color: #1a6dd9; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style></head><body>
<h1>Jobs · Cohorte Literatura Americana</h1>
<p class="summary">
  Generado {datetime.now().isoformat(timespec='seconds')} · {len(jobs)} jobs
  · ranked por relevance para un Lit grad (entry-level, editorial, content, communications).
</p>
<p class="legend">
  <span class="high">alta relevancia (≥30)</span>
  <span class="mid">media (15–29)</span>
  <span class="low">baja (&lt;15)</span>
</p>
<table>
<thead><tr><th>Rel</th><th>Empresa</th><th>Puesto</th><th>Área</th><th>Ubicación</th><th>Depto</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table></body></html>"""
    path.write_text(doc, encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="Fetch jobs directly from ATS APIs for the literature cohort.")
    p.add_argument("--dry-run", action="store_true", help="Fetch and report only (no DB writes).")
    p.add_argument("--append", action="store_true",
                   help="Keep existing company_job_roles; by default, rows for each target company are replaced.")
    p.add_argument("--output", default=None, help="HTML report path (default: output/daughter_lit_jobs_<date>.html).")
    args = p.parse_args()

    out_path = Path(args.output) if args.output else (
        Path("output") / f"daughter_lit_jobs_{datetime.now():%Y%m%d_%H%M}.html"
    )

    db = SessionLocal()
    all_jobs: list[dict] = []
    inserted_total = 0
    deleted_total = 0

    try:
        for domain, cfg in TARGETS.items():
            company = db.query(Company).filter(Company.domain == domain).one_or_none()
            if not company:
                print(f"[skip] no company row for {domain}")
                continue
            fetcher = ADAPTERS[cfg["adapter"]]
            try:
                jobs = fetcher(cfg)
            except Exception as e:
                print(f"[err]  {domain}: {type(e).__name__}: {e}")
                continue

            print(f"[{cfg['adapter']:<10}] {domain:<25}  {len(jobs)} jobs")

            if not args.dry_run and not args.append:
                deleted = (
                    db.query(CompanyJobRole)
                    .filter(CompanyJobRole.company_id == company.id)
                    .delete(synchronize_session=False)
                )
                deleted_total += deleted

            for j in jobs:
                title = (j.get("title") or "").strip()
                if not title:
                    continue
                desc = j.get("description") or ""
                area = classify_area(title, desc)
                rel = relevance_score(title, desc)
                all_jobs.append({
                    **j,
                    "title": title,
                    "company": company.name,
                    "company_id": str(company.id),
                    "domain": domain,
                    "functional_area": area,
                    "relevance": rel,
                })
                if not args.dry_run:
                    db.add(CompanyJobRole(
                        company_id=company.id,
                        source_url=j.get("url"),
                        role_title=title[:500],
                        role_location=(j.get("location") or None) and str(j["location"])[:200],
                        role_department=(j.get("department") or None) and str(j["department"])[:200],
                        role_description=desc[:8000] if desc else None,
                        functional_area=area,
                        functional_area_confidence="ats_direct_pattern",
                    ))
                    inserted_total += 1

        if not args.dry_run:
            db.commit()

        all_jobs.sort(key=lambda x: (-x["relevance"], x["company"], x["title"]))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_html(all_jobs, out_path)

        print("\n" + "=" * 64)
        print(f"  Total jobs fetched : {len(all_jobs)}")
        if not args.dry_run:
            print(f"  DB rows deleted    : {deleted_total}")
            print(f"  DB rows inserted   : {inserted_total}")
        print(f"  Report             : {out_path}")
        print(f"  High relevance     : {sum(1 for j in all_jobs if j['relevance'] >= 30)}")
        print(f"  Mid  relevance     : {sum(1 for j in all_jobs if 15 <= j['relevance'] < 30)}")
        print("=" * 64)

    finally:
        db.close()


if __name__ == "__main__":
    main()
