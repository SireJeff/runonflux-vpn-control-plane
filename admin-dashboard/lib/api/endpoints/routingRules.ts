import { apiClient } from '../client'

export const PRESET_KEYS = ['block_ads', 'block_porn', 'iran_direct'] as const
export type PresetKey = (typeof PRESET_KEYS)[number]

export interface RoutingRules {
  is_enabled: boolean
  ban_domains: string[]
  allow_domains: string[]
  presets: Partial<Record<PresetKey, boolean>>
}

export type RoutingRulesUpdate = RoutingRules

export const routingRulesApi = {
  get: async (): Promise<RoutingRules> => {
    const response = await apiClient.get('/admin/routing-rules')
    return response.data
  },
  update: async (payload: RoutingRulesUpdate): Promise<RoutingRules> => {
    const response = await apiClient.put('/admin/routing-rules', payload)
    return response.data
  },
}
