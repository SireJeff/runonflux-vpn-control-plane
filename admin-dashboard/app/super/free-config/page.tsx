'use client'

import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { FreeConfigGlobal } from '@/lib/api'
import { Gift, Loader2, KeyRound, Save } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ChannelEditor } from '@/components/free-config/ChannelEditor'
import toast from 'react-hot-toast'

interface GlobalFormData {
  is_enabled: boolean
  default_daily_limit_mb: string
  default_max_free_users: string
}

const emptyForm: GlobalFormData = {
  is_enabled: false,
  default_daily_limit_mb: '',
  default_max_free_users: '',
}

function toForm(config: FreeConfigGlobal): GlobalFormData {
  return {
    is_enabled: config.is_enabled,
    default_daily_limit_mb:
      config.default_daily_limit_mb != null ? String(config.default_daily_limit_mb) : '',
    default_max_free_users:
      config.default_max_free_users != null ? String(config.default_max_free_users) : '',
  }
}

export default function GlobalFreeConfigPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<GlobalFormData>(emptyForm)
  // Write-only token field — never bound from server data.
  const [token, setToken] = useState('')

  const { data: config, isLoading } = useQuery({
    queryKey: ['free-config-global'],
    queryFn: () => api.freeConfigGlobal.get(),
  })

  const { data: channels } = useQuery({
    queryKey: ['free-config-global', 'channels'],
    queryFn: () => api.freeConfigGlobal.listChannels(),
  })

  useEffect(() => {
    if (config) {
      setForm(toForm(config))
    }
  }, [config])

  const hasToken = config?.has_token ?? false
  const botUsername = config?.verification_bot_username ?? null

  const saveMutation = useMutation({
    mutationFn: () =>
      api.freeConfigGlobal.update({
        is_enabled: form.is_enabled,
        default_daily_limit_mb: form.default_daily_limit_mb.trim()
          ? Number(form.default_daily_limit_mb)
          : null,
        default_max_free_users: form.default_max_free_users.trim()
          ? Number(form.default_max_free_users)
          : null,
      }),
    onSuccess: () => {
      toast.success('Global free config saved')
      queryClient.invalidateQueries({ queryKey: ['free-config-global'] })
    },
    onError: () => {
      toast.error('Failed to save global free config')
    },
  })

  const setTokenMutation = useMutation({
    mutationFn: () => api.freeConfigGlobal.setToken(token.trim()),
    onSuccess: () => {
      toast.success('Verification bot token saved')
      setToken('')
      queryClient.invalidateQueries({ queryKey: ['free-config-global'] })
    },
    onError: () => {
      toast.error('Failed to save token')
    },
  })

  const addChannelMutation = useMutation({
    mutationFn: ({ identifier, inviteUrl }: { identifier: string; inviteUrl?: string }) =>
      api.freeConfigGlobal.addChannel(identifier, inviteUrl),
    onSuccess: () => {
      toast.success('Channel added')
      queryClient.invalidateQueries({ queryKey: ['free-config-global', 'channels'] })
    },
    onError: () => {
      toast.error('Failed to add channel')
    },
  })

  const deleteChannelMutation = useMutation({
    mutationFn: (id: number) => api.freeConfigGlobal.deleteChannel(id),
    onSuccess: () => {
      toast.success('Channel removed')
      queryClient.invalidateQueries({ queryKey: ['free-config-global', 'channels'] })
    },
    onError: () => {
      toast.error('Failed to remove channel')
    },
  })

  const handleSaveToken = () => {
    if (!token.trim()) return
    setTokenMutation.mutate()
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Free Config (Global)</h2>
        <p className="text-muted-foreground">
          Platform-wide free-config policy applied across all resellers
        </p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Gift className="h-4 w-4" />
            Global Free Config
          </CardTitle>
          <CardDescription>
            Enable the free config platform-wide and set the ceiling and cap that
            resellers cannot exceed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <Label htmlFor="fcg-enabled">Enabled</Label>
                  <p className="text-xs text-muted-foreground">
                    Toggle the free config on or off across the platform.
                  </p>
                </div>
                <Switch
                  id="fcg-enabled"
                  checked={form.is_enabled}
                  onCheckedChange={(checked) => setForm({ ...form, is_enabled: checked })}
                />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fcg-ceiling">Ceiling (MB)</Label>
                  <Input
                    id="fcg-ceiling"
                    type="number"
                    min={0}
                    placeholder="e.g. 500"
                    value={form.default_daily_limit_mb}
                    onChange={(e) =>
                      setForm({ ...form, default_daily_limit_mb: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Maximum daily limit resellers may set.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fcg-max-users">Max free users</Label>
                  <Input
                    id="fcg-max-users"
                    type="number"
                    min={0}
                    placeholder="e.g. 1000"
                    value={form.default_max_free_users}
                    onChange={(e) =>
                      setForm({ ...form, default_max_free_users: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Global cap on concurrent free users.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-2">
                <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  Save
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verification Bot Token (write-only) */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" />
            Verification Bot Token
          </CardTitle>
          <CardDescription>
            Bot token used to verify channel membership. Write-only: the value is
            never displayed after saving.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Status:</span>
              {hasToken ? (
                <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">
                  Configured: @{botUsername ?? 'unknown'}
                </Badge>
              ) : (
                <Badge className="bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300">
                  Not configured
                </Badge>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="fcg-token">Bot token</Label>
              <Input
                id="fcg-token"
                type="password"
                autoComplete="off"
                placeholder="123456:ABC-DEF..."
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Paste a new token to replace the existing one.
              </p>
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleSaveToken}
                disabled={!token.trim() || setTokenMutation.isPending}
              >
                {setTokenMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save token
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Global required channels */}
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Required global channels</CardTitle>
          <CardDescription>
            Channels every free user must join, enforced across all resellers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChannelEditor
            channels={channels ?? []}
            onAdd={(identifier, inviteUrl) =>
              addChannelMutation.mutate({ identifier, inviteUrl })
            }
            onDelete={(id) => deleteChannelMutation.mutate(id)}
          />
        </CardContent>
      </Card>
    </div>
  )
}
