"""
Bulk-analyze a list of companies by calling Friction Radar's
POST /analyze-company endpoint concurrently.

Features:
    - Reads tools/data/utah_companies.json (from scrape_utah_companies.py)
    - Concurrency limited via semaphore (default 3)
    - Incremental JSONL output so runs can be resumed safely
    - Skips any company already present in the output JSONL

Usage:
    python tools/bulk_analyze.py
    python tools/bulk_analyze.py --input tools/data/utah_companies.json --concurrency 4
    python tools/bulk_analyze.py --api http://127.0.0.1:3000/api/v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

DEFAULT_INPUT = Path(__file__).parent / "data" / "utah_companies.json"
OUTPUT_DIR = Path(__file__).parent / "data"
DEFAULT_API = "http://127.0.0.1:3000/api/v1"


def load_input(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [c for c in data if c.get("domain")]
    if isinstance(data, dict):
        companies = data.get("companies_with_domain") or data.get("companies") or []
        return [c for c in companies if c.get("domain")]
    raise ValueError(f"{path} must be a JSON array or object with 'companies_with_domain'")


def load_completed_domains(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    done: set[str] = set()
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            domain = (row.get("input") or {}).get("domain")
            if domain:
                done.add(domain.lower())
    return done


async def analyze_one(
    client: httpx.AsyncClient,
    company: dict,
    api_base: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    payload = {
        "domain": company["domain"],
        "name": company.get("name"),
        "industry": company.get("industry"),
    }
    url = f"{api_base}/analyze-company"
    started = time.monotonic()

    async with semaphore:
        try:
            resp = await client.post(url, json=payload, timeout=300.0)
            elapsed = time.monotonic() - started
            if resp.status_code >= 400:
                return {
                    "input": company,
                    "status": "error",
                    "http_status": resp.status_code,
                    "elapsed_s": round(elapsed, 1),
                    "error": resp.text[:500],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

            data = resp.json()
            evaluation_kpis: dict[str, Any] = {}
            diagnostic_state: str | None = None
            evaluation: dict[str, Any] = {}
            # If the backend ever inlines evaluation in the response, pick it up.
            if isinstance(data.get("evaluation"), dict):
                evaluation = data["evaluation"]
                evaluation_kpis = evaluation.get("kpis", {}) or {}
                diagnostic_state = evaluation.get("diagnostic_state")

            return {
                "input": company,
                "status": "ok",
                "http_status": resp.status_code,
                "elapsed_s": round(elapsed, 1),
                "company_id": (data.get("company") or {}).get("id"),
                "company_type": data.get("company_type"),
                "target_fit": data.get("target_fit"),
                "company_type_confidence": data.get("company_type_confidence"),
                "signals_count": data.get("signals_count"),
                "friction_score": (data.get("friction_score") or {}).get("total_score"),
                "dominant_friction_type": (data.get("friction_score") or {}).get(
                    "dominant_friction_type"
                ),
                "diagnostic_state": diagnostic_state,
                "evaluation_kpis": evaluation_kpis,
                "evaluation": evaluation,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            elapsed = time.monotonic() - started
            return {
                "input": company,
                "status": "exception",
                "elapsed_s": round(elapsed, 1),
                "error": f"{type(e).__name__}: {e}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }


async def fetch_evaluation(
    client: httpx.AsyncClient, api_base: str, company_id: str
) -> dict | None:
    try:
        r = await client.get(
            f"{api_base}/companies/{company_id}/evaluation", timeout=30.0
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


async def run(
    input_path: Path,
    output_path: Path,
    api_base: str,
    concurrency: int,
) -> int:
    companies = load_input(input_path)
    done = load_completed_domains(output_path)
    pending = [c for c in companies if c["domain"].lower() not in done]

    total = len(companies)
    print(f"Loaded {total} companies with resolved domains.")
    print(f"Already completed: {len(done)}")
    print(f"Pending: {len(pending)}")
    print(f"Concurrency: {concurrency}")
    print(f"Output: {output_path}")
    print(f"API: {api_base}\n")

    if not pending:
        print("Nothing to do.")
        return 0

    semaphore = asyncio.Semaphore(concurrency)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out = output_path.open("a", encoding="utf-8")
    async with httpx.AsyncClient() as client:
        async def task(company: dict, idx: int) -> None:
            result = await analyze_one(client, company, api_base, semaphore)
            if result["status"] == "ok" and not result["evaluation"] and result.get("company_id"):
                evaluation = await fetch_evaluation(client, api_base, result["company_id"])
                if evaluation:
                    result["evaluation"] = evaluation
                    result["evaluation_kpis"] = evaluation.get("kpis", {})
                    result["diagnostic_state"] = evaluation.get("diagnostic_state")
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()

            name = company.get("name", company["domain"])
            status = result["status"]
            elapsed = result.get("elapsed_s", "?")
            diag = result.get("diagnostic_state") or "—"
            score = result.get("friction_score") or "—"
            print(
                f"[{idx:3d}/{len(pending)}] {name[:35]:<35s} "
                f"{status:<10s} {elapsed}s  diag={diag}  score={score}"
            )

        try:
            await asyncio.gather(
                *(task(c, i + 1) for i, c in enumerate(pending))
            )
        finally:
            out.close()

    print(f"\nDone. Results appended to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--api", type=str, default=DEFAULT_API)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL path (default: tools/data/bulk_run_<timestamp>.jsonl). "
        "Pass an existing file to resume.",
    )
    args = parser.parse_args()

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = OUTPUT_DIR / f"bulk_run_{ts}.jsonl"

    return asyncio.run(run(args.input, args.output, args.api, args.concurrency))


if __name__ == "__main__":
    sys.exit(main())
