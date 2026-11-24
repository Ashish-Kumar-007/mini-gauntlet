import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'

import { ScansPage } from './pages/ScansPage'

const ScanDetailsPage = lazy(() =>
  import('./pages/ScanDetailsPage').then((module) => ({ default: module.ScanDetailsPage })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen">
          <header className="border-b border-slate-800 bg-slate-950 text-white">
            <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
              <Link to="/" className="flex items-center gap-3 font-semibold tracking-wide">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal-500 text-sm font-black text-slate-950">MG</span>
                MINI GAUNTLET
              </Link>
              <span className="text-sm text-slate-400">Cloud security posture</span>
            </div>
          </header>
          <Routes>
            <Route path="/" element={<ScansPage />} />
            <Route
              path="/scans/:scanId"
              element={
                <Suspense fallback={<main className="p-10 text-center text-slate-500">Loading scan details…</main>}>
                  <ScanDetailsPage />
                </Suspense>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
