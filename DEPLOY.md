# Production deployment design (AWS)

This design runs the Mini Gauntlet API and scanner worker as separate ECS Fargate services. An internet-facing Application Load Balancer serves the API and dashboard entry point; an internal Nginx frontend can serve the static dashboard and proxy `/api` requests. API/worker tasks run in private application subnets. Amazon RDS for PostgreSQL runs in isolated private database subnets, accepts traffic only from the application security group, uses encryption at rest, automated backups, and multi-AZ failover. Container images are built in CI and stored in Amazon ECR.

## Operations and delivery

Store database credentials and any future integration secrets in AWS Secrets Manager and expose them to ECS tasks through task execution/task roles, not image layers or source control. Use short-lived task-role credentials. Send structured API/worker logs to CloudWatch Logs with retention limits; publish ECS CPU/memory, task health, queue age, failed scans, and database health metrics. Alert on repeated scan failures, queue backlog, unhealthy tasks, and database capacity. Keep the database inaccessible from public subnets and restrict inbound application access to the load balancer.

GitHub Actions builds and tests the same Dockerfiles used locally, pushes immutable image tags to ECR, and updates ECS task definitions/services. Configure GitHub's OIDC provider and a narrowly scoped deployment role; trust only the intended repository and protected branch/environment. The workflow exchanges its short-lived OIDC token for temporary AWS credentials, avoiding long-lived access keys. Require successful tests and image builds before deployment; use ECS rolling deployments with health checks and rollback on unhealthy tasks. No cloud resources are created by this project.

## Least-privilege read-only permissions for optional live checks

Live cloud collection is not part of the simulated scanner and is not required to run it. If added, limit the collector to the specific accounts/resources and read-only actions:

| Provider/checks | Minimum discovery/read actions |
|---|---|
| AWS S3 public access | `s3:ListAllMyBuckets`, `s3:GetBucketPublicAccessBlock` |
| AWS security groups | `ec2:DescribeSecurityGroups` |
| AWS IAM MFA and key age | `iam:ListUsers`, `iam:GetLoginProfile`, `iam:ListMFADevices`, `iam:ListAccessKeys` |
| AWS RDS public access | `rds:DescribeDBInstances` |
| Azure storage | `Microsoft.Storage/storageAccounts/read` |
| Azure NSGs | `Microsoft.Network/networkSecurityGroups/read` |
| GCP bucket public IAM and uniform access | `storage.buckets.list`, `storage.buckets.get`, `storage.buckets.getIamPolicy` |
| GCP firewall exposure | `compute.firewalls.list` |

Use the narrowest account/project/resource scope supported by each provider. Do not grant write, credential, policy-mutation, or administrative permissions. Confirm provider API permission granularity and any required list/discovery permissions before enabling live collection.
