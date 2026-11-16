/**
 * User Management API Endpoints
 */
import { apiClient } from '../client'
import type { UserResponse, UserUpdate, SuccessResponse } from '@/types/api'

export const usersApi = {
  /**
   * List all users (admin only)
   */
  list: async (params?: {
    skip?: number
    limit?: number
    search?: string
  }): Promise<UserResponse[]> => {
    const response = await apiClient.get('/users', { params })
    return response.data
  },

  /**
   * Get user by ID
   */
  get: async (userId: number): Promise<UserResponse> => {
    const response = await apiClient.get(`/users/${userId}`)
    return response.data
  },

  /**
   * Update user
   */
  update: async (userId: number, data: UserUpdate): Promise<UserResponse> => {
    const response = await apiClient.put(`/users/${userId}`, data)
    return response.data
  },

  /**
   * Delete user
   */
  delete: async (userId: number): Promise<SuccessResponse> => {
    const response = await apiClient.delete(`/users/${userId}`)
    return response.data
  },

  /**
   * Get current authenticated user
   */
  getCurrentUser: async (): Promise<UserResponse> => {
    const response = await apiClient.get('/users/me')
    return response.data
  },
}
