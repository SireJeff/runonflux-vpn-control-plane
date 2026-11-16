import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../client', () => ({
  apiClient: { get: vi.fn(), put: vi.fn(), post: vi.fn() },
}))

import { apiClient } from '../../client'
import { adminNewApi } from '../admin-api'

describe('adminNewApi.getPanelUrl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches the reseller panel url', async () => {
    const payload = { panel_url: 'https://panel.acme.info', domain: 'panel.acme.info', is_fallback: false }
    vi.mocked(apiClient.get).mockResolvedValue({ data: payload })

    const result = await adminNewApi.getPanelUrl()

    expect(apiClient.get).toHaveBeenCalledWith('/admin/panel-url')
    expect(result).toEqual(payload)
  })
})
