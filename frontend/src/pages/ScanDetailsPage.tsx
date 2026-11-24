import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, getFindings, getScan } from '../api/client'
import { FindingsTable } from '../components/FindingsTable'
import { StatusChart } from '../components/StatusChart'
import type { FindingsFilters } from '../types/api'

export function ScanDetailsPage() {
  const { scanId = '' } = useParams()
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<FindingsFilters>({})
  const [page, setPage] = useState(1)
  const scanWasRunning = useRef(false)
  const scanQuery = useQuery({
    queryKey: ['scan', scanId],
    queryFn: () => getScan(scanId),
    enabled: Boolean(scanId),
    refetchInterval: (query) => query.state.data?.status === 'RUNNING' ? 1500 : false,
  })
  const findingsQuery = useQuery({
    queryKey: ['findings', scanId, filters, page],
    queryFn: () => getFindings(scanId, filters, page),
    enabled: Boolean(scanId),
    refetchInterval: scanQuery.data?.status === 'RUNNING' ? 1500 : false,
  })

  useEffect(() => {
    if (scanQuery.data?.status === 'RUNNING') {
      scanWasRunning.current = true
    } else if (scanWasRunning.current) {
      scanWasRunning.current = false
      void queryClient.invalidateQueries({ queryKey: ['findings', scanId] })
    }
  }, [queryClient, scanId, scanQuery.data?.status])

  if (scanQuery.isLoading) {
    return <main className="p-10 text-center text-slate-500">Loading scan details…</main>
  }
  if (scanQuery.isError || !scanQuery.data) {
    return (
      <main role="alert" className="p-10 text-center text-red-700">
        {scanQuery.error instanceof ApiError ? scanQuery.error.message : 'Could not load scan details.'}
      </main>
    )
  }

  const scan = scanQuery.data
  const updateFilters = (next: FindingsFilters) => {
    setFilters(next)
    setPage(1)
  }

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <Link to="/" className="text-sm font-medium text-teal-700 hover:text-teal-900">← Scan history</Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-teal-700">Scan details</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Security posture</h1>
          <p className="mt-1 font-mono text-xs text-slate-500">{scan.id}</p>
        </div>
        <span className={`rounded-full px-3 py-1.5 text-sm font-semibold ${scan.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700' : scan.status === 'FAILED' ? 'bg-red-50 text-red-700' : 'bg-sky-50 text-sky-700'}`}>{scan.status}</span>
      </div>

      {scan.status === 'FAILED' && scan.error_message && (
        <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{scan.error_message}</p>
      )}
      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_1.5fr]">
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-800">Overall posture</h2>
          <p className="mt-3 text-4xl font-bold text-slate-900">{scan.score === null ? '—' : `${scan.score.toFixed(1)}%`}</p>
          <progress aria-label="Overall posture score" className="mt-3 h-2 w-full accent-teal-600" max={100} value={scan.score ?? 0} />
          <p className="mt-2 text-sm text-slate-500">{scan.score === null ? 'No evaluable findings yet' : 'PASS findings divided by PASS and FAIL findings'}</p>
          <div className="mt-5 grid grid-cols-3 gap-2 text-center">
            {(['PASS', 'FAIL', 'CANNOT_SCAN'] as const).map((status) => (
              <div key={status} className="rounded-lg bg-slate-50 px-2 py-3">
                <div className="text-xl font-bold text-slate-900">{scan.counts_by_status[status]}</div>
                <div className="mt-1 text-[10px] font-semibold text-slate-500">{status.replace('_', ' ')}</div>
              </div>
            ))}
          </div>
        </section>
        <section className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="font-semibold text-slate-800">Findings by status</h2>
            <StatusChart counts={scan.counts_by_status} />
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="font-semibold text-slate-800">Failed findings by severity</h2>
            <div className="mt-4 space-y-3">
              {Object.entries(scan.fail_counts_by_severity).map(([severity, count]) => (
                <div key={severity} className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">{severity}</span><span className="font-semibold text-slate-900">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="mt-5 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold text-slate-800">Posture by account</h2>
        {scan.account_scores.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">Account scores will appear when findings are available.</p>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {scan.account_scores.map((account) => (
              <div key={account.account_id} className="rounded-lg bg-slate-50 p-3">
                <div className="truncate font-mono text-xs text-slate-600" title={account.account_id}>{account.account_id}</div>
                <div className="mt-1 text-lg font-bold text-slate-900">{account.score === null ? 'N/A' : `${account.score.toFixed(1)}%`}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mt-7">
        <div className="mb-3">
          <h2 className="text-xl font-bold text-slate-900">Findings</h2>
          <p className="text-sm text-slate-500">Filter results; the server applies the required severity and status ordering.</p>
        </div>
        {findingsQuery.isError && (
          <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {findingsQuery.error instanceof ApiError ? findingsQuery.error.message : 'Could not load findings.'}
          </p>
        )}
        <FindingsTable
          pageData={findingsQuery.data}
          filters={filters}
          accounts={scan.account_ids}
          page={page}
          onFiltersChange={updateFilters}
          onPageChange={setPage}
        />
      </section>
    </main>
  )
}
