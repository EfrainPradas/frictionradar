"""Denormalized snapshot of a company's pain verdict + pgvector embedding.

Populated by `scripts/nightly_smart_match_refresh.py`; consumed by
`app/services/smart_match_engine.py` to rank companies for a candidate.
"""
from sqlalchemy import Column, String, Numeric, DateTime, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone

from app.db.base import Base


EMBEDDING_DIM = 1536  # text-embedding-3-small


class SmartMatchCache(Base):
    __tablename__ = "smart_match_cache"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain = Column(Text, nullable=False)

    friction_score = Column(Numeric, nullable=True)
    dominant_friction_type = Column(Text, nullable=True)
    diagnostic_state = Column(Text, nullable=True)
    main_pain = Column(Text, nullable=True)
    where_pain_lives = Column(Text, nullable=True)
    what_the_company_needs = Column(Text, nullable=True)
    recommended_positioning = Column(Text, nullable=True)

    confidence = Column(Text, nullable=True)
    eligibility_gate = Column(Text, nullable=True)

    evaluation_kpis = Column(JSONB, nullable=True)
    inferred_sector = Column(Text, nullable=True)

    pain_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)

    refreshed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    refresh_run_id = Column(Text, nullable=True)
