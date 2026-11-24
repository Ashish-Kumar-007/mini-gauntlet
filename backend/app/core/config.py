import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://mini:mini@db:5432/mini_gauntlet"
    inventory_path: str = "data/inventory.json"
    scan_concurrency: int = 4
    job_lease_seconds: int = 30
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        concurrency = int(os.getenv("SCAN_CONCURRENCY", "4"))
        if concurrency < 1:
            raise ValueError("SCAN_CONCURRENCY must be at least one")
        lease_seconds = int(os.getenv("JOB_LEASE_SECONDS", "30"))
        if lease_seconds < 1:
            raise ValueError("JOB_LEASE_SECONDS must be at least one")
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            inventory_path=os.getenv("INVENTORY_PATH", cls.inventory_path),
            scan_concurrency=concurrency,
            job_lease_seconds=lease_seconds,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
