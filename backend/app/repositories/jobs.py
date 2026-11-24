from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import FindingRecord, ScanJob, ScanRecord
from app.domain.models import Finding, JobStatus, ScanStatus


@dataclass(frozen=True)
class ClaimedJob:
    job_id: UUID
    scan_id: UUID
    account_ids: tuple[str, ...]
    attempt: int


def claim_next_job(
    session_factory: sessionmaker[Session],
    worker_id: str,
    now: datetime,
    lease_seconds: int,
    max_attempts: int = 3,
) -> ClaimedJob | None:
    with session_factory.begin() as session:
        job = session.scalar(
            select(ScanJob)
            .where(
                or_(
                    ScanJob.status == JobStatus.PENDING.value,
                    and_(
                        ScanJob.status == JobStatus.RUNNING.value,
                        ScanJob.lease_expires_at <= now,
                    ),
                )
            )
            .order_by(ScanJob.created_at, ScanJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None

        scan = session.get(ScanRecord, job.scan_id)
        if scan is None:
            job.status = JobStatus.FAILED.value
            job.last_error = "Associated scan no longer exists"
            return None

        if job.attempts >= max_attempts:
            job.status = JobStatus.FAILED.value
            job.last_error = "Worker lease expired; retry limit exceeded"
            scan.status = ScanStatus.FAILED.value
            scan.finished_at = now
            scan.error_message = job.last_error
            return None

        job.status = JobStatus.RUNNING.value
        job.attempts += 1
        job.claimed_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.claimed_by = worker_id
        return ClaimedJob(
            job_id=job.id,
            scan_id=scan.id,
            account_ids=tuple(scan.account_ids),
            attempt=job.attempts,
        )


def complete_job(
    session_factory: sessionmaker[Session],
    claim: ClaimedJob,
    worker_id: str,
    findings: list[Finding],
    finished_at: datetime,
) -> bool:
    with session_factory.begin() as session:
        job = session.scalar(
            select(ScanJob)
            .where(
                ScanJob.id == claim.job_id,
                ScanJob.claimed_by == worker_id,
                ScanJob.attempts == claim.attempt,
                ScanJob.status == JobStatus.RUNNING.value,
            )
            .with_for_update()
        )
        if job is None:
            return False
        scan = session.get(ScanRecord, claim.scan_id)
        if scan is None:
            job.status = JobStatus.FAILED.value
            job.last_error = "Associated scan no longer exists"
            return False

        session.add_all(FindingRecord.from_domain(scan.id, finding) for finding in findings)
        scan.status = ScanStatus.COMPLETED.value
        scan.finished_at = finished_at
        scan.error_message = None
        job.status = JobStatus.COMPLETED.value
        job.lease_expires_at = None
        job.claimed_by = None
        job.last_error = None
        return True


def fail_job(
    session_factory: sessionmaker[Session],
    claim: ClaimedJob,
    worker_id: str,
    message: str,
    failed_at: datetime,
) -> bool:
    with session_factory.begin() as session:
        job = session.scalar(
            select(ScanJob)
            .where(
                ScanJob.id == claim.job_id,
                ScanJob.claimed_by == worker_id,
                ScanJob.attempts == claim.attempt,
                ScanJob.status == JobStatus.RUNNING.value,
            )
            .with_for_update()
        )
        if job is None:
            return False
        scan = session.get(ScanRecord, claim.scan_id)
        job.status = JobStatus.FAILED.value
        job.lease_expires_at = None
        job.last_error = message
        if scan is not None:
            scan.status = ScanStatus.FAILED.value
            scan.finished_at = failed_at
            scan.error_message = message
        return True
