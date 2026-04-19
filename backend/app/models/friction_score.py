import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class FrictionScore(Base):
    __tablename__ = "friction_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_score = Column(Numeric, nullable=False)
    dominant_friction_type = Column(String, nullable=False, index=True)
    scoring_breakdown_json = Column(JSONB, nullable=False)
    scoring_version = Column(String, nullable=True)
    open_positions_count = Column(Numeric, nullable=True)
    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    company = relationship("Company")
    hypotheses = relationship("OpportunityHypothesis", back_populates="friction_score")
