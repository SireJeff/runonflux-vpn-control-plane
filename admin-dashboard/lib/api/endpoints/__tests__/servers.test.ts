import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

import { apiClient } from '../../client'
import { serversApi } from '../servers'

describe('serversApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches instances from backend endpoint', async () => {
    const payload = [{ id: 1 }]
    vi.mocked(apiClient.get).mockResolvedValue({ data: payload })

    const result = await serversApi.listInstances({ country_code: 'US' })

    expect(apiClient.get).toHaveBeenCalledWith('/admin/servers/instances', {
      params: { country_code: 'US' },
    })
    expect(result).toEqual(payload)
  })

  it('fetches server stats from backend endpoint', async () => {
    const stats = { total_instances: 1 }
    vi.mocked(apiClient.get).mockResolvedValue({ data: stats })

    const result = await serversApi.getInstanceStats()

    expect(apiClient.get).toHaveBeenCalledWith('/admin/servers/stats')
    expect(result).toEqual(stats)
  })
})
