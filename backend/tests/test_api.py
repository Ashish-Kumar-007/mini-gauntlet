from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.models import FindingRecord, ScanRecord
from app.main import create_app


@pytest.fixture
def api() -> tuple[TestClient, object]:
    inventory = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
    application = create_app(
        Settings(database_url="sqlite:///:memory:", inventory_path=str(inventory))
    )
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as client:
        yield client, application


def test_health_and_check_catalog(api: tuple[TestClient, object]) -> None:
    client, _ = api
    assert client.get("/api/health").json() == {"status": "ok"}
    checks_response = client.get("/api/checks")
    assert checks_response.status_code == 200
    assert len(checks_response.json()) == 10
    assert checks_response.json()[0]["check_id"] == "AWS-EC2-01"


def test_create_scan_for_all_or_selected_accounts_and_validate_request(
    api: tuple[TestClient, object],
) -> None:
    client, _ = api
    all_accounts = client.post("/api/scans")
    assert all_accounts.status_code == 202
    assert all_accounts.json()["status"] == "RUNNING"
    assert len(all_accounts.json()["account_ids"]) == 4

    selected = client.post("/api/scans", json={"account_ids": ["123456789012"]})
    assert selected.status_code == 202
    assert selected.json()["account_ids"] == ["123456789012"]

    assert client.post("/api/scans", json={"account_ids": []}).status_code == 422
    assert client.post("/api/scans", json={"account_ids": ["not-an-account"]}).status_code == 422


def test_scan_listing_detail_filters_and_ordering(api: tuple[TestClient, object]) -> None:
    client, application = api
    created = client.post(
        "/api/scans", json={"account_ids": ["123456789012", "210987654321"]}
    ).json()
    scan_id = UUID(created["id"])
    started_at = datetime.fromisoformat(created["started_at"].replace("Z", "+00:00"))

    with application.state.session_factory() as session:
        session.add_all(
            [
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-S3-01",
                    title="Bucket check",
                    provider="aws",
                    account_id="123456789012",
                    region="us-east-1",
                    resource_id="bucket-b",
                    status="FAIL",
                    severity="HIGH",
                    details="public",
                ),
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-EC2-01",
                    title="Network check",
                    provider="aws",
                    account_id="123456789012",
                    region="us-east-1",
                    resource_id="sg-1",
                    status="FAIL",
                    severity="CRITICAL",
                    details="open",
                ),
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-IAM-01",
                    title="MFA check",
                    provider="aws",
                    account_id="123456789012",
                    region=None,
                    resource_id="alice",
                    status="FAIL",
                    severity="HIGH",
                    details="MFA missing",
                ),
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-IAM-01",
                    title="MFA check",
                    provider="aws",
                    account_id="123456789012",
                    region=None,
                    resource_id="bob",
                    status="FAIL",
                    severity="HIGH",
                    details="MFA missing",
                ),
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-IAM-01",
                    title="MFA check",
                    provider="aws",
                    account_id="210987654321",
                    region=None,
                    resource_id=None,
                    status="CANNOT_SCAN",
                    severity="HIGH",
                    details="AccessDenied",
                ),
                FindingRecord(
                    scan_id=scan_id,
                    check_id="AWS-RDS-01",
                    title="RDS check",
                    provider="aws",
                    account_id="123456789012",
                    region="us-east-1",
                    resource_id="db-1",
                    status="PASS",
                    severity="HIGH",
                    details="private",
                ),
            ]
        )
        scan = session.get(ScanRecord, scan_id)
        scan.status = "COMPLETED"
        scan.finished_at = started_at + timedelta(seconds=2)
        session.commit()

    scan_list = client.get("/api/scans").json()
    assert scan_list[0]["id"] == str(scan_id)
    assert scan_list[0]["counts_by_status"] == {"PASS": 1, "FAIL": 4, "CANNOT_SCAN": 1}
    assert scan_list[0]["score"] == 20.0

    detail_response = client.get(f"/api/scans/{scan_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["fail_counts_by_severity"] == {
        "CRITICAL": 1,
        "HIGH": 3,
        "MEDIUM": 0,
        "LOW": 0,
    }
    assert detail["account_scores"] == [
        {"account_id": "123456789012", "score": 20.0},
        {"account_id": "210987654321", "score": None},
    ]

    page_one = client.get(
        f"/api/scans/{scan_id}/findings", params={"status": "fail", "page_size": 1}
    ).json()
    page_two = client.get(
        f"/api/scans/{scan_id}/findings", params={"status": "FAIL", "page": 2, "page_size": 1}
    ).json()
    page_three = client.get(
        f"/api/scans/{scan_id}/findings", params={"status": "FAIL", "page": 3, "page_size": 1}
    ).json()
    assert page_one["items"][0]["check_id"] == "AWS-EC2-01"
    assert page_two["items"][0]["resource_id"] == "alice"
    assert page_three["items"][0]["resource_id"] == "bob"
    assert page_one["total"] == 4
    assert page_two["page"] == 2

    cannot_scan = client.get(
        f"/api/scans/{scan_id}/findings",
        params={"provider": "AWS", "account_id": "210987654321", "status": "cannot_scan"},
    ).json()
    assert [item["check_id"] for item in cannot_scan["items"]] == ["AWS-IAM-01"]
    assert (
        client.get(f"/api/scans/{scan_id}/findings", params={"page_size": 101}).status_code == 422
    )
    assert (
        client.get(f"/api/scans/{scan_id}/findings", params={"status": "UNKNOWN"}).status_code
        == 422
    )


def test_unknown_scan_returns_404(api: tuple[TestClient, object]) -> None:
    client, _ = api
    unknown = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/scans/{unknown}").status_code == 404
    assert client.get(f"/api/scans/{unknown}/findings").status_code == 404
