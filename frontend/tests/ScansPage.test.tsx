import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getScans, startScan } from '../src/api/client'
import { ScansPage } from '../src/pages/ScansPage'

vi.mock('../src/api/client', () => ({
  ApiError: class ApiError extends Error {},
  getScans: vi.fn(),
  startScan: vi.fn(),
}))

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><ScansPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ScansPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getScans).mockResolvedValue([])
    vi.mocked(startScan).mockResolvedValue({
      id: 'scan-12345678',
      status: 'RUNNING',
      started_at: '2026-10-01T00:00:00Z',
      account_ids: [],
    })
  })

  it('starts a scan and confirms that it was queued', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Run scan' }))

    await waitFor(() => expect(startScan).toHaveBeenCalledOnce())
    expect(await screen.findByRole('status')).toHaveTextContent('Scan scan-123 queued.')
  })

  it('shows an empty state when scan history is empty', async () => {
    renderPage()
    expect(await screen.findByText('No scans yet')).toBeInTheDocument()
  })
})
