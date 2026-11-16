/**
 * Usage & Bandwidth Analytics API Endpoints
 */
import { apiClient } from '../client'

export interface UsageSummary {
  protocol_id: number
  date: string
  uploaded_gb: number
  downloaded_gb: number
  total_gb: number
  connections: number
  unique_users: number
}

export interface UsageAnalyticsResponse {
  summaries: UsageSummary[]
}

export interface BandwidthDataPoint {
  period_start: string
  uploaded_gb: number
  downloaded_gb: number
  total_gb: number
}

export interface BandwidthAnalyticsResponse {
  period_type: string
  data: BandwidthDataPoint[]
}

export const usageEndpoints = {
  /**
   * Get usage analytics summaries
   */
  getUsageAnalytics: async (params?: {
    period?: string
    protocol_id?: number
    start_date?: string
    end_date?: string
  }): Promise<UsageAnalyticsResponse> => {
    const { data } = await apiClient.get('/admin/analytics/usage', { params })
    return data
  },

  /**
   * Get bandwidth timeseries data
   */
  getBandwidthTimeseries: async (params?: {
    period_type?: string
    limit?: number
  }): Promise<BandwidthAnalyticsResponse> => {
    const { data } = await apiClient.get('/admin/analytics/bandwidth', { params })
    return data
  },
}
