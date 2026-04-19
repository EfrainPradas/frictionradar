from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.db.session import get_db
from app.models.company_signal import CompanySignal
from app.models.friction_score import FrictionScore
from app.models.collection_run import CollectionRun

router = APIRouter()


@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Return aggregated stats for all companies in one query: latest scores, signal counts, last collection."""

    # Signal counts per company
    signal_counts = dict(
        db.query(CompanySignal.company_id, func.count(CompanySignal.id))
        .group_by(CompanySignal.company_id)
        .all()
    )

    # Latest score per company (subquery for max computed_at)
    latest_score_sub = (
        db.query(
            FrictionScore.company_id,
            func.max(FrictionScore.computed_at).label("max_computed"),
        )
        .group_by(FrictionScore.company_id)
        .subquery()
    )
    latest_scores_rows = (
        db.query(FrictionScore)
        .join(
            latest_score_sub,
            (FrictionScore.company_id == latest_score_sub.c.company_id)
            & (FrictionScore.computed_at == latest_score_sub.c.max_computed),
        )
        .all()
    )

    # Last completed collection run per company
    last_collection = dict(
        db.query(
            CollectionRun.company_id,
            func.max(CollectionRun.started_at),
        )
        .filter(CollectionRun.status == "completed")
        .group_by(CollectionRun.company_id)
        .all()
    )

    scores = {}
    for s in latest_scores_rows:
        cid = str(s.company_id)
        scores[cid] = {
            "id": str(s.id),
            "company_id": cid,
            "total_score": float(s.total_score) if s.total_score is not None else None,
            "dominant_friction_type": s.dominant_friction_type,
            "scoring_breakdown_json": s.scoring_breakdown_json,
            "scoring_version": s.scoring_version,
            "open_positions_count": int(s.open_positions_count) if s.open_positions_count is not None else None,
            "computed_at": s.computed_at.isoformat() if s.computed_at else None,
        }

    stats = {}
    all_company_ids = set(
        [str(k) for k in signal_counts.keys()]
        + list(scores.keys())
        + [str(k) for k in last_collection.keys()]
    )
    for cid_raw in all_company_ids:
        cid = str(cid_raw)
        import uuid as _uuid
        try:
            uid = _uuid.UUID(cid)
        except ValueError:
            continue
        stats[cid] = {
            "signalsCount": signal_counts.get(uid, 0),
            "lastCollectedAt": last_collection.get(uid, None),
            "lastScoredAt": scores.get(cid, {}).get("computed_at"),
        }
        if stats[cid]["lastCollectedAt"]:
            stats[cid]["lastCollectedAt"] = stats[cid]["lastCollectedAt"].isoformat()

    return {"scores": scores, "stats": stats}
