/**
 * Bot Config API Endpoints
 * Register and manage Telegram bot configuration for reseller end-user bot
 */
import { apiClient } from '../client'

export interface BotConfig {
  id: number
  admin_id: number
  bot_username: string
  bot_user_id: number
  bot_display_name: string | null
  welcome_message_fa: string | null
  welcome_message_en: string | null
  card_number: string | null
  card_holder_name: string | null
  crypto_address: string | null
  crypto_network: string | null
  crypto_memo: string | null
  support_phone: string | null
  support_telegram: string | null
  default_macro_region: string
  is_active: boolean
  webhook_registered_at: string | null
  created_at: string
}

export interface BotConfigCreateRequest {
  bot_token: string
  bot_display_name?: string
  welcome_message_fa?: string
  welcome_message_en?: string
  card_number?: string
  card_holder_name?: string
  crypto_address?: string
  crypto_network?: string
  crypto_memo?: string
  support_phone?: string
  support_telegram?: string
  default_macro_region?: string
}

export interface BotTestPingResult {
  ok: boolean
  bot_username: string
  webhook_url: string | null
  pending_update_count: number | null
  last_error_message: string | null
  dm_sent: boolean
  detail: string
}

export interface BotConfigUpdateRequest {
  bot_display_name?: string
  welcome_message_fa?: string
  welcome_message_en?: string
  card_number?: string
  card_holder_name?: string
  crypto_address?: string
  crypto_network?: string
  crypto_memo?: string
  support_phone?: string
  support_telegram?: string
  default_macro_region?: string
}

export const botConfigApi = {
  /**
   * Get current bot config (returns 404 if not yet configured)
   */
  get: async (): Promise<BotConfig> => {
    const response = await apiClient.get('/admin/bot-config')
    return response.data
  },

  /**
   * Register a new bot (POST — includes bot_token)
   */
  create: async (data: BotConfigCreateRequest): Promise<BotConfig> => {
    const response = await apiClient.post('/admin/bot-config', data)
    return response.data
  },

  /**
   * Update existing bot config (PUT — no bot_token)
   */
  update: async (data: BotConfigUpdateRequest): Promise<BotConfig> => {
    const response = await apiClient.put('/admin/bot-config', data)
    return response.data
  },

  /**
   * Deactivate the bot
   */
  deactivate: async (): Promise<BotConfig> => {
    const response = await apiClient.post('/admin/bot-config/deactivate')
    return response.data
  },

  /**
   * Reactivate a previously deactivated bot
   */
  reactivate: async (): Promise<BotConfig> => {
    const response = await apiClient.post('/admin/bot-config/reactivate')
    return response.data
  },

  /**
   * Diagnose the reseller's own bot (token + webhook health + live DM).
   */
  testPing: async (): Promise<BotTestPingResult> => {
    const response = await apiClient.post('/admin/bot-config/test')
    return response.data
  },
}
