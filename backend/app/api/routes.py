from collections import Counter, defaultdict
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import FindingRecord, ScanRecord
from app.domain.errors import InventoryLoadError, UnknownAccountError
from app.domain.models import Finding, FindingStatus, Provider, Severity
from app.domain.scoring import posture_score
from app.schemas import (
    AccountScore,
    CheckCatalogItem,
    FindingResponse,
    FindingsPage,
    ScanAccepted,
    ScanCreateRequest,
    ScanDetail,
    ScanListItem,
    StatusCounts,
)
from app.services.scans import create_scan

router = APIRouter(prefix="/api")
STATUS_ORDER = case(
    (FindingRecord.status == FindingStatus.FAIL.value, 0),
    (FindingRecord.status == FindingStatus.CANNOT_SCAN.value, 1),
    else_=2,
)
SEVERITY_ORDER = case(
    (FindingRecord.severity == Severity.CRITICAL.value, 0),
    (FindingRecord.severity == Severity.HIGH.value, 1),
    (FindingRecord.severity == Severity.MEDIUM.value, 2),
    else_=3,
)


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def _find_scan(session: Session, scan_id: UUID) -> ScanRecord:
    scan = session.get(ScanRecord, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


def _validate_filter(value: str | None, allowed: set[str], field: str) -> None:
    if value is not None and value.upper() not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid {field} filter")


def _finding_domain(record: FindingRecord) -> Finding:
    return Finding(
        check_id=record.check_id,
        title=record.title,
        provider=Provider(record.provider),
        account_id=record.account_id,
        region=record.region,
        resource_id=record.resource_id,
        status=FindingStatus(record.status),
        severity=Severity(record.severity),
        details=record.details,
    )


def _api_score(score: Decimal | None) -> float | None:
    return float(score) if score is not None else None


def _counts_by_scan(session: Session, scan_ids: list[UUID]) -> dict[UUID, StatusCounts]:
    counts: dict[UUID, Counter[str]] = defaultdict(Counter)
    if scan_ids:
        rows = session.execute(
            select(FindingRecord.scan_id, FindingRecord.status, func.count())
            .where(FindingRecord.scan_id.in_(scan_ids))
            .group_by(FindingRecord.scan_id, FindingRecord.status)
        )
        for scan_id, finding_status, count in rows:
            counts[scan_id][finding_status] = count
    return {
        scan_id: StatusCounts(
            PASS=counts[scan_id][FindingStatus.PASS.value],
            FAIL=counts[scan_id][FindingStatus.FAIL.value],
            CANNOT_SCAN=counts[scan_id][FindingStatus.CANNOT_SCAN.value],
        )
        for scan_id in scan_ids
    }


def _score_for_scan(session: Session, scan_id: UUID) -> Decimal | None:
    records = session.scalars(select(FindingRecord).where(FindingRecord.scan_id == scan_id))
    return posture_score(_finding_domain(record) for record in records)


def _scan_list_item(scan: ScanRecord, counts: StatusCounts, score: Decimal | None) -> ScanListItem:
    return ScanListItem(
        id=scan.id,
        status=scan.status,
        started_at=scan.started_at,
        finished_at=scan.finished_at,
        account_ids=scan.account_ids,
        score=_api_score(score),
        counts_by_status=counts,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/checks", response_model=list[CheckCatalogItem])
def checks(request: Request) -> list[CheckCatalogItem]:
    registry = request.app.state.check_registry
    return [
        CheckCatalogItem(
            check_id=check.check_id,
            title=check.title,
            provider=check.provider.value,
            severity=check.severity.value,
            collection=check.collection,
            resource_id_field=check.resource_id_field,
        )
        for check in registry.catalog()
    ]


@router.post("/scans", response_model=ScanAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_scan(
    request: Request,
    session: SessionDependency,
    body: ScanCreateRequest | None = None,
) -> ScanAccepted:
    account_ids = body.account_ids if body else None
    try:
        scan = create_scan(session, request.app.state.settings.inventory_path, account_ids)
    except UnknownAccountError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except InventoryLoadError as error:
        raise HTTPException(
            status_code=500, detail="Configured inventory cannot be loaded"
        ) from error
    return ScanAccepted(
        id=scan.id,
        status=scan.status,
        started_at=scan.started_at,
        account_ids=scan.account_ids,
    )


@router.get("/scans", response_model=list[ScanListItem])
def list_scans(session: SessionDependency) -> list[ScanListItem]:
    scans = list(session.scalars(select(ScanRecord).order_by(ScanRecord.started_at.desc())))
    counts = _counts_by_scan(session, [scan.id for scan in scans])
    return [
        _scan_list_item(scan, counts[scan.id], _score_for_scan(session, scan.id)) for scan in scans
    ]


@router.get("/scans/{scan_id}", response_model=ScanDetail)
def scan_detail(scan_id: UUID, session: SessionDependency) -> ScanDetail:
    scan = _find_scan(session, scan_id)
    counts = _counts_by_scan(session, [scan.id])[scan.id]
    records = list(session.scalars(select(FindingRecord).where(FindingRecord.scan_id == scan.id)))
    scores: dict[str, list[Finding]] = {account_id: [] for account_id in scan.account_ids}
    severity_counts: Counter[str] = Counter()
    for record in records:
        finding = _finding_domain(record)
        scores.setdefault(record.account_id, []).append(finding)
        if finding.status is FindingStatus.FAIL:
            severity_counts[finding.severity.value] += 1

    score = posture_score(_finding_domain(record) for record in records)
    return ScanDetail(
        id=scan.id,
        status=scan.status,
        started_at=scan.started_at,
        finished_at=scan.finished_at,
        account_ids=scan.account_ids,
        score=_api_score(score),
        counts_by_status=counts,
        fail_counts_by_severity={
            severity.value: severity_counts[severity.value] for severity in Severity
        },
        account_scores=[
            AccountScore(account_id=account_id, score=_api_score(posture_score(findings)))
            for account_id, findings in sorted(scores.items())
        ],
        error_message=scan.error_message,
    )


@router.get("/scans/{scan_id}/findings", response_model=FindingsPage)
def scan_findings(
    scan_id: UUID,
    session: SessionDependency,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity_filter: str | None = None,
    provider_filter: str | None = None,
    account_id: str | None = None,
    check_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FindingsPage:
    _find_scan(session, scan_id)
    _validate_filter(
        status_filter,
        {finding_status.value for finding_status in FindingStatus},
        "status",
    )
    _validate_filter(severity_filter, {severity.value for severity in Severity}, "severity")
    _validate_filter(provider_filter, {provider.value.upper() for provider in Provider}, "provider")
    query = select(FindingRecord).where(FindingRecord.scan_id == scan_id)
    count_query = (
        select(func.count()).select_from(FindingRecord).where(FindingRecord.scan_id == scan_id)
    )
    filters: list[tuple[object, str | None]] = [
        (FindingRecord.status, status_filter),
        (FindingRecord.severity, severity_filter),
        (FindingRecord.provider, provider_filter),
        (FindingRecord.account_id, account_id),
        (FindingRecord.check_id, check_id),
    ]
    for column, value in filters:
        if value is not None:
            query = query.where(func.lower(column) == value.lower())
            count_query = count_query.where(func.lower(column) == value.lower())

    total = session.scalar(count_query) or 0
    records = session.scalars(
        query.order_by(
            STATUS_ORDER,
            SEVERITY_ORDER,
            FindingRecord.check_id,
            FindingRecord.resource_id.asc().nulls_last(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return FindingsPage(
        items=[FindingResponse.model_validate(record) for record in records],
        total=total,
        page=page,
        page_size=page_size,
    )
