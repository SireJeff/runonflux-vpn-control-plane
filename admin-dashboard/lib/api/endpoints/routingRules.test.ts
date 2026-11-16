import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), put: vi.fn() },
}))

import { apiClient } from '../client'
import { routingRulesApi, PRESET_KEYS } from './routingRules'

describe('routingRulesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('get() calls the admin routing-rules endpoint', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { is_enabled: false } })
    await routingRulesApi.get()
    expect(apiClient.get).toHaveBeenCalledWith('/admin/routing-rules')
  })

  it('update() PUTs the payload', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ data: { is_enabled: true } })
    const payload = { is_enabled: true, ban_domains: ['x.com'], allow_domains: [], presets: {} }
    await routingRulesApi.update(payload)
    expect(apiClient.put).toHaveBeenCalledWith('/admin/routing-rules', payload)
  })

  it('exposes the preset catalog keys', () => {
    expect(PRESET_KEYS).toEqual(['block_ads', 'block_porn', 'iran_direct'])
  })
})
