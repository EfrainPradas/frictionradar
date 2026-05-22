"""Validate a synthetic dataset against the invariants in
backend/docs/synthetic_data_spec.md §6.

Usage:
  python backend/scripts/synthetic/validate_dataset.py
  python backend/scripts/synthetic/validate_dataset.py --version synth-test-v1

Exit code 0 if all invariants pass, 1 otherwise. Prints a per-check report.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_OUT_ROOT = BACKEND_ROOT / "data" / "synthetic"

SECTORS = {
    "Software & SaaS", "AI & Machine Learning", "Semiconductors & Hardware",
    "Fintech & Financial Services", "Ecommerce & Consumer", "Healthcare & Biotech",
    "Media & Entertainment", "Gaming", "Retail & Hospitality",
    "Manufacturing & Industrial", "Logistics & Transportation",
    "Telco & Internet Infra", "Education", "Real Estate & Construction",
    "Energy & Utilities", "Professional Services", "Other",
}
DIAGNOSTIC_STATES = {
    "insufficient_evidence", "broad_hiring_pattern_detected",
    "specific_pain_emerging", "specific_pain_identified",
    "ready_for_positioning",
}
FRICTION_TYPES = {
    "reporting_fragmentation", "process_inefficiency", "tooling_inconsistency",
    "scaling_strain", "customer_experience_friction",
}
ELIGIBILITY_GATES = {"full", "conditional", "blocked", "none"}
ENTITY_TYPES = {"operating_company", "job_market_intermediary"}


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passes.append(f"  [OK] {name}")
        else:
            self.failures.append(f"  [FAIL] {name}: {detail}")

    def render(self) -> str:
        lines = []
        if self.passes:
            lines.append("PASSES:")
            lines.extend(self.passes)
        if self.failures:
            lines.append("\nFAILURES:")
            lines.extend(self.failures)
        return "\n".join(lines)

    @property
    def ok(self) -> bool:
        return not self.failures


def _load(out_dir: Path) -> tuple[dict, list[dict], list[dict], list[dict]]:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    companies = json.loads((out_dir / "companies.json").read_text(encoding="utf-8"))
    roles = json.loads((out_dir / "roles.json").read_text(encoding="utf-8"))
    signals = json.loads((out_dir / "signals.json").read_text(encoding="utf-8"))
    return manifest, companies, roles, signals


def validate(out_dir: Path) -> Report:
    r = Report()
    manifest, companies, roles, signals = _load(out_dir)

    # ── Spec §6 invariants ──
    # 1. inferred_sector ∈ vocabulario
    bad_sectors = [c for c in companies if c.get("inferred_sector") not in SECTORS]
    r.check("companies.inferred_sector in closed vocabulary",
            not bad_sectors,
            f"{len(bad_sectors)} bad: {[c.get('inferred_sector') for c in bad_sectors[:5]]}")

    # 2. expected_diagnostic_state ∈ vocabulario
    bad_ds = [
        c for c in companies
        if (c.get("synthetic_meta") or {}).get("expected_diagnostic_state") not in DIAGNOSTIC_STATES
    ]
    r.check("expected_diagnostic_state in closed vocabulary",
            not bad_ds,
            f"{len(bad_ds)} bad")

    # 3. expected_dominant_friction_type ∈ vocabulario or null
    bad_dft = [
        c for c in companies
        if (sm := c.get("synthetic_meta") or {}).get("expected_dominant_friction_type") is not None
        and sm.get("expected_dominant_friction_type") not in FRICTION_TYPES
    ]
    r.check("expected_dominant_friction_type in vocab or null",
            not bad_dft,
            f"{len(bad_dft)} bad")

    # 4. expected_eligibility_gate ∈ vocabulario
    bad_gate = [
        c for c in companies
        if (c.get("synthetic_meta") or {}).get("expected_eligibility_gate") not in ELIGIBILITY_GATES
    ]
    r.check("expected_eligibility_gate in closed vocabulary",
            not bad_gate, f"{len(bad_gate)} bad")

    # 5. domains unique + prefix synth-
    domains = [c["domain"] for c in companies]
    dup = [d for d, n in Counter(domains).items() if n > 1]
    r.check("domains are unique", not dup, f"{len(dup)} duplicates: {dup[:5]}")
    bad_prefix = [d for d in domains if not d.startswith("synth-")]
    r.check("domains start with 'synth-'", not bad_prefix,
            f"{len(bad_prefix)} bad: {bad_prefix[:5]}")

    # 6. entity_type valid
    bad_et = [c for c in companies if c.get("entity_type") not in ENTITY_TYPES]
    r.check("entity_type in {operating_company, job_market_intermediary}",
            not bad_et, f"{len(bad_et)} bad")

    # 7. is_synthetic flag everywhere
    bad_co_flag = [c for c in companies if not (c.get("synthetic_meta") or {}).get("is_synthetic")]
    bad_role_flag = [r_ for r_ in roles if not (r_.get("synthetic_meta") or {}).get("is_synthetic")]
    bad_sig_flag = [s for s in signals if not (s.get("synthetic_meta") or {}).get("is_synthetic")]
    r.check("all companies marked is_synthetic", not bad_co_flag,
            f"{len(bad_co_flag)} missing")
    r.check("all roles marked is_synthetic", not bad_role_flag,
            f"{len(bad_role_flag)} missing")
    r.check("all signals marked is_synthetic", not bad_sig_flag,
            f"{len(bad_sig_flag)} missing")

    # 8. Manifest totals match files
    r.check("manifest.totals.companies matches", manifest["totals"]["companies"] == len(companies),
            f"manifest={manifest['totals']['companies']} actual={len(companies)}")
    r.check("manifest.totals.roles matches", manifest["totals"]["roles"] == len(roles),
            f"manifest={manifest['totals']['roles']} actual={len(roles)}")
    r.check("manifest.totals.signals matches", manifest["totals"]["signals"] == len(signals),
            f"manifest={manifest['totals']['signals']} actual={len(signals)}")

    # 9. Roles refer to existing companies
    company_ids = {c["id"] for c in companies}
    orphan_roles = [r_ for r_ in roles if r_.get("company_id") not in company_ids]
    r.check("all roles reference an existing company",
            not orphan_roles, f"{len(orphan_roles)} orphans")
    orphan_signals = [s for s in signals if s.get("company_id") not in company_ids]
    r.check("all signals reference an existing company",
            not orphan_signals, f"{len(orphan_signals)} orphans")

    # 10. Counterfactual pairing — both sides have same pair_id
    cf_pairs: dict[str, list[dict]] = {}
    for c in companies:
        pid = (c.get("synthetic_meta") or {}).get("counterfactual_pair_id")
        if pid:
            cf_pairs.setdefault(pid, []).append(c)
    incomplete = {pid: cs for pid, cs in cf_pairs.items() if len(cs) != 2}
    r.check("counterfactual pairs are complete (2 sides each)",
            not incomplete,
            f"{len(incomplete)} incomplete: {list(incomplete.keys())[:5]}")
    r.check("counterfactual_pairs in manifest matches found pairs",
            manifest["counterfactual_pairs"] == len([p for p in cf_pairs if len(cf_pairs[p]) == 2]),
            f"manifest={manifest['counterfactual_pairs']} found={len(cf_pairs)}")

    # 11. Score band coherence: score_band[0] ≥ 0, [1] ≤ 100, lo ≤ hi
    bad_band = []
    for c in companies:
        band = (c.get("synthetic_meta") or {}).get("expected_friction_score_band")
        if band is None:
            continue
        if not (isinstance(band, list) and len(band) == 2):
            bad_band.append(c["domain"]); continue
        lo, hi = band
        if lo < 0 or hi > 100 or lo > hi:
            bad_band.append(c["domain"])
    r.check("expected_friction_score_band coherent (0≤lo≤hi≤100)",
            not bad_band, f"{len(bad_band)} bad: {bad_band[:5]}")

    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=None,
                    help="Dataset version slug. Default: latest under data/synthetic/")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()

    if args.version:
        out_dir = args.out_root / args.version
    else:
        candidates = [
            p for p in args.out_root.iterdir()
            if p.is_dir() and p.name != "seed" and (p / "manifest.json").exists()
        ]
        if not candidates:
            print(f"[validate] no datasets found under {args.out_root}")
            sys.exit(1)
        out_dir = max(candidates, key=lambda p: p.stat().st_mtime)

    print(f"[validate] checking {out_dir}")
    report = validate(out_dir)
    print(report.render())
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
