from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Provider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class FindingStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CANNOT_SCAN = "CANNOT_SCAN"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ScanStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Account:
    provider: Provider
    account_id: str
    name: str | None
    simulated_latency_ms: int
    errors: Mapping[str, str]
    resources: Mapping[str, list[object]]


@dataclass(frozen=True)
class InventorySnapshot:
    snapshot_taken_at: datetime
    accounts: tuple[Account, ...]


@dataclass(frozen=True)
class EvaluationContext:
    provider: Provider
    account_id: str
    region: str | None
    snapshot_taken_at: datetime


@dataclass(frozen=True)
class EvaluationOutcome:
    status: FindingStatus
    details: str


@dataclass(frozen=True)
class Finding:
    check_id: str
    title: str
    provider: Provider
    account_id: str
    region: str | None
    resource_id: str | None
    status: FindingStatus
    severity: Severity
    details: str
