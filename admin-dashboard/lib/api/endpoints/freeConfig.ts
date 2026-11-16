/**
 * Free Config API Endpoints
 * Manage the reseller's shared free public config (get / update / rotate).
 */
import { apiClient } from '../client'

export interface ChannelOut {
  id: number
  chat_id: number | null
  username: string | null
  title: string
  invite_url: string | null
}

export interface FreeConfig {
  is_enabled: boolean
  kind: string
  label: string | null
  region: string | null
  traffic_limit_gb: string | null
  duration_days: number | null
  has_credential: boolean
  daily_limit_mb: number | null
  max_free_users: number | null
  global_ceiling_mb: number | null
  global_channels: ChannelOut[]
}

export type FreeConfigUpdate = Partial<
  Pick<
    FreeConfig,
    | 'is_enabled'
    | 'kind'
    | 'label'
    | 'region'
    | 'traffic_limit_gb'
    | 'duration_days'
    | 'daily_limit_mb'
    | 'max_free_users'
  >
>

export const freeConfigApi = {
  /**
   * Get the current free config
   */
  get: async (): Promise<FreeConfig> => {
    const response = await apiClient.get('/admin/free-config')
    return response.data
  },

  /**
   * Update free config fields.
   * `region` must be a valid macro-region code (eu/as/na/row) or null else 422.
   */
  update: async (payload: FreeConfigUpdate): Promise<FreeConfig> => {
    const response = await apiClient.put('/admin/free-config', payload)
    return response.data
  },

  /**
   * Provision / rotate the shared credential
   */
  rotate: async (): Promise<FreeConfig> => {
    const response = await apiClient.post('/admin/free-config/rotate')
    return response.data
  },

  /**
   * List required Telegram channels for the free config.
   */
  listChannels: async (): Promise<ChannelOut[]> =>
    (await apiClient.get('/admin/free-config/channels')).data,

  /**
   * Add a required channel by identifier (@username or -100... chat id).
   */
  addChannel: async (identifier: string, invite_url?: string): Promise<ChannelOut> =>
    (await apiClient.post('/admin/free-config/channels', { identifier, invite_url })).data,

  /**
   * Delete a required channel by id.
   */
  deleteChannel: async (id: number): Promise<void> => {
    await apiClient.delete(`/admin/free-config/channels/${id}`)
  },
}
