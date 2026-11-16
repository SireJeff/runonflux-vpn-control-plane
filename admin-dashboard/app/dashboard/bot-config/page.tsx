'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { BotConfig } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import {
  Bot,
  Loader2,
  Save,
  Send,
  PowerOff,
  Power,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import toast from 'react-hot-toast'
import { isAxiosError } from 'axios'

const MACRO_REGIONS = [
  { value: 'eu', label: 'Europe (EU)' },
  { value: 'as', label: 'Asia (AS)' },
  { value: 'na', label: 'North America (NA)' },
  { value: 'row', label: 'Rest of World (ROW)' },
]

export default function BotConfigPage() {
  const queryClient = useQueryClient()

  // Fetch bot config — 404 means not yet configured
  const { data: config, isLoading, error } = useQuery({
    queryKey: ['bot-config'],
    queryFn: () => api.botConfig.get(),
    retry: false,
  })

  const isConfigured = !!config && !isNotFoundError(error)

  // Form state
  const [botToken, setBotToken] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [welcomeFa, setWelcomeFa] = useState('')
  const [welcomeEn, setWelcomeEn] = useState('')
  const [cardNumber, setCardNumber] = useState('')
  const [cardHolderName, setCardHolderName] = useState('')
  const [cryptoAddress, setCryptoAddress] = useState('')
  const [cryptoNetwork, setCryptoNetwork] = useState('')
  const [cryptoMemo, setCryptoMemo] = useState('')
  const [supportPhone, setSupportPhone] = useState('')
  const [supportTelegram, setSupportTelegram] = useState('')
  const [macroRegion, setMacroRegion] = useState('eu')

  // Populate form when config loads
  useEffect(() => {
    if (config) {
      setDisplayName(config.bot_display_name || '')
      setWelcomeFa(config.welcome_message_fa || '')
      setWelcomeEn(config.welcome_message_en || '')
      setCardNumber(config.card_number || '')
      setCardHolderName(config.card_holder_name || '')
      setCryptoAddress(config.crypto_address || '')
      setCryptoNetwork(config.crypto_network || '')
      setCryptoMemo(config.crypto_memo || '')
      setSupportPhone(config.support_phone || '')
      setSupportTelegram(config.support_telegram || '')
      setMacroRegion(config.default_macro_region || 'eu')
    }
  }, [config])

  // Register mutation (POST — includes bot_token)
  const registerMutation = useMutation({
    mutationFn: () =>
      api.botConfig.create({
        bot_token: botToken,
        bot_display_name: displayName || undefined,
        welcome_message_fa: welcomeFa || undefined,
        welcome_message_en: welcomeEn || undefined,
        card_number: cardNumber || undefined,
        card_holder_name: cardHolderName || undefined,
        crypto_address: cryptoAddress || undefined,
        crypto_network: cryptoNetwork || undefined,
        crypto_memo: cryptoMemo || undefined,
        support_phone: supportPhone || undefined,
        support_telegram: supportTelegram || undefined,
        default_macro_region: macroRegion,
      }),
    onSuccess: () => {
      toast.success('Bot registered successfully')
      queryClient.invalidateQueries({ queryKey: ['bot-config'] })
    },
    onError: () => {
      toast.error('Failed to register bot')
    },
  })

  // Update mutation (PUT — no bot_token)
  const updateMutation = useMutation({
    mutationFn: () =>
      api.botConfig.update({
        bot_display_name: displayName || undefined,
        welcome_message_fa: welcomeFa || undefined,
        welcome_message_en: welcomeEn || undefined,
        card_number: cardNumber || undefined,
        card_holder_name: cardHolderName || undefined,
        crypto_address: cryptoAddress || undefined,
        crypto_network: cryptoNetwork || undefined,
        crypto_memo: cryptoMemo || undefined,
        support_phone: supportPhone || undefined,
        support_telegram: supportTelegram || undefined,
        default_macro_region: macroRegion,
      }),
    onSuccess: () => {
      toast.success('Bot config updated')
      queryClient.invalidateQueries({ queryKey: ['bot-config'] })
    },
    onError: () => {
      toast.error('Failed to update bot config')
    },
  })

  // Deactivate mutation
  const deactivateMutation = useMutation({
    mutationFn: () => api.botConfig.deactivate(),
    onSuccess: () => {
      toast.success('Bot deactivated')
      queryClient.invalidateQueries({ queryKey: ['bot-config'] })
    },
    onError: () => {
      toast.error('Failed to deactivate bot')
    },
  })

  // Reactivate mutation
  const reactivateMutation = useMutation({
    mutationFn: () => api.botConfig.reactivate(),
    onSuccess: () => {
      toast.success('Bot reactivated')
      queryClient.invalidateQueries({ queryKey: ['bot-config'] })
    },
    onError: (err) => {
      if (isAxiosError(err) && err.response?.status === 409) {
        toast.success('Bot was already active — refreshed config')
        queryClient.invalidateQueries({ queryKey: ['bot-config'] })
      } else {
        toast.error('Failed to reactivate bot')
      }
    },
  })

  // Test ping mutation — diagnoses the reseller's OWN bot and surfaces the
  // actionable detail (token / webhook health / live DM), so a broken bot is
  // reported instead of a misleading success.
  const testPingMutation = useMutation({
    mutationFn: () => api.botConfig.testPing(),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success(result.detail || 'Your bot is working', { duration: 6000 })
      } else {
        toast.error(result.detail || 'Your bot is not working', { duration: 8000 })
      }
    },
    onError: () => {
      toast.error('Failed to run the bot test')
    },
  })

  const handleRegister = () => {
    if (!botToken.trim()) {
      toast.error('Bot token is required')
      return
    }
    registerMutation.mutate()
  }

  const handleUpdate = () => {
    updateMutation.mutate()
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Bot Configuration</h2>
          <p className="text-muted-foreground">Manage your Telegram bot settings</p>
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  // Not configured — show registration form
  if (!isConfigured) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Bot Configuration</h2>
          <p className="text-muted-foreground">Register your Telegram bot for end-user access</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              Register New Bot
            </CardTitle>
            <CardDescription>
              Enter your Telegram bot token from @BotFather to get started
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="bot-token">Bot Token *</Label>
              <Input
                id="bot-token"
                type="password"
                placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="display-name">Bot Display Name</Label>
              <Input
                id="display-name"
                placeholder="My VPN Bot"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="welcome-fa">Welcome Message (Farsi)</Label>
                <Textarea
                  id="welcome-fa"
                  placeholder="...به ربات خوش آمدید"
                  value={welcomeFa}
                  onChange={(e) => setWelcomeFa(e.target.value)}
                  rows={3}
                  dir="rtl"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="welcome-en">Welcome Message (English)</Label>
                <Textarea
                  id="welcome-en"
                  placeholder="Welcome to the VPN bot..."
                  value={welcomeEn}
                  onChange={(e) => setWelcomeEn(e.target.value)}
                  rows={3}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="card-number">Card Number</Label>
                <Input
                  id="card-number"
                  placeholder="6037-XXXX-XXXX-XXXX"
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="card-holder">Card Holder Name</Label>
                <Input
                  id="card-holder"
                  placeholder="Card holder name"
                  value={cardHolderName}
                  onChange={(e) => setCardHolderName(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="crypto-address">Crypto Address (for end-user plan payments)</Label>
                <Input
                  id="crypto-address"
                  value={cryptoAddress}
                  onChange={(e) => setCryptoAddress(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="crypto-network">Crypto Network</Label>
                <Input
                  id="crypto-network"
                  placeholder="USDT (TRC20)"
                  value={cryptoNetwork}
                  onChange={(e) => setCryptoNetwork(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="crypto-memo">Crypto Memo (optional)</Label>
                <Input
                  id="crypto-memo"
                  value={cryptoMemo}
                  onChange={(e) => setCryptoMemo(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="support-phone">Support Phone</Label>
                <Input
                  id="support-phone"
                  placeholder="+12025550123"
                  value={supportPhone}
                  onChange={(e) => setSupportPhone(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="support-telegram">Support Telegram</Label>
                <Input
                  id="support-telegram"
                  placeholder="@support_username"
                  value={supportTelegram}
                  onChange={(e) => setSupportTelegram(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="macro-region">Default Region</Label>
                <Select value={macroRegion} onValueChange={setMacroRegion}>
                  <SelectTrigger id="macro-region">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MACRO_REGIONS.map((r) => (
                      <SelectItem key={r.value} value={r.value}>
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button
              onClick={handleRegister}
              disabled={!botToken.trim() || registerMutation.isPending}
              className="w-full md:w-auto"
            >
              {registerMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Bot className="mr-2 h-4 w-4" />
              )}
              Register Bot
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Configured — show summary + edit form + actions
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Bot Configuration</h2>
          <p className="text-muted-foreground">Manage your Telegram bot settings</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={config?.is_active ? 'default' : 'secondary'}>
            {config?.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>
      </div>

      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            @{config?.bot_username}
          </CardTitle>
          <CardDescription>
            Bot ID: {config?.bot_user_id} | Registered: {config?.created_at ? formatDate(config.created_at) : 'N/A'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Display Name</p>
              <p className="font-medium">{config?.bot_display_name || '-'}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Default Region</p>
              <p className="font-medium uppercase">{config?.default_macro_region}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Webhook Set</p>
              <p className="font-medium">
                {config?.webhook_registered_at ? formatDate(config.webhook_registered_at, true) : 'No'}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Support</p>
              <p className="font-medium">
                {config?.support_telegram || config?.support_phone || '-'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Edit Form */}
      <Card>
        <CardHeader>
          <CardTitle>Edit Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-display-name">Bot Display Name</Label>
            <Input
              id="edit-display-name"
              placeholder="My VPN Bot"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-welcome-fa">Welcome Message (Farsi)</Label>
              <Textarea
                id="edit-welcome-fa"
                value={welcomeFa}
                onChange={(e) => setWelcomeFa(e.target.value)}
                rows={3}
                dir="rtl"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-welcome-en">Welcome Message (English)</Label>
              <Textarea
                id="edit-welcome-en"
                value={welcomeEn}
                onChange={(e) => setWelcomeEn(e.target.value)}
                rows={3}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-card-number">Card Number</Label>
              <Input
                id="edit-card-number"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-card-holder">Card Holder Name</Label>
              <Input
                id="edit-card-holder"
                value={cardHolderName}
                onChange={(e) => setCardHolderName(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-crypto-address">Crypto Address (for end-user plan payments)</Label>
              <Input
                id="edit-crypto-address"
                value={cryptoAddress}
                onChange={(e) => setCryptoAddress(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-crypto-network">Crypto Network</Label>
              <Input
                id="edit-crypto-network"
                placeholder="USDT (TRC20)"
                value={cryptoNetwork}
                onChange={(e) => setCryptoNetwork(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-crypto-memo">Crypto Memo (optional)</Label>
              <Input
                id="edit-crypto-memo"
                value={cryptoMemo}
                onChange={(e) => setCryptoMemo(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-support-phone">Support Phone</Label>
              <Input
                id="edit-support-phone"
                value={supportPhone}
                onChange={(e) => setSupportPhone(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-support-telegram">Support Telegram</Label>
              <Input
                id="edit-support-telegram"
                value={supportTelegram}
                onChange={(e) => setSupportTelegram(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-macro-region">Default Region</Label>
              <Select value={macroRegion} onValueChange={setMacroRegion}>
                <SelectTrigger id="edit-macro-region">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MACRO_REGIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <Button
              onClick={handleUpdate}
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save Changes
            </Button>

            <Button
              variant="outline"
              onClick={() => testPingMutation.mutate()}
              disabled={testPingMutation.isPending}
            >
              {testPingMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Send className="mr-2 h-4 w-4" />
              )}
              Send Test Ping
            </Button>

            {config?.is_active ? (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive">
                    <PowerOff className="mr-2 h-4 w-4" />
                    Deactivate
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Deactivate Bot?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will disable the bot for all end-users. The Telegram webhook
                      is removed and the bot stops responding. To bring it back online,
                      contact your platform admin to re-register the bot.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deactivateMutation.mutate()}
                      disabled={deactivateMutation.isPending}
                    >
                      {deactivateMutation.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Deactivate
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            ) : (
              <Button
                variant="outline"
                onClick={() => reactivateMutation.mutate()}
                disabled={reactivateMutation.isPending}
              >
                {reactivateMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Power className="mr-2 h-4 w-4" />
                )}
                Reactivate
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/** Check if an error is a 404 (bot not yet configured) */
function isNotFoundError(error: unknown): boolean {
  if (!error) return false
  return isAxiosError(error) && error.response?.status === 404
}
