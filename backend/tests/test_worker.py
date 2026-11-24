from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.base import Base
from app.db.models import FindingRecord, ScanJob, ScanRecord
from app.db.session import build_engine, build_session_factory
from app.domain.errors import InventoryLoadError
from app.domain.models import JobStatus, ScanStatus
from app.repositories.jobs import claim_next_job, complete_job
from app.worker import execute_claim


@pytest.fixture
def worker_db():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield build_session_factory(engine)
    engine.dispose()


def _create_scan(session_factory, account_ids: list[str] | None = None) -> ScanRecord:
    now = datetime.now(UTC)
    scan = ScanRecord(
        status=ScanStatus.RUNNING.value,
        started_at=now,
        account_ids=account_ids or ["123456789012"],
    )
    with session_factory.begin() as session:
        session.add(scan)
        session.flush()
        session.add(
            ScanJob(
                scan_id=scan.id,
                status=JobStatus.PENDING.value,
                created_at=now,
            )
        )
    return scan


def test_worker_claims_scans_persists_findings_and_completes(worker_db) -> None:
    scan = _create_scan(worker_db)
    now = datetime.now(UTC)
    claim = claim_next_job(worker_db, "worker-a", now, lease_seconds=30)
    assert claim is not None
    assert claim.scan_id == scan.id

    inventory = Path(__file__).resolve().parents[1] / "data" / "inventory.json"

    async def no_wait(_: float) -> None:
        return None

    completed = execute_claim(
        worker_db,
        claim,
        "worker-a",
        Settings(database_url="sqlite:///:memory:", inventory_path=str(inventory)),
        sleep=no_wait,
    )
    assert completed is True
    with worker_db() as session:
        persisted_scan = session.get(ScanRecord, scan.id)
        job = session.query(ScanJob).filter_by(scan_id=scan.id).one()
        findings = session.query(FindingRecord).filter_by(scan_id=scan.id).all()
        assert persisted_scan.status == ScanStatus.COMPLETED.value
        assert job.status == JobStatus.COMPLETED.value
        assert len(findings) == 24

    assert complete_job(worker_db, claim, "worker-a", [], datetime.now(UTC)) is False


def test_worker_marks_scan_failed_when_inventory_cannot_be_loaded(
    worker_db, tmp_path: Path
) -> None:
    scan = _create_scan(worker_db)
    worker_id = "worker-failure"
    claim = claim_next_job(worker_db, worker_id, datetime.now(UTC), lease_seconds=30)
    assert claim is not None

    with pytest.raises(InventoryLoadError, match="Inventory file"):
        execute_claim(
            worker_db,
            claim,
            worker_id,
            Settings(
                database_url="sqlite:///:memory:",
                inventory_path=str(tmp_path / "missing.json"),
            ),
        )

    with worker_db() as session:
        persisted_scan = session.get(ScanRecord, scan.id)
        job = session.query(ScanJob).filter_by(scan_id=scan.id).one()
        assert persisted_scan.status == ScanStatus.FAILED.value
        assert job.status == JobStatus.FAILED.value
        assert "InventoryLoadError" in persisted_scan.error_message


def test_expired_job_is_reclaimed_with_fencing_and_attempt_limit(worker_db) -> None:
    scan = _create_scan(worker_db)
    start = datetime.now(UTC)
    first = claim_next_job(worker_db, "worker-a", start, lease_seconds=1, max_attempts=2)
    assert first is not None and first.attempt == 1

    second = claim_next_job(
        worker_db,
        "worker-b",
        start + timedelta(seconds=2),
        lease_seconds=1,
        max_attempts=2,
    )
    assert second is not None and second.attempt == 2
    assert complete_job(worker_db, first, "worker-a", [], start + timedelta(seconds=2)) is False

    assert (
        claim_next_job(
            worker_db,
            "worker-c",
            start + timedelta(seconds=4),
            lease_seconds=1,
            max_attempts=2,
        )
        is None
    )
    with worker_db() as session:
        persisted_scan = session.get(ScanRecord, scan.id)
        job = session.query(ScanJob).filter_by(scan_id=scan.id).one()
        assert persisted_scan.status == ScanStatus.FAILED.value
        assert job.status == JobStatus.FAILED.value
