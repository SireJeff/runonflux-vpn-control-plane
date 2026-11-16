'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatDate, getStatusColor, formatCurrency } from '@/lib/utils'
import {
  ShoppingCart,
  CheckCircle2,
  XCircle,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileText,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import toast from 'react-hot-toast'

const STATUS_TABS = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

const PER_PAGE = 20

export default function SuperAdminOrdersPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('all')
  const [page, setPage] = useState(1)

  // Approve dialog state
  const [approveDialogOpen, setApproveDialogOpen] = useState(false)
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null)
  const [approveExchangeRate, setApproveExchangeRate] = useState('600000')
  const [approveNotes, setApproveNotes] = useState('')

  // Reject dialog state
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)
  const [rejectNotes, setRejectNotes] = useState('')

  // Fetch orders
  const { data, isLoading } = useQuery({
    queryKey: ['super', 'orders', activeTab, page],
    queryFn: () =>
      api.superAdmin.listOrders({
        status: activeTab === 'all' ? undefined : activeTab,
        page,
        per_page: PER_PAGE,
      }),
  })

  const orders = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / PER_PAGE)

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: (data: { orderId: number; exchangeRate?: number; adminNotes?: string }) =>
      api.superAdmin.approveOrder(data.orderId, {
        ...(data.exchangeRate !== undefined ? { exchange_rate: data.exchangeRate } : {}),
        admin_notes: data.adminNotes,
      }),
    onSuccess: (response) => {
      toast.success(
        `Order approved: ${response.amount_tomans?.toLocaleString()} tomans -> ${formatCurrency(response.amount_usd || 0)}`
      )
      setApproveDialogOpen(false)
      setSelectedOrderId(null)
      setApproveNotes('')
      queryClient.invalidateQueries({ queryKey: ['super', 'orders'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to approve order')
    },
  })

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: (data: { orderId: number; adminNotes: string }) =>
      api.superAdmin.rejectOrder(data.orderId, { admin_notes: data.adminNotes }),
    onSuccess: (response) => {
      toast.success(response.message)
      setRejectDialogOpen(false)
      setSelectedOrderId(null)
      setRejectNotes('')
      queryClient.invalidateQueries({ queryKey: ['super', 'orders'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to reject order')
    },
  })

  const handleApproveSubmit = () => {
    if (!selectedOrderId) return
    const order = orders.find((o) => o.id === selectedOrderId)
    const isCrypto = order?.payment_method === 'crypto'
    if (!isCrypto && (!approveExchangeRate || parseFloat(approveExchangeRate) <= 0)) return
    approveMutation.mutate({
      orderId: selectedOrderId,
      exchangeRate: isCrypto ? undefined : parseFloat(approveExchangeRate),
      adminNotes: approveNotes || undefined,
    })
  }

  const handleRejectSubmit = () => {
    if (!selectedOrderId || !rejectNotes.trim()) {
      toast.error('Please provide rejection notes')
      return
    }
    rejectMutation.mutate({ orderId: selectedOrderId, adminNotes: rejectNotes })
  }

  const selectedOrder = orders.find((o) => o.id === selectedOrderId)
  const selectedIsCrypto = selectedOrder?.payment_method === 'crypto'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Orders</h2>
        <p className="text-muted-foreground">View and manage wire transfer orders</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Wire Orders</CardTitle>
              <CardDescription>{total} total orders</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v); setPage(1) }}>
            <TabsList>
              {STATUS_TABS.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value={activeTab} className="mt-4">
              {isLoading ? (
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : orders.length === 0 ? (
                <div className="text-center py-10">
                  <ShoppingCart className="mx-auto h-10 w-10 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">
                    No orders found
                  </p>
                </div>
              ) : (
                <>
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Admin</TableHead>
                          <TableHead>Method</TableHead>
                          <TableHead>Amount (Tomans)</TableHead>
                          <TableHead className="hidden sm:table-cell">Amount (USD)</TableHead>
                          <TableHead className="hidden md:table-cell">Telegram</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="hidden lg:table-cell">Date</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {orders.map((order) => (
                          <TableRow key={order.id}>
                            <TableCell className="font-medium">
                              {order.admin_username || `Admin #${order.admin_id}`}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">
                                {order.payment_method === 'crypto' ? '🪙 Crypto' : '💳 Wire'}
                              </Badge>
                              {order.payment_method === 'crypto' && order.crypto_txid && (
                                <div className="mt-1 text-xs text-muted-foreground">
                                  {order.crypto_txid.length > 14
                                    ? `${order.crypto_txid.slice(0, 6)}...${order.crypto_txid.slice(-6)}`
                                    : order.crypto_txid}
                                  {order.crypto_link && (
                                    <>
                                      {' '}
                                      <a
                                        href={order.crypto_link}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="underline"
                                      >
                                        View on explorer
                                      </a>
                                    </>
                                  )}
                                </div>
                              )}
                            </TableCell>
                            <TableCell>
                              {Number(order.amount_tomans).toLocaleString()} T
                            </TableCell>
                            <TableCell className="hidden sm:table-cell">
                              {order.amount_usd
                                ? formatCurrency(Number(order.amount_usd))
                                : '-'}
                            </TableCell>
                            <TableCell className="hidden md:table-cell">
                              {order.contact_telegram}
                            </TableCell>
                            <TableCell>
                              <Badge className={getStatusColor(order.status)}>
                                {order.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="hidden lg:table-cell">
                              {order.created_at ? formatDate(order.created_at) : '-'}
                            </TableCell>
                            <TableCell className="text-right">
                              {order.status === 'pending' && (
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-8 w-8">
                                      <MoreHorizontal className="h-4 w-4" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setSelectedOrderId(order.id)
                                        setApproveDialogOpen(true)
                                      }}
                                    >
                                      <CheckCircle2 className="mr-2 h-4 w-4" />
                                      Approve
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setSelectedOrderId(order.id)
                                        setRejectDialogOpen(true)
                                      }}
                                    >
                                      <XCircle className="mr-2 h-4 w-4" />
                                      Reject
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <p className="text-sm text-muted-foreground">
                        Showing {(page - 1) * PER_PAGE + 1}-
                        {Math.min(page * PER_PAGE, total)} of {total}
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={page <= 1}
                        >
                          <ChevronLeft className="h-4 w-4" />
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                          disabled={page >= totalPages}
                        >
                          Next
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Approve Dialog */}
      <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve Wire Order</DialogTitle>
            <DialogDescription>
              Set the exchange rate to convert Tomans to USD. The admin wallet will be credited.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border p-3 bg-muted/50">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-muted-foreground">Order ID</span>
                <span className="font-medium">#{selectedOrderId}</span>
              </div>
            </div>
            {selectedIsCrypto ? (
              <p className="text-sm">
                Will credit{' '}
                {selectedOrder?.amount_usd
                  ? formatCurrency(Number(selectedOrder.amount_usd))
                  : '$0.00'}{' '}
                to the reseller.
              </p>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="exchange-rate">Exchange Rate (Toman per USD)</Label>
                <Input
                  id="exchange-rate"
                  type="number"
                  step="1000"
                  min="1"
                  placeholder="e.g. 600000"
                  value={approveExchangeRate}
                  onChange={(e) => setApproveExchangeRate(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  USD Amount = Order Tomans / Exchange Rate
                </p>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="approve-notes">Notes (optional)</Label>
              <Textarea
                id="approve-notes"
                placeholder="Optional notes..."
                value={approveNotes}
                onChange={(e) => setApproveNotes(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleApproveSubmit}
              disabled={
                approveMutation.isPending ||
                (!selectedIsCrypto && (!approveExchangeRate || parseFloat(approveExchangeRate) <= 0))
              }
            >
              {approveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Approve Order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Wire Order</DialogTitle>
            <DialogDescription>
              Rejecting this order will notify the admin. Please provide a reason.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border p-3 bg-muted/50">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-muted-foreground">Order ID</span>
                <span className="font-medium">#{selectedOrderId}</span>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="reject-notes">Rejection Notes</Label>
              <Textarea
                id="reject-notes"
                placeholder="Reason for rejection..."
                value={rejectNotes}
                onChange={(e) => setRejectNotes(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleRejectSubmit}
              disabled={!rejectNotes.trim() || rejectMutation.isPending}
            >
              {rejectMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Reject Order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
