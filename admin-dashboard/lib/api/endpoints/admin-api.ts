/**
 * Admin API Endpoints (New)
 * End user CRUD, wallet, connections, regions, analytics
 * These are the admin-facing endpoints at /api/v1/admin/*
 */
import { apiClient } from '../client'

// ============================================================================
// TYPES
// ============================================================================

export interface RegionInfo {
  macro_region: string
  assigned_at?: string | null
}

export interface CountryInfo {
  code: string
  name: string
  flag: string
  healthy_instances: number
}

export interface MacroRegionInfo {
  code: string
  name: string
  flag: string
  healthy_instances: number
  countries: CountryInfo[]
}

export interface EndUser {
  id: number
  username: string
  display_name?: string
  remark?: string
  status: string
  traffic_used_gb: number
  traffic_limit_gb?: number
  macro_region?: string
  created_at?: string
  subscription_url?: string
  expires_at?: string
}

export interface EndUserDetail {
  id: number
  username: string
  display_name?: string
  remark?: string
  status: string
  traffic_used_gb: number
  traffic_limit_gb?: number
  macro_region?: string
  macro_region_info?: RegionInfo
  macro_regions?: string[]
  adjustments?: Array<{
    id: number
    action: string
    details: Record<string, unknown>
    reason?: string | null
    created_at: string
  }>
  created_at?: string
  subscription_url?: string
  expires_at?: string
  telegram_id?: number | null
  telegram_chat_id?: number | null
}

export interface UserCreateRequest {
  username: string
  display_name?: string
  remark?: string
  macro_region?: string
  traffic_limit_gb?: number
}

export interface UserCreateResponse {
  id: number
  username: string
  password: string
  display_name: string | null
  remark: string | null
  status: string
  connection_strings: Record<string, Record<string, ProtocolConnections>>
  portal_url: string | null
}

export interface UserUpdateRequest {
  display_name?: string
  remark?: string
  new_password?: string
  traffic_limit_gb?: number | null
}

export interface UserListParams {
  status?: string
  search?: string
  page?: number
  per_page?: number
}

export interface PaginatedUsers {
  items: EndUser[]
  total: number
  page: number
  per_page: number
}

export interface UserRegion {
  macro_region: string
  assigned_at?: string | null
}

export interface ProtocolConnections {
  primary: string
  fallbacks: string[]
}

export interface ConnectionStrings {
  connections: Record<string, Record<string, ProtocolConnections>>
  telegram_proxies: Record<string, string>
  last_refreshed_at: string | null
}

export interface WalletInfo {
  balance: number
  recent_transactions: WalletTransaction[]
}

export interface PaymentConfig {
  crypto_enabled: boolean
  crypto_topup_address: string | null
  crypto_topup_network: string | null
  crypto_topup_memo: string | null
  min_topup_usd: number
  toman_per_usd_rate: number
}

export interface WalletTransaction {
  id: number
  amount_usd: number
  balance_after: number | null
  transaction_type: string
  description: string | null
  created_at: string | null
}

export interface TransactionListParams {
  page?: number
  per_page?: number
  type?: string
}

export interface PaginatedTransactions {
  items: WalletTransaction[]
  total: number
  page: number
  per_page: number
}

export interface WireOrderRequest {
  payment_method?: 'wire' | 'crypto'
  amount_tomans?: number
  amount_usd?: number
  contact_telegram: string
  contact_whatsapp?: string
  contact_phone?: string
  notes?: string
  crypto_txid?: string
  crypto_link?: string
}

export interface WireOrderResponse {
  id: number
  amount_tomans: string
  status: string
  message: string
}

export interface AdminAnalytics {
  total_users: number
  active_users: number
  total_traffic_gb: number
  total_cost_usd: number
  top_users_by_traffic: TopUserTraffic[]
  protocol_breakdown: ProtocolBreakdown[]
}

export interface TopUserTraffic {
  username: string
  traffic_gb: number
}

export interface ProtocolBreakdown {
  protocol: string
  traffic_gb: number
  user_count: number
}

export interface AvailableRegion {
  code: string
  name: string
  flag: string
  healthy_instances: number
  countries: CountryInfo[]
}

export interface PanelUrlResponse {
  panel_url: string
  domain: string | null
  is_fallback: boolean
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

export const adminNewApi = {
  // --- Users ---
  listUsers: async (params?: UserListParams): Promise<PaginatedUsers> => {
    const response = await apiClient.get('/admin/users', { params })
    return response.data
  },

  createUser: async (data: UserCreateRequest): Promise<UserCreateResponse> => {
    const response = await apiClient.post('/admin/users', data)
    return response.data
  },

  getUser: async (userId: number): Promise<EndUserDetail> => {
    const response = await apiClient.get(`/admin/users/${userId}`)
    return response.data
  },

  updateUser: async (userId: number, data: UserUpdateRequest): Promise<EndUserDetail> => {
    const response = await apiClient.put(`/admin/users/${userId}`, data)
    return response.data
  },

  deleteUser: async (userId: number): Promise<{ message: string }> => {
    const response = await apiClient.delete(`/admin/users/${userId}`)
    return response.data
  },

  toggleUser: async (userId: number): Promise<EndUser> => {
    const response = await apiClient.post(`/admin/users/${userId}/toggle`)
    return response.data
  },

  // --- Connections ---
  getUserConnections: async (userId: number): Promise<ConnectionStrings> => {
    const response = await apiClient.get(`/admin/users/${userId}/connections`)
    return response.data
  },

  refreshUserConnections: async (userId: number): Promise<ConnectionStrings> => {
    const response = await apiClient.post(`/admin/users/${userId}/refresh-connections`)
    return response.data
  },

  sendConnectionsToTelegram: async (userId: number): Promise<{ message: string; new_password: string }> => {
    const response = await apiClient.post(`/admin/users/${userId}/send-connections`)
    return response.data
  },

  resetUserPassword: async (userId: number): Promise<{ password: string }> => {
    const response = await apiClient.post(`/admin/users/${userId}/reset-password`)
    return response.data
  },

  regenerateSubToken: async (userId: number): Promise<EndUserDetail> => {
    const response = await apiClient.post(`/admin/users/${userId}/regenerate-sub-token`)
    return response.data
  },

  // --- Wallet ---
  getWallet: async (): Promise<WalletInfo> => {
    const response = await apiClient.get('/admin/wallet')
    return response.data
  },

  getPaymentConfig: async (): Promise<PaymentConfig> => {
    const { data } = await apiClient.get('/admin/payment-config')
    return data
  },

  createWireOrder: async (data: WireOrderRequest): Promise<WireOrderResponse> => {
    const response = await apiClient.post('/admin/wallet/wire-order', data)
    return response.data
  },

  getTransactions: async (
    params?: TransactionListParams
  ): Promise<PaginatedTransactions> => {
    const response = await apiClient.get('/admin/wallet/transactions', { params })
    return response.data
  },

  // --- Analytics ---
  getAnalytics: async (): Promise<AdminAnalytics> => {
    const response = await apiClient.get('/admin/analytics')
    return response.data
  },

  // --- Dynamic Regions ---
  getAvailableRegions: async (): Promise<AvailableRegion[]> => {
    const response = await apiClient.get('/admin/available-regions')
    return response.data
  },

  // --- Panel Domain ---
  getPanelUrl: async (): Promise<PanelUrlResponse> => {
    const response = await apiClient.get('/admin/panel-url')
    return response.data
  },

  renewUser: async (
    userId: number,
    payload: {
      extend_days?: number
      topup_gb?: number
      set_expiry?: string
      reapply_package_id?: number
      set_traffic_limit_gb?: number
      set_unlimited?: boolean
      reason?: string
    }
  ): Promise<EndUserDetail> => {
    const response = await apiClient.post(`/admin/users/${userId}/renew`, payload)
    return response.data
  },

  setUserRegions: async (
    userId: number,
    payload: { macro_regions: string[]; reason?: string }
  ): Promise<EndUserDetail> => {
    const response = await apiClient.put(`/admin/users/${userId}/regions`, payload)
    return response.data
  },

  setUsername: async (
    userId: number,
    payload: { new_username: string; reason?: string }
  ): Promise<EndUserDetail> => {
    const response = await apiClient.put(`/admin/users/${userId}/username`, payload)
    return response.data
  },

  setTelegram: async (
    userId: number,
    payload: { telegram_id: number | null; telegram_chat_id: number | null; reason?: string }
  ): Promise<EndUserDetail> => {
    const response = await apiClient.put(`/admin/users/${userId}/telegram`, payload)
    return response.data
  },

  resetTraffic: async (userId: number): Promise<EndUserDetail> => {
    const response = await apiClient.post(`/admin/users/${userId}/reset-traffic`, {})
    return response.data
  },
}
