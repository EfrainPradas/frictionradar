"""Inject FrictionRadar VIP opportunities into Ascendia smart_match tables.

Reads VIP opportunities from FrictionRadar, maps companies by domain,
and upserts into Ascendia's smart_match_briefs + smart_match_cv_versions.

Usage:
    python -m scripts.inject_to_ascendia [--user-id USER_ID] [--dry-run] [--top-n N]

Environment variables required:
    ASCENDIA_DATABASE_URL  — Postgres connection string for Ascendia
    DATABASE_URL           — Postgres connection string for FrictionRadar
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def get_env_or_die(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"ERROR: {key} not set in environment", file=sys.stderr)
        sys.exit(1)
    return val


def align_score_to_match(score_01: float) -> int:
    """Convert FrictionRadar 0-1 alignment_score to Ascendia 0-10 match_score."""
    raw = round(score_01 * 10)
    return max(1, min(10, raw))


def build_snapshot_neutral(opp: dict, pain_profile: dict | None, open_roles: list) -> dict:
    """Build enriched snapshot_neutral from FrictionRadar data."""
    snapshot = {
        "domain": opp["domain"],
        "company_id": opp["company_id"],
        "positioning_angle": opp.get("strategic_positioning") or "",
        "match_insight": opp.get("company_pain_summary") or opp.get("why_you_fit") or "",
        "what_they_seek": opp.get("why_they_value_you") or "",
        "inferred_sector": opp.get("inferred_sector") or "",
        "opportunity_score": round((opp.get("alignment_score") or 0) * 10, 1),
        "detection_evidence": {
            "source": "frictionradar",
            "alignment_score": opp.get("alignment_score"),
            "opportunity_type": opp.get("opportunity_type"),
            "pain_type": pain_profile.get("dominant_pain") if pain_profile else None,
            "pain_dimensions": pain_profile.get("pain_dimensions") if pain_profile else None,
            "confidence_band": pain_profile.get("confidence_band") if pain_profile else None,
        },
    }
    if open_roles:
        snapshot["open_roles"] = open_roles[:5]
        snapshot["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def build_bullets_tailored(resume_emphasis: list[str] | None, pain_summary: str | None) -> list[dict]:
    """Convert FrictionRadar resume_emphasis into Ascendia-style bullets_tailored."""
    if not resume_emphasis:
        return []
    bullets = []
    for i, emphasis in enumerate(resume_emphasis[:8]):
        bullets.append({
            "original_index": i,
            "tailored_text": emphasis,
            "pain_hook": pain_summary[:60] + "..." if pain_summary and len(pain_summary) > 60 else (pain_summary or ""),
        })
    return bullets


def main():
    parser = argparse.ArgumentParser(description="Inject FrictionRadar VIP data into Ascendia")
    parser.add_argument("--user-id", default="c1f53ebc-b8d1-42f1-8ed1-fd44e5ed4f4c",
                        help="Ascendia user ID to inject for")
    parser.add_argument("--top-n", type=int, default=30,
                        help="Max VIP opportunities to inject")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to Ascendia")
    args = parser.parse_args()

    # ── Connect to both databases ──────────────────────────────────────────
    fr_url = get_env_or_die("DATABASE_URL")
    asc_url = get_env_or_die("ASCENDIA_DATABASE_URL")

    fr_engine = create_engine(fr_url)
    asc_engine = create_engine(asc_url)

    user_id = args.user_id

    # ── 1. Read VIP opportunities from FrictionRadar ─────────────────────────
    with Session(fr_engine) as fr_db:
        opportunities = fr_db.execute(text("""
            SELECT vo.company_id, vo.alignment_score, vo.opportunity_type,
                   vo.company_pain_summary, vo.strategic_positioning,
                   vo.resume_emphasis, vo.networking_positioning,
                   vo.interview_positioning, vo.why_you_fit, vo.why_they_value_you,
                   c.name AS company_name, c.domain, c.inferred_sector
            FROM friction_vip_opportunities vo
            JOIN companies c ON c.id = vo.company_id
            WHERE vo.user_id = :uid AND vo.is_active = true
            ORDER BY vo.alignment_score DESC
            LIMIT :limit
        """), {"uid": user_id, "limit": args.top_n}).fetchall()

        # Also fetch company pain profiles for enrichment
        company_ids = [str(o.company_id) for o in opportunities]
        pain_profiles = {}
        if company_ids:
            rows = fr_db.execute(text("""
                SELECT company_id, dominant_pain, pain_dimensions,
                       confidence_band, evidence_depth,
                       recommended_positioning, candidate_archetype,
                       positioning_angle, resume_emphasis AS profile_resume_emphasis,
                       networking_angle, interview_themes, temporal_status, trend_direction
                FROM friction_company_profiles
                WHERE company_id = ANY(:ids)
            """), {"ids": company_ids}).fetchall()
            for r in rows:
                pain_profiles[str(r.company_id)] = dict(r._mapping)

        # Fetch open roles for each company
        open_roles_map = {}
        if company_ids:
            roles_rows = fr_db.execute(text("""
                SELECT company_id, role_title, source_url, functional_area
                FROM company_job_roles
                WHERE company_id = ANY(:ids)
                AND functional_area_confidence != 'none:junk'
                AND functional_area != 'junk'
                AND functional_area != 'unknown'
                ORDER BY company_id, functional_area_confidence DESC
            """), {"ids": company_ids}).fetchall()
            for r in roles_rows:
                cid = str(r.company_id)
                if cid not in open_roles_map:
                    open_roles_map[cid] = []
                open_roles_map[cid].append({
                    "title": r.role_title,
                    "url": r.source_url,
                    "functional_area": r.functional_area,
                })

    if not opportunities:
        print("No active VIP opportunities found. Run the sweep first.")
        print("  curl -X POST http://localhost:8000/api/v1/intelligence/candidates/{USER_ID}/vip-opportunities?top_n=30")
        sys.exit(0)

    print(f"\nFound {len(opportunities)} VIP opportunities for user {user_id}")
    print("=" * 80)

    # ── 2. Find matching Ascendia briefs by domain ──────────────────────────
    with Session(asc_engine) as asc_db:
        domains = [o.domain for o in opportunities if o.domain]
        existing_briefs = asc_db.execute(text("""
            SELECT id, company_id, domain, match_score, status
            FROM smart_match_briefs
            WHERE user_id = :uid
        """), {"uid": user_id}).fetchall()

        domain_to_brief = {}
        for b in existing_briefs:
            domain_to_brief[b.domain] = dict(b._mapping)

        print(f"Existing Ascendia briefs: {len(existing_briefs)}")
        print(f"Domains in VIP opportunities: {len(domains)}")

        # ── 3. Build injection plan ──────────────────────────────────────────
        to_update = []  # briefs that already exist (update)
        to_insert = []  # new briefs to create

        for opp in opportunities:
            if not opp.domain:
                continue

            pain_profile = pain_profiles.get(str(opp.company_id))
            roles = open_roles_map.get(str(opp.company_id), [])[:5]

            match_score = align_score_to_match(opp.alignment_score)
            snapshot = build_snapshot_neutral(dict(opp._mapping), pain_profile, roles)
            rationale = opp.why_you_fit or opp.company_pain_summary or ""

            existing = domain_to_brief.get(opp.domain)

            if existing:
                to_update.append({
                    "brief_id": existing["id"],
                    "domain": opp.domain,
                    "company_name": opp.company_name,
                    "match_score": match_score,
                    "old_score": int(existing["match_score"]) if existing["match_score"] else None,
                    "rationale": rationale,
                    "snapshot": snapshot,
                    "status": "saved" if match_score >= 7 else "proposed",
                    "opp": opp,
                    "pain_profile": pain_profile,
                    "roles": roles,
                })
            else:
                to_insert.append({
                    "domain": opp.domain,
                    "company_name": opp.company_name,
                    "match_score": match_score,
                    "rationale": rationale,
                    "snapshot": snapshot,
                    "status": "saved" if match_score >= 7 else "proposed",
                    "opp": opp,
                    "pain_profile": pain_profile,
                    "roles": roles,
                })

        # ── 4. Print plan ────────────────────────────────────────────────────
        print(f"\n--- UPDATE (existing briefs) ---")
        for item in to_update:
            print(f"  {item['domain']:25s}  {item['old_score']:>2s} → {item['match_score']:>2d}/10  "
                  f"{item['company_name'] or '?':30s}  [{item['status']}]")

        print(f"\n--- INSERT (new briefs) ---")
        for item in to_insert:
            print(f"  {item['domain']:25s}  NEW → {item['match_score']:>2d}/10  "
                  f"{item['company_name'] or '?':30s}  [{item['status']}]")

        if args.dry_run:
            print(f"\n{'DRY RUN':=^80}")
            print(f"Would update {len(to_update)} briefs and insert {len(to_insert)} briefs.")
            print("Run without --dry-run to apply changes.")
            return

        # ── 5. Execute updates ───────────────────────────────────────────────
        now = datetime.now(timezone.utc)

        for item in to_update:
            asc_db.execute(text("""
                UPDATE smart_match_briefs
                SET match_score = :score,
                    match_rationale = :rationale,
                    snapshot_neutral = :snapshot,
                    status = :status,
                    updated_at = :now
                WHERE id = :id
            """), {
                "id": item["brief_id"],
                "score": item["match_score"],
                "rationale": item["rationale"],
                "snapshot": json.dumps(item["snapshot"], default=str),
                "status": item["status"],
                "now": now,
            })

            # Update cv_version with FrictionRadar data
            opp = item["opp"]
            pain = item["pain_profile"]
            bullets = build_bullets_tailored(
                opp.resume_emphasis if hasattr(opp, 'resume_emphasis') else None,
                opp.company_pain_summary
            )

            asc_db.execute(text("""
                UPDATE smart_match_cv_versions
                SET pain_interpretation = :pain_interp,
                    positioning_angle_used = :positioning,
                    what_they_seek_used = :what_they_seek,
                    top_role_title_used = :top_role,
                    bullets_tailored = :bullets,
                    gaps = :gaps
                WHERE brief_id = :brief_id
            """), {
                "brief_id": item["brief_id"],
                "pain_interp": opp.company_pain_summary or (pain.get("positioning_angle") if pain else None),
                "positioning": opp.strategic_positioning or (pain.get("recommended_positioning") if pain else None),
                "what_they_seek": opp.why_they_value_you or None,
                "top_role": item["roles"][0]["title"] if item["roles"] else None,
                "bullets": json.dumps(bullets) if bullets else None,
                "gaps": None,
            })

        # ── 6. Execute inserts ──────────────────────────────────────────────
        # Use UPSERT on (user_id, company_id) to handle duplicates cleanly
        for item in to_insert:
            brief_id = str(uuid4())

            result = asc_db.execute(text("""
                INSERT INTO smart_match_briefs
                    (id, user_id, company_id, domain, match_score, match_rationale, snapshot_neutral, status, created_at, updated_at)
                VALUES
                    (:id, :uid, :cid, :domain, :score, :rationale, :snapshot, :status, :now, :now)
                ON CONFLICT (user_id, company_id) DO UPDATE SET
                    match_score = EXCLUDED.match_score,
                    match_rationale = EXCLUDED.match_rationale,
                    snapshot_neutral = EXCLUDED.snapshot_neutral,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            """), {
                "id": brief_id,
                "uid": user_id,
                "cid": item["opp"].company_id,
                "domain": item["domain"],
                "score": item["match_score"],
                "rationale": item["rationale"],
                "snapshot": json.dumps(item["snapshot"], default=str),
                "status": item["status"],
                "now": now,
            })

            # Get the actual brief_id (could be existing or new)
            actual_brief_id = str(result.scalar_one())

            opp = item["opp"]
            pain = item["pain_profile"]
            bullets = build_bullets_tailored(
                opp.resume_emphasis if hasattr(opp, 'resume_emphasis') else None,
                opp.company_pain_summary
            )

            # Upsert cv_version (one per brief, unique constraint on brief_id)
            asc_db.execute(text("""
                INSERT INTO smart_match_cv_versions
                    (id, brief_id, user_id, master_resume_id,
                     profile_summary_tailored, bullets_tailored,
                     positioning_angle_used, what_they_seek_used, top_role_title_used,
                     pain_interpretation, gaps,
                     generation_model, created_at)
                VALUES
                    (:id, :brief_id, :uid, :master_id,
                     :profile_summary, :bullets,
                     :positioning, :what_they_seek, :top_role,
                     :pain_interp, :gaps,
                     'frictionradar-inject', :now)
                ON CONFLICT (brief_id) DO UPDATE SET
                    profile_summary_tailored = EXCLUDED.profile_summary_tailored,
                    bullets_tailored = EXCLUDED.bullets_tailored,
                    positioning_angle_used = EXCLUDED.positioning_angle_used,
                    what_they_seek_used = EXCLUDED.what_they_seek_used,
                    top_role_title_used = EXCLUDED.top_role_title_used,
                    pain_interpretation = EXCLUDED.pain_interpretation,
                    gaps = EXCLUDED.gaps
            """), {
                "id": str(uuid4()),
                "brief_id": actual_brief_id,
                "uid": user_id,
                "master_id": "f048e19d-e7a4-4233-93e7-17d914515308",  # Isabella's master resume
                "profile_summary": opp.strategic_positioning or opp.why_you_fit or None,
                "bullets": json.dumps(bullets) if bullets else None,
                "positioning": opp.strategic_positioning or (pain.get("recommended_positioning") if pain else None),
                "what_they_seek": opp.why_they_value_you or None,
                "top_role": item["roles"][0]["title"] if item["roles"] else None,
                "pain_interp": opp.company_pain_summary or (pain.get("positioning_angle") if pain else None),
                "gaps": None,
                "now": now,
            })

        asc_db.commit()

    print(f"\n{'INJECTION COMPLETE':=^80}")
    print(f"Updated: {len(to_update)} briefs")
    print(f"Inserted: {len(to_insert)} briefs")
    print(f"Total: {len(to_update) + len(to_insert)} companies synced to Ascendia")


if __name__ == "__main__":
    main()