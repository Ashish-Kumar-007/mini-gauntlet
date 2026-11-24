from collections.abc import Mapping
from typing import Protocol

from app.domain.models import (
    EvaluationContext,
    EvaluationOutcome,
    Provider,
    Severity,
)


class SecurityCheck(Protocol):
    check_id: str
    title: str
    provider: Provider
    severity: Severity
    collection: str
    resource_id_field: str

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome: ...


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, SecurityCheck] = {}

    def register(self, check: SecurityCheck) -> None:
        if check.check_id in self._checks:
            raise ValueError(f"duplicate check ID: {check.check_id}")
        self._checks[check.check_id] = check

    def checks_for(self, provider: Provider) -> tuple[SecurityCheck, ...]:
        return tuple(
            sorted(
                (check for check in self._checks.values() if check.provider is provider),
                key=lambda check: check.check_id,
            )
        )

    def catalog(self) -> tuple[SecurityCheck, ...]:
        return tuple(self._checks[key] for key in sorted(self._checks))
