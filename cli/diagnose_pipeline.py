#!/usr/bin/env python
"""
Pipeline Health Check — Diagnostic tool.

Tests the collection pipeline against a sample of domains to identify
weaknesses and estimate the expected improvement.

Usage:
    python cli/diagnose_pipeline.py --domains agreserves.com,digicert.com,qualtrics.com
    python cli/diagnose_pipeline.py --sample needs_recollection.json --count 20
    python cli/diagnose_pipeline.py --all-results results/all_results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass


def diagnose_domain(domain: str, company_name: str = None) -> dict:
    """Run the full diagnostic against a single domain."""
    from app.collectors.careers_url_finder import careers_url_finder

    result = {
        "domain": domain,
        "company_name": company_name,
        "careers_url": None,
        "strategy": None,
        "collector_signals": {},
        "errors": [],
    }

    # Step 1: Find careers URL
    t0 = time.monotonic()
    try:
        url, strategy, meta = careers_url_finder.find(domain, company_name)
        result["careers_url"] = url
        result["strategy"] = strategy
        result["finder_time_ms"] = round((time.monotonic() - t0) * 1000)
    except Exception as e:
        result["errors"].append(f"Finder error: {e}")

    # Step 2: Run each collector individually
    from app.collectors import ACTIVE_COLLECTORS
    from app.models.company import Company

    mock_company = Company(
        name=company_name or domain,
        domain=domain,
        industry=None,
    )

    for collector in ACTIVE_COLLECTORS:
        t0 = time.monotonic()
        try:
            signals = collector.collect(mock_company)
            result["collector_signals"][collector.collector_type] = {
                "count": len(signals),
                "types": [s.signal_type for s in signals],
                "time_ms": round((time.monotonic() - t0) * 1000),
            }
        except Exception as e:
            result["collector_signals"][collector.collector_type] = {
                "count": 0,
                "error": str(e),
                "time_ms": round((time.monotonic() - t0) * 1000),
            }
            result["errors"].append(f"{collector.collector_type}: {e}")

    result["total_signals"] = sum(
        c.get("count", 0) for c in result["collector_signals"].values()
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="Pipeline health check")
    parser.add_argument("--domains", type=str, help="Comma-separated domains to test")
    parser.add_argument("--sample", type=Path, help="JSON file to sample domains from")
    parser.add_argument("--count", type=int, default=10, help="How many to sample")
    parser.add_argument("--all-results", type=Path, help="Analyze all_results.json for patterns")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    domains_to_test: list[tuple[str, str]] = []

    if args.domains:
        for d in args.domains.split(","):
            d = d.strip()
            if d:
                domains_to_test.append((d, None))

    elif args.sample:
        data = json.loads(args.sample.read_text(encoding="utf-8"))
        for entry in data[: args.count]:
            domain = entry.get("domain", "")
            name = entry.get("company_name", "")
            if domain:
                domains_to_test.append((domain, name))

    else:
        parser.print_help()
        return

    if args.all_results:
        # Analyze patterns in previous results
        print("\n" + "=" * 60)
        print("PREVIOUS RUN ANALYSIS")
        print("=" * 60)
        data = json.loads(args.all_results.read_text(encoding="utf-8"))
        
        zero_signals = [e for e in data if e.get("signals_count", 0) == 0]
        low_signals = [e for e in data if 0 < e.get("signals_count", 0) <= 3]
        good_signals = [e for e in data if e.get("signals_count", 0) > 3]
        
        print(f"Total companies: {len(data)}")
        print(f"  0 signals:      {len(zero_signals)} ({len(zero_signals)*100//len(data)}%)")
        print(f"  1-3 signals:    {len(low_signals)} ({len(low_signals)*100//len(data)}%)")
        print(f"  4+ signals:     {len(good_signals)} ({len(good_signals)*100//len(data)}%)")
        
        # Status breakdown
        from collections import Counter
        statuses = Counter(e.get("status") for e in data)
        for s, c in statuses.most_common():
            pct = c * 100 // len(data)
            print(f"  {s:<25s}{c:>4d} ({pct}%)")
        
        # Domains with issues
        print(f"\nSample of 0-signal domains:")
        for e in zero_signals[:10]:
            print(f"  - {e.get('domain', '?'):40s} {e.get('company_name', '?')}")

    print("\n" + "=" * 60)
    print(f"PIPELINE DIAGNOSTIC — testing {len(domains_to_test)} domains")
    print("=" * 60)

    results = []
    for i, (domain, name) in enumerate(domains_to_test, 1):
        print(f"\n[{i}/{len(domains_to_test)}] {domain}" + (f" ({name})" if name else ""))
        
        r = diagnose_domain(domain, name)
        results.append(r)

        url = r.get("careers_url") or "NOT FOUND"
        strategy = r.get("strategy") or "N/A"
        total = r.get("total_signals", 0)
        
        print(f"  Careers URL: {url}")
        print(f"  Strategy:    {strategy}")
        print(f"  Total signals: {total}")
        
        for collector, info in r.get("collector_signals", {}).items():
            count = info.get("count", 0)
            status = "[OK]" if count > 0 else "[NO]"
            if info.get("error"):
                status = "[ERR]"
            print(f"    {status} {collector:<25s} {count} signals  ({info.get('time_ms', 0)}ms)")
        
        if r.get("errors"):
            for err in r["errors"]:
                print(f"    ! {err}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    found_url = sum(1 for r in results if r.get("careers_url"))
    total = len(results)
    has_signals = sum(1 for r in results if r.get("total_signals", 0) > 0)
    
    print(f"Careers URL found:   {found_url}/{total} ({found_url*100//total if total else 0}%)")
    print(f"Has signals:         {has_signals}/{total} ({has_signals*100//total if total else 0}%)")
    
    avg_signals = sum(r.get("total_signals", 0) for r in results) / max(total, 1)
    print(f"Avg signals/domain:  {avg_signals:.1f}")


if __name__ == "__main__":
    main()
