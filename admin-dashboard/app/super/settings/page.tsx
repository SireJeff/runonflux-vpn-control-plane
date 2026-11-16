'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Settings, Loader2, KeyRound, Save } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import toast from 'react-hot-toast'

export default function SuperAdminSettingsPage() {
  const queryClient = useQueryClient()

  // Platform settings form state
  const [pricePerGb, setPricePerGb] = useState('')
  const [pricePerRegionMonthly, setPricePerRegionMonthly] = useState('')
  const [minTopupTomans, setMinTopupTomans] = useState('')
  const [tomanToUsdRate, setTomanToUsdRate] = useState('')
  const [tomanPerUsdRate, setTomanPerUsdRate] = useState('')
  const [minTopupUsd, setMinTopupUsd] = useState('')
  const [cryptoTopupAddress, setCryptoTopupAddress] = useState('')
  const [cryptoTopupNetwork, setCryptoTopupNetwork] = useState('')
  const [cryptoTopupMemo, setCryptoTopupMemo] = useState('')

  // DNS API keys state
  const [cloudflareApiToken, setCloudflareApiToken] = useState('')
  const [arvanApiKey, setArvanApiKey] = useState('')

  // Change password form state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // Fetch current settings
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['super', 'settings'],
    queryFn: api.superAdmin.getSettings,
  })

  // Populate form when settings load
  useEffect(() => {
    if (settings) {
      setPricePerGb(settings.price_per_gb)
      setPricePerRegionMonthly(settings.price_per_region_monthly)
      setMinTopupTomans(settings.min_topup_tomans)
      setTomanToUsdRate(settings.toman_to_usd_rate)
      setTomanPerUsdRate(settings.toman_per_usd_rate || '')
      setMinTopupUsd(settings.min_topup_usd || '')
      setCryptoTopupAddress(settings.crypto_topup_address || '')
      setCryptoTopupNetwork(settings.crypto_topup_network || '')
      setCryptoTopupMemo(settings.crypto_topup_memo || '')
      setCloudflareApiToken(settings.cloudflare_api_token || '')
      setArvanApiKey(settings.arvan_api_key || '')
    }
  }, [settings])

  // Update settings mutation
  const updateSettingsMutation = useMutation({
    mutationFn: () =>
      api.superAdmin.updateSettings({
        price_per_gb: pricePerGb || null,
        price_per_region_monthly: pricePerRegionMonthly || null,
        min_topup_tomans: minTopupTomans || null,
        toman_to_usd_rate: tomanToUsdRate || null,
        toman_per_usd_rate: tomanPerUsdRate || null,
        min_topup_usd: minTopupUsd || null,
        crypto_topup_address: cryptoTopupAddress || null,
        crypto_topup_network: cryptoTopupNetwork || null,
        crypto_topup_memo: cryptoTopupMemo || null,
        cloudflare_api_token: cloudflareApiToken || null,
        arvan_api_key: arvanApiKey || null,
      }),
    onSuccess: () => {
      toast.success('Platform settings updated successfully')
      queryClient.invalidateQueries({ queryKey: ['super', 'settings'] })
    },
    onError: () => {
      toast.error('Failed to update settings')
    },
  })

  // Change password mutation
  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      if (newPassword !== confirmPassword) {
        throw new Error('Passwords do not match')
      }
      if (newPassword.length < 8) {
        throw new Error('Password must be at least 8 characters')
      }
      // Use the auth API to change password (call the auth change-password endpoint)
      const { apiClient } = await import('@/lib/api/client')
      const response = await apiClient.put('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || error.message || 'Failed to change password'
      toast.error(msg)
    },
  })

  const handleSaveSettings = () => {
    updateSettingsMutation.mutate()
  }

  const handleChangePassword = () => {
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    changePasswordMutation.mutate()
  }

  // Check if any settings have changed
  const hasSettingsChanged =
    settings &&
    (pricePerGb !== settings.price_per_gb ||
      pricePerRegionMonthly !== settings.price_per_region_monthly ||
      minTopupTomans !== settings.min_topup_tomans ||
      tomanToUsdRate !== settings.toman_to_usd_rate ||
      tomanPerUsdRate !== (settings.toman_per_usd_rate || '') ||
      minTopupUsd !== (settings.min_topup_usd || '') ||
      cryptoTopupAddress !== (settings.crypto_topup_address || '') ||
      cryptoTopupNetwork !== (settings.crypto_topup_network || '') ||
      cryptoTopupMemo !== (settings.crypto_topup_memo || ''))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
        <p className="text-muted-foreground">Platform configuration and settings</p>
      </div>

      {/* Platform Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings className="h-4 w-4" />
            Platform Settings
          </CardTitle>
          <CardDescription>
            Configure pricing, limits, and exchange rates for the platform
          </CardDescription>
        </CardHeader>
        <CardContent>
          {settingsLoading ? (
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="flex items-center justify-between">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-10 w-48" />
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="price-per-gb">Price per GB (USD)</Label>
                  <Input
                    id="price-per-gb"
                    type="number"
                    step="0.001"
                    min="0"
                    placeholder="0.00"
                    value={pricePerGb}
                    onChange={(e) => setPricePerGb(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Cost per GB of traffic
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="price-per-region">
                    Price per Region Monthly (USD)
                  </Label>
                  <Input
                    id="price-per-region"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={pricePerRegionMonthly}
                    onChange={(e) => setPricePerRegionMonthly(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Monthly cost per VPN region
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="min-topup">Minimum Top-up (Tomans)</Label>
                  <Input
                    id="min-topup"
                    type="number"
                    step="1000"
                    min="0"
                    placeholder="0"
                    value={minTopupTomans}
                    onChange={(e) => setMinTopupTomans(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Minimum wire transfer amount
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="exchange-rate">Toman to USD Rate</Label>
                  <Input
                    id="exchange-rate"
                    type="number"
                    step="1000"
                    min="0"
                    placeholder="e.g. 600000"
                    value={tomanToUsdRate}
                    onChange={(e) => setTomanToUsdRate(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Current Tomans per 1 USD
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="toman-per-usd">Crypto Rate (Toman per USD)</Label>
                  <Input
                    id="toman-per-usd"
                    type="number"
                    step="1000"
                    min="0"
                    placeholder="e.g. 600000"
                    value={tomanPerUsdRate}
                    onChange={(e) => setTomanPerUsdRate(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Toman conversion rate used for crypto top-ups
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="min-topup-usd">Min Crypto Top-up (USD)</Label>
                  <Input
                    id="min-topup-usd"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="10"
                    value={minTopupUsd}
                    onChange={(e) => setMinTopupUsd(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Minimum crypto top-up amount in USD
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="crypto-address">Crypto Top-up Address</Label>
                  <Input
                    id="crypto-address"
                    value={cryptoTopupAddress}
                    onChange={(e) => setCryptoTopupAddress(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Wallet address shown to users for crypto top-ups
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="crypto-network">Crypto Network</Label>
                  <Input
                    id="crypto-network"
                    placeholder="USDT (TRC20)"
                    value={cryptoTopupNetwork}
                    onChange={(e) => setCryptoTopupNetwork(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Network label shown alongside the address
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="crypto-memo">Crypto Memo (optional)</Label>
                  <Input
                    id="crypto-memo"
                    value={cryptoTopupMemo}
                    onChange={(e) => setCryptoTopupMemo(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Optional memo/tag required by some networks
                  </p>
                </div>
              </div>

              <Separator />

              <div className="flex justify-end">
                <Button
                  onClick={handleSaveSettings}
                  disabled={!hasSettingsChanged || updateSettingsMutation.isPending}
                >
                  {updateSettingsMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  Save Settings
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Change Password */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" />
            Change Password
          </CardTitle>
          <CardDescription>Update your super admin account password</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => { e.preventDefault(); handleChangePassword() }}
            className="space-y-4 max-w-md"
          >
            <div className="space-y-2">
              <Label htmlFor="current-password">Current Password</Label>
              <Input
                id="current-password"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="Enter current password"
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password (min 8 characters)"
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm New Password</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
                autoComplete="new-password"
              />
            </div>
            <Button
              type="submit"
              disabled={
                !currentPassword ||
                !newPassword ||
                !confirmPassword ||
                changePasswordMutation.isPending
              }
            >
              {changePasswordMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <KeyRound className="mr-2 h-4 w-4" />
              )}
              Change Password
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* DNS API Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" />
            DNS Provider API Keys
          </CardTitle>
          <CardDescription>
            API keys for Cloudflare and ArvanCloud DNS management. Used by the TLD activation pipelines.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="cf-api-token">Cloudflare API Token</Label>
              <Input
                id="cf-api-token"
                type="password"
                value={cloudflareApiToken}
                onChange={(e) => setCloudflareApiToken(e.target.value)}
                placeholder="Cloudflare API token with DNS edit permissions"
              />
              <p className="text-xs text-muted-foreground">
                {cloudflareApiToken ? `${cloudflareApiToken.slice(0, 8)}${'*'.repeat(20)}${cloudflareApiToken.slice(-4)}` : 'Not configured'}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="arvan-api-key">ArvanCloud API Key</Label>
              <Input
                id="arvan-api-key"
                type="password"
                value={arvanApiKey}
                onChange={(e) => setArvanApiKey(e.target.value)}
                placeholder="ArvanCloud Machine User API key"
              />
              <p className="text-xs text-muted-foreground">
                {arvanApiKey ? `${arvanApiKey.slice(0, 8)}${'*'.repeat(20)}${arvanApiKey.slice(-4)}` : 'Not configured'}
              </p>
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => updateSettingsMutation.mutate()}
                disabled={updateSettingsMutation.isPending}
              >
                {updateSettingsMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save API Keys
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
