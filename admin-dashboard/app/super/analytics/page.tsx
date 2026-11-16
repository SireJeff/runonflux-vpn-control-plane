'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatTraffic, getStatusColor } from '@/lib/utils'
import {
  DollarSign,
  Users,
  UserCheck,
  Wifi,
  TrendingUp,
  ShoppingCart,
  BarChart3,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { AdminListItem } from '@/lib/api/endpoints/super-admin'
import { TldUsageChart } from '@/components/dashboard/TldUsageChart'

export default function SuperAdminAnalyticsPage() {
  // Fetch analytics
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['super', 'analytics'],
    queryFn: api.superAdmin.getAnalytics,
    refetchInterval: 60000,
  })

  // Fetch top admins (sorted by wallet balance, take all active ones)
  const { data: adminsData, isLoading: adminsLoading } = useQuery({
    queryKey: ['super', 'admins', 'top'],
    queryFn: () => api.superAdmin.listAdmins({ status: 'active', per_page: 10 }),
  })

  const topAdmins: AdminListItem[] = adminsData?.items || []

  // TLD analytics: live distribution + per-purpose daily series
  const { data: tldSnapshot } = useQuery({
    queryKey: ['super', 'tld-analytics'],
    queryFn: () => api.superAdmin.getTldAnalytics(),
  })
  const fdmSeries = useQuery({
    queryKey: ['super', 'tld-series', 'fdm'],
    queryFn: () => api.superAdmin.getTldAnalyticsSeries('fdm', 30),
  })
  const subSeries = useQuery({
    queryKey: ['super', 'tld-series', 'subscription'],
    queryFn: () => api.superAdmin.getTldAnalyticsSeries('subscription', 30),
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Analytics</h2>
        <p className="text-muted-foreground">Platform-wide analytics and reporting</p>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <div className="text-2xl font-bold">
                {formatCurrency(Number(analytics?.total_revenue_usd || 0))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">Sum of admin wallet balances</p>
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
              <div className="text-2xl font-bold">
                {formatTraffic(analytics?.total_traffic_gb || 0)}
              </div>
            )}
            <p className="text-xs text-muted-foreground">Platform-wide bandwidth</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Admins</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-8" />
            ) : (
              <div className="text-2xl font-bold">{analytics?.active_admins || 0}</div>
            )}
            <p className="text-xs text-muted-foreground">of {analytics?.total_admins || 0} total</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active End Users</CardTitle>
            <UserCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-8" />
            ) : (
              <div className="text-2xl font-bold">{analytics?.active_end_users || 0}</div>
            )}
            <p className="text-xs text-muted-foreground">of {analytics?.total_end_users || 0} total</p>
          </CardContent>
        </Card>
      </div>

      {/* Secondary Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Registrations</CardTitle>
            <TrendingUp className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-8" />
            ) : (
              <div className="text-2xl font-bold">{analytics?.pending_admins || 0}</div>
            )}
            <p className="text-xs text-muted-foreground">Awaiting approval</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Wire Orders</CardTitle>
            <ShoppingCart className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-8" />
            ) : (
              <div className="text-2xl font-bold">{analytics?.total_wire_orders_pending || 0}</div>
            )}
            <p className="text-xs text-muted-foreground">Awaiting review</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Revenue per Admin</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">
                {analytics && analytics.active_admins > 0
                  ? formatCurrency(
                      Number(analytics.total_revenue_usd) / analytics.active_admins
                    )
                  : '$0.00'}
              </div>
            )}
            <p className="text-xs text-muted-foreground">Average wallet balance</p>
          </CardContent>
        </Card>
      </div>

      {/* Top Admins */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top Admins</CardTitle>
          <CardDescription>Active admins sorted by wallet balance</CardDescription>
        </CardHeader>
        <CardContent>
          {adminsLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : topAdmins.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No active admins yet
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rank</TableHead>
                    <TableHead>Username</TableHead>
                    <TableHead>Wallet Balance</TableHead>
                    <TableHead>End Users</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {topAdmins.map((admin, index) => (
                    <TableRow key={admin.id}>
                      <TableCell className="font-medium text-muted-foreground">
                        #{index + 1}
                      </TableCell>
                      <TableCell className="font-medium">{admin.username}</TableCell>
                      <TableCell>{formatCurrency(Number(admin.wallet_balance))}</TableCell>
                      <TableCell>{admin.user_count}</TableCell>
                      <TableCell>
                        <Badge className={getStatusColor(admin.status)}>{admin.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* TLD Distribution */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">TLD Distribution (live)</CardTitle>
          <CardDescription>Active users per TLD — same count the load-balancer sees</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Purpose</TableHead>
                  <TableHead>TLD</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Active users</TableHead>
                  <TableHead>DNS</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(['fdm', 'subscription', 'dashboard', 'admin_panel'] as const).flatMap((p) =>
                  (tldSnapshot?.[p] || []).map((t) => {
                    const dh = t.dns_health
                    const badge =
                      p === 'fdm' && dh
                        ? dh.all_dns_failed
                          ? { txt: 'DNS down', variant: 'destructive' as const }
                          : dh.healthy_domains > 0
                            ? { txt: `${dh.healthy_domains}/${dh.total_domains}`, variant: 'default' as const }
                            : { txt: 'no domains', variant: 'secondary' as const }
                        : null
                    return (
                      <TableRow key={`${p}-${t.tld_id}`}>
                        <TableCell className="capitalize">{p.replace('_', ' ')}</TableCell>
                        <TableCell className="font-medium">{t.domain}</TableCell>
                        <TableCell>{t.is_active ? 'Active' : 'Inactive'}</TableCell>
                        <TableCell className="text-right">{t.active_user_count}</TableCell>
                        <TableCell>
                          {badge ? <Badge variant={badge.variant}>{badge.txt}</Badge> : '—'}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* TLD trends */}
      <div className="grid gap-4 lg:grid-cols-2">
        <TldUsageChart purpose="fdm" data={fdmSeries.data} loading={fdmSeries.isLoading} />
        <TldUsageChart purpose="subscription" data={subSeries.data} loading={subSeries.isLoading} />
      </div>
    </div>
  )
}
