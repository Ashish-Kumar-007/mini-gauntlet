from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.errors import InvalidResource
from app.domain.models import (
    EvaluationContext,
    EvaluationOutcome,
    FindingStatus,
    Provider,
    Severity,
)

PUBLIC_ACCESS_FLAGS = (
    "block_public_acls",
    "ignore_public_acls",
    "block_public_policy",
    "restrict_public_buckets",
)


@dataclass(frozen=True)
class AwsS3PublicAccessCheck:
    check_id: str = "AWS-S3-01"
    title: str = "S3 bucket blocks public access"
    provider: Provider = Provider.AWS
    severity: Severity = Severity.HIGH
    collection: str = "s3_buckets"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        config = resource.get("public_access_block")
        if not isinstance(config, dict):
            raise InvalidResource("public_access_block must be an object")

        flags: list[bool] = []
        for flag in PUBLIC_ACCESS_FLAGS:
            value = config.get(flag)
            if type(value) is not bool:
                raise InvalidResource(f"public_access_block.{flag} must be a boolean")
            flags.append(value)

        passed = all(flags)
        return EvaluationOutcome(
            status=FindingStatus.PASS if passed else FindingStatus.FAIL,
            details=(
                "All public access block settings are enabled."
                if passed
                else "One or more public access block settings are disabled."
            ),
        )
