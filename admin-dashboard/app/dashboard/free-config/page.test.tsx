import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { api } from '@/lib/api'
import FreeConfigPage from './page'

vi.mock('@/lib/api', () => ({
  api: {
    freeConfig: {
      get: vi.fn(),
      update: vi.fn(),
      rotate: vi.fn(),
      listChannels: vi.fn(),
      addChannel: vi.fn(),
      deleteChannel: vi.fn(),
    },
  },
}))

function renderPage() {
  const c = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={c}>
      <FreeConfigPage />
    </QueryClientProvider>,
  )
}

describe('FreeConfigPage per-user mode', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('exposes the per-user region and saves the daily allowance without shared rotation', async () => {
    vi.mocked(api.freeConfig.get).mockResolvedValue({
      is_enabled: true, kind: 'per_user', region: 'eu', daily_limit_mb: 1024,
      global_ceiling_mb: 2000, global_channels: [], has_credential: false,
    } as any)
    vi.mocked(api.freeConfig.listChannels).mockResolvedValue([])
    vi.mocked(api.freeConfig.update).mockResolvedValue({} as any)
    renderPage()
    await waitFor(() => expect(screen.getByLabelText(/^region$/i)).toHaveTextContent('Europe'))
    expect(screen.queryByRole('button', { name: /rotate/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(api.freeConfig.update).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'per_user', region: 'eu', daily_limit_mb: 1024 }),
    ))
  })

  it('blocks save when daily limit exceeds the global ceiling', async () => {
    vi.mocked(api.freeConfig.get).mockResolvedValue({
      is_enabled: true,
      kind: 'per_user',
      label: null,
      region: null,
      traffic_limit_gb: null,
      duration_days: null,
      has_credential: false,
      daily_limit_mb: 100,
      max_free_users: null,
      global_ceiling_mb: 200,
      global_channels: [],
    } as any)
    vi.mocked(api.freeConfig.listChannels).mockResolvedValue([])
    renderPage()
    await waitFor(() => screen.getByLabelText(/daily limit/i))
    fireEvent.change(screen.getByLabelText(/daily limit/i), { target: { value: '5000' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(await screen.findByText(/cannot exceed/i)).toBeInTheDocument()
    expect(api.freeConfig.update).not.toHaveBeenCalled()
  })

  it('adds a channel row via the editor', async () => {
    vi.mocked(api.freeConfig.get).mockResolvedValue({
      kind: 'per_user',
      global_ceiling_mb: 200,
      global_channels: [],
      daily_limit_mb: 200,
      is_enabled: true,
    } as any)
    vi.mocked(api.freeConfig.listChannels).mockResolvedValue([])
    vi.mocked(api.freeConfig.addChannel).mockResolvedValue({ id: 1, username: '@x', title: 'X' } as any)
    renderPage()
    await waitFor(() => screen.getByPlaceholderText(/@channel/i))
    fireEvent.change(screen.getByPlaceholderText(/@channel/i), { target: { value: '@x' } })
    fireEvent.click(screen.getByRole('button', { name: /add channel/i }))
    await waitFor(() => expect(api.freeConfig.addChannel).toHaveBeenCalledWith('@x', undefined))
  })
})
