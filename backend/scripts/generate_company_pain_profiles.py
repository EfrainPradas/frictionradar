"""Generate friction_company_profiles from existing company signals.

Maps signal_types to friction categories and computes dominant pain + dimensions.

Usage:
    python -m scripts.generate_company_pain_profiles                # sequential
    python -m scripts.generate_company_pain_profiles --parallel 4    # 4 workers
    python -m scripts.generate_company_pain_profiles --parallel 8    # 8 workers
    python -m scripts.generate_company_pain_profiles --dry-run        # preview only
"""
import argparse
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.db.session import get_db, SessionLocal
from app.models.candidate_intelligence import FrictionCompanyProfile
from app.models.company_signal import CompanySignal
from app.models.company import Company

# ── Signal type → friction category mapping ──────────────────────────────────

SIGNAL_TO_CATEGORY = {
    # ── reporting_fragmentation ──
    "analytics_role_detected":            ("reporting_fragmentation", 0.6),
    "analytics_concentration_high":        ("reporting_fragmentation", 0.8),
    "analytics_concentration_moderate":    ("reporting_fragmentation", 0.4),
    "data_and_analytics_hiring_detected":  ("reporting_fragmentation", 0.7),
    "data_engineering_and_analytics_hiring_detected": ("reporting_fragmentation", 0.7),
    "data_hiring_detected":                ("reporting_fragmentation", 0.5),
    "data_science_hiring_detected":        ("reporting_fragmentation", 0.6),
    "finance_and_data_hiring_detected":    ("reporting_fragmentation", 0.6),
    "reporting_language_detected":         ("reporting_fragmentation", 0.9),
    "revops_language_detected":            ("reporting_fragmentation", 0.7),

    # ── process_inefficiency ──
    "operations_hiring_detected":          ("process_inefficiency", 0.6),
    "operations_concentration_high":       ("process_inefficiency", 0.8),
    "operations_concentration_moderate":  ("process_inefficiency", 0.4),
    "business_operations_hiring_detected":  ("process_inefficiency", 0.5),
    "admin_hiring_detected":              ("process_inefficiency", 0.5),
    "business_hiring_detected":           ("process_inefficiency", 0.3),
    "compliance_hiring_detected":         ("process_inefficiency", 0.6),
    "hr_people_hiring_detected":           ("process_inefficiency", 0.4),
    "human_resources_hiring_detected":     ("process_inefficiency", 0.4),
    "hr_concentration_high":              ("process_inefficiency", 0.6),
    "hr_concentration_moderate":          ("process_inefficiency", 0.3),
    "people_and_culture_hiring_detected":  ("process_inefficiency", 0.3),
    "accounting_hiring_detected":         ("process_inefficiency", 0.5),
    "accounts_payable_/_receivable_hiring_detected": ("process_inefficiency", 0.5),
    "supply_chain_hiring_detected":        ("process_inefficiency", 0.6),
    "supply_chain_concentration_high":     ("process_inefficiency", 0.7),
    "supply_chain_concentration_moderate": ("process_inefficiency", 0.4),
    "distribution_hiring_detected":        ("process_inefficiency", 0.5),
    "distribution_center_hiring_detected": ("process_inefficiency", 0.5),
    "legal_hiring_detected":              ("process_inefficiency", 0.4),
    "legal_concentration_high":           ("process_inefficiency", 0.5),
    "legal_concentration_moderate":       ("process_inefficiency", 0.3),
    "finance_hiring_detected":            ("process_inefficiency", 0.4),
    "finance_concentration_high":         ("process_inefficiency", 0.5),
    "finance_concentration_moderate":       ("process_inefficiency", 0.3),
    "automation_hiring_detected":         ("process_inefficiency", 0.7),
    "recruiting_concentration_high":       ("process_inefficiency", 0.5),
    "recruiting_concentration_moderate":   ("process_inefficiency", 0.3),

    # ── tooling_inconsistency ──
    "technology_hiring_detected":          ("tooling_inconsistency", 0.5),
    "engineering_hiring_detected":         ("tooling_inconsistency", 0.5),
    "engineering_concentration_high":       ("tooling_inconsistency", 0.7),
    "engineering_concentration_moderate":   ("tooling_inconsistency", 0.4),
    "it_hiring_detected":                  ("tooling_inconsistency", 0.5),
    "information_technology_hiring_detected": ("tooling_inconsistency", 0.6),
    "it_-_software_engineering_hiring_detected": ("tooling_inconsistency", 0.7),
    "it_-_tech_operation_hiring_detected":  ("tooling_inconsistency", 0.6),
    "it_-_e-commerce_hiring_detected":     ("tooling_inconsistency", 0.5),
    "backend_hiring_detected":             ("tooling_inconsistency", 0.6),
    "ats_embed_detected_ashby":            ("tooling_inconsistency", 0.3),
    "ats_embed_detected_greenhouse":       ("tooling_inconsistency", 0.3),
    "ats_embed_detected_icims":            ("tooling_inconsistency", 0.3),
    "ats_embed_detected_lever":            ("tooling_inconsistency", 0.3),
    "ats_embed_detected_smartrecruiters":  ("tooling_inconsistency", 0.3),
    "ats_embed_detected_workday":          ("tooling_inconsistency", 0.3),
    "open_source_hiring_detected":         ("tooling_inconsistency", 0.4),
    "codex_-_engineering_hiring_detected":  ("tooling_inconsistency", 0.5),

    # ── scaling_strain ──
    "growth_language_detected":            ("scaling_strain", 0.7),
    "scaling_language_detected":           ("scaling_strain", 0.9),
    "expansion_language_detected":         ("scaling_strain", 0.8),
    "hiring_language_detected":            ("scaling_strain", 0.6),
    "hiring_news_detected":                ("scaling_strain", 0.5),
    "funding_detected":                    ("scaling_strain", 0.8),
    "acquisition_detected":                ("scaling_strain", 0.7),
    "partnership_detected":                ("scaling_strain", 0.5),
    "multiple_open_roles":                 ("scaling_strain", 0.6),
    "high_open_positions_count_detected":   ("scaling_strain", 0.7),
    "open_positions_count_detected":        ("scaling_strain", 0.4),
    "broad_hiring_pattern":               ("scaling_strain", 0.6),
    "high_hiring_volume":                  ("scaling_strain", 0.7),
    "company_size_detected":               ("scaling_strain", 0.3),
    "sales_hiring_detected":               ("scaling_strain", 0.4),
    "sales_concentration_high":            ("scaling_strain", 0.5),
    "sales_concentration_moderate":        ("scaling_strain", 0.3),
    "business_development_hiring_detected": ("scaling_strain", 0.5),
    "business_strategy__hiring_detected":   ("scaling_strain", 0.5),
    "field_sales_hiring_detected":         ("scaling_strain", 0.4),
    "consumer_sales_hiring_detected":       ("scaling_strain", 0.4),
    "revenue-share_hiring_detected":         ("scaling_strain", 0.4),
    "crm_and_repeat_hiring_detected":       ("scaling_strain", 0.4),
    "cross_team_language_detected":         ("scaling_strain", 0.6),

    # ── customer_experience_friction ──
    "customer_success_hiring_detected":           ("customer_experience_friction", 0.7),
    "customer_success_and_support_hiring_detected": ("customer_experience_friction", 0.7),
    "customer_support_concentration_high":         ("customer_experience_friction", 0.8),
    "customer_support_concentration_moderate":     ("customer_experience_friction", 0.5),
    "client_management_hiring_detected":           ("customer_experience_friction", 0.5),
    "client_service_hiring_detected":              ("customer_experience_friction", 0.5),
    "inbound_sales_and_service_hiring_detected":    ("customer_experience_friction", 0.5),
    "field_service_hiring_detected":               ("customer_experience_friction", 0.4),

    # ── Also-map hiring that signals transformation ──
    "ai_hiring_detected":                  ("tooling_inconsistency", 0.4),
    "ai_+_machine_learning_engineering_hiring_detected": ("tooling_inconsistency", 0.5),
    "ai_for_science_hiring_detected":      ("tooling_inconsistency", 0.4),
    "ai_success_hiring_detected":          ("tooling_inconsistency", 0.4),
    "applied_ai_engineering_hiring_detected": ("tooling_inconsistency", 0.5),
    "applied_ai_infrastructure_hiring_detected": ("tooling_inconsistency", 0.5),
    "advanced_innovation_hiring_detected": ("tooling_inconsistency", 0.5),

    # ── Product/design → scaling strain ──
    "product_hiring_detected":             ("scaling_strain", 0.4),
    "product_concentration_high":          ("scaling_strain", 0.5),
    "product_concentration_moderate":      ("scaling_strain", 0.3),
    "product_and_design_hiring_detected":  ("scaling_strain", 0.4),
    "design_hiring_detected":             ("scaling_strain", 0.3),
    "brand_design_hiring_detected":        ("scaling_strain", 0.3),

    # ── Marketing → scaling strain ──
    "marketing_hiring_detected":           ("scaling_strain", 0.4),
    "marketing_concentration_high":        ("scaling_strain", 0.5),
    "marketing_concentration_moderate":    ("scaling_strain", 0.3),
    "creative_marketing_hiring_detected":  ("scaling_strain", 0.3),
    "creative_marketing_(md)_hiring_detected": ("scaling_strain", 0.3),
    "creative_marketing_(mp)_hiring_detected": ("scaling_strain", 0.3),
    "content_hiring_detected":            ("scaling_strain", 0.3),
    "content_(md)_hiring_detected":       ("scaling_strain", 0.3),
    "content_(mm)_hiring_detected":       ("scaling_strain", 0.3),
    "communications_hiring_detected":     ("scaling_strain", 0.3),

    # ── Leadership signals → scaling_strain ──
    "global_administrative_and_executive_team_hiring_detected": ("scaling_strain", 0.6),
    "alignment_hiring_detected":          ("scaling_strain", 0.5),
    "strategy__hiring_detected":         ("scaling_strain", 0.5),
    "professional_development_hiring_detected": ("scaling_strain", 0.3),

    # ── Industry-specific hiring → process_inefficiency ──
    "manufacturing_hiring_detected":      ("process_inefficiency", 0.6),
    "manufacturing_concentration_high":    ("process_inefficiency", 0.7),
    "manufacturing_concentration_moderate": ("process_inefficiency", 0.4),
    "construction_hiring_detected":         ("process_inefficiency", 0.5),
    "healthcare_hiring_detected":          ("process_inefficiency", 0.5),
    "healthcare_concentration_high":       ("process_inefficiency", 0.6),
    "healthcare_concentration_moderate":   ("process_inefficiency", 0.3),
    "retail_hiring_detected":              ("process_inefficiency", 0.4),
    "retail_concentration_high":            ("process_inefficiency", 0.5),
    "retail_concentration_moderate":        ("process_inefficiency", 0.3),
    "food_service_concentration_high":      ("process_inefficiency", 0.5),
    "trades_concentration_high":            ("process_inefficiency", 0.5),
    "trades_concentration_moderate":         ("process_inefficiency", 0.3),
    "education_concentration_high":          ("process_inefficiency", 0.4),
    "lab_hiring_detected":                  ("tooling_inconsistency", 0.3),
    "science_hiring_detected":              ("tooling_inconsistency", 0.3),

    # ── Leadership/exec → scaling_strain ──
    "b2b_applications_hiring_detected":    ("scaling_strain", 0.4),

    # ── Android/interbrand → tooling ──
    "android_hiring_detected":             ("tooling_inconsistency", 0.3),
    "interbrand_hiring_detected":          ("scaling_strain", 0.3),

    # ── Infrastructure/distributed energy → tooling ──
    "distributed_energy_resources__hiring_detected": ("tooling_inconsistency", 0.4),
}

# Signal types that don't map to a friction category (neutral/discovery signals)
NEUTRAL_SIGNALS = {
    "careers_page_found", "job_cards_visible_detected", "job_links_extracted",
    "newsroom_found", "narrow_hiring_focus", "no_department_hiring_detected",
    "other_hiring_detected", "wild_card_hiring_detected",
    "complex_hiring_detected",
    "ashby_board_detected", "greenhouse_board_detected", "icims_board_detected",
    "lever_board_detected", "smartrecruiters_board_detected", "workday_board_detected",
}

PAIN_DESCRIPTIONS = {
    "reporting_fragmentation": "Struggling with fragmented reporting, analytics gaps, and data visibility challenges.",
    "process_inefficiency": "Experiencing operational inefficiencies, process bottlenecks, and organizational complexity.",
    "tooling_inconsistency": "Dealing with technology fragmentation, engineering scaling, and infrastructure challenges.",
    "scaling_strain": "Under pressure from rapid growth, hiring expansion, and organizational scaling challenges.",
    "customer_experience_friction": "Facing customer experience friction, support gaps, and client retention challenges.",
}


def _compute_and_upsert_profile(company_id, company_name, sigs_data):
    """Compute pain profile from pre-loaded signals and upsert. Each worker owns its own session."""
    db = SessionLocal()
    try:
        category_weights = Counter()
        for sig_type, sig_confidence in sigs_data:
            mapping = SIGNAL_TO_CATEGORY.get(sig_type)
            if mapping:
                cat, weight = mapping
                category_weights[cat] += weight

        if not category_weights:
            return None

        max_weight = max(category_weights.values())
        pain_dimensions = {}
        for cat, weight in category_weights.items():
            pain_dimensions[cat] = round(min(weight / max_weight, 1.0), 2)

        dominant = category_weights.most_common(1)[0][0]
        signal_count = len(sigs_data)

        if signal_count > 10:
            confidence_band = "high"
            evidence_depth = "deep"
        elif signal_count > 5:
            confidence_band = "moderate"
            evidence_depth = "moderate"
        else:
            confidence_band = "low"
            evidence_depth = "shallow"

        existing = db.query(FrictionCompanyProfile).filter(
            FrictionCompanyProfile.company_id == company_id
        ).first()

        if existing:
            existing.dominant_pain = dominant
            existing.pain_dimensions = pain_dimensions
            existing.confidence_band = confidence_band
            existing.evidence_depth = evidence_depth
            db.commit()
            return ("updated", company_name, dominant, pain_dimensions)
        else:
            profile = FrictionCompanyProfile(
                company_id=company_id,
                dominant_pain=dominant,
                pain_dimensions=pain_dimensions,
                confidence_band=confidence_band,
                evidence_depth=evidence_depth,
            )
            db.add(profile)
            db.commit()
            return ("created", company_name, dominant, pain_dimensions)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return ("error", company_name, str(e))
    finally:
        db.close()


def generate_profiles(parallel: int = 1, dry_run: bool = False):
    """Generate friction_company_profiles from signals. Supports parallel execution."""
    db = next(get_db())

    companies = db.query(Company).filter(Company.positioning_eligible == True).all()  # noqa: E712
    print(f"Positioning-eligible companies: {len(companies)}")

    company_ids = [c.id for c in companies]
    signals = db.query(CompanySignal).filter(
        CompanySignal.company_id.in_(company_ids)
    ).all()
    print(f"Total signals: {len(signals)}")

    # Group signals by company (in-memory, before parallel)
    company_signals = defaultdict(list)
    for s in signals:
        company_signals[s.company_id].append((s.signal_type, s.confidence))

    db.close()

    # Build work items
    work_items = []
    for company in companies:
        sigs_data = company_signals.get(company.id, [])
        if not sigs_data:
            continue
        work_items.append((company.id, company.name, sigs_data))

    print(f"Companies with signals to process: {len(work_items)}")

    if dry_run:
        print("\nDRY RUN — no database writes.")
        for _, name, sigs_data in work_items[:10]:
            cat_weights = Counter()
            for sig_type, _ in sigs_data:
                mapping = SIGNAL_TO_CATEGORY.get(sig_type)
                if mapping:
                    cat, weight = mapping
                    cat_weights[cat] += weight
            if cat_weights:
                dominant = cat_weights.most_common(1)[0][0]
                print(f"  {name}: dominant={dominant}, signals={len(sigs_data)}, categories={dict(cat_weights)}")
        print(f"  ... and {max(0, len(work_items) - 10)} more")
        return

    created = 0
    updated = 0
    errors = 0
    t_start = time.monotonic()

    if parallel <= 1:
        # Sequential mode (original behavior)
        for cid, name, sigs_data in work_items:
            result = _compute_and_upsert_profile(cid, name, sigs_data)
            if result is None:
                continue
            status = result[0]
            if status == "created":
                created += 1
            elif status == "updated":
                updated += 1
            else:
                errors += 1
                print(f"  ERROR {name}: {result[2]}")

            if (created + updated + errors) % 100 == 0:
                elapsed = time.monotonic() - t_start
                print(f"  [{created + updated + errors}/{len(work_items)}] {elapsed:.0f}s elapsed")
    else:
        # Parallel mode
        print(f"Running with {parallel} workers...")
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(_compute_and_upsert_profile, cid, name, sigs_data): (cid, name)
                for cid, name, sigs_data in work_items
            }
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result is None:
                    continue
                status = result[0]
                if status == "created":
                    created += 1
                elif status == "updated":
                    updated += 1
                else:
                    errors += 1
                    print(f"  ERROR {result[1]}: {result[2]}")

                if i % 100 == 0:
                    elapsed = time.monotonic() - t_start
                    print(f"  [{i}/{len(work_items)}] created={created} updated={updated} errors={errors} {elapsed:.0f}s")

    elapsed = time.monotonic() - t_start
    print(f"\nCreated: {created}, Updated: {updated}, Errors: {errors}")
    print(f"Total profiles: {created + updated} in {elapsed:.1f}s")

    # Distribution summary
    db = SessionLocal()
    all_profiles = db.query(FrictionCompanyProfile).all()
    pain_dist = Counter(p.dominant_pain for p in all_profiles)
    print(f"\nDominant pain distribution ({len(all_profiles)} total):")
    for pain, count in pain_dist.most_common():
        print(f"  {pain}: {count}")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate company pain profiles from signals")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()
    generate_profiles(parallel=args.parallel, dry_run=args.dry_run)