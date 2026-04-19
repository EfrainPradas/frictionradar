#!/usr/bin/env python
"""
Friction Radar — Extraction Pipeline Benchmark

Runs extract_company() against a sample of companies and measures:
  - Strategy distribution (ats_api / http_static / playwright)
  - Time per strategy and overall
  - Success rate per strategy
  - Fallback rate and reason codes
  - Comparison against baseline

Usage:
    python cli/benchmark_extraction.py                          # 30 companies, no Playwright
    python cli/benchmark_extraction.py --limit 50               # 50 companies
    python cli/benchmark_extraction.py --with-playwright        # include Playwright fallback
    python cli/benchmark_extraction.py --output bench.json      # save results to file
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass


def parse_args():
    p = argparse.ArgumentParser(description="Extraction pipeline benchmark")
    p.add_argument("--input", type=Path, default=_ROOT / "tools" / "data" / "utah_companies.json")
    p.add_argument("--limit", type=int, default=30, help="Companies to benchmark (0=all)")
    p.add_argument("--with-playwright", action="store_true", help="Include Playwright fallback")
    p.add_argument("--output", type=Path, default=None, help="Save JSON report to file")
    p.add_argument("--delay", type=float, default=0.5, help="Delay between companies (seconds)")
    return p.parse_args()


# ── Baseline from original pipeline run ─────────────────────────────

BASELINE = {
    "total_companies": 154,
    "duration_seconds": 9920.5,
    "avg_per_company_s": 64.4,
    "playwright_ran": 3,
    "playwright_skipped": 96,
    "ready_for_review": 104,
    "needs_recollection": 45,
    "tier_2_after_qa": 38,
    "tier_3_after_qa": 110,
    "notes": "Original pipeline: sync collectors + Playwright threshold of sync<3. "
             "Most Playwright 'skips' were due to false positive signals from dynamic_careers, "
             "not because extraction was successful.",
}


def load_companies(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("companies_with_domain", data if isinstance(data, list) else [])
    companies = []
    for c in raw:
        name = c.get("name") or c.get("company_name", "")
        domain = c.get("domain", "")
        if not domain or domain == "eb.archive.org":
            continue
        companies.append({
            "company_name": name,
            "domain": domain,
            "industry": c.get("industry"),
        })
    return companies


def run_benchmark(companies: list[dict], with_playwright: bool, delay: float) -> list[dict]:
    from app.extraction.dispatcher import extract_company

    results = []
    total = len(companies)

    for i, entry in enumerate(companies, 1):
        domain = entry["domain"]
        name = entry["company_name"]

        print(f"  [{i}/{total}] {domain:<35s}", end="", flush=True)

        t0 = time.monotonic()
        result = extract_company(
            domain=domain,
            company_name=name,
            skip_playwright=not with_playwright,
        )
        elapsed = time.monotonic() - t0

        strategy = result.strategy_used.value
        success = result.success
        reason = result.reason_code.value
        fallback = result.fallback_from.value if result.fallback_from else None

        print(
            f"  {strategy:<12s} "
            f"{'OK' if success else 'FAIL':<5s} "
            f"jobs={result.jobs_count:<4d} "
            f"conf={result.confidence:<5.2f} "
            f"{elapsed:.1f}s"
        )

        results.append({
            "domain": domain,
            "company_name": name,
            "strategy": strategy,
            "success": success,
            "jobs_count": result.jobs_count,
            "positions_count": result.open_positions_count,
            "confidence": result.confidence,
            "evidence_quality": result.evidence_quality,
            "reason_code": reason,
            "fallback_from": fallback,
            "duration_s": round(elapsed, 2),
            "error": result.error,
            "used_cache": result.used_cache,
        })

        if i < total and delay > 0:
            time.sleep(delay)

    return results


def compute_metrics(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {"error": "No results"}

    # ── Strategy distribution ───────────────────────────────────
    strategy_counts = Counter(r["strategy"] for r in results)
    strategy_pct = {k: round(v / total * 100, 1) for k, v in strategy_counts.items()}

    # ── Time per strategy ───────────────────────────────────────
    strategy_times = defaultdict(list)
    for r in results:
        strategy_times[r["strategy"]].append(r["duration_s"])

    strategy_avg_time = {
        k: round(sum(v) / len(v), 2) for k, v in strategy_times.items()
    }

    # ── Global timing ───────────────────────────────────────────
    all_times = [r["duration_s"] for r in results]
    total_time = sum(all_times)
    avg_time = total_time / total

    # ── Success rates ───────────────────────────────────────────
    strategy_success = defaultdict(lambda: {"total": 0, "success": 0})
    for r in results:
        s = r["strategy"]
        strategy_success[s]["total"] += 1
        if r["success"]:
            strategy_success[s]["success"] += 1

    success_rates = {
        k: round(v["success"] / v["total"] * 100, 1) if v["total"] > 0 else 0
        for k, v in strategy_success.items()
    }
    global_success = sum(1 for r in results if r["success"])
    global_success_rate = round(global_success / total * 100, 1)

    # ── Fallback analysis ───────────────────────────────────────
    fallback_count = sum(1 for r in results if r["fallback_from"])
    fallback_rate = round(fallback_count / total * 100, 1)

    fallback_reasons = Counter(
        r["reason_code"] for r in results if r["fallback_from"]
    )

    # ── Reason code distribution ────────────────────────────────
    reason_counts = Counter(r["reason_code"] for r in results)

    # ── Cache hits ──────────────────────────────────────────────
    cache_hits = sum(1 for r in results if r["used_cache"])
    cache_rate = round(cache_hits / total * 100, 1)

    # ── Quality distribution ────────────────────────────────────
    quality_counts = Counter(r["evidence_quality"] for r in results)

    # ── Non-Playwright rate (key metric) ────────────────────────
    non_pw = sum(1 for r in results if r["strategy"] != "playwright")
    non_pw_rate = round(non_pw / total * 100, 1)

    # ── Non-Playwright success rate ─────────────────────────────
    non_pw_success = sum(
        1 for r in results
        if r["strategy"] != "playwright" and r["success"]
    )
    non_pw_success_rate = round(non_pw_success / total * 100, 1)

    return {
        "total_companies": total,
        "total_time_s": round(total_time, 1),
        "avg_time_per_company_s": round(avg_time, 2),
        "strategy_distribution": dict(strategy_counts),
        "strategy_pct": strategy_pct,
        "strategy_avg_time_s": strategy_avg_time,
        "global_success_rate_pct": global_success_rate,
        "success_rates_by_strategy_pct": success_rates,
        "non_playwright_pct": non_pw_rate,
        "non_playwright_success_pct": non_pw_success_rate,
        "fallback_rate_pct": fallback_rate,
        "fallback_reasons": dict(fallback_reasons),
        "top_reason_codes": dict(reason_counts.most_common(10)),
        "cache_hit_rate_pct": cache_rate,
        "quality_distribution": dict(quality_counts),
    }


def compare_to_baseline(metrics: dict) -> dict:
    """Compare current metrics against the original pipeline baseline."""
    b = BASELINE

    # Time comparison
    baseline_avg = b["avg_per_company_s"]
    current_avg = metrics["avg_time_per_company_s"]
    time_reduction_pct = round((1 - current_avg / baseline_avg) * 100, 1)

    # Playwright reduction
    # Baseline: effectively ~100% needed Playwright (skips were due to false signals, not good data)
    baseline_pw_pct = 100.0  # honest baseline: nothing resolved without Playwright
    current_pw_pct = metrics["strategy_pct"].get("playwright", 0)
    pw_reduction_pct = round(baseline_pw_pct - current_pw_pct, 1)

    return {
        "baseline_avg_time_s": baseline_avg,
        "current_avg_time_s": current_avg,
        "time_reduction_pct": time_reduction_pct,
        "baseline_playwright_pct": baseline_pw_pct,
        "current_playwright_pct": current_pw_pct,
        "playwright_reduction_pct": pw_reduction_pct,
        "targets": {
            "non_playwright_70pct": metrics["non_playwright_pct"] >= 70,
            "time_reduction_50pct": time_reduction_pct >= 50,
            "success_rate_maintained": metrics["global_success_rate_pct"] >= 60,
        },
    }


def print_report(metrics: dict, comparison: dict):
    print()
    print("=" * 70)
    print("EXTRACTION PIPELINE BENCHMARK REPORT")
    print("=" * 70)
    print()

    print("── Strategy Distribution ──────────────────────────────────")
    for s in ["ats_api", "http_static", "playwright"]:
        count = metrics["strategy_distribution"].get(s, 0)
        pct = metrics["strategy_pct"].get(s, 0)
        avg_t = metrics["strategy_avg_time_s"].get(s, 0)
        sr = metrics["success_rates_by_strategy_pct"].get(s, 0)
        print(f"  {s:<15s}  {count:>3d} companies  ({pct:>5.1f}%)  "
              f"avg={avg_t:>5.1f}s  success={sr:.0f}%")
    print()

    print("── Timing ────────────────────────────────────────────────")
    print(f"  Total time:              {metrics['total_time_s']:>8.1f}s")
    print(f"  Avg per company:         {metrics['avg_time_per_company_s']:>8.2f}s")
    print(f"  Baseline avg (original): {comparison['baseline_avg_time_s']:>8.1f}s")
    print(f"  Time reduction:          {comparison['time_reduction_pct']:>8.1f}%")
    print()

    print("── Success & Quality ─────────────────────────────────────")
    print(f"  Global success rate:     {metrics['global_success_rate_pct']:>8.1f}%")
    print(f"  Non-Playwright rate:     {metrics['non_playwright_pct']:>8.1f}%")
    print(f"  Non-PW success rate:     {metrics['non_playwright_success_pct']:>8.1f}%")
    print(f"  Fallback rate:           {metrics['fallback_rate_pct']:>8.1f}%")
    print(f"  Cache hit rate:          {metrics['cache_hit_rate_pct']:>8.1f}%")
    print()

    print("── Evidence Quality ──────────────────────────────────────")
    for q in ["high", "moderate", "limited", "none"]:
        count = metrics["quality_distribution"].get(q, 0)
        print(f"  {q:<12s}  {count:>3d}")
    print()

    print("── Top Reason Codes ──────────────────────────────────────")
    for reason, count in sorted(
        metrics["top_reason_codes"].items(), key=lambda x: -x[1]
    ):
        print(f"  {reason:<45s}  {count:>3d}")
    print()

    if metrics["fallback_reasons"]:
        print("── Fallback Reasons ──────────────────────────────────────")
        for reason, count in sorted(
            metrics["fallback_reasons"].items(), key=lambda x: -x[1]
        ):
            print(f"  {reason:<45s}  {count:>3d}")
        print()

    print("── Target Checklist ──────────────────────────────────────")
    targets = comparison["targets"]
    for label, passed in [
        (f">= 70% without Playwright (actual: {metrics['non_playwright_pct']:.1f}%)", targets["non_playwright_70pct"]),
        (f">= 50% time reduction (actual: {comparison['time_reduction_pct']:.1f}%)", targets["time_reduction_50pct"]),
        (f"Success rate maintained (actual: {metrics['global_success_rate_pct']:.1f}%)", targets["success_rate_maintained"]),
    ]:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label}")
    print()
    print("=" * 70)


def main():
    args = parse_args()

    print(f"Loading companies from {args.input}")
    companies = load_companies(args.input)
    print(f"Loaded {len(companies)} companies")

    if args.limit > 0:
        companies = companies[:args.limit]
    print(f"Benchmarking {len(companies)} companies (playwright={'ON' if args.with_playwright else 'OFF'})")
    print()

    results = run_benchmark(companies, args.with_playwright, args.delay)
    metrics = compute_metrics(results)
    comparison = compare_to_baseline(metrics)

    print_report(metrics, comparison)

    # ── Save report ─────────────────────────────────────────────
    report = {
        "benchmark_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(companies),
        "with_playwright": args.with_playwright,
        "metrics": metrics,
        "comparison": comparison,
        "baseline": BASELINE,
        "per_company": results,
    }

    output_path = args.output or (_ROOT / "cli" / "results" / "benchmark_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
