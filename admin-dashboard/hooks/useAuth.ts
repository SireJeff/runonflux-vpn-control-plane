/**
 * Authentication Hook
 * Manages user authentication state, roles, and operations
 */
'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import { api } from '@/lib/api'
import {
  setAuthToken,
  clearAuthToken,
  getAuthToken,
  setRefreshToken,
  getRefreshToken,
  setUserRole,
  getUserRole,
} from '@/lib/api/client'
import type { AuthResponse, UserResponse, LoginRequest } from '@/types/api'

export function useAuth() {
  const router = useRouter()
  const queryClient = useQueryClient()

  // Query to get current user (if token exists)
  const {
    data: user,
    isLoading,
    error,
  } = useQuery<UserResponse | null>({
    queryKey: ['auth', 'user'],
    queryFn: async () => {
      const token = getAuthToken()
      if (!token) return null

      try {
        const user = await api.auth.verifyToken()
        setUserRole(user.role)
        return user
      } catch {
        // Attempt token refresh
        const refreshToken = getRefreshToken()
        if (refreshToken) {
          try {
            const response = await api.auth.refreshToken(refreshToken)
            setAuthToken(response.access_token)
            if (response.refresh_token) {
              setRefreshToken(response.refresh_token)
            }
            setUserRole(response.role)
            return {
              id: 0,
              username: response.username,
              role: response.role as UserResponse['role'],
              display_name: response.display_name,
              status: 'active',
            } satisfies UserResponse
          } catch {
            clearAuthToken()
            return null
          }
        }
        clearAuthToken()
        return null
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false,
  })

  // Derive role from user data or stored role
  const role = user?.role || getUserRole()

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: async (data: LoginRequest) => {
      const response = await api.auth.login(data)
      return response
    },
    onSuccess: (data) => {
      setAuthToken(data.access_token)
      if (data.refresh_token) {
        setRefreshToken(data.refresh_token)
      }
      setUserRole(data.role)

      // Seed the auth cache so any mounted component using useAuth sees the
      // user immediately (otherwise the cache stays null from the initial
      // no-token load and components act as if not authenticated until refresh).
      queryClient.setQueryData(['auth', 'user'], {
        id: 0,
        username: data.username,
        role: data.role as UserResponse['role'],
        display_name: data.display_name,
        status: 'active',
      } satisfies UserResponse)
      queryClient.invalidateQueries({ queryKey: ['auth', 'user'] })

      toast.success(`Welcome back, ${data.display_name || data.username}!`)

      // Redirect based on role
      switch (data.role) {
        case 'super_admin':
          router.push('/super/dashboard')
          break
        case 'admin':
          router.push('/dashboard')
          break
        case 'end_user':
          router.push('/user/connections')
          break
        default:
          router.push('/login')
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Login failed')
    },
  })

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: async () => {
      await api.auth.logout()
    },
    onSuccess: () => {
      clearAuthToken()
      queryClient.setQueryData(['auth', 'user'], null)
      queryClient.clear()
      toast.success('Logged out successfully')
      router.push('/login')
    },
  })

  return {
    user,
    role,
    isLoading,
    isAuthenticated: !!user,
    isSuperAdmin: role === 'super_admin',
    isAdmin: role === 'admin',
    isEndUser: role === 'end_user',
    login: loginMutation.mutate,
    logout: logoutMutation.mutate,
    isLoggingIn: loginMutation.isPending,
    isLoggingOut: logoutMutation.isPending,
  }
}
