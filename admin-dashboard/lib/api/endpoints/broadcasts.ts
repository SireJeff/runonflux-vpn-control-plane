/**
 * Broadcasts API — reseller sends messages to end-users who started their bot.
 */
import { apiClient } from '../client'

export type BroadcastSegment =
  | 'all'
  | 'lang_fa'
  | 'lang_en'
  | 'active_paid'
  | 'expired_free'

export interface Broadcast {
  id: number
  admin_id: number
  segment: BroadcastSegment
  message_text: string
  button_label: string | null
  button_url: string | null
  status: 'queued' | 'sending' | 'completed' | 'failed'
  audience_count: number
  sent_count: number
  failed_count: number
  blocked_count: number
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface BroadcastCreateRequest {
  message_text: string
  button_label?: string
  button_url?: string
  segment: BroadcastSegment
}

export const broadcastsApi = {
  audienceCount: async (segment: BroadcastSegment): Promise<number> => {
    const response = await apiClient.post('/admin/broadcasts/audience-count', { segment })
    return response.data.count
  },

  create: async (data: BroadcastCreateRequest): Promise<Broadcast> => {
    const response = await apiClient.post('/admin/broadcasts', data)
    return response.data
  },

  list: async (limit = 50, offset = 0): Promise<Broadcast[]> => {
    const response = await apiClient.get('/admin/broadcasts', { params: { limit, offset } })
    return response.data
  },

  get: async (id: number): Promise<Broadcast> => {
    const response = await apiClient.get(`/admin/broadcasts/${id}`)
    return response.data
  },
}
