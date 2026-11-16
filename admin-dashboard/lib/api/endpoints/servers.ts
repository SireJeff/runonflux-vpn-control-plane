/**
 * Servers API Endpoints
 */
import { apiClient } from '../client'

export interface ServerInstance {
  id: number
  protocol_id: number
  protocol_name: string
  country_code: string
  country_name: string
  public_ip: string
  port: number
  health_status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  active_connections: number
  is_active: boolean
  created_at: string
  last_health_check: string | null
}

export interface ServerStats {
  total_instances: number
  healthy_instances: number
  degraded_instances: number
  unhealthy_instances: number
  total_countries: number
  total_connections: number
  avg_health_score: number
}

export interface ServerFilters {
  protocol_id?: number
  country_code?: string
  health_status?: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
}

export const serversApi = {
  listInstances: async (filters?: ServerFilters): Promise<ServerInstance[]> => {
    const response = await apiClient.get('/admin/servers/instances', { params: filters })
    return response.data
  },

  getInstanceStats: async (): Promise<ServerStats> => {
    const response = await apiClient.get('/admin/servers/stats')
    return response.data
  },

  getInstanceById: async (id: number): Promise<ServerInstance | null> => {
    const instances = await serversApi.listInstances()
    return instances.find(i => i.id === id) || null
  },
}
