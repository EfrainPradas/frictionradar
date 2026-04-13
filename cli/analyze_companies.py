#!/usr/bin/env python
"""
Friction Radar — Batch Company Analysis CLI

Reads a JSON file of companies, analyzes each one through the full pipeline
(collection, scoring, evaluation, verdict), assigns an operational status,
and writes structured output files.

Usage:
    python cli/analyze_companies.py --input companies.json --output ./results
    python cli/analyze_companies.py --input companies.json --resume --limit 10
    python cli/analyze_companies.py --input companies.json --only-status needs_recollection
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable and its .env is loaded
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND / ".env")
except ImportError:
    import os
    env_path = _BACKEND / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

from services.input_loader import load_companies
from services.batch_processor import process_company
from services.result_writer import (
    write_results,
    load_progress,
    save_progress,
)

LOG_FORMAT = "%(asctime)s  %(message)s"
LOG_DATE = "%H:%M:%S"


def setup_logging(level: str) -> logging.Logger:
    log = logging.getLogger("batch_cli")
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE))
    log.addHandler(handler)
    return log


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch company analysis for Friction Radar"
    )
    p.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="JSON input file with companies",
    )
    p.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("./results"),
        help="Output directory for result files (default: ./results)",
    )
    p.add_argument("--limit", type=int, default=0, help="Max companies to process (0=all)")
    p.add_argument("--resume", action="store_true", help="Skip already-processed domains")
    p.add_argument(
        "--only-status",
        type=str,
        default=None,
        help="Re-process only companies with this status in a previous run",
    )
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Delay between companies")
    p.add_argument("--max-errors", type=int, default=20, help="Abort after N consecutive errors")
    p.add_argument("--log-level", type=str, default="info")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log = setup_logging(args.log_level)
    started_at = datetime.now(timezone.utc)

    # ── Load input ──────────────────────────────────────────────────
    log.info(f"Loading input: {args.input}")
    companies = load_companies(args.input)
    log.info(f"Loaded {len(companies)} entries")

    excluded_early = [c for c in companies if c.get("_exclude_reason")]
    valid = [c for c in companies if not c.get("_exclude_reason")]
    log.info(f"  Valid: {len(valid)}  |  Pre-excluded: {len(excluded_early)}")

    # ── Resume support ──────────────────────────────────────────────
    state_file = args.output / ".batch_state.json"
    done_domains: set[str] = set()
    if args.resume:
        done_domains = load_progress(state_file)
        log.info(f"  Resuming: {len(done_domains)} already done")

    # ── Filter by --only-status ─────────────────────────────────────
    prev_results: dict[str, dict] = {}
    if args.only_status:
        prev_all = args.output / "all_results.json"
        if prev_all.exists():
            import json
            prev = json.loads(prev_all.read_text(encoding="utf-8"))
            prev_results = {r["domain"]: r for r in prev if r.get("domain")}
            target_domains = {
                d for d, r in prev_results.items() if r.get("status") == args.only_status
            }
            valid = [c for c in valid if c["domain"] in target_domains]
            done_domains -= target_domains
            log.info(f"  Filtered to {len(valid)} companies with status={args.only_status}")

    # ── Apply limit ─────────────────────────────────────────────────
    to_process = [c for c in valid if c["domain"] not in done_domains]
    if args.limit > 0:
        to_process = to_process[: args.limit]

    log.info(f"  Will process: {len(to_process)} companies")
    log.info(f"  Output: {args.output}")
    log.info("")

    # ── First pass: collect all results (for QA cross-checks) ───────
    # QA needs to see all companies to detect patterns like repeated
    # open_positions_count. We do a two-pass approach:
    #   Pass 1: run pipeline, collect results, apply basic QA
    #   Pass 2: re-evaluate QA with full snapshot (for cross-company checks)
    #
    # In practice, we use a growing snapshot so the QA gets progressively
    # better as more companies are processed.

    results: list[dict] = []
    consecutive_errors = 0
    total = len(to_process)

    for i, entry in enumerate(to_process, start=1):
        name = entry.get("company_name", entry.get("domain", "?"))
        domain = entry.get("domain", "?")
        log.info(f"[{i}/{total}] {domain}")

        t0 = time.monotonic()
        result = process_company(entry, all_companies_snapshot=results)
        elapsed = round(time.monotonic() - t0, 1)

        status = result.get("status", "-")
        signals = result.get("signals_count", 0)
        hp = result.get("hiring_pressure", "-")
        pc = result.get("pain_clarity", "-")
        tier = result.get("target_tier", "-")
        op_state = result.get("operational_state", "-")

        log.info(f"  - signals: {signals}  hiring_pressure: {hp}  pain_clarity: {pc}")
        log.info(f"  - status: {status}  tier: {tier}  action: {op_state}  ({elapsed}s)")

        if result.get("qa_flags"):
            log.info(f"  - qa_flags: {result['qa_flags']}")

        if result.get("notes"):
            for note in result["notes"][:3]:
                log.info(f"  - {note}")

        results.append(result)
        done_domains.add(domain)

        # Save incremental progress
        if i % 5 == 0 or i == total:
            args.output.mkdir(parents=True, exist_ok=True)
            save_progress(state_file, done_domains)

        # Error tracking
        if result.get("error"):
            consecutive_errors += 1
            if consecutive_errors >= args.max_errors:
                log.error(f"Aborting: {args.max_errors} consecutive errors reached")
                break
        else:
            consecutive_errors = 0

        if i < total and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

        log.info("")

    # ── Add pre-excluded entries ────────────────────────────────────
    for entry in excluded_early:
        from services.batch_processor import _excluded_result
        results.append(_excluded_result(entry, entry["_exclude_reason"]))

    # ── Merge with previous results if filtering by status ──────────
    if args.only_status and prev_results:
        updated_domains = {r["domain"] for r in results if r.get("domain")}
        for domain, prev_r in prev_results.items():
            if domain not in updated_domains:
                results.append(prev_r)

    # ── Write output ────────────────────────────────────────────────
    log.info("Writing results…")
    out_path = write_results(results, args.output, started_at)

    # ── Summary ─────────────────────────────────────────────────────
    from collections import Counter
    status_counts = Counter(r["status"] for r in results)
    tier_counts = Counter(r.get("target_tier", "unknown") for r in results)
    state_counts = Counter(r.get("operational_state", "unknown") for r in results)
    qa_counts = Counter(r.get("data_quality_status", "unknown") for r in results)

    log.info("")
    log.info("═" * 60)
    log.info("RUN COMPLETE")
    log.info(f"  Total:              {len(results)}")
    log.info("")
    log.info("  Tiers:")
    for tier in ("tier_1_ready_for_positioning", "tier_2_ready_for_review", "tier_3_needs_recollection", "tier_4_excluded"):
        log.info(f"    {tier:<40s}{tier_counts.get(tier, 0)}")
    log.info("")
    log.info("  Operational States:")
    for state in ("position_now", "inspect_human", "collect_more", "exclude"):
        log.info(f"    {state:<40s}{state_counts.get(state, 0)}")
    log.info("")
    log.info("  Data Quality:")
    for qa in ("high", "medium", "low"):
        log.info(f"    {qa:<40s}{qa_counts.get(qa, 0)}")
    log.info("")
    log.info("  Original Pipeline Status:")
    for s in ("ready_for_review", "collected", "needs_recollection", "excluded"):
        log.info(f"    {s:<40s}{status_counts.get(s, 0)}")
    errors_count = sum(1 for r in results if r.get("error"))
    log.info(f"    {'errors':<40s}{errors_count}")
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    log.info(f"  Duration:           {duration:.0f}s")
    log.info(f"  Output:             {out_path}")
    log.info("═" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
