/**
 * Super Admin API Endpoints
 * Manage admin resellers, wire orders, platform analytics, and settings
 */
import { apiClient } from '../client'
import type { Broadcast } from './broadcasts'

// ============================================================================
// TYPES
// ============================================================================

export interface AdminListItem {
  id: number
  username: string
  display_name: string | null
  telegram_id: string | null
  wallet_balance: string
  status: 'pending' | 'active' | 'suspended'
  created_at: string | null
  user_count: number
}

export interface AdminDetail {
  id: number
  username: string
  display_name: string | null
  telegram_id: string | null
  whatsapp_number: string | null
  phone_number: string | null
  wallet_balance: string
  status: 'pending' | 'active' | 'suspended'
  notes: string | null
  approved_by: number | null
  approved_at: string | null
  created_at: string | null
  user_count: number
  broadcasts_enabled: boolean
  recent_transactions: WalletTransaction[]
}

export interface WalletTransaction {
  id: number
  amount_usd: number
  transaction_type: string
  status: string
  description: string
  created_at: string | null
}

export interface AdminListParams {
  status?: string
  search?: string
  page?: number
  per_page?: number
}

export interface PaginatedAdmins {
  items: AdminListItem[]
  total: number
  page: number
  per_page: number
}

export interface WireOrderItem {
  id: number
  admin_id: number
  admin_username: string | null
  amount_tomans: string
  amount_usd: string | null
  contact_telegram: string
  contact_whatsapp: string | null
  contact_phone: string | null
  notes: string | null
  status: 'pending' | 'approved' | 'rejected'
  admin_notes: string | null
  reviewed_by: number | null
  reviewed_at: string | null
  created_at: string | null
  payment_method: 'wire' | 'crypto'
  crypto_txid: string | null
  crypto_link: string | null
}

export interface OrderListParams {
  status?: string
  page?: number
  per_page?: number
}

export interface PaginatedOrders {
  items: WireOrderItem[]
  total: number
  page: number
  per_page: number
}

export interface PlatformAnalytics {
  total_admins: number
  active_admins: number
  pending_admins: number
  total_end_users: number
  active_end_users: number
  total_revenue_usd: string
  total_traffic_gb: number
  total_wire_orders_pending: number
}

export interface PlatformSettings {
  price_per_gb: string
  price_per_region_monthly: string
  min_topup_tomans: string
  toman_to_usd_rate: string
  toman_per_usd_rate: string
  crypto_topup_address: string
  crypto_topup_network: string
  crypto_topup_memo: string
  min_topup_usd: string
  cloudflare_domain: string
  cloudflare_zone_id: string
  cloudflare_api_token: string
  arvan_api_key: string
}

export interface UpdateSettingsPayload {
  price_per_gb?: string | null
  price_per_region_monthly?: string | null
  min_topup_tomans?: string | null
  toman_to_usd_rate?: string | null
  toman_per_usd_rate?: string | null
  crypto_topup_address?: string | null
  crypto_topup_network?: string | null
  crypto_topup_memo?: string | null
  min_topup_usd?: string | null
  cloudflare_domain?: string | null
  cloudflare_zone_id?: string | null
  cloudflare_api_token?: string | null
  arvan_api_key?: string | null
}

export interface ApproveAdminResponse {
  success: boolean
  message: string
  admin_id: number
  username: string
  assigned_password: string
}

export interface CreditWalletResponse {
  success: boolean
  message: string
  admin_id: number
  amount_usd: number
  new_balance: number
  transaction_id: number
}

export interface ReviewOrderResponse {
  success: boolean
  message: string
  order_id: number
  amount_tomans?: number
  amount_usd?: number
  exchange_rate?: number
}

// ============================================================================
// FLUX APP REGISTRATION
// ============================================================================

export interface RegisterAppRequest {
  app_name: string
  protocol_ports: Record<string, number>
}

export interface AppRegistration {
  id: number
  app_name: string
  protocol_ports: Record<string, number>
  is_active: boolean
  registered_by: number | null
  last_discovery_at: string | null
  last_discovery_ips: string[] | null
  created_at: string | null
  updated_at: string | null
  regions: string[]
  healthy_instances: number
}

export interface UpdateAppRequest {
  protocol_ports?: Record<string, number>
  is_active?: boolean
}

export interface MigrateTldRequest {
  new_domain: string
  new_zone_id: string
}

export interface MigrateTldResponse {
  success: boolean
  message: string
  old_domain: string
  new_domain: string
  deployments_updated: number
  domains_renamed: number
  dns_records_deleted: number
  dns_delete_errors: number
  sync_triggered: boolean
}

// --- TLD Management Types ---

export interface TldEntry {
  id: number
  domain: string
  dns_provider: 'cloudflare' | 'arvancloud'
  zone_id: string | null
  purpose: 'fdm' | 'subscription' | 'dashboard' | 'admin_panel'
  server_ip: string | null
  is_active: boolean
  created_at: string | null
}

export interface TldListResponse {
  fdm: TldEntry[]
  subscription: TldEntry[]
  dashboard: TldEntry[]
  admin_panel: TldEntry[]
}

export interface TldCreateRequest {
  domain: string
  dns_provider: 'cloudflare' | 'arvancloud'
  zone_id?: string | null
  purpose: 'fdm' | 'subscription' | 'dashboard' | 'admin_panel'
}

export interface TldActivateResponse {
  success: boolean
  message: string
  purpose: string
  old_domain: string | null
  new_domain: string
  details: Record<string, unknown>
}

export interface TldPinRequest {
  admin_id: number
  purpose: string
  /** Set to pin an admin to a TLD; null/undefined to clear the pin (revert to LB). */
  tld_id: number | null
}

export interface TldPinResponse {
  success: boolean
  admin_id: number
  purpose: string
  pinned_tld_id: number | null
}

// --- TLD Analytics Types ---

export interface TldDnsHealth {
  healthy_domains: number
  total_domains: number
  all_dns_failed: boolean
  last_error: string | null
}

export interface TldAnalyticsTld {
  tld_id: number
  domain: string
  dns_provider: 'cloudflare' | 'arvancloud'
  is_active: boolean
  active_user_count: number
  dns_health?: TldDnsHealth | null
}

export interface TldAnalyticsSnapshot {
  fdm: TldAnalyticsTld[]
  subscription: TldAnalyticsTld[]
  dashboard: TldAnalyticsTld[]
  admin_panel: TldAnalyticsTld[]
}

export interface TldAnalyticsSeriesDay {
  date: string
  values: Record<string, number>
}

export interface TldAnalyticsSeries {
  purpose: string
  days: number
  domains: string[]
  series: TldAnalyticsSeriesDay[]
}

// --- TLD Assignment Types ---

export interface TldAssignmentCell {
  effective_tld_id: number | null
  pinned_tld_id: number | null
  source: string | null
}

export interface TldAdminAssignment {
  admin_id: number
  username: string
  assignments: Record<string, TldAssignmentCell>
}

export interface TldAssignmentsResponse {
  assignments: TldAdminAssignment[]
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

export const superAdminApi = {
  // --- Analytics ---
  getAnalytics: async (): Promise<PlatformAnalytics> => {
    const response = await apiClient.get('/super/analytics')
    return response.data
  },

  // --- Admin Management ---
  listAdmins: async (params?: AdminListParams): Promise<PaginatedAdmins> => {
    const response = await apiClient.get('/super/admins', { params })
    return response.data
  },

  getAdminDetail: async (adminId: number): Promise<AdminDetail> => {
    const response = await apiClient.get(`/super/admins/${adminId}`)
    return response.data
  },

  approveAdmin: async (
    adminId: number,
    password: string
  ): Promise<ApproveAdminResponse> => {
    const response = await apiClient.post(`/super/admins/${adminId}/approve`, {
      password,
    })
    return response.data
  },

  suspendAdmin: async (adminId: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post(`/super/admins/${adminId}/suspend`)
    return response.data
  },

  activateAdmin: async (adminId: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post(`/super/admins/${adminId}/activate`)
    return response.data
  },

  creditWallet: async (
    adminId: number,
    amount_usd: number,
    reason: string
  ): Promise<CreditWalletResponse> => {
    const response = await apiClient.post(`/super/admins/${adminId}/credit`, {
      amount_usd,
      reason,
    })
    return response.data
  },

  // --- Broadcasts (superadmin visibility + kill-switch) ---
  listBroadcasts: async (adminId?: number): Promise<Broadcast[]> => {
    const response = await apiClient.get('/super-admin/broadcasts', {
      params: adminId != null ? { admin_id: adminId } : undefined,
    })
    return response.data
  },

  setBroadcastsEnabled: async (
    adminId: number,
    enabled: boolean
  ): Promise<{ admin_id: number; broadcasts_enabled: boolean }> => {
    const response = await apiClient.patch(
      `/super-admin/admins/${adminId}/broadcasts-enabled`,
      { enabled }
    )
    return response.data
  },

  // --- Wire Order Management ---
  listOrders: async (params?: OrderListParams): Promise<PaginatedOrders> => {
    const response = await apiClient.get('/super/orders', { params })
    return response.data
  },

  approveOrder: async (
    orderId: number,
    data: { admin_notes?: string; exchange_rate?: number }
  ): Promise<ReviewOrderResponse> => {
    const response = await apiClient.post(`/super/orders/${orderId}/approve`, data)
    return response.data
  },

  rejectOrder: async (
    orderId: number,
    data: { admin_notes: string }
  ): Promise<ReviewOrderResponse> => {
    const response = await apiClient.post(`/super/orders/${orderId}/reject`, data)
    return response.data
  },

  // --- Platform Settings ---
  getSettings: async (): Promise<PlatformSettings> => {
    const response = await apiClient.get('/super/settings')
    return response.data
  },

  updateSettings: async (data: UpdateSettingsPayload): Promise<PlatformSettings> => {
    const response = await apiClient.put('/super/settings', data)
    return response.data
  },

  // --- Flux App Registration ---
  listApps: async (): Promise<AppRegistration[]> => {
    const response = await apiClient.get('/super/apps')
    return response.data
  },

  registerApp: async (
    request: RegisterAppRequest
  ): Promise<{ id: number; app_name: string; message: string }> => {
    const response = await apiClient.post('/super/apps', request)
    return response.data
  },

  getApp: async (appId: number): Promise<AppRegistration> => {
    const response = await apiClient.get(`/super/apps/${appId}`)
    return response.data
  },

  updateApp: async (
    appId: number,
    request: UpdateAppRequest
  ): Promise<{ message: string }> => {
    const response = await apiClient.put(`/super/apps/${appId}`, request)
    return response.data
  },

  deleteApp: async (appId: number): Promise<{ message: string }> => {
    const response = await apiClient.delete(`/super/apps/${appId}`)
    return response.data
  },

  syncApp: async (
    appId: number
  ): Promise<{
    message: string
    tasks: { deployment_id: number; protocol: string; task_id: string }[]
  }> => {
    const response = await apiClient.post(`/super/apps/${appId}/sync`)
    return response.data
  },

  // --- TLD Migration ---
  migrateTld: async (request: MigrateTldRequest): Promise<MigrateTldResponse> => {
    const response = await apiClient.post('/super/settings/migrate-tld', request)
    return response.data
  },

  // TLD Management
  listTlds: async (): Promise<TldListResponse> => {
    const response = await apiClient.get('/super/settings/tlds')
    return response.data
  },

  createTld: async (request: TldCreateRequest): Promise<TldEntry> => {
    const response = await apiClient.post('/super/settings/tlds', request)
    return response.data
  },

  deleteTld: async (tldId: number): Promise<void> => {
    await apiClient.delete(`/super/settings/tlds/${tldId}`)
  },

  activateTld: async (tldId: number): Promise<TldActivateResponse> => {
    const response = await apiClient.post(`/super/settings/tlds/${tldId}/activate`)
    return response.data
  },

  deactivateTld: async (tldId: number): Promise<TldActivateResponse> => {
    const response = await apiClient.post(`/super/settings/tlds/${tldId}/deactivate`)
    return response.data
  },

  setTldPin: async (request: TldPinRequest): Promise<TldPinResponse> => {
    const response = await apiClient.post('/super/settings/tlds/pin', request)
    return response.data
  },

  // TLD Analytics + Assignments
  getTldAnalytics: async (): Promise<TldAnalyticsSnapshot> => {
    const response = await apiClient.get('/super/tlds/analytics')
    return response.data
  },

  getTldAnalyticsSeries: async (purpose: string, days = 30): Promise<TldAnalyticsSeries> => {
    const response = await apiClient.get('/super/tlds/analytics/series', {
      params: { purpose, days },
    })
    return response.data
  },

  getTldAssignments: async (): Promise<TldAssignmentsResponse> => {
    const response = await apiClient.get('/super/tlds/assignments')
    return response.data
  },
}
