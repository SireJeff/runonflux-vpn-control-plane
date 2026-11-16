/**
 * Authentication API Endpoints
 */
import { apiClient } from '../client'
import type { AuthResponse, LoginRequest, RegisterRequest, UserResponse } from '@/types/api'

export const authApi = {
  /**
   * Login with username + password
   */
  login: async (data: LoginRequest): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/login', data)
    return response.data
  },

  /**
   * Register a new admin user
   */
  register: async (data: RegisterRequest): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/register', data)
    return response.data
  },

  /**
   * Get current authenticated user
   */
  verifyToken: async (): Promise<UserResponse> => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },

  /**
   * Refresh access token
   */
  refreshToken: async (refresh_token: string): Promise<AuthResponse> => {
    const response = await apiClient.post('/auth/refresh', { refresh_token })
    return response.data
  },

  /**
   * Logout
   */
  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout')
  },
}
