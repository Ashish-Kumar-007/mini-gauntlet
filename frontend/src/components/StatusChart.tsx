import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import type { StatusCounts } from '../types/api'

const COLORS = {
  PASS: '#059669',
  FAIL: '#dc2626',
  CANNOT_SCAN: '#d97706',
}

export function StatusChart({ counts }: { counts: StatusCounts }) {
  const data = (Object.entries(counts) as [keyof StatusCounts, number][])
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name: name.replace('_', ' '), value, color: COLORS[name] }))

  if (data.length === 0) {
    return <p className="text-sm text-slate-500">No findings yet.</p>
  }

  return (
    <div aria-label="Findings by status" className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78}>
            {data.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
      <div className="-mt-2 flex justify-center gap-4 text-xs text-slate-600">
        {data.map((entry) => (
          <span key={entry.name} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.color }} />
            {entry.name}: {entry.value}
          </span>
        ))}
      </div>
    </div>
  )
}
