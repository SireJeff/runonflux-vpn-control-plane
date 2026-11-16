/**
 * Orders API Endpoints
 * List, view, approve, reject orders + receipt download
 */
import { apiClient } from '../client'

export interface PackageSnapshot {
  name?: string
  traffic_gb?: number
  duration_days?: number
  price_tomans?: string
}

export interface Order {
  id: number
  kind: 'subscription' | 'topup'
  user_id: number
  admin_id: number
  package_id: number | null
  package_snapshot: PackageSnapshot
  macro_region: string
  amount_tomans: string // Pydantic Decimal → string
  wallet_credit_applied_tomans: string
  status: 'pending' | 'approved' | 'rejected'
  reviewer_admin_id: number | null
  reviewed_at: string | null
  rejection_reason: string | null
  receipt_file_id: string | null
  receipt_local_path: string | null
  payment_method: 'card' | 'crypto'
  crypto_txid: string | null
  crypto_link: string | null
  amount_usd_snapshot: string | null
  created_at: string
  expires_at: string | null
}

export const ordersApi = {
  /**
   * List orders, optionally filtered by status
   */
  list: async (status?: string): Promise<Order[]> => {
    const response = await apiClient.get('/admin/orders', {
      params: status ? { status } : undefined,
    })
    return response.data
  },

  /**
   * Get a single order
   */
  get: async (id: number): Promise<Order> => {
    const response = await apiClient.get(`/admin/orders/${id}`)
    return response.data
  },

  /**
   * Get receipt image as blob URL
   * Returns null if no receipt available
   */
  getReceiptUrl: async (id: number): Promise<string | null> => {
    const response = await apiClient.get(`/admin/orders/${id}/receipt`, {
      responseType: 'blob',
    })
    if (response.data instanceof Blob) {
      return URL.createObjectURL(response.data)
    }
    return null
  },

  /**
   * Approve an order
   */
  approve: async (id: number): Promise<Order> => {
    const response = await apiClient.post(`/admin/orders/${id}/approve`)
    return response.data
  },

  /**
   * Reject an order
   */
  reject: async (id: number, reason?: string): Promise<Order> => {
    const response = await apiClient.post(`/admin/orders/${id}/reject`, {
      reason,
    })
    return response.data
  },
}
