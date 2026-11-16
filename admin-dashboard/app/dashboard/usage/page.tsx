'use client'

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useRouter } from 'next/navigation'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Activity, ArrowUp, ArrowDown, Loader2, RefreshCw } from 'lucide-react'
import { formatTraffic } from '@/lib/utils'

type PeriodType = 'daily' | 'weekly' | 'monthly'

export default function UsagePage() {
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const router = useRouter()
  const [periodType, setPeriodType] = React.useState<PeriodType>('daily')
  const [limit, setLimit] = React.useState(30)

  // Redirect if not authenticated
  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch usage analytics
  const { data: usageData, isLoading: usageLoading, refetch: refetchUsage } = useQuery({
    queryKey: ['analytics-usage'],
    queryFn: () => api.usage.getUsageAnalytics(),
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 60000,
  })

  // Fetch bandwidth timeseries
  const { data: bandwidthData, isLoading: bandwidthLoading, refetch: refetchBandwidth } = useQuery({
    queryKey: ['analytics-bandwidth', { periodType, limit }],
    queryFn: () =>
      api.usage.getBandwidthTimeseries({
        period_type: periodType,
        limit,
      }),
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 60000,
  })

  // Aggregate totals from usage summaries
  const totals = React.useMemo(() => {
    if (!usageData?.summaries?.length) {
      return { uploaded_gb: 0, downloaded_gb: 0, total_gb: 0, unique_users: 0 }
    }
    return usageData.summaries.reduce(
      (acc, item) => ({
        uploaded_gb: acc.uploaded_gb + (item.uploaded_gb || 0),
        downloaded_gb: acc.downloaded_gb + (item.downloaded_gb || 0),
        total_gb: acc.total_gb + (item.total_gb || 0),
        unique_users: Math.max(acc.unique_users, item.unique_users || 0),
      }),
      { uploaded_gb: 0, downloaded_gb: 0, total_gb: 0, unique_users: 0 }
    )
  }, [usageData])

  // Transform bandwidth data for chart
  const bandwidthChartData = React.useMemo(() => {
    if (!bandwidthData?.data?.length) return []
    return bandwidthData.data.map((item) => ({
      period: new Date(item.period_start).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      }),
      uploaded: Number(item.uploaded_gb.toFixed(2)),
      downloaded: Number(item.downloaded_gb.toFixed(2)),
      total: Number(item.total_gb.toFixed(2)),
    }))
  }, [bandwidthData])

  // Aggregate per-protocol data from usage summaries
  const protocolData = React.useMemo(() => {
    if (!usageData?.summaries?.length) return []
    const map = new Map<number, { protocol_id: number; uploaded_gb: number; downloaded_gb: number; total_gb: number; connections: number; unique_users: number }>()
    for (const item of usageData.summaries) {
      const existing = map.get(item.protocol_id) || {
        protocol_id: item.protocol_id,
        uploaded_gb: 0,
        downloaded_gb: 0,
        total_gb: 0,
        connections: 0,
        unique_users: 0,
      }
      existing.uploaded_gb += item.uploaded_gb || 0
      existing.downloaded_gb += item.downloaded_gb || 0
      existing.total_gb += item.total_gb || 0
      existing.connections += item.connections || 0
      existing.unique_users = Math.max(existing.unique_users, item.unique_users || 0)
      map.set(item.protocol_id, existing)
    }
    return Array.from(map.values())
  }, [usageData])

  const handleRefresh = () => {
    refetchUsage()
    refetchBandwidth()
  }

  // Loading state
  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">Loading usage analytics...</p>
        </div>
      </div>
    )
  }

  // Access denied
  if (!user?.is_admin) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Access Denied</h1>
          <p className="text-muted-foreground">Admin privileges required</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Activity className="h-8 w-8" />
            Usage & Bandwidth
          </h1>
          <p className="text-muted-foreground mt-1">
            Monitor bandwidth consumption, traffic trends, and protocol-level usage
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={periodType} onValueChange={(val) => setPeriodType(val as PeriodType)}>
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">Daily</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="monthly">Monthly</SelectItem>
            </SelectContent>
          </Select>
          <Select value={limit.toString()} onValueChange={(val) => setLimit(parseInt(val))}>
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 periods</SelectItem>
              <SelectItem value="30">Last 30 periods</SelectItem>
              <SelectItem value="90">Last 90 periods</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Upload</CardTitle>
            <ArrowUp className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            {usageLoading ? (
              <div className="h-8 w-24 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold">{formatTraffic(totals.uploaded_gb)}</div>
            )}
            <p className="text-xs text-muted-foreground">Across all protocols</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Download</CardTitle>
            <ArrowDown className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            {usageLoading ? (
              <div className="h-8 w-24 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold">{formatTraffic(totals.downloaded_gb)}</div>
            )}
            <p className="text-xs text-muted-foreground">Across all protocols</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Traffic</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {usageLoading ? (
              <div className="h-8 w-24 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold">{formatTraffic(totals.total_gb)}</div>
            )}
            <p className="text-xs text-muted-foreground">Upload + Download</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Users</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {usageLoading ? (
              <div className="h-8 w-24 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold">{totals.unique_users}</div>
            )}
            <p className="text-xs text-muted-foreground">Unique users recorded</p>
          </CardContent>
        </Card>
      </div>

      {/* Bandwidth Trend Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Bandwidth Trends</CardTitle>
          <CardDescription>
            Upload and download traffic over time ({periodType})
          </CardDescription>
        </CardHeader>
        <CardContent>
          {bandwidthLoading ? (
            <div className="h-[350px] w-full animate-pulse rounded bg-muted" />
          ) : bandwidthChartData.length === 0 ? (
            <div className="flex h-[350px] items-center justify-center text-muted-foreground">
              No bandwidth data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={bandwidthChartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="period"
                  className="text-xs"
                  tick={{ fill: 'currentColor' }}
                />
                <YAxis
                  className="text-xs"
                  tick={{ fill: 'currentColor' }}
                  tickFormatter={(value) => formatTraffic(value)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                  }}
                  labelStyle={{ color: 'hsl(var(--foreground))' }}
                  formatter={(value: number, name: string) => {
                    const label = name.charAt(0).toUpperCase() + name.slice(1)
                    return [formatTraffic(value), label]
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="uploaded"
                  stroke="hsl(142, 76%, 36%)"
                  strokeWidth={2}
                  dot={{ fill: 'hsl(142, 76%, 36%)' }}
                  activeDot={{ r: 6 }}
                  name="Uploaded"
                />
                <Line
                  type="monotone"
                  dataKey="downloaded"
                  stroke="hsl(221, 83%, 53%)"
                  strokeWidth={2}
                  dot={{ fill: 'hsl(221, 83%, 53%)' }}
                  activeDot={{ r: 6 }}
                  name="Downloaded"
                />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={{ fill: 'hsl(var(--primary))' }}
                  activeDot={{ r: 6 }}
                  name="Total"
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Per-Protocol Breakdown Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            <CardTitle>Per-Protocol Breakdown</CardTitle>
          </div>
          <CardDescription>
            Aggregated usage statistics by VPN protocol
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usageLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-12 w-full animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : protocolData.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-muted-foreground">
              No usage data available
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Protocol ID</TableHead>
                  <TableHead className="text-right">Upload</TableHead>
                  <TableHead className="text-right">Download</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-center">Connections</TableHead>
                  <TableHead className="text-center">Unique Users</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocolData.map((row) => (
                  <TableRow key={row.protocol_id} className="hover:bg-muted/50">
                    <TableCell className="font-medium">Protocol #{row.protocol_id}</TableCell>
                    <TableCell className="text-right font-mono">
                      {formatTraffic(row.uploaded_gb)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatTraffic(row.downloaded_gb)}
                    </TableCell>
                    <TableCell className="text-right font-mono font-bold">
                      {formatTraffic(row.total_gb)}
                    </TableCell>
                    <TableCell className="text-center">{row.connections}</TableCell>
                    <TableCell className="text-center">{row.unique_users}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
