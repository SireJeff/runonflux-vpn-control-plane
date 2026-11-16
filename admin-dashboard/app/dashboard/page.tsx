'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatTraffic } from '@/lib/utils'
import {
  Wallet,
  Users,
  UserCheck,
  Wifi,
  DollarSign,
  ArrowRight,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export default function DashboardPage() {
  // Fetch analytics
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['admin', 'analytics'],
    queryFn: api.adminNew.getAnalytics,
    refetchInterval: 30000,
  })

  // Fetch wallet
  const { data: wallet, isLoading: walletLoading } = useQuery({
    queryKey: ['admin', 'wallet'],
    queryFn: api.adminNew.getWallet,
    refetchInterval: 30000,
  })

  const balance = Number(wallet?.balance || 0)
  const balanceColor =
    balance >= 50
      ? 'text-green-600 dark:text-green-400'
      : balance >= 10
        ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

  const recentTransactions = wallet?.recent_transactions || []
  const topUsers = analytics?.top_users_by_traffic || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">Overview of your VPN reseller platform</p>
      </div>

      {/* Wallet Balance - PROMINENT */}
      <Card className="border-2">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Wallet className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-sm font-medium">Wallet Balance</CardTitle>
            </div>
            <Link href="/dashboard/wallet">
              <Button variant="ghost" size="sm" className="gap-1">
                Manage
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {walletLoading ? (
            <Skeleton className="h-12 w-48" />
          ) : (
            <div className={`text-4xl font-bold ${balanceColor}`}>
              {formatCurrency(balance)}
            </div>
          )}
          {balance < 10 && (
            <p className="mt-1 text-xs text-red-500">
              Low balance - consider topping up
            </p>
          )}
        </CardContent>
      </Card>

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total End Users</CardTitle>
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
            <UserCheck className="h-4 w-4 text-muted-foreground" />
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
            <CardTitle className="text-sm font-medium">Traffic This Month</CardTitle>
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
          </CardContent>
        </Card>
      </div>

      {/* Top Users + Recent Transactions */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Top 5 Users by Traffic */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Top Users by Traffic</CardTitle>
              <CardDescription>Highest bandwidth consumers</CardDescription>
            </div>
            <Link href="/dashboard/analytics">
              <Button variant="ghost" size="sm" className="gap-1">
                Analytics
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
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
                      <TableHead>#</TableHead>
                      <TableHead>Username</TableHead>
                      <TableHead className="text-right">Traffic</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {topUsers.slice(0, 5).map((user, index) => (
                      <TableRow key={user.username}>
                        <TableCell className="font-medium text-muted-foreground">
                          {index + 1}
                        </TableCell>
                        <TableCell className="font-medium">{user.username}</TableCell>
                        <TableCell className="text-right">
                          {formatTraffic(user.traffic_gb)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Transactions */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">Recent Transactions</CardTitle>
              <CardDescription>Last wallet movements</CardDescription>
            </div>
            <Link href="/dashboard/wallet">
              <Button variant="ghost" size="sm" className="gap-1">
                Wallet
                <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {walletLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : recentTransactions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No transactions yet
              </p>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Amount</TableHead>
                      <TableHead>Description</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recentTransactions.slice(0, 5).map((txn) => (
                      <TableRow key={txn.id}>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="text-xs"
                          >
                            {txn.transaction_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span
                            className={
                              Number(txn.amount_usd) >= 0
                                ? 'text-green-600'
                                : 'text-red-600'
                            }
                          >
                            {Number(txn.amount_usd) >= 0 ? '+' : ''}
                            {formatCurrency(txn.amount_usd)}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                          {txn.description}
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

      {/* Protocol Breakdown */}
      {analytics?.protocol_breakdown && analytics.protocol_breakdown.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Protocol Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {analytics.protocol_breakdown.map((p) => (
                <div key={p.protocol} className="rounded-lg border p-3 text-center">
                  <p className="text-xs text-muted-foreground mb-1">{p.protocol}</p>
                  <p className="text-lg font-bold">
                    {formatTraffic(p.traffic_gb)}
                  </p>
                  <p className="text-xs text-muted-foreground">{p.user_count} users</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
