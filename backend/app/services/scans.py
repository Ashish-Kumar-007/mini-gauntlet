from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import ScanJob, ScanRecord
from app.domain.errors import UnknownAccountError
from app.domain.models import ScanStatus
from app.inventory import load_inventory


def create_scan(
    session: Session,
    inventory_path: str,
    account_ids: list[str] | None,
) -> ScanRecord:
    snapshot = load_inventory(inventory_path)
    available = [account.account_id for account in snapshot.accounts]
    available_ids = set(available)
    selected = available if account_ids is None else account_ids
    unknown = set(selected) - available_ids
    if unknown:
        raise UnknownAccountError(f"unknown account IDs: {', '.join(sorted(unknown))}")

    now = datetime.now(UTC)
    scan = ScanRecord(
        status=ScanStatus.RUNNING.value,
        started_at=now,
        account_ids=selected,
    )
    session.add(scan)
    session.flush()
    session.add(
        ScanJob(
            scan_id=scan.id,
            status="PENDING",
            created_at=now,
        )
    )
    session.commit()
    session.refresh(scan)
    return scan
