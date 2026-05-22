"""Evaluate Smart-Match eligibility on the synthetic dataset.

The Smart-Match prefilter (smart_match_engine._prefilter_candidates) accepts
companies whose eligibility_gate ∈ {full, conditional}. Eligibility is
computed by positioning_engine.check_eligibility based on diagnostic_state,
classified_roles, and jds_extracted.

So Smart-Match hit (engine view) ≡ check_eligibility(...).gate_passed ∈
{"full", "conditional"}.

This script:
  1. For each synthetic company, runs the real evaluation_engine to get
     diagnostic_state + KPIs (same as evaluate_synthetic.py).
  2. Counts classified_roles and jds_extracted from roles.json.
  3. Calls check_eligibility() — the real positioning gate.
  4. Maps gate ∈ {full, conditional} → predicted_smart_match_hit=True.
  5. Compares against expected_smart_match_hit ground truth.

Ground truth values: True | False | "borderline".
"borderline" companies are reported separately (not counted in accuracy).

Usage:
  python backend/scripts/synthetic/evaluate_smart_match.py --version synth-2026-04-27-v3
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

from app.services.company_evaluation import CompanyEvaluationEngine  # noqa: E402
from app.services.positioning_engine import check_eligibility  # noqa: E402

DEFAULT_OUT_ROOT = BACKEND_ROOT / "data" / "synthetic"

ENGINE_HIT_GATES = {"full", "conditional"}


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
    if company.get("entity_type") == "job_market_intermediary":
        return "low"
    return "moderate"


def evaluate(out_dir: Path) -> dict:
    companies = json.loads((out_dir / "companies.json").read_text(encoding="utf-8"))
    roles = json.loads((out_dir / "roles.json").read_text(encoding="utf-8"))
    signals = json.loads((out_dir / "signals.json").read_text(encoding="utf-8"))

    roles_by_co: dict[str, list[dict]] = defaultdict(list)
    for r in roles:
        roles_by_co[r["company_id"]].append(r)
    signals_by_co: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        signals_by_co[s["company_id"]].append(s)

    eval_engine = CompanyEvaluationEngine()
    per_company: list[dict] = []

    for c in companies:
        cid = c["id"]
        sm = c.get("synthetic_meta") or {}
        comp_signals = [_mock_signal(s) for s in signals_by_co.get(cid, [])]
        comp_roles_raw = roles_by_co.get(cid, [])
        comp_roles = [_mock_role(r) for r in comp_roles_raw]

        try:
            ev = eval_engine.evaluate(
                company_id=UUID(cid),
                signals=comp_signals,
                job_roles=comp_roles,
                company_type_confidence=_company_type_confidence(c),
            )
        except Exception as exc:
            ev = {"diagnostic_state": f"<error:{exc}>", "kpis": {}}

        ds = ev.get("diagnostic_state") or ""
        kpis = ev.get("kpis") or {}

        classified_roles = sum(
            1 for r in comp_roles_raw
            if r.get("functional_area") and r["functional_area"] not in ("junk", "unknown")
        )
        jds_extracted = sum(
            1 for r in comp_roles_raw
            if (r.get("role_description") or "").strip()
        )

        elig = check_eligibility(
            diagnostic_state=ds,
            pain_clarity=kpis.get("pain_clarity", "low"),
            function_concentration=kpis.get("function_concentration", "low"),
            positioning_readiness=kpis.get("positioning_readiness", "low"),
            classified_roles=classified_roles,
            jds_extracted=jds_extracted,
        )

        predicted_hit = elig.gate_passed in ENGINE_HIT_GATES
        expected_hit = sm.get("expected_smart_match_hit")

        per_company.append({
            "domain": c["domain"],
            "archetype": sm.get("archetype_id"),
            "is_counterfactual": bool(sm.get("is_counterfactual")),
            "diagnostic_state": ds,
            "classified_roles": classified_roles,
            "jds_extracted": jds_extracted,
            "engine_gate": elig.gate_passed,
            "engine_eligible": elig.eligible,
            "predicted_hit": predicted_hit,
            "expected_hit": expected_hit,
            "expected_gate": sm.get("expected_eligibility_gate"),
            "expected_diagnostic_state": sm.get("expected_diagnostic_state"),
        })

    # ── Aggregate ──
    decisive = [r for r in per_company if r["expected_hit"] in (True, False)]
    borderline = [r for r in per_company if r["expected_hit"] == "borderline"]

    n = len(decisive)
    matches = sum(1 for r in decisive if r["predicted_hit"] == r["expected_hit"])
    overall = {
        "n_total": len(per_company),
        "n_decisive": n,
        "n_borderline": len(borderline),
        "smart_match_accuracy": round(matches / n, 4) if n else 0.0,
    }

    # 2x2 confusion (predicted_hit vs expected_hit on decisive only).
    confusion = {
        "tp": sum(1 for r in decisive if r["predicted_hit"] and r["expected_hit"]),
        "tn": sum(1 for r in decisive if not r["predicted_hit"] and not r["expected_hit"]),
        "fp": sum(1 for r in decisive if r["predicted_hit"] and not r["expected_hit"]),
        "fn": sum(1 for r in decisive if not r["predicted_hit"] and r["expected_hit"]),
    }
    tp, tn, fp, fn = confusion["tp"], confusion["tn"], confusion["fp"], confusion["fn"]
    confusion["precision"] = round(tp / (tp + fp), 3) if (tp + fp) else 0.0
    confusion["recall"] = round(tp / (tp + fn), 3) if (tp + fn) else 0.0

    # Per-archetype hit rate.
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for r in per_company:
        by_arch[r["archetype"]].append(r)
    archetype_report: dict[str, dict] = {}
    for arch, rows in by_arch.items():
        n_a = len(rows)
        n_dec = sum(1 for r in rows if r["expected_hit"] in (True, False))
        n_match = sum(1 for r in rows
                      if r["expected_hit"] in (True, False)
                      and r["predicted_hit"] == r["expected_hit"])
        archetype_report[arch] = {
            "n": n_a,
            "n_decisive": n_dec,
            "accuracy": round(n_match / n_dec, 3) if n_dec else None,
            "predicted_hit_rate": round(sum(1 for r in rows if r["predicted_hit"]) / n_a, 3),
            "expected_hit_rate": (
                round(
                    sum(1 for r in rows if r["expected_hit"] is True) / n_a, 3
                )
            ),
        }

    # Borderline outcomes
    borderline_outcomes = Counter(
        ("hit" if r["predicted_hit"] else "miss") for r in borderline
    )

    return {
        "overall": overall,
        "confusion": confusion,
        "by_archetype": archetype_report,
        "borderline_outcomes": dict(borderline_outcomes),
        "per_company": per_company,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()

    out_dir = args.out_root / args.version
    if not out_dir.exists():
        print(f"[sm-eval] dataset not found: {out_dir}")
        sys.exit(1)

    report = evaluate(out_dir)
    (out_dir / "smart_match_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"[sm-eval] {out_dir}")
    o = report["overall"]
    print(f"\nOverall:")
    print(f"  total companies:      {o['n_total']}")
    print(f"  decisive (T/F):       {o['n_decisive']}")
    print(f"  borderline:           {o['n_borderline']}")
    print(f"  smart_match accuracy: {o['smart_match_accuracy']*100:.1f}%")

    c = report["confusion"]
    print(f"\nConfusion (decisive only):")
    print(f"  TP={c['tp']:4d}  FP={c['fp']:4d}")
    print(f"  FN={c['fn']:4d}  TN={c['tn']:4d}")
    print(f"  precision={c['precision']*100:.1f}%  recall={c['recall']*100:.1f}%")

    print("\nPer-archetype:")
    print(f"  {'archetype':<28} {'n':>4} {'dec':>4} {'acc%':>6} {'pred_hit':>8} {'exp_hit':>8}")
    for arch, rep in sorted(report["by_archetype"].items(), key=lambda x: -x[1]["n"]):
        acc = "n/a" if rep["accuracy"] is None else f"{rep['accuracy']*100:5.1f}%"
        print(f"  {arch:<28} {rep['n']:>4} {rep['n_decisive']:>4} {acc:>6} "
              f"{rep['predicted_hit_rate']*100:>7.1f}% {rep['expected_hit_rate']*100:>7.1f}%")

    if report["borderline_outcomes"]:
        print(f"\nBorderline (n={o['n_borderline']}): {report['borderline_outcomes']}")

    print(f"\nFull report -> {out_dir / 'smart_match_eval.json'}")


if __name__ == "__main__":
    main()
