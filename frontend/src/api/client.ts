import type {
  FindingsFilters,
  FindingsPage,
  ScanAccepted,
  ScanDetail,
  ScanListItem,
} from '../types/api'

export class ApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('The API is unavailable. Check that the backend is running.', 0)
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new ApiError(body?.detail ?? `Request failed (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

export const getScans = (): Promise<ScanListItem[]> => request('/api/scans')
export const getScan = (id: string): Promise<ScanDetail> => request(`/api/scans/${id}`)
export const startScan = (accountIds?: string[]): Promise<ScanAccepted> =>
  request('/api/scans', {
    method: 'POST',
    body: accountIds ? JSON.stringify({ account_ids: accountIds }) : undefined,
  })

export function getFindings(
  scanId: string,
  filters: FindingsFilters,
  page: number,
): Promise<FindingsPage> {
  const params = new URLSearchParams({ page: String(page), page_size: '25' })
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  return request(`/api/scans/${scanId}/findings?${params.toString()}`)
}
