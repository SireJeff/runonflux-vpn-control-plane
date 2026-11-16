/**
 * Settings API Endpoints
 * Manage system configuration and admin users
 */
import { apiClient } from '../client'

export interface SystemSettings {
  trial_days: number
  referral_commission_bronze: number
  referral_commission_silver: number
  referral_commission_gold: number
  referral_commission_platinum: number
  maintenance_mode: boolean
  max_ip_changes_per_month: number
}

export interface AdminUser {
  id: number
  telegram_username: string | null
  email: string | null
  is_admin: boolean
  created_at: string
}

export const settingsApi = {
  getSettings: async (): Promise<SystemSettings> => {
    const response = await apiClient.get('/admin/settings')
    return response.data
  },

  updateSettings: async (data: Partial<SystemSettings>): Promise<SystemSettings> => {
    const response = await apiClient.put('/admin/settings', data)
    return response.data
  },

  getAdmins: async (): Promise<AdminUser[]> => {
    const response = await apiClient.get('/admin/admins')
    return response.data
  },

  addAdmin: async (userId: number): Promise<{ message: string }> => {
    const response = await apiClient.post(`/admin/users/${userId}/make-admin`)
    return response.data
  },

  removeAdmin: async (adminId: number): Promise<{ message: string }> => {
    const response = await apiClient.post(`/admin/users/${adminId}/remove-admin`)
    return response.data
  },
}
