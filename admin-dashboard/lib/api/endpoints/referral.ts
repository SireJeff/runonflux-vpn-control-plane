/**
 * Referral API Endpoints
 * Config, stats, and earnings for the referral program
 */
import { apiClient } from '../client'

export interface ReferralConfig {
  admin_id: number
  is_enabled: boolean
  reward_percentage: string // Pydantic Decimal → string
  reward_type: 'cashback' | 'traffic' | 'both'
  traffic_per_referral_mb: number
  traffic_max_bonus_mb: number
  updated_at: string
}

export interface ReferralConfigUpdate {
  is_enabled?: boolean
  reward_percentage?: number
  reward_type?: 'cashback' | 'traffic' | 'both'
  traffic_per_referral_mb?: number
  traffic_max_bonus_mb?: number
}

export interface ReferralStats {
  my_referral_code: string | null
  total_referrals: number
  total_earned_tomans: string // Pydantic Decimal → string
  wallet_credit_tomans: string // Pydantic Decimal → string
}

export interface ReferralEarning {
  id: number
  order_id: number
  commission_percent: string // Pydantic Decimal → string
  amount_tomans: string // Pydantic Decimal → string
  created_at: string
}

export const referralApi = {
  /**
   * Get referral config (auto-creates if missing)
   */
  getConfig: async (): Promise<ReferralConfig> => {
    const response = await apiClient.get('/admin/referral/config')
    return response.data
  },

  /**
   * Update referral config
   */
  updateConfig: async (data: ReferralConfigUpdate): Promise<ReferralConfig> => {
    const response = await apiClient.put('/admin/referral/config', data)
    return response.data
  },

  /**
   * Get referral stats
   */
  getStats: async (): Promise<ReferralStats> => {
    const response = await apiClient.get('/admin/referral/stats')
    return response.data
  },

  /**
   * Get referral earnings
   */
  getEarnings: async (limit = 50): Promise<ReferralEarning[]> => {
    const response = await apiClient.get('/admin/referral/earnings', {
      params: { limit },
    })
    return response.data
  },
}
