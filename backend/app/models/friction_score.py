import uuid
from sqlalchemy import CheckConstraint, Numeric, String, DateTime, ForeignKey, Integer, text
from sqlalchemy import Column
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
    # Raw total score = sum of all category raw_scores.
    # Preserved for backward compatibility and auditability.
    total_score = Column(Numeric, nullable=False)

    # Dominant friction type determined by HIGHEST NORMALIZED SCORE.
    # "no_signal" when no rules matched (all normalized_scores = 0).
    # "no_signal" is an INTERNAL sentinel value; API schemas translate it to null.
    # Do NOT expose "no_signal" to API consumers.
    dominant_friction_type = Column(String, nullable=False, index=True)

    # JSON breakdown containing both raw and normalized scores per category.
    # v1.0.0 format: {"reporting_fragmentation": {"score": 2.5, "matched_signals": [...]}, ...}
    # v2.0.0 format: {"categories": {"reporting_fragmentation": {"raw_score": 2.5,
    #   "max_possible": 5.5, "normalized_score": 0.4545, "matched_signals": [...]}},
    #   "confidence": {"signal_diversity": N, "contributing_signal_count": N,
    #   "evidence_breadth": N, "confidence_level": "high|medium|low|none"},
    #   "scoring_version": "2.0.0"}
    scoring_breakdown_json = Column(JSONB, nullable=False)

    scoring_version = Column(String, nullable=True)

    # Number of open positions detected for this company at scoring time.
    # Stored as Numeric for consistency, but semantically an integer count.
    open_positions_count = Column(Numeric, nullable=True)

    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    company = relationship("Company")
    hypotheses = relationship("OpportunityHypothesis", back_populates="friction_score")