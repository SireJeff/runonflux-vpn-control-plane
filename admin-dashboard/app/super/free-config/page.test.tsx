import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi } from 'vitest'
import { api } from '@/lib/api'
import GlobalFreeConfigPage from './page'

vi.mock('@/lib/api', () => ({
  api: {
    freeConfigGlobal: {
      get: vi.fn(),
      update: vi.fn(),
      setToken: vi.fn(),
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
      <GlobalFreeConfigPage />
    </QueryClientProvider>,
  )
}

describe('GlobalFreeConfigPage', () => {
  it('shows token status without exposing the token value', async () => {
    vi.mocked(api.freeConfigGlobal.get).mockResolvedValue({
      is_enabled: true,
      default_daily_limit_mb: 200,
      default_max_free_users: null,
      has_token: true,
      verification_bot_username: 'checkbot',
    } as any)
    vi.mocked(api.freeConfigGlobal.listChannels).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(/checkbot/i)).toBeInTheDocument()
    expect(screen.queryByDisplayValue(/123:/)).not.toBeInTheDocument()
  })

  it('submits a new token', async () => {
    vi.mocked(api.freeConfigGlobal.get).mockResolvedValue({
      has_token: false,
      default_daily_limit_mb: 200,
      is_enabled: false,
    } as any)
    vi.mocked(api.freeConfigGlobal.listChannels).mockResolvedValue([])
    vi.mocked(api.freeConfigGlobal.setToken).mockResolvedValue({
      verification_bot_username: 'checkbot',
    } as any)
    renderPage()
    await waitFor(() => screen.getByLabelText(/bot token/i))
    fireEvent.change(screen.getByLabelText(/bot token/i), { target: { value: '123:abc' } })
    fireEvent.click(screen.getByRole('button', { name: /save token/i }))
    await waitFor(() => expect(api.freeConfigGlobal.setToken).toHaveBeenCalledWith('123:abc'))
  })
})
