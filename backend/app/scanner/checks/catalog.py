from app.scanner.checks.aws_ec2 import AwsSecurityGroupCheck
from app.scanner.checks.aws_iam import AwsIamAccessKeyAgeCheck, AwsIamMfaCheck
from app.scanner.checks.aws_rds import AwsRdsPublicAccessCheck
from app.scanner.checks.aws_s3 import AwsS3PublicAccessCheck
from app.scanner.checks.azure import AzureNsgExposureCheck, AzureStoragePublicAccessCheck
from app.scanner.checks.gcp import (
    GcpBucketPublicAccessCheck,
    GcpFirewallExposureCheck,
    GcpUniformBucketAccessCheck,
)
from app.scanner.registry import CheckRegistry


def build_check_registry() -> CheckRegistry:
    registry = CheckRegistry()
    for check in (
        AwsS3PublicAccessCheck(),
        AwsSecurityGroupCheck(),
        AwsIamMfaCheck(),
        AwsIamAccessKeyAgeCheck(),
        AwsRdsPublicAccessCheck(),
        AzureStoragePublicAccessCheck(),
        AzureNsgExposureCheck(),
        GcpBucketPublicAccessCheck(),
        GcpUniformBucketAccessCheck(),
        GcpFirewallExposureCheck(),
    ):
        registry.register(check)
    return registry
