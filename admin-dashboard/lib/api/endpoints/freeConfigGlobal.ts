/**
 * Global Free Config API Endpoints (Superadmin)
 * Manage the platform-wide free-config policy: global toggle, ceiling,
 * max free users, write-only verification bot token, and global required channels.
 */
import { apiClient } from '../client'
import type { ChannelOut } from './freeConfig'

export interface FreeConfigGlobal {
  is_enabled: boolean
  default_daily_limit_mb: number | null
  default_max_free_users: number | null
  has_token: boolean
  verification_bot_username: string | null
}

export type FreeConfigGlobalUpdate = Partial<
  Pick<
    FreeConfigGlobal,
    'is_enabled' | 'default_daily_limit_mb' | 'default_max_free_users'
  >
>

export interface SetTokenResponse {
  verification_bot_username: string | null
}

export const freeConfigGlobalApi = {
  /**
   * Get the global free-config policy. Never returns the token value; only
   * `has_token` and the derived bot username.
   */
  get: async (): Promise<FreeConfigGlobal> => {
    const response = await apiClient.get('/super/free-config/global')
    return response.data
  },

  /**
   * Update the global toggle, ceiling (MB), and max-free-users defaults.
   */
  update: async (payload: FreeConfigGlobalUpdate): Promise<FreeConfigGlobal> => {
    const response = await apiClient.put('/super/free-config/global', payload)
    return response.data
  },

  /**
   * Write-only: set the verification bot token. The token is never read back.
   */
  setToken: async (token: string): Promise<SetTokenResponse> => {
    const response = await apiClient.put('/super/free-config/global/token', { token })
    return response.data
  },

  /**
   * List required global Telegram channels.
   */
  listChannels: async (): Promise<ChannelOut[]> =>
    (await apiClient.get('/super/free-config/channels')).data,

  /**
   * Add a required global channel by identifier (@username or -100... chat id).
   */
  addChannel: async (identifier: string, invite_url?: string): Promise<ChannelOut> =>
    (await apiClient.post('/super/free-config/channels', { identifier, invite_url })).data,

  /**
   * Delete a required global channel by id.
   */
  deleteChannel: async (id: number): Promise<void> => {
    await apiClient.delete(`/super/free-config/channels/${id}`)
  },
}
