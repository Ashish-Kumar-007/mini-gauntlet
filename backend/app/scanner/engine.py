import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping

from app.domain.errors import InvalidResource, UnknownAccountError
from app.domain.models import (
    Account,
    EvaluationContext,
    Finding,
    FindingStatus,
    InventorySnapshot,
)
from app.scanner.registry import CheckRegistry, SecurityCheck


class Scanner:
    def __init__(
        self,
        registry: CheckRegistry,
        concurrency: int = 4,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least one")
        self._registry = registry
        self._concurrency = concurrency
        self._sleep = sleep
        self._logger = logger or logging.getLogger(__name__)

    async def scan(
        self, snapshot: InventorySnapshot, account_ids: list[str] | None = None
    ) -> list[Finding]:
        if account_ids is None:
            accounts = list(snapshot.accounts)
        else:
            requested = set(account_ids)
            available = {account.account_id for account in snapshot.accounts}
            unknown = requested - available
            if unknown:
                raise UnknownAccountError(f"unknown account IDs: {', '.join(sorted(unknown))}")
            accounts = [account for account in snapshot.accounts if account.account_id in requested]
            if not accounts:
                raise ValueError("at least one account must be selected")

        if not accounts:
            return []

        worker_count = min(self._concurrency, len(accounts))
        queue: asyncio.Queue[Account | None] = asyncio.Queue(maxsize=worker_count)
        findings: list[Finding] = []

        async def account_worker() -> None:
            while True:
                account = await queue.get()
                try:
                    if account is None:
                        return
                    findings.extend(await self._scan_account(account, snapshot))
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as task_group:
            for _ in range(worker_count):
                task_group.create_task(account_worker())
            for account in accounts:
                await queue.put(account)
            for _ in range(worker_count):
                await queue.put(None)
            await queue.join()

        return sorted(
            findings,
            key=lambda finding: (
                finding.provider.value,
                finding.account_id,
                finding.check_id,
                finding.resource_id or "",
                finding.status.value,
            ),
        )

    async def _scan_account(self, account: Account, snapshot: InventorySnapshot) -> list[Finding]:
        if account.simulated_latency_ms:
            await self._sleep(account.simulated_latency_ms / 1000)

        findings: list[Finding] = []
        for check in self._registry.checks_for(account.provider):
            if check.collection in account.errors:
                findings.append(self._collection_error_finding(account, check))
                continue

            resources = account.resources.get(check.collection)
            if resources is None:
                continue

            for resource in resources:
                findings.append(self._evaluate_resource(account, snapshot, check, resource))
        return findings

    def _collection_error_finding(self, account: Account, check: SecurityCheck) -> Finding:
        error_code = account.errors[check.collection]
        return Finding(
            check_id=check.check_id,
            title=check.title,
            provider=account.provider,
            account_id=account.account_id,
            region=None,
            resource_id=None,
            status=FindingStatus.CANNOT_SCAN,
            severity=check.severity,
            details=f"Collection could not be scanned; error code: {error_code}",
        )

    def _evaluate_resource(
        self,
        account: Account,
        snapshot: InventorySnapshot,
        check: SecurityCheck,
        value: object,
    ) -> Finding:
        resource: Mapping[str, object] | None = value if isinstance(value, dict) else None
        resource_id: str | None = None
        region: str | None = None
        error: str | None = None

        if resource is None:
            error = "resource must be an object"
        else:
            candidate_id = resource.get(check.resource_id_field)
            if not isinstance(candidate_id, str) or not candidate_id.strip():
                error = f"{check.resource_id_field} must be a non-empty string"
            else:
                resource_id = candidate_id

            candidate_region = resource.get("region")
            if candidate_region is not None and not isinstance(candidate_region, str):
                error = "region must be a string or null"
            else:
                region = candidate_region

        context = EvaluationContext(
            provider=account.provider,
            account_id=account.account_id,
            region=region,
            snapshot_taken_at=snapshot.snapshot_taken_at,
        )
        if error is None and resource is not None:
            try:
                outcome = check.evaluate(dict(resource), context)
            except InvalidResource as invalid:
                error = str(invalid)
            else:
                return Finding(
                    check_id=check.check_id,
                    title=check.title,
                    provider=account.provider,
                    account_id=account.account_id,
                    region=region,
                    resource_id=resource_id,
                    status=outcome.status,
                    severity=check.severity,
                    details=outcome.details,
                )

        self._logger.warning(
            "Malformed resource during check evaluation",
            extra={
                "provider": account.provider.value,
                "account_id": account.account_id,
                "check_id": check.check_id,
                "resource_id": resource_id,
            },
        )
        return Finding(
            check_id=check.check_id,
            title=check.title,
            provider=account.provider,
            account_id=account.account_id,
            region=region,
            resource_id=resource_id,
            status=FindingStatus.CANNOT_SCAN,
            severity=check.severity,
            details=error or "resource could not be evaluated",
        )
