"""Run FunctionInferenceEngine.infer_functional_area against the synthetic
roles dataset and compare engine output to the ground-truth functional_area
assigned by the generator.

Why this matters:
  The synthetic generator stamps functional_area directly from the archetype
  mix. The real pipeline derives functional_area from role_title (+ optional
  description) via the keyword engine. If the engine disagrees with the
  generator on >X% of roles, downstream KPIs (function_concentration,
  pain_clarity) will diverge from ground truth — which is exactly what we
  saw in the v1→v3 evaluation.

Mapping:
  Generator "data" → Engine "data_analytics" (renamed for comparison).
  Engine domains absent from generator (supply_chain) → never expected.
  Generator domains absent from engine (editorial/content/teaching/other)
    are tagged out_of_engine_scope and reported separately, not counted as
    misses, since the keyword engine has no rules for them by design.

Usage:
  python backend/scripts/synthetic/evaluate_function_inference.py --version synth-2026-04-27-v3

Outputs:
  - prints overall accuracy + per-area precision/recall + confusion matrix
  - writes function_inference_eval.json next to the dataset
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.function_inference_engine import FunctionInferenceEngine  # noqa: E402

DEFAULT_OUT_ROOT = BACKEND_ROOT / "data" / "synthetic"

# generator → engine vocabulary
GEN_TO_ENGINE = {
    "data": "data_analytics",
    "engineering": "engineering",
    "product": "product",
    "sales": "sales",
    "marketing": "marketing",
    "operations": "operations",
    "customer_success": "customer_success",
    "finance": "finance",
}
# Generator domains the engine has no rules for.
OUT_OF_ENGINE_SCOPE = {"editorial", "content", "teaching", "other"}


def evaluate(out_dir: Path) -> dict:
    roles = json.loads((out_dir / "roles.json").read_text(encoding="utf-8"))

    engine = FunctionInferenceEngine()
    per_role: list[dict] = []

    for r in roles:
        gen_fa = r.get("functional_area")
        title = r.get("role_title") or ""
        desc = r.get("role_description")

        result = engine.infer_functional_area(title, desc)
        engine_area = result.get("area")

        is_oos = gen_fa in OUT_OF_ENGINE_SCOPE
        expected = GEN_TO_ENGINE.get(gen_fa, gen_fa)
        match = (engine_area == expected) and not is_oos

        per_role.append({
            "title": title,
            "gen_fa": gen_fa,
            "expected_engine_area": expected,
            "actual_engine_area": engine_area,
            "match": match,
            "out_of_engine_scope": is_oos,
            "confidence": result.get("confidence"),
            "reason_code": result.get("reason_code"),
        })

    # ── Aggregate ──
    in_scope = [r for r in per_role if not r["out_of_engine_scope"]]
    oos = [r for r in per_role if r["out_of_engine_scope"]]

    overall = {
        "n_total": len(per_role),
        "n_in_scope": len(in_scope),
        "n_out_of_scope": len(oos),
        "accuracy": (
            round(sum(r["match"] for r in in_scope) / len(in_scope), 4)
            if in_scope else 0.0
        ),
    }

    # Per-class precision/recall on in-scope roles.
    classes = sorted({r["expected_engine_area"] for r in in_scope})
    per_class: dict[str, dict] = {}
    for cls in classes:
        tp = sum(1 for r in in_scope if r["expected_engine_area"] == cls and r["actual_engine_area"] == cls)
        fp = sum(1 for r in in_scope if r["expected_engine_area"] != cls and r["actual_engine_area"] == cls)
        fn = sum(1 for r in in_scope if r["expected_engine_area"] == cls and r["actual_engine_area"] != cls)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        per_class[cls] = {
            "n": tp + fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "tp": tp, "fp": fp, "fn": fn,
        }

    # Confusion matrix expected → actual (in-scope only).
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in in_scope:
        confusion[r["expected_engine_area"]][r["actual_engine_area"] or "<none>"] += 1

    # OOS distribution: where do editorial/content/teaching/other fall?
    oos_dist: dict[str, Counter] = defaultdict(Counter)
    for r in oos:
        oos_dist[r["gen_fa"]][r["actual_engine_area"] or "<none>"] += 1

    return {
        "overall": overall,
        "per_class": per_class,
        "confusion_in_scope": {k: dict(v) for k, v in confusion.items()},
        "out_of_scope_distribution": {k: dict(v) for k, v in oos_dist.items()},
        "n_per_role": len(per_role),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()

    out_dir = args.out_root / args.version
    if not out_dir.exists():
        print(f"[fn-eval] dataset not found: {out_dir}")
        sys.exit(1)

    report = evaluate(out_dir)
    (out_dir / "function_inference_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fn-eval] {out_dir}")
    o = report["overall"]
    print(f"\nOverall (in-scope only):")
    print(f"  total roles:      {o['n_total']}")
    print(f"  in_scope:         {o['n_in_scope']}")
    print(f"  out_of_scope:     {o['n_out_of_scope']}")
    print(f"  accuracy:         {o['accuracy']*100:.1f}%")

    print("\nPer-class precision/recall (in-scope):")
    print(f"  {'class':<22} {'n':>5} {'prec':>6} {'rec':>6} {'tp':>4} {'fp':>4} {'fn':>4}")
    for cls, m in sorted(report["per_class"].items(), key=lambda x: -x[1]["n"]):
        print(f"  {cls:<22} {m['n']:>5} {m['precision']*100:>5.1f}% {m['recall']*100:>5.1f}% "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4}")

    print("\nConfusion (expected → actual, top mismatches in-scope):")
    for expected, actuals in report["confusion_in_scope"].items():
        for actual, n in sorted(actuals.items(), key=lambda x: -x[1])[:5]:
            mark = "  " if expected == actual else "* "
            print(f"  {mark}{expected:<22} -> {actual:<22} {n}")

    print("\nOut-of-engine-scope distribution (generator domains the engine has no rules for):")
    for gen_fa, actuals in report["out_of_scope_distribution"].items():
        total = sum(actuals.values())
        print(f"  {gen_fa} (n={total}):")
        for actual, n in sorted(actuals.items(), key=lambda x: -x[1])[:5]:
            print(f"    -> {actual:<22} {n} ({n/total*100:.0f}%)")

    print(f"\nFull report -> {out_dir / 'function_inference_eval.json'}")


if __name__ == "__main__":
    main()
