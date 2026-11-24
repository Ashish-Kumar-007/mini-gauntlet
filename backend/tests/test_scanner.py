import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.errors import InvalidResource, InventoryLoadError
from app.domain.models import (
    Account,
    EvaluationContext,
    Finding,
    FindingStatus,
    InventorySnapshot,
    Provider,
    Severity,
)
from app.domain.scoring import posture_score
from app.inventory import load_inventory
from app.scanner.checks.aws_s3 import PUBLIC_ACCESS_FLAGS, AwsS3PublicAccessCheck
from app.scanner.checks.catalog import build_check_registry
from app.scanner.engine import Scanner
from app.scanner.registry import CheckRegistry


def _snapshot(accounts: tuple[Account, ...]) -> InventorySnapshot:
    return InventorySnapshot(
        snapshot_taken_at=datetime(2026, 10, 1, tzinfo=UTC),
        accounts=accounts,
    )


def _account(
    account_id: str,
    *,
    resources: dict[str, list[object]] | None = None,
    errors: dict[str, str] | None = None,
    latency: int = 0,
) -> Account:
    return Account(
        provider=Provider.AWS,
        account_id=account_id,
        name=None,
        simulated_latency_ms=latency,
        errors=errors or {},
        resources=resources or {},
    )


def _s3_bucket(**overrides: object) -> dict[str, object]:
    config = dict.fromkeys(PUBLIC_ACCESS_FLAGS, True)
    return {
        "name": "bucket",
        "public_access_block": config | overrides,
        "region": "us-east-1",
    }


def _registry() -> CheckRegistry:
    registry = CheckRegistry()
    registry.register(AwsS3PublicAccessCheck())
    return registry


def test_s3_check_passes_only_when_all_flags_are_true() -> None:
    check = AwsS3PublicAccessCheck()
    context = EvaluationContext(
        provider=Provider.AWS,
        account_id="account",
        region="us-east-1",
        snapshot_taken_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert check.evaluate(_s3_bucket(), context).status is FindingStatus.PASS
    assert check.evaluate(_s3_bucket(block_public_acls=False), context).status is FindingStatus.FAIL


@pytest.mark.parametrize(
    "resource",
    [
        {"name": "bucket", "public_access_block": None},
        {"name": "bucket", "public_access_block": {"block_public_acls": "true"}},
    ],
)
def test_s3_check_rejects_malformed_configuration(resource: dict[str, object]) -> None:
    check = AwsS3PublicAccessCheck()
    context = EvaluationContext(
        provider=Provider.AWS,
        account_id="account",
        region=None,
        snapshot_taken_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    with pytest.raises(InvalidResource, match="public_access_block"):
        check.evaluate(resource, context)


def test_registry_rejects_duplicate_check_ids() -> None:
    registry = CheckRegistry()
    registry.register(AwsS3PublicAccessCheck())

    with pytest.raises(ValueError, match="duplicate check ID"):
        registry.register(AwsS3PublicAccessCheck())


def test_collection_error_and_malformed_resources_become_cannot_scan(
    caplog: pytest.LogCaptureFixture,
) -> None:
    account = _account(
        "account",
        resources={"s3_buckets": [_s3_bucket(), {"name": "broken", "public_access_block": None}]},
    )
    scanner = Scanner(_registry())

    with caplog.at_level(logging.WARNING):
        findings = asyncio.run(scanner.scan(_snapshot((account,))))
    assert {finding.resource_id: finding.status for finding in findings} == {
        "bucket": FindingStatus.PASS,
        "broken": FindingStatus.CANNOT_SCAN,
    }
    assert "Malformed resource" in caplog.text

    denied = _account("denied", errors={"s3_buckets": "AccessDenied"})
    denied_findings = asyncio.run(Scanner(_registry()).scan(_snapshot((denied,))))
    assert len(denied_findings) == 1
    assert denied_findings[0].status is FindingStatus.CANNOT_SCAN
    assert denied_findings[0].resource_id is None
    assert "AccessDenied" in denied_findings[0].details


def test_missing_collection_produces_no_findings() -> None:
    findings = asyncio.run(Scanner(_registry()).scan(_snapshot((_account("account"),))))
    assert findings == []


def test_scanner_respects_account_concurrency_limit() -> None:
    active = 0
    max_active = 0

    async def tracked_sleep(_: float) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1

    accounts = tuple(_account(str(index), latency=1) for index in range(7))
    asyncio.run(Scanner(_registry(), concurrency=3, sleep=tracked_sleep).scan(_snapshot(accounts)))
    assert max_active == 3


def test_scanner_respects_each_account_simulated_latency() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
    snapshot = load_inventory(path)
    observed_delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        observed_delays.append(delay)

    asyncio.run(Scanner(build_check_registry(), sleep=record_sleep).scan(snapshot))
    assert sorted(observed_delays) == [1.0, 1.5, 2.5, 3.0]


def test_scoring_excludes_cannot_scan_and_returns_null_without_evaluable_findings() -> None:
    def finding(status: FindingStatus) -> Finding:
        return Finding(
            check_id="AWS-S3-01",
            title="title",
            provider=Provider.AWS,
            account_id="account",
            region=None,
            resource_id=None,
            status=status,
            severity=Severity.HIGH,
            details="details",
        )

    assert (
        posture_score(
            [
                finding(FindingStatus.PASS),
                finding(FindingStatus.FAIL),
                finding(FindingStatus.CANNOT_SCAN),
            ]
        )
        == 50
    )
    assert posture_score([finding(FindingStatus.CANNOT_SCAN)]) is None
    assert posture_score(
        [
            finding(FindingStatus.PASS),
            finding(FindingStatus.PASS),
            finding(FindingStatus.FAIL),
        ]
    ) == Decimal("66.7")


def test_supplied_inventory_loads_without_modifying_fixture() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
    snapshot = load_inventory(path)
    assert snapshot.snapshot_taken_at == datetime(2026, 10, 1, tzinfo=UTC)
    assert len(snapshot.accounts) == 4
    assert snapshot.accounts[-1].provider is Provider.GCP


def test_supplied_inventory_scan_is_complete_and_deterministic() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
    snapshot = load_inventory(path)

    async def no_wait(_: float) -> None:
        return None

    scanner = Scanner(build_check_registry(), sleep=no_wait)
    findings = asyncio.run(scanner.scan(snapshot))
    repeated_findings = asyncio.run(scanner.scan(snapshot))
    counts = {status: sum(item.status is status for item in findings) for status in FindingStatus}

    assert len(findings) == 49
    assert counts == {
        FindingStatus.PASS: 27,
        FindingStatus.FAIL: 17,
        FindingStatus.CANNOT_SCAN: 5,
    }
    assert posture_score(findings) == Decimal("61.4")
    assert repeated_findings == findings
    assert any(
        item.check_id == "AWS-EC2-01"
        and item.resource_id == "sg-0b1c2d3e4f5a60002"
        and item.status is FindingStatus.CANNOT_SCAN
        for item in findings
    )
    assert (
        sum(
            item.account_id == "210987654321" and item.status is FindingStatus.CANNOT_SCAN
            for item in findings
        )
        == 4
    )


def test_inventory_rejects_timezone_naive_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text('{"snapshot_taken_at":"2026-10-01T00:00:00","accounts":[]}', encoding="utf-8")
    with pytest.raises(InventoryLoadError, match="timezone"):
        load_inventory(path)
