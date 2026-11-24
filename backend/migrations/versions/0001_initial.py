"""Initial scan, job, and finding tables.

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    account_ids_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "scans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_ids", account_ids_type, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_scans_status",
        ),
    )
    op.create_index("ix_scans_started_at", "scans", ["started_at"])
    op.create_index("ix_scans_status", "scans", ["status"])

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_scan_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_scan_jobs_attempts"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("check_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("resource_id", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'CANNOT_SCAN')",
            name="ck_findings_status",
        ),
        sa.CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="ck_findings_severity",
        ),
        sa.CheckConstraint(
            "provider IN ('aws', 'azure', 'gcp')",
            name="ck_findings_provider",
        ),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_findings_resource_identity",
        "findings",
        ["scan_id", "check_id", "provider", "account_id", "resource_id"],
        unique=True,
        postgresql_where=sa.text("resource_id IS NOT NULL"),
        sqlite_where=sa.text("resource_id IS NOT NULL"),
    )
    op.create_index(
        "uq_findings_collection_error_identity",
        "findings",
        ["scan_id", "check_id", "provider", "account_id"],
        unique=True,
        postgresql_where=sa.text("resource_id IS NULL"),
        sqlite_where=sa.text("resource_id IS NULL"),
    )
    op.create_index(
        "ix_findings_scan_status_severity",
        "findings",
        ["scan_id", "status", "severity"],
    )
    op.create_index(
        "ix_findings_scan_provider_account",
        "findings",
        ["scan_id", "provider", "account_id"],
    )


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("scan_jobs")
    op.drop_index("ix_scans_status", table_name="scans")
    op.drop_index("ix_scans_started_at", table_name="scans")
    op.drop_table("scans")
