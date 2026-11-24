from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.models import (
    EvaluationContext,
    EvaluationOutcome,
    FindingStatus,
    Provider,
    Severity,
)
from app.scanner.checks.helpers import require_boolean


@dataclass(frozen=True)
class AwsRdsPublicAccessCheck:
    check_id: str = "AWS-RDS-01"
    title: str = "RDS instance isn't publicly accessible"
    provider: Provider = Provider.AWS
    severity: Severity = Severity.HIGH
    collection: str = "rds_instances"
    resource_id_field: str = "db_instance_id"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        public = require_boolean(resource.get("publicly_accessible"), "publicly_accessible")
        return EvaluationOutcome(
            status=FindingStatus.FAIL if public else FindingStatus.PASS,
            details=(
                "RDS instance is publicly accessible."
                if public
                else "RDS instance is not publicly accessible."
            ),
        )
