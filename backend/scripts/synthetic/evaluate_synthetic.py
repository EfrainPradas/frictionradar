"""Run the real FrictionRadar engines (scoring + company evaluation) against
the synthetic dataset and compare each company's actual output to its
ground-truth expected_*.

Why no SQLite?
  CompanyEvaluationEngine.evaluate() and scoring_engine._evaluate_rules()
  both accept signals / job_roles as plain lists of objects with the right
  attributes — no DB required. SimpleNamespace mocks are faster, more
  portable, and avoid the JSONB / pgvector / UUID friction of mounting the
  real schema in SQLite.

Usage:
  python backend/scripts/synthetic/evaluate_synthetic.py --version synth-2026-04-27-v1

Outputs:
  - prints a per-archetype accuracy report
  - writes evaluation_report.json next to the dataset

Compared metrics:
  - dominant_friction_type     (engine vs expected_dominant_friction_type)
  - friction_score in band     (total_score in expected_friction_score_band)
  - diagnostic_state           (engine vs expected_diagnostic_state)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scoring_engine import _evaluate_rules  # noqa: E402
from app.services.company_evaluation import CompanyEvaluationEngine  # noqa: E402
from app.core.friction_categories import FRICTION_CATEGORIES  # noqa: E402

DEFAULT_OUT_ROOT = BACKEND_ROOT / "data" / "synthetic"


def _mock_signal(s: dict) -> SimpleNamespace:
    return SimpleNamespace(
        signal_type=s.get("signal_type") or "",
        signal_text=s.get("signal_text") or "",
        numeric_value=s.get("numeric_value"),
        source_type=s.get("source_type"),
        functional_area=s.get("functional_area"),
        company_id=s.get("company_id"),
    )


def _mock_role(r: dict) -> SimpleNamespace:
    return SimpleNamespace(
        role_title=r.get("role_title") or "",
        role_description=r.get("role_description"),
        functional_area=r.get("functional_area"),
        role_location=r.get("role_location"),
        company_id=r.get("company_id"),
    )


def _company_type_confidence(company: dict) -> str:
    """The real pipeline derives this from a separate engine. For synthetic
    data we map it directly from entity_type."""
    if company.get("entity_type") == "job_market_intermediary":
        return "low"
    return "moderate"


def evaluate(out_dir: Path) -> dict:
    companies = json.loads((out_dir / "companies.json").read_text(encoding="utf-8"))
    roles = json.loads((out_dir / "roles.json").read_text(encoding="utf-8"))
    signals = json.loads((out_dir / "signals.json").read_text(encoding="utf-8"))

    # Index by company_id for O(1) lookups.
    roles_by_company: dict[str, list[dict]] = defaultdict(list)
    for r in roles:
        roles_by_company[r["company_id"]].append(r)
    signals_by_company: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        signals_by_company[s["company_id"]].append(s)

    eval_engine = CompanyEvaluationEngine()
    per_company: list[dict] = []

    for c in companies:
        cid = c["id"]
        sm = c.get("synthetic_meta") or {}
        comp_signals = [_mock_signal(s) for s in signals_by_company.get(cid, [])]
        comp_roles = [_mock_role(r) for r in roles_by_company.get(cid, [])]

        # ── Scoring engine ────────────────────────────────────────────
        breakdown = _evaluate_rules(comp_signals)
        total_score = round(sum(cat["score"] for cat in breakdown.values()), 2)
        dominant = max(
            breakdown,
            key=lambda k: breakdown[k]["score"],
            default=FRICTION_CATEGORIES[0],
        )
        # If everything is zero, dominant is meaningless — emit None.
        if total_score == 0:
            dominant_actual = None
        else:
            dominant_actual = dominant

        # ── Evaluation engine ─────────────────────────────────────────
        try:
            eval_result = eval_engine.evaluate(
                company_id=UUID(cid),
                signals=comp_signals,
                job_roles=comp_roles,
                company_type_confidence=_company_type_confidence(c),
            )
            diagnostic_actual = eval_result.get("diagnostic_state")
        except Exception as exc:  # pragma: no cover — defensive
            diagnostic_actual = f"<error:{exc}>"

        # ── Compare to ground truth ───────────────────────────────────
        expected_band = sm.get("expected_friction_score_band") or [0, 100]
        in_band = expected_band[0] <= total_score <= expected_band[1]
        expected_dom = sm.get("expected_dominant_friction_type")
        expected_ds = sm.get("expected_diagnostic_state")

        dom_match = (dominant_actual == expected_dom)
        ds_match = (diagnostic_actual == expected_ds)

        per_company.append({
            "domain": c["domain"],
            "archetype": sm.get("archetype_id"),
            "is_counterfactual": bool(sm.get("is_counterfactual")),
            "expected_dominant": expected_dom,
            "actual_dominant": dominant_actual,
            "dom_match": dom_match,
            "expected_score_band": expected_band,
            "actual_score": total_score,
            "score_in_band": in_band,
            "expected_diagnostic": expected_ds,
            "actual_diagnostic": diagnostic_actual,
            "ds_match": ds_match,
            "n_signals": len(comp_signals),
            "n_roles": len(comp_roles),
        })

    # ── Aggregate per archetype ───────────────────────────────────────
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for row in per_company:
        by_arch[row["archetype"]].append(row)

    archetype_report: dict[str, dict] = {}
    for arch, rows in by_arch.items():
        n = len(rows)
        archetype_report[arch] = {
            "n": n,
            "dom_match_rate": round(sum(r["dom_match"] for r in rows) / n, 3),
            "score_in_band_rate": round(sum(r["score_in_band"] for r in rows) / n, 3),
            "ds_match_rate": round(sum(r["ds_match"] for r in rows) / n, 3),
            "avg_score": round(sum(r["actual_score"] for r in rows) / n, 2),
            "avg_signals": round(sum(r["n_signals"] for r in rows) / n, 1),
            "avg_roles": round(sum(r["n_roles"] for r in rows) / n, 1),
        }

    # ── Confusion: what diagnostic_state did we get when we expected X?
    ds_confusion: dict[str, Counter] = defaultdict(Counter)
    dom_confusion: dict[str, Counter] = defaultdict(Counter)
    for row in per_company:
        ds_confusion[str(row["expected_diagnostic"])][str(row["actual_diagnostic"])] += 1
        dom_confusion[str(row["expected_dominant"])][str(row["actual_dominant"])] += 1

    overall = {
        "n": len(per_company),
        "dom_match_rate": round(sum(r["dom_match"] for r in per_company) / len(per_company), 3),
        "score_in_band_rate": round(sum(r["score_in_band"] for r in per_company) / len(per_company), 3),
        "ds_match_rate": round(sum(r["ds_match"] for r in per_company) / len(per_company), 3),
    }

    return {
        "overall": overall,
        "by_archetype": archetype_report,
        "diagnostic_state_confusion": {k: dict(v) for k, v in ds_confusion.items()},
        "dominant_friction_confusion": {k: dict(v) for k, v in dom_confusion.items()},
        "per_company": per_company,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--top-mismatches", type=int, default=10)
    args = ap.parse_args()

    out_dir = args.out_root / args.version
    if not out_dir.exists():
        print(f"[evaluate] dataset not found: {out_dir}")
        sys.exit(1)

    report = evaluate(out_dir)

    # Persist full report
    (out_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Console summary
    print(f"[evaluate] {out_dir}")
    print(f"\nOverall (n={report['overall']['n']}):")
    print(f"  dominant_friction match:  {report['overall']['dom_match_rate']*100:5.1f}%")
    print(f"  score in expected band:   {report['overall']['score_in_band_rate']*100:5.1f}%")
    print(f"  diagnostic_state match:   {report['overall']['ds_match_rate']*100:5.1f}%")

    print("\nPer archetype:")
    print(f"  {'archetype':<28} {'n':>4} {'dom%':>6} {'band%':>6} {'ds%':>6} {'avg_sc':>7} {'sigs':>5} {'roles':>5}")
    for arch, rep in sorted(report["by_archetype"].items(), key=lambda x: -x[1]["n"]):
        print(f"  {arch:<28} {rep['n']:>4} {rep['dom_match_rate']*100:>5.1f}% "
              f"{rep['score_in_band_rate']*100:>5.1f}% {rep['ds_match_rate']*100:>5.1f}% "
              f"{rep['avg_score']:>7.2f} {rep['avg_signals']:>5.1f} {rep['avg_roles']:>5.1f}")

    print("\nDiagnostic state confusion (expected → actual):")
    for expected, actuals in report["diagnostic_state_confusion"].items():
        for actual, n in actuals.most_common() if isinstance(actuals, Counter) else sorted(actuals.items(), key=lambda x: -x[1]):
            mark = " " if expected == actual else "*"
            print(f"  {mark} {expected:<32} -> {actual:<32} {n}")

    print(f"\nFull report → {out_dir / 'evaluation_report.json'}")


if __name__ == "__main__":
    main()
