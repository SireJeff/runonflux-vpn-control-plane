/**
 * IP Management API Endpoints
 */
import { apiClient } from '../client'
import type { IPChangeRequestResponse } from '@/types/api'

export interface IPStats {
  total_ip_changes: number
  pending_requests: number
  completed_today: number
  failed_requests: number
  success_rate: number
}

export const ipManagementApi = {
  /**
   * List all IP change requests
   */
  listIPChanges: async (params?: { status?: string }): Promise<IPChangeRequestResponse[]> => {
    const response = await apiClient.get('/admin/ip-changes', { params })
    return response.data
  },

  /**
   * Get IP change statistics
   */
  getIPStats: async (): Promise<IPStats> => {
    const response = await apiClient.get('/admin/ip-stats')
    return response.data
  },
}
