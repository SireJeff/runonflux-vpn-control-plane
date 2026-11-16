'use client'

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useRouter } from 'next/navigation'
import { WalletTransactionResponse } from '@/types/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CreditCard, Loader2, CheckCircle, XCircle, Search, DollarSign, AlertCircle } from 'lucide-react'
import { formatCurrency, formatDate } from '@/lib/utils'
import toast from 'react-hot-toast'

export default function PaymentsPage() {
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  const [typeFilter, setTypeFilter] = React.useState<string>('all')
  const [statusFilter, setStatusFilter] = React.useState<string>('all')
  const [search, setSearch] = React.useState('')

  // Redirect if not authenticated
  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch transactions
  const { data: transactions, isLoading: transactionsLoading } = useQuery({
    queryKey: ['transactions', { type: typeFilter, status: statusFilter, search }],
    queryFn: async () => {
      const params: any = {}
      if (typeFilter !== 'all') params.transaction_type = typeFilter
      if (statusFilter !== 'all') params.status = statusFilter
      return api.payments.listTransactions(params)
    },
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 30000,
  })

  // Fetch pending withdrawals
  const { data: pendingWithdrawals, isLoading: withdrawalsLoading } = useQuery({
    queryKey: ['withdrawals-pending'],
    queryFn: api.payments.getPendingWithdrawals,
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 10000, // More frequent for pending items
  })

  // Approve withdrawal
  const approveMutation = useMutation({
    mutationFn: (transactionId: number) => api.payments.approveWithdrawal(transactionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['withdrawals-pending'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Withdrawal approved')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to approve withdrawal')
    },
  })

  // Reject withdrawal
  const rejectMutation = useMutation({
    mutationFn: (transactionId: number) =>
      api.payments.rejectWithdrawal(transactionId, 'Rejected by admin'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['withdrawals-pending'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Withdrawal rejected')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to reject withdrawal')
    },
  })

  // Filter transactions
  const filteredTransactions = React.useMemo(() => {
    if (!transactions) return []

    return transactions.filter((t) => {
      if (search) {
        const searchLower = search.toLowerCase()
        return (
          t.reference_id.toLowerCase().includes(searchLower) ||
          t.user_id.toString().includes(search) ||
          t.description.toLowerCase().includes(searchLower)
        )
      }
      return true
    })
  }, [transactions, search])

  const getStatusBadge = (status: string) => {
    const variants = {
      pending: { variant: 'secondary' as const, label: 'Pending' },
      completed: { variant: 'default' as const, label: 'Completed' },
      failed: { variant: 'destructive' as const, label: 'Failed' },
    }
    const config = variants[status as keyof typeof variants] || variants.pending
    return <Badge variant={config.variant}>{config.label}</Badge>
  }

  const getTypeBadge = (type: string) => {
    const colors = {
      deposit: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      withdrawal: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
      purchase: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
      fee: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
      referral_commission: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    }
    return (
      <Badge className={colors[type as keyof typeof colors] || colors.fee}>
        {type.replace('_', ' ').toUpperCase()}
      </Badge>
    )
  }

  // Loading state
  if (authLoading || (transactionsLoading && !transactions)) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">Loading transactions...</p>
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

  // Calculate stats
  const totalDeposits = transactions?.filter(t => t.transaction_type === 'deposit' && t.status === 'completed').reduce((sum, t) => sum + parseFloat(t.amount_usd), 0) || 0
  const totalWithdrawals = transactions?.filter(t => t.transaction_type === 'withdrawal' && t.status === 'completed').reduce((sum, t) => sum + parseFloat(t.amount_usd), 0) || 0
  const pendingCount = pendingWithdrawals?.length || 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <CreditCard className="h-8 w-8" />
          Payment Management
        </h1>
        <p className="text-muted-foreground mt-1">
          Manage transactions, deposits, and withdrawals
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Deposits</CardTitle>
            <DollarSign className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${formatCurrency(totalDeposits)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Withdrawals</CardTitle>
            <DollarSign className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${formatCurrency(totalWithdrawals)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Withdrawals</CardTitle>
            <AlertCircle className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{pendingCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Net Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${formatCurrency(totalDeposits - totalWithdrawals)}</div>
          </CardContent>
        </Card>
      </div>

      {/* Pending Withdrawals */}
      {pendingCount > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Pending Withdrawals ({pendingCount})</CardTitle>
            <CardDescription>Withdrawal requests awaiting approval</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {pendingWithdrawals?.map((withdrawal) => (
                <div
                  key={withdrawal.id}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div>
                    <p className="font-medium">User #{withdrawal.user_id}</p>
                    <p className="text-sm text-muted-foreground">
                      Amount: ${formatCurrency(parseFloat(withdrawal.amount_usd))}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Requested: {formatDate(withdrawal.created_at)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => approveMutation.mutate(withdrawal.id)}
                      disabled={approveMutation.isPending}
                    >
                      <CheckCircle className="mr-2 h-4 w-4" />
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => rejectMutation.mutate(withdrawal.id)}
                      disabled={rejectMutation.isPending}
                    >
                      <XCircle className="mr-2 h-4 w-4" />
                      Reject
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by reference ID, user ID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="deposit">Deposit</SelectItem>
                <SelectItem value="withdrawal">Withdrawal</SelectItem>
                <SelectItem value="purchase">Purchase</SelectItem>
                <SelectItem value="fee">Fee</SelectItem>
                <SelectItem value="referral_commission">Referral</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Transactions Table */}
      <Card>
        <CardHeader>
          <CardTitle>All Transactions ({filteredTransactions.length})</CardTitle>
          <CardDescription>Complete transaction history</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>User</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Reference</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTransactions.length > 0 ? (
                filteredTransactions.map((transaction) => (
                  <TableRow key={transaction.id}>
                    <TableCell className="font-medium">#{transaction.id}</TableCell>
                    <TableCell>User #{transaction.user_id}</TableCell>
                    <TableCell>{getTypeBadge(transaction.transaction_type)}</TableCell>
                    <TableCell className="font-mono">
                      ${formatCurrency(parseFloat(transaction.amount_usd))}
                    </TableCell>
                    <TableCell>{getStatusBadge(transaction.status)}</TableCell>
                    <TableCell className="font-mono text-xs">{transaction.reference_id.slice(0, 12)}...</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(transaction.created_at)}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                    No transactions found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
