"""Tests for the synthetic dataset generator.

Covers:
  1. Reproducibility — same seed produces bit-identical output.
  2. Archetype counts — each archetype contributes its declared `n`.
  3. Counterfactual pairing — pairs are complete and tagged correctly.
  4. Ground-truth vocabularies — every expected_* field uses closed enums.
  5. Score bands — coherent (0 ≤ lo ≤ hi ≤ 100).
  6. Determinism — sub-seeds derived per archetype isolate diffs.

Run:
  python backend/tests/test_synthetic_generator.py
  pytest backend/tests/test_synthetic_generator.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.synthetic.validate_dataset import validate  # noqa: E402

REPO_ROOT = _BACKEND.parent
GEN_SCRIPT = _BACKEND / "scripts" / "synthetic" / "generate_dataset.py"
ARCH_PATH = _BACKEND / "scripts" / "synthetic" / "archetypes.yaml"
SEED_PATH = _BACKEND / "data" / "synthetic" / "seed" / "real_seed.json"


def _run_generator(out_root: Path, version: str, seed: int = 42) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(GEN_SCRIPT),
        "--seed", str(seed),
        "--version", version,
        "--seed-path", str(SEED_PATH),
        "--archetypes-path", str(ARCH_PATH),
        "--out-root", str(out_root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"generator failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return out_root / version


def _load_dataset(out_dir: Path) -> tuple[dict, list[dict], list[dict], list[dict]]:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    companies = json.loads((out_dir / "companies.json").read_text(encoding="utf-8"))
    roles = json.loads((out_dir / "roles.json").read_text(encoding="utf-8"))
    signals = json.loads((out_dir / "signals.json").read_text(encoding="utf-8"))
    return manifest, companies, roles, signals


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestSyntheticGenerator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out_root = Path(cls._tmp.name)
        cls.out_dir = _run_generator(cls.out_root, version="synth-test-seed42")
        cls.manifest, cls.companies, cls.roles, cls.signals = _load_dataset(cls.out_dir)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ── 1. Reproducibility ──────────────────────────────────────────
    def test_reproducibility_seed_42(self):
        """Same seed → bit-identical companies/roles/signals files."""
        with tempfile.TemporaryDirectory() as tmp2:
            out2 = _run_generator(Path(tmp2), version="synth-test-seed42")
            for fname in ["companies.json", "roles.json", "signals.json"]:
                h1 = _hash_file(self.out_dir / fname)
                h2 = _hash_file(out2 / fname)
                self.assertEqual(h1, h2, f"{fname} not bit-identical between runs")

    def test_different_seeds_produce_different_output(self):
        with tempfile.TemporaryDirectory() as tmp2:
            out2 = _run_generator(Path(tmp2), version="synth-test-seed7", seed=7)
            h1 = _hash_file(self.out_dir / "companies.json")
            h2 = _hash_file(out2 / "companies.json")
            self.assertNotEqual(h1, h2, "different seeds should diverge")

    # ── 2. Counts ───────────────────────────────────────────────────
    def test_total_companies_includes_primary_plus_cf(self):
        """200 primary + 18 counterfactuals = 218 total."""
        self.assertEqual(self.manifest["totals"]["companies"], 218)

    def test_archetype_distribution_matches_yaml(self):
        """Each primary archetype contributes exactly its declared n."""
        import yaml
        arch_data = yaml.safe_load(ARCH_PATH.read_text(encoding="utf-8"))
        expected = {a["id"]: a["n"] for a in arch_data["archetypes"]}
        actual = {}
        for c in self.companies:
            aid = c["synthetic_meta"]["archetype_id"]
            # CF copies use "<archetype>_cf" — ignore for primary count.
            if aid.endswith("_cf"):
                continue
            actual[aid] = actual.get(aid, 0) + 1
        for aid, n in expected.items():
            self.assertEqual(actual.get(aid, 0), n, f"archetype {aid}: expected {n}, got {actual.get(aid, 0)}")

    # ── 3. Counterfactual pairing ──────────────────────────────────
    def test_counterfactual_pairs_complete(self):
        from collections import defaultdict
        pairs = defaultdict(list)
        for c in self.companies:
            pid = c["synthetic_meta"].get("counterfactual_pair_id")
            if pid:
                pairs[pid].append(c)
        self.assertEqual(self.manifest["counterfactual_pairs"], 18)
        for pid, cs in pairs.items():
            self.assertEqual(len(cs), 2, f"pair {pid} has {len(cs)} sides, expected 2")
        # Each pair: one primary + one cf
        for pid, cs in pairs.items():
            cf_count = sum(1 for c in cs if c["synthetic_meta"].get("is_counterfactual"))
            self.assertEqual(cf_count, 1, f"pair {pid} should have exactly one cf side")

    def test_counterfactual_baseline_score_band(self):
        """CF copies always have score_band [0, 3] — engine returns 0 with no signals."""
        for c in self.companies:
            if c["synthetic_meta"].get("is_counterfactual"):
                self.assertEqual(c["synthetic_meta"]["expected_friction_score_band"], [0, 3])
                self.assertEqual(c["synthetic_meta"]["expected_diagnostic_state"], "insufficient_evidence")
                self.assertIsNone(c["synthetic_meta"]["expected_dominant_friction_type"])
                self.assertEqual(c["synthetic_meta"]["expected_eligibility_gate"], "blocked")
                self.assertFalse(c["synthetic_meta"]["expected_smart_match_hit"])

    # ── 4. Vocabulary invariants (delegate to validator) ────────────
    def test_validator_passes_all_invariants(self):
        report = validate(self.out_dir)
        self.assertTrue(report.ok, f"validator failed:\n{report.render()}")

    # ── 5. Score bands sanity ──────────────────────────────────────
    def test_score_band_coherent(self):
        for c in self.companies:
            band = c["synthetic_meta"]["expected_friction_score_band"]
            self.assertEqual(len(band), 2)
            lo, hi = band
            self.assertGreaterEqual(lo, 0)
            self.assertLessEqual(hi, 100)
            self.assertLessEqual(lo, hi)

    # ── 6. Per-archetype expected outputs ──────────────────────────
    def test_novawork_ideal_expected_outputs(self):
        sample = [c for c in self.companies
                  if c["synthetic_meta"]["archetype_id"] == "novawork_ideal"]
        self.assertGreater(len(sample), 0)
        for c in sample:
            sm = c["synthetic_meta"]
            self.assertEqual(sm["expected_diagnostic_state"], "ready_for_positioning")
            self.assertEqual(sm["expected_dominant_friction_type"], "scaling_strain")
            self.assertEqual(sm["expected_eligibility_gate"], "full")
            self.assertTrue(sm["expected_smart_match_hit"])

    def test_intermediary_trap_entity_type(self):
        sample = [c for c in self.companies
                  if c["synthetic_meta"]["archetype_id"] == "intermediary_trap"]
        self.assertGreater(len(sample), 0)
        for c in sample:
            self.assertEqual(c["entity_type"], "job_market_intermediary")
            self.assertFalse(c["synthetic_meta"]["expected_smart_match_hit"])

    def test_data_quality_chaos_has_noise(self):
        sample = [c for c in self.companies
                  if c["synthetic_meta"]["archetype_id"] == "data_quality_chaos"]
        self.assertGreater(len(sample), 0)
        for c in sample:
            self.assertIn("chaos_parent_archetype", c["synthetic_meta"])
            self.assertGreaterEqual(len(c["synthetic_meta"]["noise_injected"]), 1)
            self.assertLessEqual(len(c["synthetic_meta"]["noise_injected"]), 3)

    # ── 7. Domain hygiene ──────────────────────────────────────────
    def test_no_domain_collides_with_real_seed(self):
        real = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        real_domains = {(c.get("domain") or "").lower() for c in real["companies"]}
        synth_domains = {c["domain"].lower() for c in self.companies}
        overlap = real_domains & synth_domains
        self.assertFalse(overlap, f"synthetic domains collide with real: {list(overlap)[:5]}")


if __name__ == "__main__":
    unittest.main()
