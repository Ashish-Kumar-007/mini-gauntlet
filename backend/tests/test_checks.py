from datetime import UTC, datetime

import pytest

from app.domain.errors import InvalidResource
from app.domain.models import EvaluationContext, FindingStatus, Provider
from app.scanner.checks.aws_ec2 import AwsSecurityGroupCheck
from app.scanner.checks.aws_iam import AwsIamAccessKeyAgeCheck, AwsIamMfaCheck
from app.scanner.checks.aws_rds import AwsRdsPublicAccessCheck
from app.scanner.checks.aws_s3 import PUBLIC_ACCESS_FLAGS, AwsS3PublicAccessCheck
from app.scanner.checks.azure import AzureNsgExposureCheck, AzureStoragePublicAccessCheck
from app.scanner.checks.catalog import build_check_registry
from app.scanner.checks.gcp import (
    GcpBucketPublicAccessCheck,
    GcpFirewallExposureCheck,
    GcpUniformBucketAccessCheck,
)

CONTEXT = EvaluationContext(
    provider=Provider.AWS,
    account_id="test-account",
    region=None,
    snapshot_taken_at=datetime(2026, 10, 1, tzinfo=UTC),
)


def _s3(**overrides: object) -> dict[str, object]:
    return {
        "public_access_block": dict.fromkeys(PUBLIC_ACCESS_FLAGS, True) | overrides,
    }


def _cases() -> list[tuple[object, dict[str, object], dict[str, object], dict[str, object]]]:
    return [
        (
            AwsS3PublicAccessCheck(),
            _s3(),
            _s3(block_public_acls=False),
            {"public_access_block": {"block_public_acls": "true"}},
        ),
        (
            AwsSecurityGroupCheck(),
            {
                "ingress": [
                    {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidrs": ["0.0.0.0/0"]}
                ]
            },
            {
                "ingress": [
                    {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidrs": ["0.0.0.0/0"]}
                ]
            },
            {
                "ingress": [
                    {
                        "protocol": "tcp",
                        "from_port": "twenty-two",
                        "to_port": 22,
                        "cidrs": ["0.0.0.0/0"],
                    }
                ]
            },
        ),
        (
            AwsIamMfaCheck(),
            {"console_access": True, "mfa_enabled": True},
            {"console_access": True, "mfa_enabled": False},
            {"console_access": "true", "mfa_enabled": True},
        ),
        (
            AwsIamAccessKeyAgeCheck(),
            {"access_keys": [{"status": "Active", "created_at": "2026-07-03T00:00:00Z"}]},
            {"access_keys": [{"status": "Active", "created_at": "2026-07-02T23:59:59Z"}]},
            {"access_keys": [{"status": "Active", "created_at": "not-a-date"}]},
        ),
        (
            AwsRdsPublicAccessCheck(),
            {"publicly_accessible": False},
            {"publicly_accessible": True},
            {"publicly_accessible": 1},
        ),
        (
            AzureStoragePublicAccessCheck(),
            {"allow_blob_public_access": False},
            {"allow_blob_public_access": True},
            {"allow_blob_public_access": "false"},
        ),
        (
            AzureNsgExposureCheck(),
            {
                "rules": [
                    {
                        "direction": "Inbound",
                        "access": "Allow",
                        "protocol": "Tcp",
                        "source": "Internet",
                        "destination_ports": "443",
                    }
                ]
            },
            {
                "rules": [
                    {
                        "direction": "Inbound",
                        "access": "Allow",
                        "protocol": "*",
                        "source": "*",
                        "destination_ports": "3380-3400",
                    }
                ]
            },
            {
                "rules": [
                    {
                        "direction": "Inbound",
                        "access": "Allow",
                        "protocol": "Tcp",
                        "source": "*",
                        "destination_ports": "twenty",
                    }
                ]
            },
        ),
        (
            GcpBucketPublicAccessCheck(),
            {
                "iam_bindings": [
                    {
                        "role": "roles/storage.objectViewer",
                        "members": ["group:engineering@example.com"],
                    }
                ]
            },
            {"iam_bindings": [{"role": "roles/storage.objectViewer", "members": ["allUsers"]}]},
            {"iam_bindings": [{"members": "allUsers"}]},
        ),
        (
            GcpUniformBucketAccessCheck(),
            {"uniform_bucket_level_access": True},
            {"uniform_bucket_level_access": False},
            {"uniform_bucket_level_access": "false"},
        ),
        (
            GcpFirewallExposureCheck(),
            {
                "direction": "INGRESS",
                "disabled": False,
                "source_ranges": ["35.235.240.0/20"],
                "allowed": [{"IPProtocol": "tcp", "ports": ["22"]}],
            },
            {
                "direction": "INGRESS",
                "disabled": False,
                "source_ranges": ["0.0.0.0/0"],
                "allowed": [{"IPProtocol": "tcp", "ports": ["3389"]}],
            },
            {
                "direction": "INGRESS",
                "disabled": "false",
                "source_ranges": ["0.0.0.0/0"],
                "allowed": [{"IPProtocol": "tcp", "ports": ["22"]}],
            },
        ),
    ]


@pytest.mark.parametrize(("check", "passing", "failing", "malformed"), _cases())
def test_each_check_has_pass_fail_and_cannot_scan_cases(
    check: object,
    passing: dict[str, object],
    failing: dict[str, object],
    malformed: dict[str, object],
) -> None:
    assert check.evaluate(passing, CONTEXT).status is FindingStatus.PASS
    assert check.evaluate(failing, CONTEXT).status is FindingStatus.FAIL
    with pytest.raises(InvalidResource):
        check.evaluate(malformed, CONTEXT)


def test_aws_security_group_handles_ipv6_all_protocol_and_private_cidr() -> None:
    check = AwsSecurityGroupCheck()
    assert (
        check.evaluate(
            {"ingress": [{"protocol": "tcp", "from_port": 22, "to_port": 22, "cidrs": ["::/0"]}]},
            CONTEXT,
        ).status
        is FindingStatus.FAIL
    )
    assert (
        check.evaluate(
            {
                "ingress": [
                    {"protocol": "-1", "from_port": None, "to_port": None, "cidrs": ["0.0.0.0/0"]}
                ]
            },
            CONTEXT,
        ).status
        is FindingStatus.FAIL
    )
    assert (
        check.evaluate(
            {
                "ingress": [
                    {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidrs": ["203.0.113.0/24"]}
                ]
            },
            CONTEXT,
        ).status
        is FindingStatus.PASS
    )


def test_iam_checks_ignore_non_console_mfa_and_inactive_key_age() -> None:
    mfa = AwsIamMfaCheck().evaluate(
        {"console_access": False, "mfa_enabled": "not-applicable"}, CONTEXT
    )
    age = AwsIamAccessKeyAgeCheck().evaluate(
        {"access_keys": [{"status": "Inactive", "created_at": "invalid"}]}, CONTEXT
    )
    assert mfa.status is FindingStatus.PASS
    assert age.status is FindingStatus.PASS


def test_azure_nsg_ignores_deny_and_outbound_rules() -> None:
    outcome = AzureNsgExposureCheck().evaluate(
        {
            "rules": [
                {
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "Tcp",
                    "source": "Internet",
                    "destination_ports": "22",
                },
                {
                    "direction": "Outbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source": "*",
                    "destination_ports": "22",
                },
            ]
        },
        CONTEXT,
    )
    assert outcome.status is FindingStatus.PASS


def test_gcp_firewall_ignores_disabled_egress_and_flags_wildcard_protocol() -> None:
    check = GcpFirewallExposureCheck()
    safe = check.evaluate(
        {
            "direction": "EGRESS",
            "disabled": False,
            "source_ranges": [],
            "allowed": [],
        },
        CONTEXT,
    )
    disabled = check.evaluate(
        {"direction": "INGRESS", "disabled": True},
        CONTEXT,
    )
    wildcard = check.evaluate(
        {
            "direction": "INGRESS",
            "disabled": False,
            "source_ranges": ["::/0"],
            "allowed": [{"IPProtocol": "all"}],
        },
        CONTEXT,
    )
    assert safe.status is FindingStatus.PASS
    assert disabled.status is FindingStatus.PASS
    assert wildcard.status is FindingStatus.FAIL


def test_check_catalog_contains_exactly_ten_unique_checks() -> None:
    catalog = build_check_registry().catalog()
    assert len(catalog) == 10
    assert len({check.check_id for check in catalog}) == 10
