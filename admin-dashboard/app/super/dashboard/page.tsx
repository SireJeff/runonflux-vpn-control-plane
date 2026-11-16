'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatRelativeTime, formatTraffic, getStatusColor } from '@/lib/utils'
import {
  Users,
  DollarSign,
  Wifi,
  ShoppingCart,
  Clock,
  ArrowRight,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import toast from 'react-hot-toast'
import type { AdminListItem, WireOrderItem } from '@/lib/api/endpoints/super-admin'

export default function SuperAdminDashboardPage() {
  const queryClient = useQueryClient()

  // Fetch analytics
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['super', 'analytics'],
    queryFn: api.superAdmin.getAnalytics,
    refetchInterval: 30000,
  })

  // Fetch pending admins
  const { data: pendingAdminsData, isLoading: pendingAdminsLoading } = useQuery({
    queryKey: ['super', 'admins', 'pending'],
    queryFn: () => api.superAdmin.listAdmins({ status: 'pending', per_page: 5 }),
  })

  // Fetch pending orders
  const { data: pendingOrdersData, isLoading: pendingOrdersLoading } = useQuery({
    queryKey: ['super', 'orders', 'pending'],
    queryFn: () => api.superAdmin.listOrders({ status: 'pending', per_page: 5 }),
  })

  const pendingAdmins: AdminListItem[] = pendingAdminsData?.items || []
  const pendingOrders: WireOrderItem[] = pendingOrdersData?.items || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Super Admin Dashboard</h2>
        <p className="text-muted-foreground">Platform overview and management</p>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Admins</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">{analytics?.total_admins || 0}</div>
                <p className="text-xs text-muted-foreground">
                  {analytics?.active_admins || 0} active, {analytics?.pending_admins || 0} pending
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Registrations</CardTitle>
            <Clock className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">{analytics?.pending_admins || 0}</div>
                <p className="text-xs text-muted-foreground">Awaiting approval</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatCurrency(Number(analytics?.total_revenue_usd || 0))}
                </div>
                <p className="text-xs text-muted-foreground">Platform-wide</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Traffic</CardTitle>
            <Wifi className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatTraffic(analytics?.total_traffic_gb || 0)}
                </div>
                <p className="text-xs text-muted-foreground">
                  {analytics?.active_end_users || 0} active end users
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity + Pending Orders */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Recent Admin Registrations */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Recent Admin Registrations</CardTitle>
              <CardDescription>Last 5 registered admins</CardDescription>
            </div>
            <Link href="/super/admins">
              <Button variant="ghost" size="sm" className="gap-1">
                View all
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {pendingAdminsLoading ? (
              <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : pendingAdmins.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No recent registrations
              </p>
            ) : (
              <div className="space-y-3">
                {pendingAdmins.map((admin) => (
                  <Link
                    key={admin.id}
                    href={`/super/admins/${admin.id}`}
                    className="flex items-center justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-sm font-medium text-primary">
                        {admin.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{admin.username}</p>
                        <p className="text-xs text-muted-foreground">
                          {admin.telegram_id || 'No telegram'}
                        </p>
                      </div>
                    </div>
                    <Badge className={getStatusColor(admin.status)}>{admin.status}</Badge>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pending Wire Orders */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Pending Wire Orders</CardTitle>
              <CardDescription>Awaiting review</CardDescription>
            </div>
            <Link href="/super/orders">
              <Button variant="ghost" size="sm" className="gap-1">
                View all
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {pendingOrdersLoading ? (
              <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : pendingOrders.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No pending orders
              </p>
            ) : (
              <div className="space-y-3">
                {pendingOrders.map((order) => (
                  <QuickOrderActions
                    key={order.id}
                    order={order}
                    queryClient={queryClient}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Platform Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Platform Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {analyticsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[...Array(8)].map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Total End Users</p>
                <p className="text-lg font-bold">{analytics?.total_end_users || 0}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Active End Users</p>
                <p className="text-lg font-bold">{analytics?.active_end_users || 0}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Active Admins</p>
                <p className="text-lg font-bold">{analytics?.active_admins || 0}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Pending Wire Orders</p>
                <p className="text-lg font-bold">{analytics?.total_wire_orders_pending || 0}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// Quick action component for pending orders
function QuickOrderActions({
  order,
  queryClient,
}: {
  order: WireOrderItem
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const approveMutation = useMutation({
    mutationFn: () =>
      api.superAdmin.approveOrder(order.id, {
        exchange_rate: 600000, // Default rate
      }),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'orders'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to approve order')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () =>
      api.superAdmin.rejectOrder(order.id, {
        admin_notes: 'Rejected from dashboard',
      }),
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'orders'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to reject order')
    },
  })

  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div>
        <p className="text-sm font-medium">
          {order.admin_username || `Admin #${order.admin_id}`}
        </p>
        <p className="text-xs text-muted-foreground">
          {Number(order.amount_tomans).toLocaleString()} Tomans
          {order.created_at && ` - ${formatRelativeTime(order.created_at)}`}
        </p>
      </div>
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-50"
          onClick={() => approveMutation.mutate()}
          disabled={approveMutation.isPending}
        >
          <CheckCircle2 className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50"
          onClick={() => rejectMutation.mutate()}
          disabled={rejectMutation.isPending}
        >
          <XCircle className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
