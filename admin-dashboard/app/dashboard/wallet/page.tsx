'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatDate, getStatusColor } from '@/lib/utils'
import { usdToTomans } from '@/lib/format/conversion'
import {
  Wallet,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Send,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
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
import { Label } from '@/components/ui/label'
import toast from 'react-hot-toast'

const PER_PAGE = 15

const TRANSACTION_TYPE_COLORS: Record<string, string> = {
  topup: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  traffic_charge: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  region_charge: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  credit: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  debit: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  wire_order: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
}

function getTransactionTypeColor(type: string): string {
  return TRANSACTION_TYPE_COLORS[type.toLowerCase()] || 'bg-gray-100 text-gray-800'
}

export default function WalletPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState('all')

  // Wire order form state
  const [amountTomans, setAmountTomans] = useState('')
  const [contactTelegram, setContactTelegram] = useState('')
  const [contactWhatsapp, setContactWhatsapp] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [orderNotes, setOrderNotes] = useState('')

  // Payment method + crypto top-up form state
  const [payMethod, setPayMethod] = useState<'wire' | 'crypto'>('wire')
  const [amountUsd, setAmountUsd] = useState('')
  const [cryptoTxid, setCryptoTxid] = useState('')
  const [cryptoLink, setCryptoLink] = useState('')

  // Fetch wallet
  const { data: wallet, isLoading: walletLoading } = useQuery({
    queryKey: ['admin', 'wallet'],
    queryFn: api.adminNew.getWallet,
    refetchInterval: 30000,
  })

  // Fetch payment config (tells us whether crypto top-up is enabled)
  const { data: paymentConfig } = useQuery({
    queryKey: ['admin', 'payment-config'],
    queryFn: () => api.adminNew.getPaymentConfig(),
  })

  // Fetch transactions
  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: ['admin', 'transactions', page, typeFilter],
    queryFn: () =>
      api.adminNew.getTransactions({
        page,
        per_page: PER_PAGE,
        type: typeFilter === 'all' ? undefined : typeFilter,
      }),
  })

  const transactions = txData?.items || []
  const totalTx = txData?.total || 0
  const totalPagesTx = Math.ceil(totalTx / PER_PAGE)

  const balance = Number(wallet?.balance || 0)
  const balanceColor =
    balance >= 50
      ? 'text-green-600 dark:text-green-400'
      : balance >= 10
        ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

  // Wire order mutation
  const wireOrderMutation = useMutation({
    mutationFn: () =>
      api.adminNew.createWireOrder({
        amount_tomans: parseInt(amountTomans),
        contact_telegram: contactTelegram,
        contact_whatsapp: contactWhatsapp || undefined,
        contact_phone: contactPhone || undefined,
        notes: orderNotes || undefined,
      }),
    onSuccess: (response) => {
      toast.success(response.message)
      setAmountTomans('')
      setContactTelegram('')
      setContactWhatsapp('')
      setContactPhone('')
      setOrderNotes('')
      queryClient.invalidateQueries({ queryKey: ['admin', 'wallet'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'transactions'] })
    },
    onError: () => {
      toast.error('Failed to submit wire order')
    },
  })

  const handleSubmitOrder = () => {
    if (!amountTomans || parseInt(amountTomans) < 500000) {
      toast.error('Minimum amount is 500,000 Tomans')
      return
    }
    if (!contactTelegram.trim()) {
      toast.error('Telegram contact is required')
      return
    }
    wireOrderMutation.mutate()
  }

  // Crypto order mutation
  const cryptoOrderMutation = useMutation({
    mutationFn: () =>
      api.adminNew.createWireOrder({
        payment_method: 'crypto',
        amount_usd: Number(amountUsd),
        crypto_txid: cryptoTxid,
        crypto_link: cryptoLink || undefined,
        contact_telegram: contactTelegram,
      }),
    onSuccess: () => {
      toast.success('Crypto top-up submitted for review')
      queryClient.invalidateQueries({ queryKey: ['admin', 'wallet'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'transactions'] })
      setAmountUsd('')
      setCryptoTxid('')
      setCryptoLink('')
    },
    onError: () => {
      toast.error('Failed to submit crypto top-up')
    },
  })

  const handleSubmitCrypto = () => {
    const usd = Number(amountUsd)
    if (!paymentConfig?.crypto_enabled) return
    if (!usd || usd < paymentConfig.min_topup_usd) {
      toast.error(`Minimum crypto top-up is $${paymentConfig.min_topup_usd}`)
      return
    }
    if (!cryptoTxid.trim()) {
      toast.error('Transaction ID is required')
      return
    }
    if (!contactTelegram.trim()) {
      toast.error('Telegram contact is required')
      return
    }
    cryptoOrderMutation.mutate()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Wallet</h2>
        <p className="text-muted-foreground">Manage your balance and top up</p>
      </div>

      {/* Balance Card */}
      <Card className="border-2">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Wallet className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">Current Balance</CardTitle>
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
              Low balance - top up to avoid service interruption
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Top-up Section */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top Up Wallet</CardTitle>
            <CardDescription>
              {payMethod === 'wire'
                ? 'Submit a wire order to add funds to your wallet'
                : 'Submit a crypto payment to add funds to your wallet'}
            </CardDescription>
            {paymentConfig?.crypto_enabled && (
              <div className="mt-3 inline-flex rounded-md border p-1">
                <button
                  type="button"
                  onClick={() => setPayMethod('wire')}
                  className={`rounded px-3 py-1 text-sm font-medium transition-colors ${
                    payMethod === 'wire'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Wire
                </button>
                <button
                  type="button"
                  onClick={() => setPayMethod('crypto')}
                  className={`rounded px-3 py-1 text-sm font-medium transition-colors ${
                    payMethod === 'crypto'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Crypto
                </button>
              </div>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {payMethod === 'wire' ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="amount-tomans">Amount (Tomans) *</Label>
                  <Input
                    id="amount-tomans"
                    type="number"
                    min={500000}
                    step={10000}
                    placeholder="500,000"
                    value={amountTomans}
                    onChange={(e) => setAmountTomans(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Minimum 500,000 Tomans</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="contact-telegram">Telegram Contact *</Label>
                  <Input
                    id="contact-telegram"
                    placeholder="@username"
                    value={contactTelegram}
                    onChange={(e) => setContactTelegram(e.target.value)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="contact-whatsapp">WhatsApp (optional)</Label>
                    <Input
                      id="contact-whatsapp"
                      placeholder="+1234567890"
                      value={contactWhatsapp}
                      onChange={(e) => setContactWhatsapp(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="contact-phone">Phone (optional)</Label>
                    <Input
                      id="contact-phone"
                      placeholder="+1234567890"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="order-notes">Notes (optional)</Label>
                  <Textarea
                    id="order-notes"
                    placeholder="Any additional information..."
                    value={orderNotes}
                    onChange={(e) => setOrderNotes(e.target.value)}
                    rows={2}
                  />
                </div>

                <Button
                  className="w-full"
                  onClick={handleSubmitOrder}
                  disabled={
                    !amountTomans ||
                    parseInt(amountTomans) < 500000 ||
                    !contactTelegram.trim() ||
                    wireOrderMutation.isPending
                  }
                >
                  {wireOrderMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  Submit Wire Order
                </Button>
              </>
            ) : (
              <>
                {paymentConfig?.crypto_topup_address && (
                  <div className="rounded-md border bg-muted/50 p-3 text-sm space-y-1">
                    <p>
                      <span className="text-muted-foreground">Address: </span>
                      <span className="font-mono break-all">{paymentConfig.crypto_topup_address}</span>
                    </p>
                    {paymentConfig.crypto_topup_network && (
                      <p>
                        <span className="text-muted-foreground">Network: </span>
                        {paymentConfig.crypto_topup_network}
                      </p>
                    )}
                    {paymentConfig.crypto_topup_memo && (
                      <p>
                        <span className="text-muted-foreground">Memo: </span>
                        {paymentConfig.crypto_topup_memo}
                      </p>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="amount-usd">Amount (USD) *</Label>
                  <Input
                    id="amount-usd"
                    type="number"
                    min={paymentConfig?.min_topup_usd ?? 0}
                    step="0.01"
                    placeholder={paymentConfig ? String(paymentConfig.min_topup_usd) : '0'}
                    value={amountUsd}
                    onChange={(e) => setAmountUsd(e.target.value)}
                  />
                  {paymentConfig && (
                    <p className="text-xs text-muted-foreground">
                      Minimum ${paymentConfig.min_topup_usd}
                      {Number(amountUsd) > 0 &&
                        ` ≈ ${formatCurrency(
                          usdToTomans(Number(amountUsd), paymentConfig.toman_per_usd_rate)
                        )} Tomans`}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="crypto-txid">Transaction ID *</Label>
                  <Input
                    id="crypto-txid"
                    placeholder="0x..."
                    value={cryptoTxid}
                    onChange={(e) => setCryptoTxid(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="crypto-link">Explorer Link (optional)</Label>
                  <Input
                    id="crypto-link"
                    placeholder="https://..."
                    value={cryptoLink}
                    onChange={(e) => setCryptoLink(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="crypto-contact-telegram">Telegram Contact *</Label>
                  <Input
                    id="crypto-contact-telegram"
                    placeholder="@username"
                    value={contactTelegram}
                    onChange={(e) => setContactTelegram(e.target.value)}
                  />
                </div>

                <Button
                  className="w-full"
                  onClick={handleSubmitCrypto}
                  disabled={
                    !amountUsd ||
                    !paymentConfig ||
                    Number(amountUsd) < paymentConfig.min_topup_usd ||
                    !cryptoTxid.trim() ||
                    !contactTelegram.trim() ||
                    cryptoOrderMutation.isPending
                  }
                >
                  {cryptoOrderMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  Submit Crypto Top-Up
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        {/* Recent transactions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            {walletLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (wallet?.recent_transactions || []).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No transactions yet
              </p>
            ) : (
              <div className="space-y-2">
                {(wallet?.recent_transactions || []).slice(0, 8).map((txn) => (
                  <div
                    key={txn.id}
                    className="flex items-center justify-between rounded-lg border p-2.5"
                  >
                    <div className="flex items-center gap-2">
                      <Badge className={getTransactionTypeColor(txn.transaction_type)}>
                        {txn.transaction_type}
                      </Badge>
                      <span className="text-xs text-muted-foreground truncate max-w-[120px]">
                        {txn.description}
                      </span>
                    </div>
                    <span
                      className={`text-sm font-medium ${
                        Number(txn.amount_usd) >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {Number(txn.amount_usd) >= 0 ? '+' : ''}
                      {formatCurrency(txn.amount_usd)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Full Transaction History */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-base">Transaction History</CardTitle>
              <CardDescription>{totalTx} total transactions</CardDescription>
            </div>
            <div className="w-full sm:w-48">
              <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(1) }}>
                <SelectTrigger>
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="topup">Top Up</SelectItem>
                  <SelectItem value="traffic_charge">Traffic Charge</SelectItem>
                  <SelectItem value="region_charge">Region Charge</SelectItem>
                  <SelectItem value="credit">Credit</SelectItem>
                  <SelectItem value="debit">Debit</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {txLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No transactions found
            </p>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Amount</TableHead>
                      <TableHead className="hidden sm:table-cell">Balance After</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {transactions.map((txn) => (
                      <TableRow key={txn.id}>
                        <TableCell className="text-xs text-muted-foreground">
                          {txn.created_at ? formatDate(txn.created_at, true) : '-'}
                        </TableCell>
                        <TableCell>
                          <Badge className={getTransactionTypeColor(txn.transaction_type)}>
                            {txn.transaction_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                          {txn.description}
                        </TableCell>
                        <TableCell>
                          <span
                            className={`font-medium ${
                              Number(txn.amount_usd) >= 0
                                ? 'text-green-600'
                                : 'text-red-600'
                            }`}
                          >
                            {Number(txn.amount_usd) >= 0 ? '+' : ''}
                            {formatCurrency(txn.amount_usd)}
                          </span>
                        </TableCell>
                        <TableCell className="hidden sm:table-cell text-sm">
                          {formatCurrency(txn.balance_after ?? 0)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              {totalPagesTx > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <p className="text-sm text-muted-foreground">
                    Showing {(page - 1) * PER_PAGE + 1}-
                    {Math.min(page * PER_PAGE, totalTx)} of {totalTx}
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
                      onClick={() => setPage((p) => Math.min(totalPagesTx, p + 1))}
                      disabled={page >= totalPagesTx}
                    >
                      Next
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
