import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class CompanyJobRole(Base):
    __tablename__ = "company_job_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_url = Column(String, nullable=True)
    role_title = Column(String, nullable=False)
    role_location = Column(String, nullable=True)
    role_department = Column(String, nullable=True)
    role_description = Column(Text, nullable=True)
    functional_area = Column(String, nullable=True, index=True)
    functional_area_confidence = Column(String, nullable=True)

    discovered_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )

    company = relationship("Company", back_populates="job_roles")
    role_signals = relationship(
        "CompanyRoleSignal", back_populates="job_role", cascade="all, delete-orphan"
    )


class CompanyRoleSignal(Base):
    __tablename__ = "company_role_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    job_role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_job_roles.id", ondelete="CASCADE"),
        nullable=True,
    )
    signal_type = Column(String, nullable=False, index=True)
    signal_text = Column(String, nullable=False)
    functional_area = Column(String, nullable=True, index=True)
    confidence = Column(Numeric, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )

    job_role = relationship("CompanyJobRole", back_populates="role_signals")
    company = relationship("Company", back_populates="role_signals")


class HiringPattern(Base):
    __tablename__ = "hiring_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    top_functional_areas = Column(String, nullable=True)
    top_capability_themes = Column(String, nullable=True)

    total_roles_found = Column(Numeric, default=0)
    unique_functions_found = Column(Numeric, default=0)

    generated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("now()"),
    )

    company = relationship("Company", back_populates="hiring_patterns")
