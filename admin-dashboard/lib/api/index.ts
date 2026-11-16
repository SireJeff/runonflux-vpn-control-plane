/**
 * Unified API Client
 * Import and use: import { api } from '@/lib/api'
 */
import { authApi } from './endpoints/auth'
import { adminApi } from './endpoints/admin'
import { usersApi } from './endpoints/users'
import { supportApi } from './endpoints/support'
import { paymentsApi } from './endpoints/payments'
import { serversApi } from './endpoints/servers'
import { logsApi } from './endpoints/logs'
import { settingsApi } from './endpoints/settings'
import { ipManagementApi } from './endpoints/ip-management'
import { usageEndpoints } from './endpoints/usage'
import { superAdminApi } from './endpoints/super-admin'
import { adminNewApi } from './endpoints/admin-api'
import { endUserApi } from './endpoints/end-user'
import { botConfigApi } from './endpoints/botConfig'
import { packagesApi } from './endpoints/packages'
import { ordersApi } from './endpoints/orders'
import { referralApi } from './endpoints/referral'
import { freeConfigApi } from './endpoints/freeConfig'
import { freeConfigGlobalApi } from './endpoints/freeConfigGlobal'
import { routingRulesApi } from './endpoints/routingRules'
import { broadcastsApi } from './endpoints/broadcasts'

export const api = {
  auth: authApi,
  admin: adminApi,
  adminNew: adminNewApi,
  users: usersApi,
  support: supportApi,
  payments: paymentsApi,
  servers: serversApi,
  logs: logsApi,
  settings: settingsApi,
  ipManagement: ipManagementApi,
  usage: usageEndpoints,
  superAdmin: superAdminApi,
  endUser: endUserApi,
  botConfig: botConfigApi,
  packages: packagesApi,
  orders: ordersApi,
  referral: referralApi,
  freeConfig: freeConfigApi,
  freeConfigGlobal: freeConfigGlobalApi,
  routingRules: routingRulesApi,
  broadcasts: broadcastsApi,
}

// Re-export types
export type * from '@/types/api'
export type * from './endpoints/logs'
export type { IPStats } from './endpoints/ip-management'
export type { ServerInstance, ServerStats, ServerFilters } from './endpoints/servers'
export type {
  UsageSummary,
  UsageAnalyticsResponse,
  BandwidthDataPoint,
  BandwidthAnalyticsResponse,
} from './endpoints/usage'
export type {
  RegionInfo,
  CountryInfo,
  MacroRegionInfo,
  EndUser,
  EndUserDetail,
  UserCreateRequest,
  UserCreateResponse,
  UserUpdateRequest,
  UserListParams,
  PaginatedUsers,
  UserRegion,
  ConnectionStrings,
  WalletInfo,
  WalletTransaction,
  TransactionListParams,
  PaginatedTransactions,
  WireOrderRequest,
  WireOrderResponse,
  AdminAnalytics,
  TopUserTraffic,
  ProtocolBreakdown,
} from './endpoints/admin-api'
export type {
  ConnectionCountry,
  ConnectionsResponse,
  ProtocolBreakdown as EndUserProtocolBreakdown,
  RegionBreakdown,
  UsageResponse,
  ProfileResponse,
} from './endpoints/end-user'
export type {
  BotConfig,
  BotConfigCreateRequest,
  BotConfigUpdateRequest,
} from './endpoints/botConfig'
export type {
  Package,
  PackageCreateRequest,
  PackageUpdateRequest,
} from './endpoints/packages'
export type {
  Order,
  PackageSnapshot,
} from './endpoints/orders'
export type {
  ReferralConfig,
  ReferralConfigUpdate,
  ReferralStats,
  ReferralEarning,
} from './endpoints/referral'
export type {
  FreeConfig,
  FreeConfigUpdate,
  ChannelOut,
} from './endpoints/freeConfig'
export type {
  FreeConfigGlobal,
  FreeConfigGlobalUpdate,
} from './endpoints/freeConfigGlobal'
export type {
  RoutingRules,
  RoutingRulesUpdate,
} from './endpoints/routingRules'
export type {
  Broadcast,
  BroadcastSegment,
  BroadcastCreateRequest,
} from './endpoints/broadcasts'
