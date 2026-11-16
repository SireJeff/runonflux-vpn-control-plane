import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../client', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}))

import { apiClient } from '../../client'
import { settingsApi } from '../settings'

describe('settingsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads system settings from backend', async () => {
    const settings = { trial_days: 3 }
    vi.mocked(apiClient.get).mockResolvedValue({ data: settings })

    const result = await settingsApi.getSettings()

    expect(apiClient.get).toHaveBeenCalledWith('/admin/settings')
    expect(result).toEqual(settings)
  })

  it('updates system settings via backend', async () => {
    const update = { maintenance_mode: true }
    vi.mocked(apiClient.put).mockResolvedValue({ data: update })

    const result = await settingsApi.updateSettings(update)

    expect(apiClient.put).toHaveBeenCalledWith('/admin/settings', update)
    expect(result).toEqual(update)
  })

  it('calls admin promotion endpoint by user id', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { message: 'ok' } })

    await settingsApi.addAdmin(42)

    expect(apiClient.post).toHaveBeenCalledWith('/admin/users/42/make-admin')
  })
})
