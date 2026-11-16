/**
 * TypeScript type definitions for FluxVPN API
 * Generated from backend Pydantic schemas
 */

// ============================================================================
// AUTHENTICATION
// ============================================================================

export interface AuthResponse {
  access_token: string
  refresh_token?: string
  role: string
  username: string
  display_name?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  display_name?: string
  telegram_id: string
  whatsapp_number?: string
  phone_number?: string
  notes?: string
}

// ============================================================================
// USER
// ============================================================================

export interface UserResponse {
  id: number
  username: string
  role: 'super_admin' | 'admin' | 'end_user' | 'pending'
  display_name?: string
  status: string
  telegram_user_id?: number
  telegram_username?: string | null
  email?: string | null
  flux_wallet_address?: string | null
  referral_code?: string | null
  referred_by?: number | null
  referral_tier?: 'bronze' | 'silver' | 'gold' | 'platinum'
  total_referrals?: number
  referral_earnings_usd?: string
  wallet_balance?: string
  trial_used?: boolean
  trial_started_at?: string | null
  trial_expires_at?: string | null
  is_admin?: boolean
  language?: string
  created_at?: string
}

export interface UserUpdate {
  telegram_username?: string
  email?: string
  language?: string
  wallet_balance?: number
}

// ============================================================================
// DASHBOARD STATS
// ============================================================================

export interface DashboardStats {
  // User metrics
  total_users: number
  active_users: number
  new_users_today: number
  new_users_this_month: number

  // Subscription metrics
  total_subscriptions: number
  active_subscriptions: number
  trial_subscriptions: number
  expiring_soon: number

  // Revenue metrics
  total_revenue: string
  revenue_today: string
  revenue_this_month: string
  avg_revenue_per_user: string

  // Infrastructure
  total_instances: number
  healthy_instances: number
  unhealthy_instances: number
  total_countries: number

  // Support
  open_tickets: number
  unassigned_tickets: number
  avg_resolution_hours: number | null
}

// ============================================================================
// ANALYTICS
// ============================================================================

export interface RevenueAnalytics {
  period: 'daily' | 'weekly' | 'monthly'
  data: Array<{
    date: string
    revenue: number
    transactions: number
  }>
  total_revenue: string
  avg_transaction: string
  growth_percentage: number | null
}

export interface UserGrowthAnalytics {
  period: 'daily' | 'weekly' | 'monthly'
  data: Array<{
    date: string
    new_users: number
    total_users: number
  }>
  total_new_users: number
  growth_rate: number | null
}

export interface ProtocolStats {
  protocol_id: number
  protocol_name: string
  active_subscriptions: number
  total_subscriptions: number
  revenue: string
  active_instances: number
  avg_health_score: number
  popularity_rank: number
}

export interface CountryStats {
  country_code: string
  country_name: string
  active_instances: number
  total_connections: number
  avg_health: number
}

export interface TopUser {
  user_id: number
  username: string | null
  total_spent: string
  active_subscriptions: number
  referrals: number
  joined_date: string
}

export interface SystemHealth {
  overall_health: number
  database_status: string
  redis_status: string
  celery_status: string
  api_uptime_hours: number
  total_requests_today: number
  avg_response_time_ms: number
}

export interface AlertStats {
  total_alerts: number
  unacknowledged: number
  critical: number
  warning: number
  info: number
  recent_alerts: Array<{
    id: number
    type: string
    priority: string
    title: string
    message: string
    created_at: string
    acknowledged: boolean
  }>
}

// ============================================================================
// SUBSCRIPTIONS
// ============================================================================

export interface ProtocolResponse {
  id: number
  name: string
  display_name: string
  description: string
  price_usd_monthly: string
  trial_enabled: boolean
  trial_days: number
  data_limit_gb: number | null
  is_active: boolean
  created_at: string
}

export interface SubscriptionResponse {
  id: number
  user_id: number
  protocol_id: number
  start_date: string
  end_date: string
  is_active: boolean
  auto_renew: boolean
  price_usd: string
  is_trial: boolean
  created_at: string
}

// ============================================================================
// SUPPORT TICKETS
// ============================================================================

export interface TicketResponse {
  id: number
  user_id: number
  ticket_number: string
  subject: string
  description: string
  category: 'technical' | 'billing' | 'account' | 'feature_request' | 'other'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  status: 'open' | 'in_progress' | 'waiting_customer' | 'resolved' | 'closed'
  created_at: string
  updated_at: string
  resolved_at: string | null
  assigned_to: number | null
  assigned_to_name: string | null
  message_count: number
  last_message_at: string | null
}

export interface TicketMessageResponse {
  id: number
  ticket_id: number
  user_id: number
  user_name: string | null
  is_staff: boolean
  is_internal: boolean
  message: string
  created_at: string
}

export interface TicketDetailResponse {
  ticket: TicketResponse
  messages: TicketMessageResponse[]
}

export interface TicketStats {
  total_tickets: number
  open_tickets: number
  in_progress_tickets: number
  resolved_tickets: number
  closed_tickets: number
  avg_resolution_time_hours: number | null
}

// ============================================================================
// PAYMENTS
// ============================================================================

export interface WalletTransactionResponse {
  id: number
  user_id: number
  amount_usd: string
  transaction_type: 'deposit' | 'withdrawal' | 'purchase' | 'fee' | 'referral_commission'
  status: 'pending' | 'completed' | 'failed'
  description: string
  reference_id: string
  metadata: Record<string, any>
  created_at: string
}

// ============================================================================
// CREDENTIALS
// ============================================================================

export interface CredentialResponse {
  id: number
  user_id: number
  protocol_id: number
  protocol_name: string
  subscription_id: number
  server_ip: string
  server_domain: string | null
  port: number
  username: string
  password: string | null
  config_data: Record<string, any> | null
  country_code: string
  country_name: string
  is_active: boolean
  created_at: string
  expires_at: string | null
  connection_string: string | null
  qr_code_data: string | null
  download_links: Record<string, any> | null
}

// ============================================================================
// IP MANAGEMENT
// ============================================================================

export interface IPChangeRequestResponse {
  id: number
  credential_id: number
  user_id: number
  old_ip: string | null
  new_ip: string | null
  old_country: string | null
  new_country: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  requested_at: string
  completed_at: string | null
  failure_reason: string | null
}

// ============================================================================
// COMMON
// ============================================================================

export interface SuccessResponse {
  message: string
  data?: Record<string, any>
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ============================================================================
// API ERROR
// ============================================================================

export interface APIError {
  detail: string
  status_code: number
}
