'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatTraffic } from '@/lib/utils'
import {
  Users,
  Wifi,
  DollarSign,
  BarChart3,
  Globe,
  TrendingUp,
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
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

const PROTOCOL_COLORS: Record<string, string> = {
  ssh: '#22c55e',
  shadowsocks: '#3b82f6',
  vless: '#a855f7',
  trojan: '#ef4444',
  outline: '#f97316',
  http_proxy: '#6b7280',
}

const PROTOCOL_LABELS: Record<string, string> = {
  ssh: 'SSH',
  shadowsocks: 'Shadowsocks',
  vless: 'VLESS',
  trojan: 'Trojan',
  outline: 'Outline',
  http_proxy: 'HTTP Proxy',
}

export default function AdminAnalyticsPage() {
  // Fetch analytics
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['admin', 'analytics'],
    queryFn: api.adminNew.getAnalytics,
    refetchInterval: 60000,
  })

  // Fetch wallet for balance info
  const { data: wallet, isLoading: walletLoading } = useQuery({
    queryKey: ['admin', 'wallet'],
    queryFn: api.adminNew.getWallet,
    refetchInterval: 30000,
  })

  const topUsers = analytics?.top_users_by_traffic || []
  const protocolBreakdown = analytics?.protocol_breakdown || []
  const balance = Number(wallet?.balance || 0)

  // Prepare chart data
  const topUsersChartData = topUsers.map((u) => ({
    name: u.username,
    traffic: Math.round(u.traffic_gb * 100) / 100,
  }))

  const protocolChartData = protocolBreakdown.map((p) => ({
    name: PROTOCOL_LABELS[p.protocol] || p.protocol,
    value: Math.round(p.traffic_gb * 100) / 100,
    users: p.user_count,
    color: PROTOCOL_COLORS[p.protocol] || '#6b7280',
  }))

  // Calculate totals
  const totalTrafficFromBreakdown = protocolBreakdown.reduce(
    (sum, p) => sum + p.traffic_gb,
    0
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Analytics</h2>
        <p className="text-muted-foreground">Platform usage and cost analytics</p>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Users</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{analytics?.total_users || 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Users</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">{analytics?.active_users || 0}</div>
                <p className="text-xs text-muted-foreground">
                  of {analytics?.total_users || 0} total
                </p>
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
              <Skeleton className="h-8 w-20" />
            ) : (
              <div className="text-2xl font-bold">
                {formatTraffic(analytics?.total_traffic_gb || 0)}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <div className="text-2xl font-bold">
                {formatCurrency(Number(analytics?.total_cost_usd || 0))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Balance: {formatCurrency(balance)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Top Users Bar Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top Users by Traffic</CardTitle>
            <CardDescription>Top 10 users by bandwidth consumption</CardDescription>
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-72" />
            ) : topUsersChartData.length === 0 ? (
              <div className="flex items-center justify-center h-72">
                <p className="text-sm text-muted-foreground">No traffic data</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={topUsersChartData.slice(0, 10)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 12 }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={100}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    formatter={(value: number) => [formatTraffic(value), 'Traffic']}
                    contentStyle={{
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                    }}
                  />
                  <Bar
                    dataKey="traffic"
                    fill="#3b82f6"
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Protocol Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Protocol Usage Breakdown</CardTitle>
            <CardDescription>Traffic distribution by protocol</CardDescription>
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <Skeleton className="h-72" />
            ) : protocolChartData.length === 0 ? (
              <div className="flex items-center justify-center h-72">
                <p className="text-sm text-muted-foreground">No protocol data</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={protocolChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                  >
                    {protocolChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => [formatTraffic(value), 'Traffic']}
                    contentStyle={{
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Cost Breakdown */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cost Breakdown</CardTitle>
            <CardDescription>Traffic costs vs remaining balance</CardDescription>
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-lg border p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Wifi className="h-4 w-4 text-blue-500" />
                      <span className="text-sm font-medium">Traffic Cost</span>
                    </div>
                    <span className="text-lg font-bold">
                      {formatCurrency(Number(analytics?.total_cost_usd || 0))}
                    </span>
                  </div>
                  <div className="mt-2 w-full bg-muted rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full"
                      style={{
                        width: totalTrafficFromBreakdown > 0 ? '100%' : '0%',
                      }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatTraffic(totalTrafficFromBreakdown)} total
                  </p>
                </div>

                <div className="rounded-lg border p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-green-500" />
                      <span className="text-sm font-medium">Remaining Balance</span>
                    </div>
                    <span className="text-lg font-bold">{formatCurrency(balance)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Wallet balance after all charges
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Protocol Details Table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Protocol Details</CardTitle>
            <CardDescription>Per-protocol traffic and user count</CardDescription>
          </CardHeader>
          <CardContent>
            {analyticsLoading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : protocolBreakdown.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No protocol data available
              </p>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Protocol</TableHead>
                      <TableHead>Traffic</TableHead>
                      <TableHead>Users</TableHead>
                      <TableHead>% of Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {protocolBreakdown.map((p) => (
                      <TableRow key={p.protocol}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div
                              className="h-3 w-3 rounded-full"
                              style={{
                                backgroundColor:
                                  PROTOCOL_COLORS[p.protocol] || '#6b7280',
                              }}
                            />
                            <span className="text-sm font-medium">
                              {PROTOCOL_LABELS[p.protocol] || p.protocol}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          {formatTraffic(p.traffic_gb)}
                        </TableCell>
                        <TableCell>{p.user_count}</TableCell>
                        <TableCell>
                          {totalTrafficFromBreakdown > 0
                            ? `${(
                                (p.traffic_gb / totalTrafficFromBreakdown) *
                                100
                              ).toFixed(1)}%`
                            : '0%'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Users Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top Users by Traffic</CardTitle>
          <CardDescription>All users sorted by bandwidth consumption</CardDescription>
        </CardHeader>
        <CardContent>
          {analyticsLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : topUsers.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No traffic data yet
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rank</TableHead>
                    <TableHead>Username</TableHead>
                    <TableHead>Traffic (GB)</TableHead>
                    <TableHead>% of Total</TableHead>
                    <TableHead className="text-right">Usage Level</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {topUsers.map((user, index) => {
                    const pct =
                      (analytics?.total_traffic_gb ?? 0) > 0
                        ? (user.traffic_gb / (analytics?.total_traffic_gb ?? 1)) * 100
                        : 0
                    return (
                      <TableRow key={user.username}>
                        <TableCell className="font-medium text-muted-foreground">
                          #{index + 1}
                        </TableCell>
                        <TableCell className="font-medium">{user.username}</TableCell>
                        <TableCell>
                          {formatTraffic(user.traffic_gb)}
                        </TableCell>
                        <TableCell>{pct.toFixed(1)}%</TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-24 bg-muted rounded-full h-2">
                              <div
                                className={`h-2 rounded-full ${
                                  pct > 20
                                    ? 'bg-red-500'
                                    : pct > 10
                                      ? 'bg-yellow-500'
                                      : 'bg-green-500'
                                }`}
                                style={{
                                  width: `${Math.min(pct, 100)}%`,
                                }}
                              />
                            </div>
                            <Badge
                              variant="outline"
                              className={`text-xs ${
                                pct > 20
                                  ? 'text-red-600'
                                  : pct > 10
                                    ? 'text-yellow-600'
                                    : 'text-green-600'
                              }`}
                            >
                              {pct > 20 ? 'High' : pct > 10 ? 'Medium' : 'Low'}
                            </Badge>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
