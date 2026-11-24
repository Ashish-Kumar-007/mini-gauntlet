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
from app.scanner.checks.helpers import (
    is_internet_wide_source,
    port_intersects_target,
    require_integer,
    require_list,
    require_object,
    require_string,
)


@dataclass(frozen=True)
class AwsSecurityGroupCheck:
    check_id: str = "AWS-EC2-01"
    title: str = "Security group doesn't expose SSH or RDP to the internet"
    provider: Provider = Provider.AWS
    severity: Severity = Severity.CRITICAL
    collection: str = "security_groups"
    resource_id_field: str = "group_id"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        ingress = require_list(resource.get("ingress"), "ingress")
        exposed = False

        for index, value in enumerate(ingress):
            rule = require_object(value, f"ingress[{index}]")
            protocol = require_string(rule.get("protocol"), f"ingress[{index}].protocol")
            cidrs = require_list(rule.get("cidrs"), f"ingress[{index}].cidrs")
            public_source = any(
                is_internet_wide_source(cidr, f"ingress[{index}].cidrs") for cidr in cidrs
            )

            normalized_protocol = protocol.lower()
            if normalized_protocol == "-1":
                exposed = exposed or public_source
                continue
            if normalized_protocol.isdigit():
                if int(normalized_protocol) > 255:
                    raise InvalidResource(f"ingress[{index}].protocol is invalid")
                is_tcp = normalized_protocol == "6"
            elif normalized_protocol in {"tcp", "udp", "icmp", "icmpv6"}:
                is_tcp = normalized_protocol == "tcp"
            else:
                raise InvalidResource(f"ingress[{index}].protocol is invalid")
            if not is_tcp:
                continue

            start = require_integer(rule.get("from_port"), f"ingress[{index}].from_port", 0, 65535)
            end = require_integer(rule.get("to_port"), f"ingress[{index}].to_port", 0, 65535)
            if start > end:
                raise InvalidResource(f"ingress[{index}] has a reversed port range")
            exposed = exposed or (public_source and port_intersects_target(start, end))

        return EvaluationOutcome(
            status=FindingStatus.FAIL if exposed else FindingStatus.PASS,
            details=(
                "Ingress exposes SSH or RDP to the internet."
                if exposed
                else "Ingress does not expose SSH or RDP to the internet."
            ),
        )
