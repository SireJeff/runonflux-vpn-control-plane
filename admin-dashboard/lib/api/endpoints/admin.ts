/**
 * Admin API Endpoints
 */
import { apiClient } from '../client'
import type {
  DashboardStats,
  RevenueAnalytics,
  UserGrowthAnalytics,
  ProtocolStats,
  CountryStats,
  TopUser,
  SystemHealth,
  AlertStats,
  SuccessResponse,
} from '@/types/api'

export const adminApi = {
  /**
   * Get dashboard statistics
   */
  getDashboardStats: async (): Promise<DashboardStats> => {
    const response = await apiClient.get('/admin/dashboard')
    return response.data
  },

  /**
   * Get revenue analytics
   */
  getRevenueAnalytics: async (params: {
    period?: 'daily' | 'weekly' | 'monthly'
    days?: number
  }): Promise<RevenueAnalytics> => {
    const response = await apiClient.get('/admin/analytics/revenue', { params })
    return response.data
  },

  /**
   * Get user growth analytics
   */
  getUserGrowthAnalytics: async (params: {
    period?: 'daily' | 'weekly' | 'monthly'
    days?: number
  }): Promise<UserGrowthAnalytics> => {
    const response = await apiClient.get('/admin/analytics/users', { params })
    return response.data
  },

  /**
   * Get protocol statistics
   */
  getProtocolStats: async (): Promise<ProtocolStats[]> => {
    const response = await apiClient.get('/admin/analytics/protocols')
    return response.data
  },

  /**
   * Get country statistics
   */
  getCountryStats: async (): Promise<CountryStats[]> => {
    const response = await apiClient.get('/admin/analytics/countries')
    return response.data
  },

  /**
   * Get top users by spending
   */
  getTopUsers: async (limit: number = 10): Promise<TopUser[]> => {
    const response = await apiClient.get('/admin/analytics/top-users', {
      params: { limit },
    })
    return response.data
  },

  /**
   * Get system health
   */
  getSystemHealth: async (): Promise<SystemHealth> => {
    const response = await apiClient.get('/admin/system/health')
    return response.data
  },

  /**
   * Get admin alerts
   */
  getAlerts: async (limit: number = 10): Promise<AlertStats> => {
    const response = await apiClient.get('/admin/alerts', { params: { limit } })
    return response.data
  },

  /**
   * Acknowledge alert
   */
  acknowledgeAlert: async (alertId: number): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/admin/alerts/${alertId}/acknowledge`)
    return response.data
  },
}
