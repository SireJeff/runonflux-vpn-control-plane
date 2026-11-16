/**
 * API Client for FluxVPN Backend
 * Handles authentication, request/response interceptors, and error handling
 */
import axios, { AxiosInstance, AxiosError } from 'axios'
import toast from 'react-hot-toast'

const USER_PORTAL_DOMAIN = process.env.NEXT_PUBLIC_USER_PORTAL_DOMAIN || 'panel.operator5.example.invalid'

const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.location.hostname === USER_PORTAL_DOMAIN) {
    return '/api/v1' // Relative → proxied by Next.js rewrite
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080/api/v1'
}

const API_BASE_URL = getApiBaseUrl()

// Create axios instance
export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
})

// Request interceptor - Add JWT token
apiClient.interceptors.request.use(
  (config) => {
    // Get token from localStorage
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * Normalize a FastAPI error `detail` into a readable string.
 *
 * `detail` may be a plain string (our HTTPException) OR, for 422 validation
 * errors, a LIST of Pydantic error objects `{type, loc, msg, input, ctx, url}`.
 * Passing that array/object straight to a toast or JSX renders it as a React
 * child and throws "Objects are not valid as a React child" (React error #31),
 * which crashes the page. Always run error detail through this first.
 */
export function formatErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((e) => {
        if (e && typeof e === 'object' && typeof (e as any).msg === 'string') {
          const loc = (e as any).loc
          const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined
          return field ? `${field}: ${(e as any).msg}` : (e as any).msg
        }
        return typeof e === 'string' ? e : null
      })
      .filter((m): m is string => Boolean(m))
    if (msgs.length) return msgs.join('; ')
  }
  if (detail && typeof detail === 'object' && typeof (detail as any).msg === 'string') {
    return (detail as any).msg
  }
  return fallback
}

// Response interceptor - Handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      const status = error.response.status
      const data = error.response.data as any

      // Handle 401 Unauthorized - Attempt token refresh, then redirect
      if (status === 401) {
        if (typeof window !== 'undefined') {
          const refreshToken = localStorage.getItem('refresh_token')
          if (refreshToken && !error.config?.url?.includes('/auth/')) {
            localStorage.removeItem('token')
            document.cookie = 'auth_token=; path=/; max-age=0'
            // The refresh attempt is handled by the useAuth hook via react-query retry
            return Promise.reject(error)
          }
          localStorage.removeItem('token')
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('user_role')
          document.cookie = 'auth_token=; path=/; max-age=0'
          // Don't redirect if already on a login page
          const loginPath = window.location.hostname === USER_PORTAL_DOMAIN
            ? '/user/login'
            : '/login'
          if (!window.location.pathname.includes('login')) {
            window.location.href = loginPath
          }
        }
        toast.error('Session expired. Please login again.')
      }

      // Handle 403 Forbidden
      else if (status === 403) {
        toast.error('Access forbidden. Admin privileges required.')
      }

      // Handle 404 Not Found
      else if (status === 404) {
        toast.error(formatErrorDetail(data?.detail, 'Resource not found'))
      }

      // Handle 422 Validation Error
      else if (status === 422) {
        toast.error(formatErrorDetail(data?.detail, 'Validation error'))
      }

      // Handle 500 Server Error
      else if (status === 500) {
        toast.error('Server error. Please try again later.')
      }

      // Other errors
      else {
        toast.error(formatErrorDetail(data?.detail, 'An error occurred'))
      }
    } else if (error.request) {
      // Request made but no response
      toast.error('Network error. Please check your connection.')
    } else {
      // Something else happened
      toast.error('An unexpected error occurred')
    }

    return Promise.reject(error)
  }
)

/**
 * Helper function to handle API errors
 */
export function handleAPIError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return formatErrorDetail(
      error.response?.data?.detail,
      error.message || 'An error occurred'
    )
  }
  return String(error)
}

/**
 * Set authentication token (localStorage + cookie for middleware)
 */
export function setAuthToken(token: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('token', token)
    document.cookie = `auth_token=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`
  }
}

/**
 * Set refresh token (localStorage only)
 */
export function setRefreshToken(token: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('refresh_token', token)
  }
}

/**
 * Clear authentication tokens
 */
export function clearAuthToken() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_role')
    document.cookie = 'auth_token=; path=/; max-age=0'
  }
}

/**
 * Get authentication token
 */
export function getAuthToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('token')
  }
  return null
}

/**
 * Get refresh token
 */
export function getRefreshToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('refresh_token')
  }
  return null
}

/**
 * Get stored user role
 */
export function getUserRole(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('user_role')
  }
  return null
}

/**
 * Set stored user role
 */
export function setUserRole(role: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('user_role', role)
  }
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getAuthToken()
}
