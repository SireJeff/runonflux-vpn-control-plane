'use client'

import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { FreeConfig } from '@/lib/api'
import { Loader2, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ChannelEditor } from '@/components/free-config/ChannelEditor'
import toast from 'react-hot-toast'

const REGIONS = [
  { value: 'eu', label: 'Europe (eu)' },
  { value: 'as', label: 'Asia (as)' },
  { value: 'na', label: 'North America (na)' },
  { value: 'row', label: 'Rest of World (row)' },
]

const NONE = '__none__'

interface FreeConfigFormData {
  is_enabled: boolean
  kind: string
  label: string
  region: string
  traffic_limit_gb: string
  duration_days: string
  daily_limit_mb: string
  max_free_users: string
}

const emptyForm: FreeConfigFormData = {
  is_enabled: false,
  kind: 'shared',
  label: '',
  region: NONE,
  traffic_limit_gb: '',
  duration_days: '',
  daily_limit_mb: '',
  max_free_users: '',
}

function toForm(config: FreeConfig): FreeConfigFormData {
  return {
    is_enabled: config.is_enabled,
    kind: config.kind ?? 'shared',
    label: config.label ?? '',
    region: config.region ?? NONE,
    traffic_limit_gb: config.traffic_limit_gb ?? '',
    duration_days: config.duration_days != null ? String(config.duration_days) : '',
    daily_limit_mb: config.daily_limit_mb != null ? String(config.daily_limit_mb) : '',
    max_free_users: config.max_free_users != null ? String(config.max_free_users) : '',
  }
}

export default function FreeConfigPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FreeConfigFormData>(emptyForm)
  const [ceilingError, setCeilingError] = useState<string | null>(null)

  const { data: config, isLoading } = useQuery({
    queryKey: ['free-config'],
    queryFn: () => api.freeConfig.get(),
  })

  const { data: channels } = useQuery({
    queryKey: ['free-config', 'channels'],
    queryFn: () => api.freeConfig.listChannels(),
  })

  useEffect(() => {
    if (config) {
      setForm(toForm(config))
    }
  }, [config])

  const globalCeiling = config?.global_ceiling_mb ?? null
  const globalChannels = config?.global_channels ?? []

  const saveMutation = useMutation({
    mutationFn: () =>
      api.freeConfig.update({
        is_enabled: form.is_enabled,
        kind: form.kind,
        label: form.label.trim() || null,
        region: form.region === NONE ? null : form.region,
        traffic_limit_gb: form.traffic_limit_gb.trim() || null,
        duration_days: form.duration_days.trim() ? Number(form.duration_days) : null,
        daily_limit_mb: form.daily_limit_mb.trim() ? Number(form.daily_limit_mb) : null,
        max_free_users: form.max_free_users.trim() ? Number(form.max_free_users) : null,
      }),
    onSuccess: () => {
      toast.success('Free config saved')
      queryClient.invalidateQueries({ queryKey: ['free-config'] })
    },
    onError: () => {
      toast.error('Failed to save free config')
    },
  })

  const rotateMutation = useMutation({
    mutationFn: () => api.freeConfig.rotate(),
    onSuccess: () => {
      toast.success('Config rotated/provisioned')
      queryClient.invalidateQueries({ queryKey: ['free-config'] })
    },
    onError: () => {
      toast.error('Failed to rotate config')
    },
  })

  const addChannelMutation = useMutation({
    mutationFn: ({ identifier, inviteUrl }: { identifier: string; inviteUrl?: string }) =>
      api.freeConfig.addChannel(identifier, inviteUrl),
    onSuccess: () => {
      toast.success('Channel added')
      queryClient.invalidateQueries({ queryKey: ['free-config', 'channels'] })
    },
    onError: () => {
      toast.error('Failed to add channel')
    },
  })

  const deleteChannelMutation = useMutation({
    mutationFn: (id: number) => api.freeConfig.deleteChannel(id),
    onSuccess: () => {
      toast.success('Channel removed')
      queryClient.invalidateQueries({ queryKey: ['free-config', 'channels'] })
    },
    onError: () => {
      toast.error('Failed to remove channel')
    },
  })

  const handleSave = () => {
    setCeilingError(null)
    if (form.kind === 'per_user' && form.daily_limit_mb.trim() && globalCeiling != null) {
      const value = Number(form.daily_limit_mb)
      if (value > globalCeiling) {
        setCeilingError(`Daily limit cannot exceed the global ceiling of ${globalCeiling} MB`)
        return
      }
    }
    saveMutation.mutate()
  }

  const hasCredential = config?.has_credential ?? false

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Free Config</h2>
          <p className="text-muted-foreground">
            Manage free subscriptions offered to bot users
          </p>
        </div>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Free Public Config</CardTitle>
          <CardDescription>
            Per-user mode activates each customer with their own subscription and daily allowance.
            Shared mode gives everyone one account and one combined allowance.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <Label htmlFor="fc-enabled">Enabled</Label>
                  <p className="text-xs text-muted-foreground">
                    Toggle the free config on or off for users.
                  </p>
                </div>
                <Switch
                  id="fc-enabled"
                  checked={form.is_enabled}
                  onCheckedChange={(checked) => setForm({ ...form, is_enabled: checked })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="fc-kind">Mode</Label>
                <Select
                  value={form.kind}
                  onValueChange={(value) => setForm({ ...form, kind: value })}
                >
                  <SelectTrigger id="fc-kind">
                    <SelectValue placeholder="Select mode" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="shared">Shared</SelectItem>
                    <SelectItem value="per_user">Per-user daily quota</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="fc-label">Label</Label>
                <Input
                  id="fc-label"
                  placeholder="e.g. Free trial config"
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                      <Label htmlFor="fc-region">Region</Label>
                      <Select
                        value={form.region}
                        onValueChange={(value) => setForm({ ...form, region: value })}
                      >
                        <SelectTrigger id="fc-region">
                          <SelectValue placeholder="Select region" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE}>Use reseller default (per-user)</SelectItem>
                          {REGIONS.map((r) => (
                            <SelectItem key={r.value} value={r.value}>
                              {r.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
              </div>

              {form.kind === 'shared' ? (
                <>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="fc-traffic">Traffic limit (GB)</Label>
                      <Input
                        id="fc-traffic"
                        type="number"
                        min={0}
                        step={0.1}
                        placeholder="e.g. 5"
                        value={form.traffic_limit_gb}
                        onChange={(e) => setForm({ ...form, traffic_limit_gb: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="fc-duration">Duration (days)</Label>
                    <Input
                      id="fc-duration"
                      type="number"
                      min={1}
                      placeholder="e.g. 30"
                      value={form.duration_days}
                      onChange={(e) => setForm({ ...form, duration_days: e.target.value })}
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">Credential status:</span>
                    <Badge
                      className={
                        hasCredential
                          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300'
                          : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                      }
                    >
                      {hasCredential ? 'Provisioned' : 'Not provisioned yet'}
                    </Badge>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    Each customer gets a separate allowance, renewed at 00:00 UTC every day.
                    Use 1024 MB for 1 GB per day. Daily subscriptions have no one-day expiry.
                  </p>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="fc-daily-limit">Daily limit (MB)</Label>
                      <Input
                        id="fc-daily-limit"
                        type="number"
                        min={0}
                        placeholder="e.g. 200"
                        value={form.daily_limit_mb}
                        onChange={(e) => setForm({ ...form, daily_limit_mb: e.target.value })}
                      />
                      {ceilingError ? (
                        <p className="text-xs text-red-600 dark:text-red-400">{ceilingError}</p>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          {globalCeiling != null
                            ? `cannot exceed ${globalCeiling}`
                            : 'cannot exceed the global ceiling'}
                        </p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="fc-max-users">Max free users</Label>
                      <Input
                        id="fc-max-users"
                        type="number"
                        min={0}
                        placeholder="e.g. 1000"
                        value={form.max_free_users}
                        onChange={(e) => setForm({ ...form, max_free_users: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="space-y-3 rounded-md border p-4">
                    <h3 className="text-sm font-semibold">Required channels</h3>
                    <ChannelEditor
                      channels={channels ?? []}
                      onAdd={(identifier, inviteUrl) =>
                        addChannelMutation.mutate({ identifier, inviteUrl })
                      }
                      onDelete={(id) => deleteChannelMutation.mutate(id)}
                    />
                  </div>

                  <div className="space-y-2 rounded-md border bg-muted/30 p-4">
                    <h3 className="text-sm font-semibold">Global requirements</h3>
                    <p className="text-xs text-muted-foreground">
                      Read-only limits enforced by the platform operator.
                    </p>
                    <p className="text-sm">
                      Global ceiling:{' '}
                      <span className="font-medium">
                        {globalCeiling != null ? `${globalCeiling} MB` : 'not set'}
                      </span>
                    </p>
                    <div>
                      <p className="text-sm font-medium">Required global channels:</p>
                      {globalChannels.length === 0 ? (
                        <p className="text-xs text-muted-foreground">None</p>
                      ) : (
                        <ul className="mt-1 list-inside list-disc text-sm">
                          {globalChannels.map((ch) => (
                            <li key={ch.id}>
                              {ch.title}
                              {ch.username ? ` (${ch.username})` : ''}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                </>
              )}

              <div className="flex flex-wrap gap-3 pt-2">
                <Button onClick={handleSave} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
                {form.kind === 'shared' && <Button
                  variant="outline"
                  onClick={() => rotateMutation.mutate()}
                  disabled={rotateMutation.isPending}
                >
                  {rotateMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-2 h-4 w-4" />
                  )}
                  {hasCredential ? 'Rotate Config' : 'Generate Config'}
                </Button>}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
