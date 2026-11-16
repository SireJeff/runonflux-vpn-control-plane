import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

import { apiClient } from '../../client'
import { logsApi } from '../logs'

describe('logsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches logs list from backend', async () => {
    const logs = [{ id: 1, message: 'test' }]
    vi.mocked(apiClient.get).mockResolvedValue({ data: logs })

    const result = await logsApi.listLogs({ level: 'INFO' })

    expect(apiClient.get).toHaveBeenCalledWith('/admin/logs', {
      params: { level: 'INFO' },
    })
    expect(result).toEqual(logs)
  })

  it('exports logs as csv blob', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [
        {
          id: 7,
          timestamp: '2026-02-20T00:00:00Z',
          level: 'INFO',
          source: 'auth',
          message: 'Auth success',
        },
      ],
    })

    const blob = await logsApi.exportLogs()
    const text = await blob.text()

    expect(text).toContain('id,timestamp,level,source,message,user_id')
    expect(text).toContain('7,2026-02-20T00:00:00Z,INFO,auth')
  })
})
