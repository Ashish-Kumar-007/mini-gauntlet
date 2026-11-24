import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FindingsTable } from '../src/components/FindingsTable'
import type { Finding } from '../src/types/api'

const finding: Finding = {
  id: 'finding-1',
  check_id: 'GCP-VPC-01',
  title: 'Firewall rule check',
  provider: 'gcp',
  account_id: 'example-account',
  region: 'global',
  resource_id: 'allow-rdp-anywhere',
  status: 'FAIL',
  severity: 'CRITICAL',
  details: "<img src=x onerror=alert('untrusted-input')>",
}

describe('FindingsTable', () => {
  it('renders inventory details as text and updates the server filter', () => {
    const onFiltersChange = vi.fn()
    render(
      <FindingsTable
        pageData={{ items: [finding], total: 1, page: 1, page_size: 25 }}
        filters={{}}
        accounts={['example-account']}
        page={1}
        onFiltersChange={onFiltersChange}
        onPageChange={vi.fn()}
      />,
    )

    expect(screen.getByText(finding.details)).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    fireEvent.change(screen.getByRole('combobox', { name: 'Status' }), {
      target: { value: 'FAIL' },
    })
    expect(onFiltersChange).toHaveBeenCalledWith({ status: 'FAIL' })
  })

  it('shows an empty result message when filters match no findings', () => {
    render(
      <FindingsTable
        pageData={{ items: [], total: 0, page: 1, page_size: 25 }}
        filters={{}}
        accounts={[]}
        page={1}
        onFiltersChange={vi.fn()}
        onPageChange={vi.fn()}
      />,
    )
    expect(screen.getByText('No findings match these filters.')).toBeInTheDocument()
  })
})
