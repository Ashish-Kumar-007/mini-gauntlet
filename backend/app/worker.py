import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import build_engine, build_session_factory
from app.domain.models import InventorySnapshot
from app.inventory import load_inventory
from app.repositories.jobs import (
    ClaimedJob,
    claim_next_job,
    complete_job,
    fail_job,
)
from app.scanner.checks.catalog import build_check_registry
from app.scanner.engine import Scanner

logger = logging.getLogger("mini_gauntlet.worker")


def execute_claim(
    session_factory: sessionmaker[Session],
    claim: ClaimedJob,
    worker_id: str,
    settings: Settings,
    snapshot_loader: Callable[[str | Path], InventorySnapshot] = load_inventory,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bool:
    try:
        snapshot: InventorySnapshot = snapshot_loader(settings.inventory_path)
        findings = asyncio.run(
            Scanner(
                build_check_registry(),
                concurrency=settings.scan_concurrency,
                sleep=sleep,
            ).scan(snapshot, list(claim.account_ids))
        )
        return complete_job(
            session_factory,
            claim,
            worker_id,
            findings,
            datetime.now(UTC),
        )
    except Exception as error:
        message = f"{type(error).__name__}: {error}"[:1000]
        fail_job(session_factory, claim, worker_id, message, datetime.now(UTC))
        logger.exception("Scan job failed", extra={"scan_id": str(claim.scan_id)})
        raise


def run_worker() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    worker_id = f"worker-{uuid4()}"
    try:
        while True:
            claim = claim_next_job(
                session_factory,
                worker_id,
                datetime.now(UTC),
                settings.job_lease_seconds,
            )
            if claim is None:
                time.sleep(1)
                continue
            execute_claim(session_factory, claim, worker_id, settings)
    finally:
        engine.dispose()


if __name__ == "__main__":
    run_worker()
