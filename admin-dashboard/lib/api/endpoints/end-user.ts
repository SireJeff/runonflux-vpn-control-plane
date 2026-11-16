/**
 * End User API Endpoints
 * All endpoints require role=end_user
 */
import { apiClient } from '../client'

export interface SSHParsedFields {
  host: string;
  port: number;
  username: string;
  password: string;
}

export interface ProtocolConnections {
  primary: string;
  fallbacks: string[];
  /** SSH only — {host, port, username, password} for field-wise display. Null for other protocols. */
  parsed_fields?: SSHParsedFields | null;
}

export interface ConnectionCountry {
  country_code: string;
  country_name: string;
  flag: string;
  connections: Record<string, ProtocolConnections>;
}

export interface ConnectionsResponse {
  macro_region?: string;
  countries: ConnectionCountry[];
  last_refreshed_at: string | null;
  can_refresh: boolean;
  refresh_available_at?: string | null;
  subscription_url?: string;
  expires_at?: string;
  /** Hero block fields (T15 redesign) — populated by backend. */
  username?: string;
  password?: string;
  dashboard_url?: string;
}

export interface ResetCredentialsResponse {
  username: string;
  password: string;
  subscription_url: string;
  dashboard_url: string;
}

export interface ProtocolBreakdown {
  protocol: string;
  bytes_total: number;
  gb_total: number;
}

export interface RegionBreakdown {
  region_code: string;
  bytes_total: number;
  gb_total: number;
}

export interface UsageResponse {
  total_bytes: number;
  total_gb: number;
  protocol_breakdown: ProtocolBreakdown[];
  region_breakdown: RegionBreakdown[];
}

export interface ProfileResponse {
  id: number;
  username: string;
  display_name?: string;
  remark?: string;
  status: string;
  macro_region?: string;
}

export const endUserApi = {
  /**
   * Get all connection strings for the authenticated end user
   */
  getConnections: async (): Promise<ConnectionsResponse> => {
    const { data } = await apiClient.get('/user/connections');
    return data;
  },

  /**
   * Refresh connection strings (rotate IPs/ports) for the authenticated end user
   */
  refreshConnections: async (): Promise<ConnectionsResponse> => {
    const { data } = await apiClient.post('/user/refresh-connections');
    return data;
  },

  /**
   * Rotate password + subscription token atomically. Returns fresh creds.
   */
  resetCredentials: async (): Promise<ResetCredentialsResponse> => {
    const { data } = await apiClient.post('/user/reset-credentials');
    return data;
  },

  /**
   * Get bandwidth usage statistics for the authenticated end user
   */
  getUsage: async (): Promise<UsageResponse> => {
    const { data } = await apiClient.get('/user/usage');
    return data;
  },

  /**
   * Get profile information for the authenticated end user
   */
  getProfile: async (): Promise<ProfileResponse> => {
    const { data } = await apiClient.get('/user/profile');
    return data;
  },
};
