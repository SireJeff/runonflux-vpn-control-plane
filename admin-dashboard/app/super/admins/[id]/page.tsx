'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatDate, formatRelativeTime, getStatusColor } from '@/lib/utils'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  DollarSign,
  Users,
  Wallet,
  CreditCard,
  Phone,
  MessageSquare,
  Loader2,
  Radio,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import toast from 'react-hot-toast'
import { useState } from 'react'

export default function AdminDetailPage({ params }: { params: { id: string } }) {
  const adminId = parseInt(params.id, 10)
  const router = useRouter()
  const queryClient = useQueryClient()

  // Credit form state
  const [creditAmount, setCreditAmount] = useState('')
  const [creditReason, setCreditReason] = useState('')

  // Fetch admin detail
  const { data: admin, isLoading } = useQuery({
    queryKey: ['super', 'admin', adminId],
    queryFn: () => api.superAdmin.getAdminDetail(adminId),
    enabled: !isNaN(adminId),
  })

  // Credit mutation
  const creditMutation = useMutation({
    mutationFn: () =>
      api.superAdmin.creditWallet(adminId, parseFloat(creditAmount), creditReason),
    onSuccess: (response) => {
      toast.success(response.message)
      setCreditAmount('')
      setCreditReason('')
      queryClient.invalidateQueries({ queryKey: ['super', 'admin', adminId] })
    },
    onError: () => {
      toast.error('Failed to credit wallet')
    },
  })

  // Broadcasts kill-switch mutation
  const broadcastsToggleMutation = useMutation({
    mutationFn: (enabled: boolean) => api.superAdmin.setBroadcastsEnabled(adminId, enabled),
    onSuccess: (res) => {
      toast.success(res.broadcasts_enabled ? 'Broadcasts enabled' : 'Broadcasts disabled')
      queryClient.invalidateQueries({ queryKey: ['super', 'admin', adminId] })
    },
    onError: () => {
      toast.error('Failed to update broadcasts setting')
    },
  })

  const handleCreditSubmit = () => {
    if (!creditAmount || parseFloat(creditAmount) <= 0 || !creditReason.trim()) {
      toast.error('Please enter a valid amount and reason')
      return
    }
    creditMutation.mutate()
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
        <Skeleton className="h-96" />
      </div>
    )
  }

  if (!admin) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Admin not found</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push('/super/admins')}>
          Back to Admins
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Back button + Header */}
      <div className="flex items-center gap-4">
        <Link href="/super/admins">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{admin.username}</h2>
          <p className="text-muted-foreground">Admin details and management</p>
        </div>
        <Badge className={`ml-auto ${getStatusColor(admin.status)}`}>{admin.status}</Badge>
      </div>

      {/* Top row: Info + Wallet */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Admin Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Admin Information</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3">
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Username</dt>
                <dd className="text-sm font-medium">{admin.username}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Display Name</dt>
                <dd className="text-sm font-medium">{admin.display_name || '-'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Telegram</dt>
                <dd className="text-sm font-medium">{admin.telegram_id || '-'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">WhatsApp</dt>
                <dd className="text-sm font-medium">{admin.whatsapp_number || '-'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Phone</dt>
                <dd className="text-sm font-medium">{admin.phone_number || '-'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Status</dt>
                <dd>
                  <Badge className={getStatusColor(admin.status)}>{admin.status}</Badge>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Created</dt>
                <dd className="text-sm font-medium">
                  {admin.created_at ? formatDate(admin.created_at, true) : '-'}
                </dd>
              </div>
              {admin.approved_at && (
                <div className="flex justify-between">
                  <dt className="text-sm text-muted-foreground">Approved At</dt>
                  <dd className="text-sm font-medium">{formatDate(admin.approved_at, true)}</dd>
                </div>
              )}
              {admin.notes && (
                <div className="pt-2 border-t">
                  <dt className="text-sm text-muted-foreground mb-1">Notes</dt>
                  <dd className="text-sm">{admin.notes}</dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        {/* Wallet Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Wallet className="h-4 w-4" />
              Wallet
            </CardTitle>
            <CardDescription>Balance: {formatCurrency(Number(admin.wallet_balance))}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">End Users</p>
                <p className="text-lg font-bold">{admin.user_count}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Wallet Balance</p>
                <p className="text-lg font-bold">{formatCurrency(Number(admin.wallet_balance))}</p>
              </div>
            </div>

            {/* Manual Credit Form */}
            <div className="space-y-3 border-t pt-4">
              <h4 className="text-sm font-medium">Manual Credit</h4>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="credit-amount" className="text-xs">
                    Amount (USD)
                  </Label>
                  <Input
                    id="credit-amount"
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="0.00"
                    value={creditAmount}
                    onChange={(e) => setCreditAmount(e.target.value)}
                  />
                </div>
                <div className="col-span-2 space-y-1">
                  <Label htmlFor="credit-reason" className="text-xs">
                    Reason
                  </Label>
                  <Textarea
                    id="credit-reason"
                    placeholder="Reason for credit..."
                    value={creditReason}
                    onChange={(e) => setCreditReason(e.target.value)}
                    rows={2}
                  />
                </div>
              </div>
              <Button
                className="w-full"
                size="sm"
                onClick={handleCreditSubmit}
                disabled={
                  !creditAmount ||
                  parseFloat(creditAmount) <= 0 ||
                  !creditReason.trim() ||
                  creditMutation.isPending
                }
              >
                {creditMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Credit Wallet
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Broadcasts kill-switch */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Radio className="h-4 w-4" />
            Broadcasts
          </CardTitle>
          <CardDescription>
            Allow this reseller to send broadcast messages to their end-users.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                {admin.broadcasts_enabled ? 'Enabled' : 'Disabled'}
              </p>
              <p className="text-xs text-muted-foreground">
                {admin.broadcasts_enabled
                  ? 'This reseller can send broadcasts.'
                  : 'Broadcasting is blocked for this reseller.'}
              </p>
            </div>
            <Switch
              checked={admin.broadcasts_enabled}
              disabled={broadcastsToggleMutation.isPending}
              onCheckedChange={(checked) => broadcastsToggleMutation.mutate(checked)}
              aria-label="Toggle broadcasts for this reseller"
            />
          </div>
        </CardContent>
      </Card>

      {/* Recent Transactions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Transactions</CardTitle>
          <CardDescription>Last {admin.recent_transactions.length} wallet transactions</CardDescription>
        </CardHeader>
        <CardContent>
          {admin.recent_transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No transactions yet
            </p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="hidden sm:table-cell">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {admin.recent_transactions.map((txn) => (
                    <TableRow key={txn.id}>
                      <TableCell className="font-mono text-xs">#{txn.id}</TableCell>
                      <TableCell>
                        <span
                          className={
                            txn.amount_usd >= 0 ? 'text-green-600' : 'text-red-600'
                          }
                        >
                          {txn.amount_usd >= 0 ? '+' : ''}
                          {formatCurrency(txn.amount_usd)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs">{txn.transaction_type}</span>
                      </TableCell>
                      <TableCell>
                        <Badge className={getStatusColor(txn.status)}>{txn.status}</Badge>
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {txn.description}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                        {txn.created_at ? formatRelativeTime(txn.created_at) : '-'}
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
  )
}
