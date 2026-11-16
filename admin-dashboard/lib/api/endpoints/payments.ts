/**
 * Payment & Transaction API Endpoints
 */
import { apiClient } from '../client'
import type { WalletTransactionResponse, SuccessResponse } from '@/types/api'

export const paymentsApi = {
  /**
   * List all transactions (admin)
   */
  listTransactions: async (params?: {
    user_id?: number
    transaction_type?: string
    status?: string
    limit?: number
    offset?: number
  }): Promise<WalletTransactionResponse[]> => {
    const response = await apiClient.get('/admin/transactions', { params })
    return response.data
  },

  /**
   * Get transaction details
   */
  getTransaction: async (transactionId: number): Promise<WalletTransactionResponse> => {
    const response = await apiClient.get(`/admin/transactions/${transactionId}`)
    return response.data
  },

  /**
   * Get pending withdrawals
   */
  getPendingWithdrawals: async (): Promise<WalletTransactionResponse[]> => {
    const response = await apiClient.get('/admin/withdrawals/pending')
    return response.data
  },

  /**
   * Approve withdrawal
   */
  approveWithdrawal: async (transactionId: number): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/admin/withdrawals/${transactionId}/approve`)
    return response.data
  },

  /**
   * Reject withdrawal
   */
  rejectWithdrawal: async (
    transactionId: number,
    reason: string
  ): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/admin/withdrawals/${transactionId}/reject`, {
      reason,
    })
    return response.data
  },

  /**
   * Refund transaction
   */
  refundTransaction: async (transactionId: number): Promise<SuccessResponse> => {
    const response = await apiClient.post(`/admin/transactions/${transactionId}/refund`)
    return response.data
  },
}
