import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class OpportunityHypothesis(Base):
    __tablename__ = "opportunity_hypotheses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    friction_score_id = Column(UUID(as_uuid=True), ForeignKey("friction_scores.id", ondelete="SET NULL"), nullable=True)
    summary = Column(String, nullable=False)
    friction_type = Column(String, nullable=False, index=True)
    suggested_opportunity = Column(String, nullable=False)
    rationale_json = Column(JSONB, nullable=True)
    llm_confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    company = relationship("Company")
    friction_score = relationship("FrictionScore", back_populates="hypotheses")
