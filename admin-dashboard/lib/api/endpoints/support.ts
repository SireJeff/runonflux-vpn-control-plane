/**
 * Support Ticket API Endpoints
 */
import { apiClient } from '../client'
import type {
  TicketResponse,
  TicketDetailResponse,
  TicketMessageResponse,
  TicketStats,
  SuccessResponse,
} from '@/types/api'

export const supportApi = {
  /**
   * List all tickets (admin)
   */
  listAllTickets: async (params?: {
    status_filter?: string
    category_filter?: string
    priority_filter?: string
    assigned_filter?: boolean
    search?: string
    limit?: number
    offset?: number
  }): Promise<TicketResponse[]> => {
    const response = await apiClient.get('/support/admin/tickets', { params })
    return response.data
  },

  /**
   * Get ticket details with messages
   */
  getTicket: async (ticketId: number): Promise<TicketDetailResponse> => {
    const response = await apiClient.get(`/support/tickets/${ticketId}`)
    return response.data
  },

  /**
   * Assign ticket to admin
   */
  assignTicket: async (ticketId: number, adminId?: number): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/support/admin/tickets/${ticketId}/assign`, {
      admin_id: adminId,
    })
    return response.data
  },

  /**
   * Resolve ticket
   */
  resolveTicket: async (ticketId: number): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/support/admin/tickets/${ticketId}/resolve`)
    return response.data
  },

  /**
   * Add message to ticket
   */
  addMessage: async (
    ticketId: number,
    data: { message: string; is_internal: boolean }
  ): Promise<TicketMessageResponse> => {
    const response = await apiClient.post(`/support/tickets/${ticketId}/messages`, data)
    return response.data
  },

  /**
   * Get ticket statistics
   */
  getStats: async (): Promise<TicketStats> => {
    const response = await apiClient.get('/support/admin/stats')
    return response.data
  },
}
