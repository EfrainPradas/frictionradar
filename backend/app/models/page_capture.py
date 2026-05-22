import uuid
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class PageCapture(Base):
    __tablename__ = "page_captures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    source_url = Column(String, nullable=False)
    final_url = Column(String, nullable=True)
    title = Column(String, nullable=True)

    rendered_html = Column(Text, nullable=True)
    visible_text = Column(Text, nullable=True)
    visible_links_json = Column(Text, nullable=True)

    screenshot_path = Column(String, nullable=True)

    load_time_ms = Column(Integer, nullable=True)

    page_type = Column(String, nullable=True)
    page_type_confidence = Column(String, nullable=True)

    captured_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), default=lambda: datetime.now(timezone.utc)
    )

    extraction_status = Column(String, default="pending")
    extraction_result_json = Column(Text, nullable=True)

    company = relationship("Company", back_populates="page_captures")
