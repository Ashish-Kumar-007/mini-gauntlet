# Mini Gauntlet Low-Level Design

This design translates the supplied project brief into implementation contracts. The assignment PDF was not present in the workspace at design time; this document is therefore based on the brief and supplied snapshot and must be checked against the PDF when available.

## 1. Design decisions and assumptions

- Keep one Python domain implementation and run it in separate FastAPI and worker processes. PostgreSQL is the durable queue and result store.
- Use PostgreSQL 16 so the findings uniqueness constraint can treat null resource IDs as equal (`NULLS NOT DISTINCT`).
- Preserve `backend\data\inventory.json` byte-for-byte and parse it as strict JSON. Mount it read-only at `/app/data/inventory.json`; `INVENTORY_PATH` remains configurable.
- Use `snapshot_taken_at` as the sole clock for check evaluation. Check outcomes are deterministic for the same snapshot.
- A scan's scores are `null` until it completes. They are calculated from persisted findings through the shared scoring function; `CANNOT_SCAN` is excluded.
- Since Azure NSG rules in the fixture have no priority field, evaluate each applicable `Allow` rule independently. Do not infer a deny-overrides policy that the snapshot does not express.
- Use a maximum of three job attempts for recoverable worker failures. A permanently unreadable/invalid snapshot fails the scan; automatic retries must not disguise that failure.

## 2. Domain model

### Enums

```text
Provider      = aws | azure | gcp
FindingStatus = PASS | FAIL | CANNOT_SCAN
Severity      = CRITICAL | HIGH | MEDIUM | LOW
ScanStatus    = RUNNING | COMPLETED | FAILED
JobStatus     = PENDING | RUNNING | COMPLETED | FAILED
```

### Value objects

```text
Account:
  provider: Provider
  account_id: non-empty string
  name: string | null
  simulated_latency_ms: non-negative integer
  errors: mapping[collection_name, error_code]
  resources: mapping[collection_name, list[JSON object]]

InventorySnapshot:
  snapshot_taken_at: timezone-aware datetime
  accounts: non-empty list[Account]

EvaluationContext:
  provider: Provider
  account_id: string
  region: string | null
  snapshot_taken_at: timezone-aware datetime

EvaluationOutcome:
  status: PASS | FAIL
  details: plain-text string

Finding:
  check_id, title, provider, account_id, region, resource_id,
  status, severity, details
```

The inventory adapter validates the root, account identity/provider, timestamp and collection shapes. A malformed individual resource remains available to the scanner so it can produce one `CANNOT_SCAN` per applicable check rather than rejecting the entire account.

## 3. Check interface and registry

Each check is an immutable implementation of this interface:

```text
check_id: str
title: str
provider: Provider
severity: Severity
collection: str
resource_id_field: str
evaluate(resource: Mapping[str, object],
         context: EvaluationContext) -> EvaluationOutcome
```

`evaluate` returns only `PASS` or `FAIL`. Missing or invalid fields raise a typed `InvalidResource` exception with a safe explanatory message; the scanner converts that to `CANNOT_SCAN` and logs the check/account/resource identifiers. Cancellation and unexpected programming/database errors are not converted into findings.

The registry is populated at application startup, rejects duplicate IDs and returns checks by provider and collection. Its catalog is the source for `GET /api/checks`. The scanner does not contain check-specific conditions. Ten check implementations live in provider-specific modules and are registered once.

### Evaluation rules

- **AWS-S3-01:** require a mapping with all four public-access-block values present and boolean; PASS iff all are true.
- **AWS-EC2-01:** validate ingress as a list of rules; detect public IPv4/IPv6 CIDRs. `-1` means all ports; otherwise validate protocol and integer port range, then test overlap with 22 or 3389.
- **AWS-IAM-01:** validate `console_access`; if false PASS; if true require boolean `mfa_enabled`.
- **AWS-IAM-02:** validate `access_keys`, each key's status and timestamp. Ignore inactive keys. Fail if an active key timestamp is strictly earlier than snapshot time minus 90 days.
- **AWS-RDS-01:** require boolean `publicly_accessible`; true FAIL.
- **AZ-STG-01:** require boolean `allow_blob_public_access`; true FAIL.
- **AZ-NSG-01:** validate rules and fields; consider inbound `Allow` only, public source forms (`Internet`, `*`, public CIDRs), wildcard or TCP protocol, and port/range overlap with 22/3389. Invalid applicable rule data makes the resource `CANNOT_SCAN`; deny/outbound rules do not fail.
- **GCP-GCS-01:** validate IAM bindings/members; fail for either public member `allUsers` or `allAuthenticatedUsers`.
- **GCP-GCS-02:** require boolean `uniform_bucket_level_access`; false FAIL.
- **GCP-VPC-01:** validate rules; ignore disabled and egress rules, then detect public source ranges with TCP or `all` protocol and port 22/3389 or ranges containing them.

Every validation path must reject booleans where an integer port is expected, malformed CIDRs, reversed ranges, non-list collections, and invalid timestamps with a useful `CANNOT_SCAN` detail.

## 4. Scanner and inventory interfaces

```text
InventoryReader.load(path) -> InventorySnapshot
Scanner.scan(snapshot, account_ids | None) -> list[Finding]
Scoring.score(findings) -> Decimal | None
```

`account_ids=None` selects every account; a selected list is validated before job creation and again against the loaded snapshot. The inventory reader reports file/parse/root errors as a typed `InventoryLoadError`. The scan worker marks the scan failed with a sanitized error category/message; it does not return a successful empty result.

For each account, the scanner:

1. Applies that account's configured simulated latency.
2. Selects checks registered for its provider.
3. For each check, emits nothing when its collection is absent from both `resources` and `errors`.
4. Emits exactly one null-resource `CANNOT_SCAN` finding for a collection-level error, preserving its error code in details and skipping that collection's resources.
5. Evaluates each resource/check pair; converts only `InvalidResource` to a resource-level `CANNOT_SCAN`.

Use a bounded queue and a fixed number of account-worker coroutines, not one task per account. The worker count is `min(configured_limit, selected_account_count)`; default limit is four. Each account's findings are returned in stable order (registry/check ID, then resource ID) before persistence. Unexpected errors fail the scan; cancellation propagates.

## 5. Scoring

One domain function is shared by the worker and API:

```text
evaluable = count(PASS) + count(FAIL)
score = null if evaluable == 0
        else quantize(100 * PASS / evaluable, one decimal, ROUND_HALF_UP)
```

It accepts a finding iterable and optional account ID filter. The API derives scan and account scores from persisted findings; the frontend displays returned values and never reimplements the formula.

## 6. Persistence model

SQLAlchemy 2 mappings and Alembic migrations implement:

```text
scans
  id UUID PK
  status ScanStatus NOT NULL
  started_at timestamptz NOT NULL
  finished_at timestamptz NULL
  account_ids JSONB NOT NULL
  error_message text NULL

scan_jobs
  id UUID PK
  scan_id UUID NOT NULL UNIQUE FK scans(id) ON DELETE CASCADE
  status JobStatus NOT NULL
  created_at timestamptz NOT NULL
  claimed_at timestamptz NULL
  lease_expires_at timestamptz NULL
  claimed_by text NULL
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0)
  last_error text NULL

findings
  id UUID PK
  scan_id UUID NOT NULL FK scans(id) ON DELETE CASCADE
  check_id text NOT NULL
  title text NOT NULL
  provider text NOT NULL
  account_id text NOT NULL
  region text NULL
  resource_id text NULL
  status text NOT NULL
  severity text NOT NULL
  details text NOT NULL
  UNIQUE NULLS NOT DISTINCT
    (scan_id, check_id, provider, account_id, resource_id)
```

Add indexes for `(scans.started_at DESC)`, `(scans.status)`, and findings query paths `(scan_id, status, severity, check_id, resource_id)` plus `(scan_id, provider, account_id)`. Keep enum/string constraints in the database where practical. Findings are written in one transaction per completed scan, so partially written scans are not exposed as complete.

Repository interfaces are intentionally small:

```text
ScanRepository.create(account_ids) -> Scan
ScanRepository.get(id) -> Scan | None
ScanRepository.list_newest() -> list[Scan]
JobRepository.claim(worker_id, now, lease_duration) -> ClaimedJob | None
JobRepository.finish(job_id, attempt, outcome) -> None
FindingRepository.insert_for_scan(scan_id, findings) -> None
FindingRepository.query(scan_id, filters, page, page_size) -> Page[Finding]
```

Repositories own SQL and transaction details. A scan service validates accounts, creates scan/job atomically, and exposes read operations without embedding business logic in route handlers.

## 7. Worker lifecycle and idempotency

Claim a pending or expired job in a short transaction with `SELECT ... FOR UPDATE SKIP LOCKED`; increment attempts and assign worker/lease metadata. Commit before reading the inventory or scanning. Expired claims are reclaimable only up to the attempt limit. The attempt number is a fencing token: completion is accepted only if the worker still owns the current attempt.

On success, insert findings and transition job/scan to `COMPLETED` in one transaction. On a scan-level error, transition to retry or `FAILED` according to error category and attempt limit, set `finished_at`, and record a sanitized message. Unique finding identity prevents duplicate inserts if a worker retries. A stale worker cannot complete a reclaimed job.

## 8. API contracts

All responses use Pydantic v2 schemas. Filters are case-insensitive exact matches. Invalid query values and page sizes above 100 return 422.

```text
GET  /api/health
  200 {"status":"ok"}

GET  /api/checks
  200 {items: CheckCatalogItem[]}

POST /api/scans
  body absent or {account_ids?: string[]}
  202 {id, status:"RUNNING", started_at, account_ids}
  422 empty selection / unknown account

GET /api/scans
  200 {items: ScanListItem[]} newest first

GET /api/scans/{id}
  200 {id, status, started_at, finished_at, account_ids,
       counts_by_status, fail_counts_by_severity, score,
       account_scores}
  404 unknown scan

GET /api/scans/{id}/findings
  query: status, severity, provider, account_id, check_id,
         page=1, page_size=25 (1..100)
  200 {items: Finding[], total, page, page_size}
```

Findings are ordered in the database: status `FAIL`, `CANNOT_SCAN`, `PASS`; severity `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`; then `check_id`, `resource_id` (nulls last). Filtering and pagination happen after scan existence validation and before response serialization.

## 9. Frontend contracts

Use a typed centralized fetch client and feature modules for scans and findings. React Router defines `/scans` and `/scans/:id`. TanStack Query fetches lists/details and polls every 1–2 seconds only while a scan is `RUNNING`; successful terminal states stop polling. The findings table uses server filters and pagination and preserves server order. Render every string as text; do not use `dangerouslySetInnerHTML`. Provide explicit loading, empty, API-unavailable, error, running, completed, and failed states.

## 10. Configuration, failures, and logs

Configuration: `DATABASE_URL`, `INVENTORY_PATH`, `SCAN_CONCURRENCY` (default 4), job lease duration, and log level. Validate settings at process startup. Logs are structured and include available `scan_id`, `account_id`, `provider`, `check_id`, and `resource_id`; never log secrets or raw stack traces to API responses.

Expected input faults become `CANNOT_SCAN` only at resource/check scope. Inventory load failures fail the scan. Database outages surface as process/API errors and do not produce success-shaped fallbacks. Unexpected scanner failures fail the job/scan and are logged with exception context.

## 11. Test seams and verification

- Unit tests call each check through its interface and cover PASS/FAIL/CANNOT_SCAN, including boundaries, malformed data, CIDRs, ranges, wildcards, deny/outbound, disabled rules, and exact/older-than-90-day timestamps.
- Scanner tests use an injected inventory snapshot and latency clock/sleeper; verify missing collections, collection errors, warnings, isolation, deterministic output, and maximum active account workers.
- Scoring tests cover exclusion, null, and one-decimal rounding.
- Repository/API integration tests use PostgreSQL and HTTPX; cover status transitions, filters, ordering, pagination, 404/422, and job claims.
- Frontend tests assert meaningful user-visible behavior, including polling/filter interactions and HTML-like details rendered as text.
- Compose verification checks health/start order, persistence, API and dashboard URLs, and that the supplied inventory is mounted read-only.

## 12. Implementation sequence

1. Project configuration and domain enums/types.
2. Inventory adapter and its fixture-compatibility test.
3. Check interface, registry, and first check with focused tests.
4. Remaining checks and scanner/concurrency tests.
5. Scoring module and tests.
6. SQLAlchemy mappings, Alembic migration, repository tests.
7. Job worker and lifecycle tests.
8. API schemas/routes and HTTPX tests.
9. Frontend client/pages/tests.
10. Docker Compose, CI, README, `DEPLOY.md`, and integrated verification.
