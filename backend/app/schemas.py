from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CheckCatalogItem(BaseModel):
    check_id: str
    title: str
    provider: str
    severity: str
    collection: str
    resource_id_field: str


class ScanCreateRequest(BaseModel):
    account_ids: list[str] | None = Field(default=None, min_length=1)

    @field_validator("account_ids")
    @classmethod
    def account_ids_are_nonempty_and_unique(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (
            any(not account_id.strip() for account_id in value) or len(set(value)) != len(value)
        ):
            raise ValueError("account IDs must be non-empty and unique")
        return value


class ScanAccepted(BaseModel):
    id: UUID
    status: str
    started_at: datetime
    account_ids: list[str]


class StatusCounts(BaseModel):
    PASS: int = 0
    FAIL: int = 0
    CANNOT_SCAN: int = 0


class ScanListItem(ScanAccepted):
    finished_at: datetime | None
    score: float | None
    counts_by_status: StatusCounts


class AccountScore(BaseModel):
    account_id: str
    score: float | None


class ScanDetail(ScanListItem):
    fail_counts_by_severity: dict[str, int]
    account_scores: list[AccountScore]
    error_message: str | None


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    check_id: str
    title: str
    provider: str
    account_id: str
    region: str | None
    resource_id: str | None
    status: str
    severity: str
    details: str


class FindingsPage(BaseModel):
    items: list[FindingResponse]
    total: int
    page: int
    page_size: int
