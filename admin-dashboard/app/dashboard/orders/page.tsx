'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Order } from '@/lib/api'
import { formatDate, formatSnapshotTrafficGb } from '@/lib/utils'
import {
  ShoppingCart,
  Loader2,
  Check,
  X,
  Eye,
  ImageIcon,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import toast from 'react-hot-toast'

type OrderStatus = 'pending' | 'approved' | 'rejected' | 'all'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  approved: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
}

function formatTomans(value: string | number): string {
  return Number(value).toLocaleString()
}

export default function OrdersPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<OrderStatus>('pending')
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [rejectOrderId, setRejectOrderId] = useState<number | null>(null)

  // Fetch orders
  const { data: orders, isLoading } = useQuery({
    queryKey: ['orders', activeTab],
    queryFn: () => api.orders.list(activeTab === 'all' ? undefined : activeTab),
  })

  // Fetch receipt as blob URL
  const { data: receiptUrl, isLoading: receiptLoading } = useQuery({
    queryKey: ['order-receipt', selectedOrder?.id],
    queryFn: () => api.orders.getReceiptUrl(selectedOrder!.id),
    enabled: !!selectedOrder?.id && !!selectedOrder.receipt_file_id,
  })

  // Cleanup blob URL on unmount or change
  useEffect(() => {
    return () => {
      if (receiptUrl) {
        URL.revokeObjectURL(receiptUrl)
      }
    }
  }, [receiptUrl])

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: (id: number) => api.orders.approve(id),
    onSuccess: () => {
      toast.success('Order approved')
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setDetailOpen(false)
      setSelectedOrder(null)
    },
    onError: () => {
      toast.error('Failed to approve order')
    },
  })

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      api.orders.reject(id, reason),
    onSuccess: () => {
      toast.success('Order rejected')
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setRejectDialogOpen(false)
      setRejectOrderId(null)
      setRejectReason('')
      setDetailOpen(false)
      setSelectedOrder(null)
    },
    onError: () => {
      toast.error('Failed to reject order')
    },
  })

  const openDetail = (order: Order) => {
    setSelectedOrder(order)
    setDetailOpen(true)
  }

  const openRejectDialog = (orderId: number) => {
    setRejectOrderId(orderId)
    setRejectReason('')
    setRejectDialogOpen(true)
  }

  const handleReject = () => {
    if (!rejectOrderId) return
    rejectMutation.mutate({ id: rejectOrderId, reason: rejectReason || undefined })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Orders</h2>
        <p className="text-muted-foreground">Review and manage subscription orders</p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as OrderStatus)}>
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected">Rejected</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-4">
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-6 space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : !orders || orders.length === 0 ? (
                <div className="p-12 text-center">
                  <ShoppingCart className="mx-auto h-12 w-12 text-muted-foreground/50" />
                  <p className="mt-4 text-muted-foreground">No orders found</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>User ID</TableHead>
                        <TableHead>Package</TableHead>
                        <TableHead>Region</TableHead>
                        <TableHead>Amount</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Method</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {orders.map((order) => (
                        <TableRow
                          key={order.id}
                          className="cursor-pointer"
                          onClick={() => openDetail(order)}
                        >
                          <TableCell className="font-medium">#{order.id}</TableCell>
                          <TableCell>
                            <Badge variant="outline">
                              {order.kind === 'topup' ? '💰 Top-up' : '📦 Sub'}
                            </Badge>
                          </TableCell>
                          <TableCell>{order.user_id}</TableCell>
                          <TableCell>
                            {order.kind === 'topup'
                              ? '—'
                              : order.package_snapshot?.name || `PKG-${order.package_id}`}
                          </TableCell>
                          <TableCell className="uppercase text-xs">{order.macro_region}</TableCell>
                          <TableCell>{formatTomans(order.amount_tomans)} T</TableCell>
                          <TableCell>
                            <Badge className={STATUS_COLORS[order.status] || ''}>
                              {order.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">
                              {order.payment_method === 'crypto' ? '🪙 Crypto' : '💳 Card'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(order.created_at, true)}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button variant="ghost" size="sm">
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Order Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Order #{selectedOrder?.id}</DialogTitle>
            <DialogDescription>
              Created {selectedOrder?.created_at ? formatDate(selectedOrder.created_at, true) : 'N/A'}
            </DialogDescription>
          </DialogHeader>

          {selectedOrder && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-muted-foreground">User ID</p>
                  <p className="font-medium">{selectedOrder.user_id}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <Badge className={STATUS_COLORS[selectedOrder.status] || ''}>
                    {selectedOrder.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">Method</p>
                  <Badge variant="outline">
                    {selectedOrder.payment_method === 'crypto' ? '🪙 Crypto' : '💳 Card'}
                  </Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">Package</p>
                  <p className="font-medium">
                    {selectedOrder.package_snapshot?.name || `PKG-${selectedOrder.package_id}`}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Region</p>
                  <p className="font-medium uppercase">{selectedOrder.macro_region}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Amount</p>
                  <p className="font-medium">{formatTomans(selectedOrder.amount_tomans)} T</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Wallet Credit</p>
                  <p className="font-medium">
                    {formatTomans(selectedOrder.wallet_credit_applied_tomans)} T
                  </p>
                </div>
                {selectedOrder.package_snapshot && (
                  <>
                    <div>
                      <p className="text-muted-foreground">Traffic</p>
                      <p className="font-medium">
                        {formatSnapshotTrafficGb(selectedOrder.package_snapshot)}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Duration</p>
                      <p className="font-medium">
                        {selectedOrder.package_snapshot.duration_days
                          ? `${selectedOrder.package_snapshot.duration_days} days`
                          : '-'}
                      </p>
                    </div>
                  </>
                )}
                {selectedOrder.rejection_reason && (
                  <div className="col-span-2">
                    <p className="text-muted-foreground">Rejection Reason</p>
                    <p className="font-medium text-red-600">{selectedOrder.rejection_reason}</p>
                  </div>
                )}
                {selectedOrder.expires_at && (
                  <div>
                    <p className="text-muted-foreground">Expires</p>
                    <p className="font-medium">{formatDate(selectedOrder.expires_at, true)}</p>
                  </div>
                )}
              </div>

              {/* Receipt / Crypto Section */}
              {selectedOrder.payment_method === 'crypto' ? (
                <div className="border rounded-lg p-4">
                  <p className="text-sm font-medium mb-2 flex items-center gap-2">
                    🪙 Crypto Payment
                  </p>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Transaction ID</p>
                      <p className="font-mono break-all text-xs">
                        {selectedOrder.crypto_txid || 'N/A'}
                      </p>
                    </div>
                    {selectedOrder.crypto_link && (
                      <a
                        href={selectedOrder.crypto_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:underline dark:text-blue-400"
                      >
                        View on explorer
                      </a>
                    )}
                    {selectedOrder.amount_usd_snapshot && (
                      <p className="text-sm text-muted-foreground">
                        USD: ${selectedOrder.amount_usd_snapshot}
                      </p>
                    )}
                  </div>
                </div>
              ) : selectedOrder.status === 'pending' || selectedOrder.receipt_file_id ? (
                <div className="border rounded-lg p-4">
                  <p className="text-sm font-medium mb-2 flex items-center gap-2">
                    <ImageIcon className="h-4 w-4" />
                    Payment Receipt
                  </p>
                  {!selectedOrder.receipt_file_id ? (
                    <p className="text-sm text-muted-foreground">
                      No receipt uploaded
                    </p>
                  ) : !selectedOrder.receipt_local_path ? (
                    <div className="flex items-center gap-2 text-sm text-yellow-600">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Receipt download in progress...
                    </div>
                  ) : receiptLoading ? (
                    <div className="flex flex-col items-center gap-2">
                      <Skeleton className="h-48 w-full max-w-sm" />
                      <p className="text-sm text-muted-foreground">Loading receipt...</p>
                    </div>
                  ) : receiptUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={receiptUrl}
                      alt="Payment receipt"
                      className="max-h-64 rounded border object-contain mx-auto"
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">Could not load receipt</p>
                  )}
                </div>
              ) : null}

              {/* Actions for pending orders */}
              {selectedOrder.status === 'pending' && (
                <div className="flex gap-3 pt-2">
                  <Button
                    className="flex-1"
                    onClick={() => approveMutation.mutate(selectedOrder.id)}
                    disabled={approveMutation.isPending}
                  >
                    {approveMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="mr-2 h-4 w-4" />
                    )}
                    Approve
                  </Button>
                  <Button
                    variant="destructive"
                    className="flex-1"
                    onClick={() => openRejectDialog(selectedOrder.id)}
                  >
                    <X className="mr-2 h-4 w-4" />
                    Reject
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Reject Reason Dialog */}
      <AlertDialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reject Order</AlertDialogTitle>
            <AlertDialogDescription>
              Optionally provide a reason for rejecting this order. The user will be notified.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <div className="space-y-2">
              <Label htmlFor="reject-reason">Rejection reason (optional)</Label>
              <Textarea
                id="reject-reason"
                placeholder="e.g. Receipt is unclear, wrong amount, etc."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleReject}
              disabled={rejectMutation.isPending}
            >
              {rejectMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Reject Order
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
