'use client'

import { useAuth } from '@/hooks/useAuth'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Globe,
  TrendingUp,
  Clock,
  CheckCircle,
  XCircle,
  Activity,
  Filter,
} from 'lucide-react'
import { IPChangeRequestResponse } from '@/types/api'

// Helper function to get flag emoji from country code
function getFlagEmoji(countryCode: string | null): string {
  if (!countryCode) return '🌍'
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map((char) => 127397 + char.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}

// Stats Card Component
function StatsCard({
  title,
  value,
  icon: Icon,
  loading,
  variant = 'default',
}: {
  title: string
  value: number | string
  icon: React.ElementType
  loading?: boolean
  variant?: 'default' | 'success' | 'warning' | 'error'
}) {
  const variantStyles = {
    default: 'text-blue-600 dark:text-blue-400',
    success: 'text-green-600 dark:text-green-400',
    warning: 'text-yellow-600 dark:text-yellow-400',
    error: 'text-red-600 dark:text-red-400',
  }

  if (loading) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            <Skeleton className="h-4 w-24" />
          </CardTitle>
          <Skeleton className="h-4 w-4 rounded" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-16" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={`h-4 w-4 ${variantStyles[variant]}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}

// Status Badge Component
function StatusBadge({ status }: { status: IPChangeRequestResponse['status'] }) {
  const statusConfig = {
    pending: {
      label: 'Pending',
      className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    },
    processing: {
      label: 'Processing',
      className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    },
    completed: {
      label: 'Completed',
      className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    },
    failed: {
      label: 'Failed',
      className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    },
  }

  const config = statusConfig[status]

  return <Badge className={config.className}>{config.label}</Badge>
}

export default function IPManagementPage() {
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const router = useRouter()
  const [statusFilter, setStatusFilter] = useState<string>('all')

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch IP change requests
  const { data: ipChanges, isLoading: ipChangesLoading } = useQuery({
    queryKey: ['ipChanges', statusFilter],
    queryFn: () =>
      api.ipManagement.listIPChanges(
        statusFilter !== 'all' ? { status: statusFilter } : undefined
      ),
    enabled: isAuthenticated,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Fetch IP stats
  const { data: ipStats, isLoading: ipStatsLoading } = useQuery({
    queryKey: ['ipStats'],
    queryFn: api.ipManagement.getIPStats,
    enabled: isAuthenticated,
    refetchInterval: 30000,
  })

  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

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

  // Format date helper
  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">IP Management</h1>
        <p className="text-muted-foreground">
          Monitor and manage IP change requests across all users
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <StatsCard
          title="Total IP Changes"
          value={ipStats?.total_ip_changes.toLocaleString() || '0'}
          icon={Globe}
          loading={ipStatsLoading}
        />
        <StatsCard
          title="Pending Requests"
          value={ipStats?.pending_requests || 0}
          icon={Clock}
          loading={ipStatsLoading}
          variant="warning"
        />
        <StatsCard
          title="Completed Today"
          value={ipStats?.completed_today || 0}
          icon={CheckCircle}
          loading={ipStatsLoading}
          variant="success"
        />
        <StatsCard
          title="Failed Requests"
          value={ipStats?.failed_requests || 0}
          icon={XCircle}
          loading={ipStatsLoading}
          variant="error"
        />
        <StatsCard
          title="Success Rate"
          value={`${ipStats?.success_rate?.toFixed(1) || '0'}%`}
          icon={TrendingUp}
          loading={ipStatsLoading}
          variant="success"
        />
      </div>

      {/* IP Change Request Queue */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              <div>
                <CardTitle>IP Change Request Queue</CardTitle>
                <CardDescription>
                  Real-time view of all IP change requests
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Requests</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="processing">Processing</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {ipChangesLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[80px]">ID</TableHead>
                    <TableHead>User ID</TableHead>
                    <TableHead>Credential ID</TableHead>
                    <TableHead>IP Change</TableHead>
                    <TableHead>Country Change</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Requested Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ipChanges && ipChanges.length > 0 ? (
                    ipChanges.map((change) => (
                      <TableRow key={change.id}>
                        <TableCell className="font-medium">#{change.id}</TableCell>
                        <TableCell>{change.user_id}</TableCell>
                        <TableCell>{change.credential_id}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <code className="text-xs bg-muted px-2 py-1 rounded">
                              {change.old_ip || 'N/A'}
                            </code>
                            <span className="text-muted-foreground">→</span>
                            <code className="text-xs bg-muted px-2 py-1 rounded">
                              {change.new_ip || 'N/A'}
                            </code>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="flex items-center gap-1">
                              <span className="text-lg">
                                {getFlagEmoji(change.old_country)}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {change.old_country || 'N/A'}
                              </span>
                            </div>
                            <span className="text-muted-foreground">→</span>
                            <div className="flex items-center gap-1">
                              <span className="text-lg">
                                {getFlagEmoji(change.new_country)}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {change.new_country || 'N/A'}
                              </span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={change.status} />
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(change.requested_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={7}
                        className="h-24 text-center text-muted-foreground"
                      >
                        {statusFilter === 'all'
                          ? 'No IP change requests found'
                          : `No ${statusFilter} requests found`}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
