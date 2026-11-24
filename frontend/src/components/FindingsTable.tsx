import type { ChangeEvent } from 'react'

import type {
  Finding,
  FindingsFilters,
  FindingsPage as FindingsPageData,
  Provider,
  Severity,
} from '../types/api'

interface Props {
  pageData: FindingsPageData | undefined
  filters: FindingsFilters
  accounts: string[]
  page: number
  onFiltersChange: (filters: FindingsFilters) => void
  onPageChange: (page: number) => void
}

const statusOptions = ['PASS', 'FAIL', 'CANNOT_SCAN'] as const
const severityOptions = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
const providerOptions = ['aws', 'azure', 'gcp'] as const

function FindingRow({ finding }: { finding: Finding }) {
  const statusStyles = {
    PASS: 'bg-emerald-50 text-emerald-700',
    FAIL: 'bg-red-50 text-red-700',
    CANNOT_SCAN: 'bg-amber-50 text-amber-800',
  }[finding.status]
  return (
    <tr className="border-t border-slate-100 align-top">
      <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusStyles}`}>{finding.status}</span></td>
      <td className="px-4 py-3 font-medium text-slate-800">{finding.severity}</td>
      <td className="px-4 py-3"><div className="font-medium">{finding.title}</div><div className="mt-1 text-xs text-slate-500">{finding.check_id}</div></td>
      <td className="px-4 py-3">{finding.provider.toUpperCase()}</td>
      <td className="px-4 py-3">{finding.account_id}</td>
      <td className="px-4 py-3 font-mono text-xs">{finding.resource_id ?? '—'}</td>
      <td className="max-w-sm whitespace-pre-wrap break-words px-4 py-3 text-slate-600">{finding.details}</td>
    </tr>
  )
}

export function FindingsTable({
  pageData,
  filters,
  accounts,
  page,
  onFiltersChange,
  onPageChange,
}: Props) {
  const totalPages = Math.max(1, Math.ceil((pageData?.total ?? 0) / (pageData?.page_size ?? 25)))

  function changeFilter(event: ChangeEvent<HTMLSelectElement>) {
    const { name, value } = event.target
    onFiltersChange({ ...filters, [name]: value || undefined } as FindingsFilters)
  }

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
        <label className="text-xs font-medium text-slate-600">
          Status
          <select aria-label="Status" name="status" value={filters.status ?? ''} onChange={changeFilter} className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-2 text-sm">
            <option value="">All statuses</option>
            {statusOptions.map((value) => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Severity
          <select aria-label="Severity" name="severity" value={filters.severity ?? ''} onChange={changeFilter} className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-2 text-sm">
            <option value="">All severities</option>
            {severityOptions.map((value: Severity) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Provider
          <select aria-label="Provider" name="provider" value={filters.provider ?? ''} onChange={changeFilter} className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-2 text-sm">
            <option value="">All providers</option>
            {providerOptions.map((value: Provider) => <option key={value} value={value}>{value.toUpperCase()}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Account
          <select aria-label="Account" name="account_id" value={filters.account_id ?? ''} onChange={changeFilter} className="mt-1 block max-w-64 rounded-md border border-slate-300 bg-white px-2 py-2 text-sm">
            <option value="">All accounts</option>
            {accounts.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      {!pageData ? (
        <div className="p-8 text-center text-sm text-slate-500">Loading findings…</div>
      ) : pageData.items.length === 0 ? (
        <div className="p-8 text-center text-sm text-slate-500">No findings match these filters.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1050px] border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Status</th><th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Check</th><th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Account</th><th className="px-4 py-3">Resource</th>
                <th className="px-4 py-3">Details</th>
              </tr>
            </thead>
            <tbody>{pageData.items.map((finding) => <FindingRow key={finding.id} finding={finding} />)}</tbody>
          </table>
        </div>
      )}
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
        <span>{pageData ? `${pageData.total} findings · Page ${page} of ${totalPages}` : 'Loading'}</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)} className="rounded border border-slate-300 px-3 py-1.5 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} className="rounded border border-slate-300 px-3 py-1.5 disabled:opacity-40">Next</button>
        </div>
      </div>
    </section>
  )
}
