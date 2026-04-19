"""Generate a self-contained HTML heatmap report from positioning_audit.json.

Reads the per-company positioning audit output and renders three heatmaps:
  1. dominant_function x score_dominant_friction
  2. archetype         x score_dominant_friction
  3. dominant_function x gate

Each cell shows count (top) and mean score (bottom). Hover reveals the
company list. Color scale is green -> yellow -> red on count, normalized
per-heatmap. No external libraries; stdlib only.

Usage:
  python backend/scripts/generate_positioning_heatmap.py
  python backend/scripts/generate_positioning_heatmap.py \
      --input backend/runs/audit_eligible_v1/positioning_audit.json \
      --output backend/runs/audit_eligible_v1/positioning_heatmap.html
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from html import escape
from pathlib import Path
from statistics import mean

DEFAULT_INPUT = Path("backend/runs/audit_eligible_v1/positioning_audit.json")
DEFAULT_OUTPUT = Path("backend/runs/audit_eligible_v1/positioning_heatmap.html")


def aggregate(companies, row_key, col_key):
    """Build cell aggregates keyed by (row, col)."""
    cells = defaultdict(lambda: {"count": 0, "scores": [], "companies": []})
    for c in companies:
        row = c.get(row_key) or "(unknown)"
        col = c.get(col_key) or "(unknown)"
        cell = cells[(row, col)]
        cell["count"] += 1
        cell["companies"].append(c.get("name", "?"))
        try:
            cell["scores"].append(float(c.get("score", 0)))
        except (TypeError, ValueError):
            pass
    return cells


def ordered_axes(cells, fixed_cols=None):
    """Return (rows, cols) with rows sorted by total count desc."""
    row_totals = defaultdict(int)
    col_totals = defaultdict(int)
    for (r, c), v in cells.items():
        row_totals[r] += v["count"]
        col_totals[c] += v["count"]
    rows = sorted(row_totals.keys(), key=lambda r: (-row_totals[r], r))
    if fixed_cols is not None:
        cols = [c for c in fixed_cols if c in col_totals] + [
            c for c in sorted(col_totals.keys()) if c not in fixed_cols
        ]
    else:
        cols = sorted(col_totals.keys(), key=lambda c: (-col_totals[c], c))
    return rows, cols


def count_color(count, max_count):
    """Green -> yellow -> red gradient on count. Returns CSS color."""
    if count == 0 or max_count == 0:
        return "#f3f4f6"  # gris claro
    t = count / max_count  # 0..1
    # hue: 120 (verde) -> 0 (rojo)
    hue = 120 * (1 - t)
    return f"hsl({hue:.0f}, 70%, 60%)"


def render_heatmap(title, cells, rows, cols):
    if not cells:
        return f'<section><h2>{escape(title)}</h2><p class="empty">Sin datos.</p></section>'

    max_count = max(v["count"] for v in cells.values())
    total = sum(v["count"] for v in cells.values())

    out = [f'<section><h2>{escape(title)} <span class="total">(n={total})</span></h2>']
    out.append('<div class="scroll"><table class="heatmap">')
    out.append("<thead><tr><th></th>")
    for c in cols:
        out.append(f'<th><span class="rot">{escape(c)}</span></th>')
    out.append("</tr></thead><tbody>")

    for r in rows:
        out.append(f'<tr><th class="rowhead">{escape(r)}</th>')
        for c in cols:
            cell = cells.get((r, c))
            if not cell:
                out.append('<td class="empty" style="background:#f3f4f6"></td>')
                continue
            count = cell["count"]
            avg = mean(cell["scores"]) if cell["scores"] else 0.0
            bg = count_color(count, max_count)
            companies = ", ".join(sorted(cell["companies"]))
            tooltip = f"{r} \u00d7 {c}\nEmpresas: {count}\nScore promedio: {avg:.2f}\n{companies}"
            text_color = "#111" if count / max_count < 0.65 else "#fff"
            out.append(
                f'<td style="background:{bg};color:{text_color}" title="{escape(tooltip)}">'
                f'<div class="count">{count}</div>'
                f'<div class="score">{avg:.1f}</div>'
                f"</td>"
            )
        out.append("</tr>")
    out.append("</tbody></table></div></section>")
    return "".join(out)


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #fafafa; color: #111; margin: 0; padding: 24px;
}
h1 { margin: 0 0 4px 0; font-size: 22px; }
h2 { margin: 28px 0 12px 0; font-size: 16px; font-weight: 600; }
h2 .total { color: #6b7280; font-weight: 400; font-size: 13px; margin-left: 6px; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 8px; }
.legend { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #374151; margin: 12px 0 0 0; }
.legend .bar {
  display: inline-block; width: 140px; height: 10px; border-radius: 4px;
  background: linear-gradient(to right, hsl(120,70%,60%), hsl(60,70%,60%), hsl(0,70%,60%));
}
.scroll { overflow-x: auto; padding-bottom: 8px; }
table.heatmap { border-collapse: separate; border-spacing: 2px; }
table.heatmap th, table.heatmap td {
  min-width: 70px; height: 60px; text-align: center; vertical-align: middle;
  font-size: 12px; padding: 4px; border-radius: 4px;
}
table.heatmap th { background: transparent; color: #374151; font-weight: 500; }
table.heatmap th.rowhead { text-align: right; padding-right: 10px; white-space: nowrap; }
table.heatmap thead th { height: 110px; vertical-align: bottom; }
table.heatmap .rot {
  display: inline-block; transform: rotate(-35deg); transform-origin: left bottom;
  white-space: nowrap; font-size: 11px;
}
table.heatmap td { cursor: help; transition: transform .08s ease; }
table.heatmap td:hover { transform: scale(1.05); outline: 2px solid #111; }
table.heatmap td.empty { cursor: default; }
.count { font-size: 16px; font-weight: 600; line-height: 1.1; }
.score { font-size: 11px; opacity: .85; margin-top: 2px; }
.empty.message { color: #9ca3af; font-style: italic; }
footer { margin-top: 32px; color: #9ca3af; font-size: 11px; }
"""


def render_html(data):
    companies = data.get("per_company", [])
    generated = data.get("generated_at", "")
    total = data.get("eligible_count", len(companies))

    h1 = aggregate(companies, "dominant_function", "score_dominant_friction")
    h2 = aggregate(companies, "archetype", "score_dominant_friction")
    h3 = aggregate(companies, "dominant_function", "gate")

    r1, c1 = ordered_axes(h1)
    r2, c2 = ordered_axes(h2)
    r3, c3 = ordered_axes(h3, fixed_cols=["full", "conditional"])

    sections = [
        render_heatmap("Funci\u00f3n \u00d7 Fricci\u00f3n dominante", h1, r1, c1),
        render_heatmap("Arquetipo \u00d7 Fricci\u00f3n dominante", h2, r2, c2),
        render_heatmap("Funci\u00f3n \u00d7 Gate", h3, r3, c3),
    ]

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Positioning Heatmap</title>
<style>{CSS}</style>
</head>
<body>
<h1>Positioning Heatmap</h1>
<div class="meta">Generado: {escape(generated)} &middot; Empresas elegibles: {total}</div>
<div class="legend">
  <span>Menos empresas</span>
  <span class="bar"></span>
  <span>M\u00e1s empresas</span>
  <span style="margin-left:16px;color:#6b7280">Color = conteo &middot; N\u00famero grande = conteo &middot; N\u00famero peque\u00f1o = score promedio &middot; Hover = empresas</span>
</div>
{''.join(sections)}
<footer>Fuente: positioning_audit.json &middot; Render stdlib-only &middot; Hover sobre cada celda para ver empresas</footer>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    html = render_html(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
