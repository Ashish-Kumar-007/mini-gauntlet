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
    parse_network,
    parse_port_expression,
    port_intersects_target,
    require_boolean,
    require_list,
    require_object,
    require_string,
)

AZURE_PRIVATE_SOURCE_TAGS = {
    "AzureCloud",
    "AzureLoadBalancer",
    "GatewayManager",
    "VirtualNetwork",
}


def _is_public_source(value: object, field: str) -> bool:
    source = require_string(value, field)
    if source in {"*", "Internet"}:
        return True
    if source in AZURE_PRIVATE_SOURCE_TAGS or source.startswith("AzureCloud."):
        return False
    return parse_network(source, field).prefixlen == 0


@dataclass(frozen=True)
class AzureStoragePublicAccessCheck:
    check_id: str = "AZ-STG-01"
    title: str = "Storage account blocks public blob access"
    provider: Provider = Provider.AZURE
    severity: Severity = Severity.HIGH
    collection: str = "storage_accounts"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        public = require_boolean(
            resource.get("allow_blob_public_access"), "allow_blob_public_access"
        )
        return EvaluationOutcome(
            status=FindingStatus.FAIL if public else FindingStatus.PASS,
            details=(
                "Storage account allows public blob access."
                if public
                else "Storage account blocks public blob access."
            ),
        )


@dataclass(frozen=True)
class AzureNsgExposureCheck:
    check_id: str = "AZ-NSG-01"
    title: str = "NSG doesn't expose SSH or RDP to the internet"
    provider: Provider = Provider.AZURE
    severity: Severity = Severity.CRITICAL
    collection: str = "network_security_groups"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        rules = require_list(resource.get("rules"), "rules")
        exposed = False
        for index, value in enumerate(rules):
            rule = require_object(value, f"rules[{index}]")
            direction = require_string(rule.get("direction"), f"rules[{index}].direction")
            access = require_string(rule.get("access"), f"rules[{index}].access")
            normalized_direction = direction.lower()
            normalized_access = access.lower()
            if normalized_direction not in {"inbound", "outbound"}:
                raise InvalidResource(f"rules[{index}].direction is invalid")
            if normalized_access not in {"allow", "deny"}:
                raise InvalidResource(f"rules[{index}].access is invalid")
            if normalized_direction != "inbound" or normalized_access != "allow":
                continue

            protocol = require_string(rule.get("protocol"), f"rules[{index}].protocol")
            normalized_protocol = protocol.lower()
            if normalized_protocol not in {"*", "tcp", "udp", "icmp", "ah", "esp"}:
                raise InvalidResource(f"rules[{index}].protocol is invalid")
            public_source = _is_public_source(rule.get("source"), f"rules[{index}].source")
            ports = parse_port_expression(
                rule.get("destination_ports"), f"rules[{index}].destination_ports"
            )
            tcp_or_wildcard = normalized_protocol in {"tcp", "*"}
            exposed = exposed or (
                public_source
                and tcp_or_wildcard
                and ports is not None
                and port_intersects_target(*ports)
            )

        return EvaluationOutcome(
            status=FindingStatus.FAIL if exposed else FindingStatus.PASS,
            details=(
                "An inbound allow rule exposes SSH or RDP to the internet."
                if exposed
                else "No inbound allow rule exposes SSH or RDP to the internet."
            ),
        )
