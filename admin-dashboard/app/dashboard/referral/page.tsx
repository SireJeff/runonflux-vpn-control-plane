'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { copyToClipboard, formatDate } from '@/lib/utils'
import {
  Gift,
  Loader2,
  Save,
  Copy,
  Check,
  Users,
  DollarSign,
  Wallet,
  Percent,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import toast from 'react-hot-toast'
import type { ReferralConfig } from '@/lib/api'

function formatTomans(value: string | number): string {
  return Number(value).toLocaleString()
}

export default function ReferralPage() {
  const queryClient = useQueryClient()
  const [rewardPercentage, setRewardPercentage] = useState('')
  const [isEnabled, setIsEnabled] = useState(false)
  const [rewardType, setRewardType] = useState<ReferralConfig['reward_type']>('cashback')
  const [trafficPerReferralMb, setTrafficPerReferralMb] = useState(0)
  const [trafficMaxBonusMb, setTrafficMaxBonusMb] = useState(0)
  const [codeCopied, setCodeCopied] = useState(false)

  // Fetch referral config
  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['referral-config'],
    queryFn: () => api.referral.getConfig(),
  })

  // Fetch referral stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['referral-stats'],
    queryFn: () => api.referral.getStats(),
  })

  // Fetch referral earnings
  const { data: earnings, isLoading: earningsLoading } = useQuery({
    queryKey: ['referral-earnings'],
    queryFn: () => api.referral.getEarnings(50),
  })

  // Populate form from config
  useEffect(() => {
    if (config) {
      setRewardPercentage(config.reward_percentage)
      setIsEnabled(config.is_enabled)
      setRewardType(config.reward_type ?? 'cashback')
      setTrafficPerReferralMb(config.traffic_per_referral_mb ?? 0)
      setTrafficMaxBonusMb(config.traffic_max_bonus_mb ?? 0)
    }
  }, [config])

  // Update config mutation
  const updateConfigMutation = useMutation({
    mutationFn: () =>
      api.referral.updateConfig({
        is_enabled: isEnabled,
        reward_percentage: Number(rewardPercentage),
        reward_type: rewardType,
        traffic_per_referral_mb: trafficPerReferralMb,
        traffic_max_bonus_mb: trafficMaxBonusMb,
      }),
    onSuccess: () => {
      toast.success('Referral config updated')
      queryClient.invalidateQueries({ queryKey: ['referral-config'] })
    },
    onError: () => {
      toast.error('Failed to update referral config')
    },
  })

  const handleSaveConfig = () => {
    const pct = Number(rewardPercentage)
    if (isNaN(pct) || pct < 0 || pct > 100) {
      toast.error('Reward percentage must be between 0 and 100')
      return
    }
    updateConfigMutation.mutate()
  }

  const handleCopyCode = async (code: string) => {
    const ok = await copyToClipboard(code)
    if (ok) {
      setCodeCopied(true)
      setTimeout(() => setCodeCopied(false), 2000)
    }
  }

  const totalEarned = Number(stats?.total_earned_tomans || 0)
  const walletCredit = Number(stats?.wallet_credit_tomans || 0)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Referral Program</h2>
        <p className="text-muted-foreground">Manage referral settings and track earnings</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Config Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {configLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <Label htmlFor="referral-enabled">Enable Referrals</Label>
                  <Switch
                    id="referral-enabled"
                    checked={isEnabled}
                    onCheckedChange={setIsEnabled}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reward-pct">Reward Percentage (0-100)</Label>
                  <div className="flex gap-2">
                    <Input
                      id="reward-pct"
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      placeholder="10"
                      value={rewardPercentage}
                      onChange={(e) => setRewardPercentage(e.target.value)}
                      className="w-32"
                    />
                    <span className="flex items-center text-sm text-muted-foreground">
                      % of order amount
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reward-type">Reward Type</Label>
                  <Select
                    value={rewardType}
                    onValueChange={(val) => setRewardType(val as ReferralConfig['reward_type'])}
                  >
                    <SelectTrigger id="reward-type" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cashback">Cashback only</SelectItem>
                      <SelectItem value="traffic">Traffic bonus only</SelectItem>
                      <SelectItem value="both">Both</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {rewardType !== 'cashback' && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="traffic-per-referral">MB per referral</Label>
                      <Input
                        id="traffic-per-referral"
                        type="number"
                        min={0}
                        value={trafficPerReferralMb}
                        onChange={(e) => setTrafficPerReferralMb(Number(e.target.value))}
                        className="w-32"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="traffic-max-bonus">Max total bonus (MB)</Label>
                      <Input
                        id="traffic-max-bonus"
                        type="number"
                        min={0}
                        value={trafficMaxBonusMb}
                        onChange={(e) => setTrafficMaxBonusMb(Number(e.target.value))}
                        className="w-32"
                      />
                      <p className="text-xs text-muted-foreground">
                        Capped by the platform ceiling; the server clamps values above it.
                      </p>
                    </div>
                  </>
                )}
                <Button
                  onClick={handleSaveConfig}
                  disabled={updateConfigMutation.isPending}
                >
                  {updateConfigMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  Save Config
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        {/* Stats Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Your Stats</CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <div className="space-y-4">
                {/* Referral Code */}
                <div className="rounded-lg border p-3">
                  <p className="text-xs text-muted-foreground mb-1">Your Referral Code</p>
                  {stats?.my_referral_code ? (
                    <div className="flex items-center gap-2">
                      <code className="text-lg font-bold">{stats.my_referral_code}</code>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopyCode(stats.my_referral_code!)}
                      >
                        {codeCopied ? (
                          <Check className="h-4 w-4 text-green-500" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No referral code generated</p>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-lg border p-3">
                    <Users className="mx-auto h-4 w-4 text-muted-foreground mb-1" />
                    <p className="text-lg font-bold">{stats?.total_referrals || 0}</p>
                    <p className="text-xs text-muted-foreground">Referrals</p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <DollarSign className="mx-auto h-4 w-4 text-muted-foreground mb-1" />
                    <p className="text-lg font-bold">{formatTomans(totalEarned)}</p>
                    <p className="text-xs text-muted-foreground">Earned (T)</p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <Wallet className="mx-auto h-4 w-4 text-muted-foreground mb-1" />
                    <p className="text-lg font-bold">{formatTomans(walletCredit)}</p>
                    <p className="text-xs text-muted-foreground">Wallet (T)</p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Earnings Table */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle className="text-base">Earnings History</CardTitle>
            <CardDescription>Commission from successful referrals (max 50)</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {earningsLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : !earnings || earnings.length === 0 ? (
            <div className="py-12 text-center">
              <Gift className="mx-auto h-12 w-12 text-muted-foreground/50" />
              <p className="mt-4 text-muted-foreground">No referral earnings yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Order ID</TableHead>
                    <TableHead>Commission</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {earnings.map((earning) => (
                    <TableRow key={earning.id}>
                      <TableCell className="font-medium">#{earning.id}</TableCell>
                      <TableCell>#{earning.order_id}</TableCell>
                      <TableCell>
                        <Badge className="bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300">
                          <Percent className="mr-1 h-3 w-3" />
                          {Number(earning.commission_percent).toFixed(1)}%
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium text-green-600">
                        +{formatTomans(earning.amount_tomans)} T
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDate(earning.created_at, true)}
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
