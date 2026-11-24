# Requirements and traceability

## Source and scope

This extraction uses the user-provided Mini Gauntlet engineering brief. The referenced assignment PDF was not in the workspace, so PDF-specific requirements remain unverified. The implementation uses the newly supplied `backend\data\inventory.json` without modifying it.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | Read a local JSON snapshot containing AWS, Azure, and GCP accounts; use its `snapshot_taken_at` as the evaluation clock. |
| FR-02 | Evaluate exactly ten registered checks and produce standardized findings per resource/check. |
| FR-03 | Isolate missing collections, collection permission errors, and malformed resources; retain original collection error codes. |
| FR-04 | Scan accounts concurrently with a configurable bound, default four, and honor each account's simulated latency. |
| FR-05 | Calculate scan and account posture using `100 × PASS / (PASS + FAIL)`; exclude `CANNOT_SCAN`, round to one decimal, and return null with no evaluable results. |
| FR-06 | Expose health, catalog, scan creation/list/detail, and paginated/filterable findings through REST endpoints. |
| FR-07 | Execute scans in a durable worker and persist scan state, jobs, and findings in PostgreSQL. |
| FR-08 | Claim jobs safely, recover expired claims, prevent stale workers from completing reclaimed jobs, and avoid duplicate findings. |
| FR-09 | Display scan history, status, duration, score, status/severity counts, account scores, and findings in a React dashboard. |
| FR-10 | Support dashboard polling while scans run, findings filters, pagination, and loading/empty/error states. |
| FR-11 | Build and run API, worker, PostgreSQL, and dashboard with Docker Compose. |
| FR-12 | Run backend/frontend quality checks and both production image builds in GitHub Actions. |
| FR-13 | Document local setup, architecture, trade-offs, unfinished work, AI assistance, and production deployment. |

## Non-functional requirements

- Typed, testable modules with a check registry; adding a check must not require changing scanner orchestration.
- Deterministic results for a fixed snapshot; stable ordering.
- Bounded concurrency and no unbounded per-account task creation.
- Fault isolation: one malformed resource must not terminate an account or scan.
- Durable scan history and worker coordination across process restarts.
- Explicit failures; no success-shaped fallback for failed inventory reads or scans.
- Untrusted inventory strings rendered only as text; no unsafe HTML rendering.
- PostgreSQL with Alembic migrations; least-privilege, read-only permissions if live cloud integration is ever added.
- Non-root application containers, pinned base image versions, health checks, and a persistent database volume.

## Business rules

1. `PASS`, `FAIL`, and `CANNOT_SCAN` are distinct finding states. `CANNOT_SCAN` is not a score numerator or denominator.
2. A collection-level error overrides resources in that collection and emits one null-resource `CANNOT_SCAN` per applicable check, with its error code.
3. A collection missing from both `resources` and `errors` emits no findings.
4. An invalid resource/check pair emits `CANNOT_SCAN` for that resource/check, includes a useful reason, logs a warning, and continues.
5. Active IAM keys strictly older than 90 days fail; exactly 90 days old passes. Inactive keys are ignored.
6. Scores are computed in one domain function, rounded to one decimal, and null if there are no PASS/FAIL results.
7. Findings are sorted by status `FAIL`, `CANNOT_SCAN`, `PASS`; severity `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`; then check ID and resource ID.
8. Account concurrency defaults to four; simulated latency values from the snapshot are respected.

## Mandatory checks

| ID | Provider / collection | Severity | Required outcome |
|---|---|---:|---|
| AWS-S3-01 | AWS `s3_buckets` | HIGH | PASS iff all four public access block flags are true. |
| AWS-EC2-01 | AWS `security_groups` | CRITICAL | FAIL for SSH 22 or RDP 3389 ingress from `0.0.0.0/0` or `::/0`; account for ranges and protocol `-1`. |
| AWS-IAM-01 | AWS `iam_users` | HIGH | MFA required only for console-access users. |
| AWS-IAM-02 | AWS `iam_users` | MEDIUM | Fail only for active keys strictly older than 90 days. |
| AWS-RDS-01 | AWS `rds_instances` | HIGH | `publicly_accessible: true` fails. |
| AZ-STG-01 | Azure `storage_accounts` | HIGH | `allow_blob_public_access: true` fails. |
| AZ-NSG-01 | Azure `network_security_groups` | CRITICAL | Fail on public inbound Allow exposure to SSH/RDP; account for wildcard protocol and port ranges; ignore Deny and outbound. |
| GCP-GCS-01 | GCP `gcs_buckets` | HIGH | Fail for `allUsers` or `allAuthenticatedUsers` IAM members. |
| GCP-GCS-02 | GCP `gcs_buckets` | LOW | Fail when uniform bucket-level access is false. |
| GCP-VPC-01 | GCP `firewall_rules` | CRITICAL | Fail on enabled ingress exposure to public SSH/RDP sources; ignore disabled and egress rules. |

## Inventory edge-case coverage

| Snapshot example | Expected behavior |
|---|---|
| Null S3 public-access config | Resource-level `CANNOT_SCAN`. |
| Public IPv6 SSH, AWS protocol `-1`, and port ranges crossing SSH/RDP | Correctly detect exposure. |
| Restricted SSH source and public HTTPS/DNS rules | PASS for this check. |
| Development AWS IAM/RDS collection errors | One collection-level finding per applicable check, preserving `AccessDenied` / `UnauthorizedOperation`. |
| Malformed security-group port string | Resource-level `CANNOT_SCAN`; other resources continue. |
| Exactly-90-day, older active, and old inactive access keys | Boundary passes; stale active fails; inactive ignored. |
| Azure NSG public wildcard/ranged Allow, Deny, and outbound rules | Detect only applicable public inbound Allow exposure. |
| GCP public principals, private principal, disabled rule, egress, IAP source, and wide port range | Detect public IAM/RDP exposure; ignore disabled/egress and non-wide source; do not flag unrelated application ports. |
| HTML-like GCP description | Return/display as plain text, never interpreted as markup. |

## API acceptance

| Route | Contract and negative case |
|---|---|
| `GET /api/health` | 200 `{"status":"ok"}`. |
| `GET /api/checks` | Full ten-check catalog. |
| `POST /api/scans` | Optional body; 202 RUNNING scan. Empty or unknown account IDs return 422. |
| `GET /api/scans` | All scans newest first, with account IDs, times, status counts, and score. |
| `GET /api/scans/{id}` | Status/counts/severity failures/overall and per-account scores; unknown ID returns 404. |
| `GET /api/scans/{id}/findings` | Case-insensitive filters, page default 1, size default 25/max 100, required backend sort. |

## Traceability

| Requirement | Implementation | Evidence |
|---|---|---|
| FR-01–04, check semantics | `backend/app/inventory.py`, `backend/app/scanner/` | `backend/tests/test_checks.py`, `backend/tests/test_scanner.py` |
| FR-05 | `backend/app/domain/scoring.py` | Scanner and API score assertions |
| FR-06 | `backend/app/api/routes.py`, `backend/app/schemas.py` | `backend/tests/test_api.py` |
| FR-07–08 | `backend/app/db/`, `backend/app/repositories/jobs.py`, `backend/app/worker.py`, `backend/migrations/` | `backend/tests/test_worker.py`, Alembic upgrade |
| FR-09–10 | `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/api/` | `frontend/tests/` |
| FR-11 | `docker-compose.yml`, backend/frontend Dockerfiles | Compose config validated; image execution pending Docker daemon availability |
| FR-12 | `.github/workflows/ci.yml` | No remote run is available yet |
| FR-13 | `README.md`, `ARCHITECTURE.md`, `LLD.md`, `DEPLOY.md` | Document files |
