export type FindingStatus = 'PASS' | 'FAIL' | 'CANNOT_SCAN'
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type Provider = 'aws' | 'azure' | 'gcp'
export type ScanStatus = 'RUNNING' | 'COMPLETED' | 'FAILED'

export interface StatusCounts {
  PASS: number
  FAIL: number
  CANNOT_SCAN: number
}

export interface ScanListItem {
  id: string
  status: ScanStatus
  started_at: string
  finished_at: string | null
  account_ids: string[]
  score: number | null
  counts_by_status: StatusCounts
}

export interface AccountScore {
  account_id: string
  score: number | null
}

export interface ScanDetail extends ScanListItem {
  fail_counts_by_severity: Record<Severity, number>
  account_scores: AccountScore[]
  error_message: string | null
}

export interface Finding {
  id: string
  check_id: string
  title: string
  provider: Provider
  account_id: string
  region: string | null
  resource_id: string | null
  status: FindingStatus
  severity: Severity
  details: string
}

export interface FindingsPage {
  items: Finding[]
  total: number
  page: number
  page_size: number
}

export interface FindingsFilters {
  status?: FindingStatus
  severity?: Severity
  provider?: Provider
  account_id?: string
}

export interface ScanAccepted {
  id: string
  status: ScanStatus
  started_at: string
  account_ids: string[]
}
