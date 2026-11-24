from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.errors import InvalidResource
from app.domain.models import (
    EvaluationContext,
    EvaluationOutcome,
    FindingStatus,
    Provider,
    Severity,
)
from app.scanner.checks.helpers import (
    require_boolean,
    require_list,
    require_object,
    require_string,
)


def _parse_timestamp(value: object, field: str) -> datetime:
    raw = require_string(value, field)
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidResource(f"{field} must be an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise InvalidResource(f"{field} must include a timezone")
    return timestamp


@dataclass(frozen=True)
class AwsIamMfaCheck:
    check_id: str = "AWS-IAM-01"
    title: str = "Console users have MFA"
    provider: Provider = Provider.AWS
    severity: Severity = Severity.HIGH
    collection: str = "iam_users"
    resource_id_field: str = "user_name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        console_access = require_boolean(resource.get("console_access"), "console_access")
        mfa_enabled = (
            require_boolean(resource.get("mfa_enabled"), "mfa_enabled") if console_access else True
        )
        return EvaluationOutcome(
            status=FindingStatus.PASS if mfa_enabled else FindingStatus.FAIL,
            details=(
                "Console user has MFA enabled."
                if mfa_enabled
                else "Console user does not have MFA enabled."
            ),
        )


@dataclass(frozen=True)
class AwsIamAccessKeyAgeCheck:
    check_id: str = "AWS-IAM-02"
    title: str = "No active access key is older than 90 days"
    provider: Provider = Provider.AWS
    severity: Severity = Severity.MEDIUM
    collection: str = "iam_users"
    resource_id_field: str = "user_name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        keys = require_list(resource.get("access_keys"), "access_keys")
        cutoff = context.snapshot_taken_at - timedelta(days=90)
        stale_key = False

        for index, value in enumerate(keys):
            key = require_object(value, f"access_keys[{index}]")
            status = require_string(key.get("status"), f"access_keys[{index}].status")
            if status not in {"Active", "Inactive"}:
                raise InvalidResource(f"access_keys[{index}].status must be Active or Inactive")
            if status == "Active":
                created_at = _parse_timestamp(
                    key.get("created_at"), f"access_keys[{index}].created_at"
                )
                if created_at < cutoff:
                    stale_key = True

        return EvaluationOutcome(
            status=FindingStatus.FAIL if stale_key else FindingStatus.PASS,
            details=(
                "At least one active access key is older than 90 days."
                if stale_key
                else "No active access key is older than 90 days."
            ),
        )
