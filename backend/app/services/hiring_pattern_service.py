"""
Feature 5: Job Family Classification + HiringPattern Aggregation.

1. Classifies all CompanyJobRole records by functional area
2. Aggregates into HiringPattern (top areas, concentration, totals)
3. Generates CompanySignal records from patterns for the scoring engine
"""

import json
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.company_job_role import CompanyJobRole, HiringPattern
from app.models.company_signal import CompanySignal
from app.services.role_ingest import CANONICAL, _canonical, classify_title
from app.core.logging import get_logger

logger = get_logger(__name__)


def classify_roles(company_id: UUID, db: Session) -> dict:
    """Classify all job roles for a company by functional area.

    Persists reason_code alongside confidence when diagnosable:
      - "high" | "medium" | "low"                (matched, normal path)
      - "low:no_keyword_match"                   (classifier saw nothing usable)
      - "none:junk_title"                        (hit a junk pattern)
      - "none:invalid_title:<detail>"            (e.g., too_short_no_role, contains_date)
    The colon-suffixed form keeps the existing string column compatible with
    all readers (which only treat it as opaque text).
    """
    roles = (
        db.query(CompanyJobRole)
        .filter(CompanyJobRole.company_id == company_id)
        .all()
    )

    if not roles:
        return {"classified": 0, "total": 0, "reason_counts": {}}

    classified = 0
    reason_counts: dict[str, int] = {}
    for role in roles:
        area, confidence_label = classify_title(
            role.role_title, role.role_description
        )
        role.functional_area = area
        role.functional_area_confidence = confidence_label
        # Derive reason key from the colon-suffixed label (matches legacy counts).
        reason = confidence_label.split(":", 1)[1] if ":" in confidence_label else "matched"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        classified += 1

    db.commit()
    return {
        "classified": classified,
        "total": len(roles),
        "reason_counts": reason_counts,
    }


def compute_hiring_pattern(company_id: UUID, db: Session) -> dict:
    """Full pipeline: classify roles -> aggregate pattern -> generate signals."""

    # Step 1: Classify all roles
    classify_result = classify_roles(company_id, db)

    # Step 2: Get classified roles
    roles = (
        db.query(CompanyJobRole)
        .filter(CompanyJobRole.company_id == company_id)
        .all()
    )

    if not roles:
        return {
            "classification": classify_result,
            "pattern": None,
            "signals_generated": 0,
        }

    # Step 3: Aggregate (exclude junk and unknown from concentration calc)
    area_counts: dict[str, int] = {}
    excluded = {"unknown", "junk"}
    for r in roles:
        area = r.functional_area or "unknown"
        if area in excluded:
            continue
        area_counts[area] = area_counts.get(area, 0) + 1

    total = sum(area_counts.values())
    unique = len(area_counts)
    sorted_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)
    top_5 = [a[0] for a in sorted_areas[:5]]

    # Concentration: HHI-style (sum of squared shares)
    shares = [count / total for _, count in sorted_areas if total > 0]
    hhi = sum(s * s for s in shares)

    dominant_function = sorted_areas[0][0] if sorted_areas else None
    dominant_share = sorted_areas[0][1] / total if sorted_areas and total > 0 else 0

    # Step 4: Upsert HiringPattern
    # Delete old patterns for this company
    db.query(HiringPattern).filter(HiringPattern.company_id == company_id).delete()

    pattern = HiringPattern(
        company_id=company_id,
        top_functional_areas=", ".join(top_5),
        top_capability_themes=json.dumps(dict(sorted_areas)),
        total_roles_found=total,
        unique_functions_found=unique,
    )
    db.add(pattern)

    # Step 5: Generate signals
    signals_generated = _generate_pattern_signals(
        company_id, area_counts, total, unique, db
    )

    db.commit()

    return {
        "classification": classify_result,
        "pattern": {
            "top_functional_areas": top_5,
            "function_distribution": dict(sorted_areas),
            "total_roles": total,
            "unique_functions": unique,
            "dominant_function": dominant_function,
            "dominant_share": round(dominant_share, 2),
            "concentration_index": round(hhi, 3),
        },
        "signals_generated": signals_generated,
    }


def _generate_pattern_signals(
    company_id: UUID,
    area_counts: dict[str, int],
    total: int,
    unique: int,
    db: Session,
) -> int:
    """Generate CompanySignal records from hiring patterns."""
    # Clean old pattern signals first
    db.query(CompanySignal).filter(
        CompanySignal.company_id == company_id,
        CompanySignal.source_type == "hiring_pattern_analysis",
    ).delete()

    signals = []

    for area, count in area_counts.items():
        if area == "unknown" or total == 0:
            continue
        share = count / total

        if share >= 0.40:
            signals.append(
                CompanySignal(
                    company_id=company_id,
                    source_type="hiring_pattern_analysis",
                    signal_type=f"{area}_concentration_high",
                    signal_text=f"{area} represents {share:.0%} of open roles ({count}/{total})",
                    numeric_value=share,
                    confidence=0.85,
                )
            )
        elif share >= 0.25:
            signals.append(
                CompanySignal(
                    company_id=company_id,
                    source_type="hiring_pattern_analysis",
                    signal_type=f"{area}_concentration_moderate",
                    signal_text=f"{area} represents {share:.0%} of open roles ({count}/{total})",
                    numeric_value=share,
                    confidence=0.75,
                )
            )

    if total >= 20:
        signals.append(
            CompanySignal(
                company_id=company_id,
                source_type="hiring_pattern_analysis",
                signal_type="high_hiring_volume",
                signal_text=f"Company has {total} open roles detected",
                numeric_value=total,
                confidence=0.80,
            )
        )

    if unique >= 5:
        signals.append(
            CompanySignal(
                company_id=company_id,
                source_type="hiring_pattern_analysis",
                signal_type="broad_hiring_pattern",
                signal_text=f"Hiring across {unique} distinct functional areas",
                numeric_value=unique,
                confidence=0.75,
            )
        )

    if unique <= 2 and total >= 5:
        signals.append(
            CompanySignal(
                company_id=company_id,
                source_type="hiring_pattern_analysis",
                signal_type="narrow_hiring_focus",
                signal_text=f"Hiring concentrated in {unique} functional area(s) with {total} roles",
                numeric_value=unique,
                confidence=0.80,
            )
        )

    for s in signals:
        db.add(s)

    return len(signals)
