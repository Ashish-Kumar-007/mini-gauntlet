import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, getScans, startScan } from '../api/client'

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function duration(startedAt: string, finishedAt: string | null) {
  const end = finishedAt ? Date.parse(finishedAt) : Date.now()
  return `${Math.max(0, Math.round((end - Date.parse(startedAt)) / 1000))} sec`
}

export function ScansPage() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState('')
  const scansQuery = useQuery({
    queryKey: ['scans'],
    queryFn: getScans,
    refetchInterval: (query) =>
      query.state.data?.some((scan) => scan.status === 'RUNNING') ? 1500 : false,
  })
  const startMutation = useMutation({
    mutationFn: () => startScan(),
    onSuccess: async (scan) => {
      setNotice(`Scan ${scan.id.slice(0, 8)} queued.`)
      await queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
  })

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-teal-700">Posture management</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">Scan history</h1>
          <p className="mt-2 text-slate-600">Review cloud security scans across AWS, Azure, and GCP.</p>
        </div>
        <button
          type="button"
          disabled={startMutation.isPending}
          onClick={() => startMutation.mutate()}
          className="rounded-lg bg-slate-900 px-4 py-2.5 font-semibold text-white shadow-sm hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {startMutation.isPending ? 'Starting…' : 'Run scan'}
        </button>
      </div>

      {notice && <p role="status" className="mb-4 text-sm text-emerald-700">{notice}</p>}
      {startMutation.isError && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {startMutation.error instanceof ApiError ? startMutation.error.message : 'Could not start scan.'}
        </p>
      )}
      {scansQuery.isLoading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">Loading scan history…</div>
      ) : scansQuery.isError ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-white p-8 text-center text-red-700">
          {scansQuery.error instanceof ApiError ? scansQuery.error.message : 'Could not load scan history.'}
        </div>
      ) : scansQuery.data.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
          <h2 className="font-semibold text-slate-800">No scans yet</h2>
          <p className="mt-2 text-sm text-slate-500">Start a scan to evaluate the supplied cloud inventory.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-5 py-3">Status</th><th className="px-5 py-3">Started</th><th className="px-5 py-3">Duration</th><th className="px-5 py-3">Accounts</th><th className="px-5 py-3">Posture</th><th className="px-5 py-3">Findings</th></tr>
            </thead>
            <tbody>
              {scansQuery.data.map((scan) => (
                <tr key={scan.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${scan.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700' : scan.status === 'FAILED' ? 'bg-red-50 text-red-700' : 'bg-sky-50 text-sky-700'}`}>{scan.status}</span></td>
                  <td className="px-5 py-4">{formatTime(scan.started_at)}</td>
                  <td className="px-5 py-4">{duration(scan.started_at, scan.finished_at)}</td>
                  <td className="px-5 py-4">{scan.account_ids.length}</td>
                  <td className="px-5 py-4 font-semibold">{scan.score === null ? '—' : `${scan.score.toFixed(1)}%`}</td>
                  <td className="px-5 py-4">
                    <Link className="font-medium text-teal-700 hover:text-teal-900" to={`/scans/${scan.id}`}>
                      {scan.counts_by_status.FAIL} failed · {scan.counts_by_status.CANNOT_SCAN} unable
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
