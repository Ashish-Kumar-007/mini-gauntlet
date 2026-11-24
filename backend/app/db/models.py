import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.models import Finding

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class ScanRecord(Base):
    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_scans_status",
        ),
        Index("ix_scans_started_at", "started_at"),
        Index("ix_scans_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_ids: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[list["FindingRecord"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    job: Mapped["ScanJob | None"] = relationship(
        back_populates="scan", cascade="all, delete-orphan", uselist=False
    )


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_scan_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_scan_jobs_attempts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    scan: Mapped[ScanRecord] = relationship(back_populates="job")


class FindingRecord(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'CANNOT_SCAN')",
            name="ck_findings_status",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="ck_findings_severity",
        ),
        CheckConstraint(
            "provider IN ('aws', 'azure', 'gcp')",
            name="ck_findings_provider",
        ),
        Index(
            "uq_findings_resource_identity",
            "scan_id",
            "check_id",
            "provider",
            "account_id",
            "resource_id",
            unique=True,
            sqlite_where=text("resource_id IS NOT NULL"),
            postgresql_where=text("resource_id IS NOT NULL"),
        ),
        Index(
            "uq_findings_collection_error_identity",
            "scan_id",
            "check_id",
            "provider",
            "account_id",
            unique=True,
            sqlite_where=text("resource_id IS NULL"),
            postgresql_where=text("resource_id IS NULL"),
        ),
        Index("ix_findings_scan_status_severity", "scan_id", "status", "severity"),
        Index("ix_findings_scan_provider_account", "scan_id", "provider", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    check_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(128))
    resource_id: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    scan: Mapped[ScanRecord] = relationship(back_populates="findings")

    @classmethod
    def from_domain(cls, scan_id: uuid.UUID, finding: Finding) -> "FindingRecord":
        return cls(
            scan_id=scan_id,
            check_id=finding.check_id,
            title=finding.title,
            provider=finding.provider.value,
            account_id=finding.account_id,
            region=finding.region,
            resource_id=finding.resource_id,
            status=finding.status.value,
            severity=finding.severity.value,
            details=finding.details,
        )
