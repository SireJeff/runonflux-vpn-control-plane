/**
 * Packages API Endpoints
 * CRUD for subscription packages
 */
import { apiClient } from '../client'

export interface Package {
  id: number
  admin_id: number
  name: string
  traffic_limit_gb: string // Pydantic Decimal → string
  duration_days: number
  price_tomans: string // Pydantic Decimal → string
  is_active: boolean
  display_order: number
  region_count: number
  all_regions: boolean
  created_at: string
  updated_at: string
}

export interface PackageCreateRequest {
  name: string
  traffic_limit_gb: number
  duration_days: number
  price_tomans: number
  display_order?: number
  region_count?: number
  all_regions?: boolean
}

export interface PackageUpdateRequest {
  name?: string
  traffic_limit_gb?: number
  duration_days?: number
  price_tomans?: number
  is_active?: boolean
  display_order?: number
  region_count?: number
  all_regions?: boolean
}

export const packagesApi = {
  /**
   * List packages
   */
  list: async (includeInactive = false): Promise<Package[]> => {
    const response = await apiClient.get('/admin/packages', {
      params: { include_inactive: includeInactive },
    })
    return response.data
  },

  /**
   * Create a new package
   */
  create: async (data: PackageCreateRequest): Promise<Package> => {
    const response = await apiClient.post('/admin/packages', data)
    return response.data
  },

  /**
   * Update a package
   */
  update: async (id: number, data: PackageUpdateRequest): Promise<Package> => {
    const response = await apiClient.put(`/admin/packages/${id}`, data)
    return response.data
  },

  /**
   * Archive a package (soft delete — sets is_active=false)
   */
  archive: async (id: number): Promise<void> => {
    await apiClient.delete(`/admin/packages/${id}`)
  },
}
