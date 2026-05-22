import uuid
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base

class CompanySignal(Base):
    __tablename__ = "company_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_type = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=True)
    signal_type = Column(String, nullable=False, index=True)
    signal_text = Column(String, nullable=False)
    numeric_value = Column(Numeric, nullable=True)
    confidence = Column(Numeric, nullable=True)

    captured_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"), index=True,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )

    company = relationship("Company", back_populates="signals")
