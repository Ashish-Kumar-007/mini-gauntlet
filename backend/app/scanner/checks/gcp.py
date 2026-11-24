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
    parse_port_expression,
    port_intersects_target,
    require_boolean,
    require_list,
    require_object,
    require_string,
)


@dataclass(frozen=True)
class GcpBucketPublicAccessCheck:
    check_id: str = "GCP-GCS-01"
    title: str = "Bucket isn't public"
    provider: Provider = Provider.GCP
    severity: Severity = Severity.HIGH
    collection: str = "gcs_buckets"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        bindings = require_list(resource.get("iam_bindings"), "iam_bindings")
        is_public = False
        for index, value in enumerate(bindings):
            binding = require_object(value, f"iam_bindings[{index}]")
            require_string(binding.get("role"), f"iam_bindings[{index}].role")
            members = require_list(binding.get("members"), f"iam_bindings[{index}].members")
            for member_index, member_value in enumerate(members):
                member = require_string(
                    member_value, f"iam_bindings[{index}].members[{member_index}]"
                )
                is_public = is_public or member in {"allUsers", "allAuthenticatedUsers"}

        return EvaluationOutcome(
            status=FindingStatus.FAIL if is_public else FindingStatus.PASS,
            details=(
                "Bucket IAM grants access to a public principal."
                if is_public
                else "Bucket IAM has no public principals."
            ),
        )


@dataclass(frozen=True)
class GcpUniformBucketAccessCheck:
    check_id: str = "GCP-GCS-02"
    title: str = "Bucket uses uniform bucket-level access"
    provider: Provider = Provider.GCP
    severity: Severity = Severity.LOW
    collection: str = "gcs_buckets"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        uniform = require_boolean(
            resource.get("uniform_bucket_level_access"), "uniform_bucket_level_access"
        )
        return EvaluationOutcome(
            status=FindingStatus.PASS if uniform else FindingStatus.FAIL,
            details=(
                "Uniform bucket-level access is enabled."
                if uniform
                else "Uniform bucket-level access is disabled."
            ),
        )


@dataclass(frozen=True)
class GcpFirewallExposureCheck:
    check_id: str = "GCP-VPC-01"
    title: str = "Firewall rule doesn't expose SSH or RDP to the internet"
    provider: Provider = Provider.GCP
    severity: Severity = Severity.CRITICAL
    collection: str = "firewall_rules"
    resource_id_field: str = "name"

    def evaluate(
        self, resource: Mapping[str, object], context: EvaluationContext
    ) -> EvaluationOutcome:
        del context
        direction = require_string(resource.get("direction"), "direction")
        disabled = require_boolean(resource.get("disabled"), "disabled")
        normalized_direction = direction.upper()
        if normalized_direction not in {"INGRESS", "EGRESS"}:
            raise InvalidResource("direction must be INGRESS or EGRESS")
        if normalized_direction != "INGRESS" or disabled:
            return EvaluationOutcome(
                status=FindingStatus.PASS,
                details="Firewall rule is disabled or is not ingress.",
            )

        source_ranges = require_list(resource.get("source_ranges"), "source_ranges")
        public_source = any(
            is_internet_wide_source(source, "source_ranges") for source in source_ranges
        )
        allowed = require_list(resource.get("allowed"), "allowed")
        exposed = False

        for index, value in enumerate(allowed):
            rule = require_object(value, f"allowed[{index}]")
            protocol = require_string(rule.get("IPProtocol"), f"allowed[{index}].IPProtocol")
            normalized_protocol = protocol.lower()
            if normalized_protocol == "all":
                exposed = exposed or public_source
                continue
            if normalized_protocol.isdigit():
                if int(normalized_protocol) > 255:
                    raise InvalidResource(f"allowed[{index}].IPProtocol is invalid")
                is_tcp = normalized_protocol == "6"
            elif normalized_protocol in {
                "tcp",
                "udp",
                "icmp",
                "esp",
                "ah",
                "sctp",
            }:
                is_tcp = normalized_protocol == "tcp"
            else:
                raise InvalidResource(f"allowed[{index}].IPProtocol is invalid")
            if not is_tcp:
                continue

            raw_ports = rule.get("ports")
            if raw_ports is None:
                exposed = exposed or public_source
                continue
            ports = require_list(raw_ports, f"allowed[{index}].ports")
            for port_index, raw_port in enumerate(ports):
                port_range = parse_port_expression(
                    raw_port, f"allowed[{index}].ports[{port_index}]"
                )
                exposed = exposed or (
                    public_source and port_range is not None and port_intersects_target(*port_range)
                )

        return EvaluationOutcome(
            status=FindingStatus.FAIL if exposed else FindingStatus.PASS,
            details=(
                "Enabled ingress rule exposes SSH or RDP to the internet."
                if exposed
                else "No enabled ingress rule exposes SSH or RDP to the internet."
            ),
        )
