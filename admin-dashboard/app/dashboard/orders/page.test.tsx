import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Order } from '@/lib/api'
import OrdersPage from './page'

// Mock the API client so the page renders deterministically without network.
vi.mock('@/lib/api', () => ({
  api: {
    orders: {
      list: vi.fn(),
      getReceiptUrl: vi.fn(),
      approve: vi.fn(),
      reject: vi.fn(),
    },
  },
}))

// jsdom has no object-URL implementation; the cleanup effect calls revoke.
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:fake')
  URL.revokeObjectURL = vi.fn()
})

import { api } from '@/lib/api'

function baseOrder(overrides: Partial<Order>): Order {
  return {
    id: 123,
    kind: 'subscription',
    user_id: 7,
    admin_id: 1,
    package_id: 1,
    package_snapshot: { name: 'Basic', traffic_gb: 50, duration_days: 30 },
    macro_region: 'eu',
    amount_tomans: '300000',
    wallet_credit_applied_tomans: '0',
    status: 'approved',
    reviewer_admin_id: 1,
    reviewed_at: '2026-08-19T00:00:00Z',
    rejection_reason: null,
    receipt_file_id: 'file-abc',
    receipt_local_path: '/data/receipts/123.jpg',
    payment_method: 'card',
    crypto_txid: null,
    crypto_link: null,
    amount_usd_snapshot: null,
    created_at: '2026-08-18T00:00:00Z',
    expires_at: '2026-09-18T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <OrdersPage />
    </QueryClientProvider>,
  )
}

describe('OrdersPage receipt visibility', () => {
  it('shows the receipt for an APPROVED card order that has a receipt', async () => {
    vi.mocked(api.orders.list).mockResolvedValue([
      baseOrder({ status: 'approved', receipt_file_id: 'file-abc' }),
    ])
    vi.mocked(api.orders.getReceiptUrl).mockResolvedValue('blob:fake')

    renderPage()

    // Open the detail modal for the approved order.
    const row = await screen.findByText('#123')
    fireEvent.click(row)

    // The receipt image must be rendered even though status is 'approved'.
    const img = await screen.findByAltText('Payment receipt')
    expect(img).toHaveAttribute('src', 'blob:fake')
  })

  it('shows no receipt block for an approved card order that never had a receipt', async () => {
    vi.mocked(api.orders.list).mockResolvedValue([
      baseOrder({ status: 'approved', receipt_file_id: null, receipt_local_path: null }),
    ])

    renderPage()

    const row = await screen.findByText('#123')
    fireEvent.click(row)

    // Modal open (unique dialog title), but no receipt section rendered.
    await screen.findByText('Order #123')
    expect(screen.queryByText('Payment Receipt')).not.toBeInTheDocument()
  })
})
