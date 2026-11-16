'use client'

import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RoutingRules } from '@/lib/api'
import { PRESET_KEYS, type PresetKey } from '@/lib/api/endpoints/routingRules'
import { formatErrorDetail } from '@/lib/api/client'
import { Loader2, Plus, X } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import toast from 'react-hot-toast'
import axios from 'axios'

const PRESET_LABELS: Record<PresetKey, string> = {
  block_ads: 'Block ads',
  block_porn: 'Block adult content',
  iran_direct: 'Iran domains direct',
}

interface RoutingRulesFormData {
  is_enabled: boolean
  ban_domains: string[]
  allow_domains: string[]
  presets: Partial<Record<PresetKey, boolean>>
}

const emptyForm: RoutingRulesFormData = {
  is_enabled: false,
  ban_domains: [],
  allow_domains: [],
  presets: {},
}

function toForm(rules: RoutingRules): RoutingRulesFormData {
  return {
    is_enabled: rules.is_enabled,
    ban_domains: rules.ban_domains ?? [],
    allow_domains: rules.allow_domains ?? [],
    presets: rules.presets ?? {},
  }
}

export default function RoutingRulesPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<RoutingRulesFormData>(emptyForm)
  const [banInput, setBanInput] = useState('')
  const [allowInput, setAllowInput] = useState('')

  const { data: rules, isLoading } = useQuery({
    queryKey: ['routing-rules'],
    queryFn: () => api.routingRules.get(),
  })

  useEffect(() => {
    if (rules) {
      setForm(toForm(rules))
    }
  }, [rules])

  const saveMutation = useMutation({
    mutationFn: () =>
      api.routingRules.update({
        is_enabled: form.is_enabled,
        ban_domains: form.ban_domains,
        allow_domains: form.allow_domains,
        presets: form.presets,
      }),
    onSuccess: () => {
      toast.success('Routing rules saved')
      queryClient.invalidateQueries({ queryKey: ['routing-rules'] })
    },
    onError: (error: unknown) => {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data as { detail?: unknown } | undefined)?.detail
        : undefined
      toast.error(formatErrorDetail(detail, 'Failed to save routing rules'))
    },
  })

  const addDomain = (list: 'ban_domains' | 'allow_domains', value: string) => {
    const domain = value.trim().toLowerCase()
    if (!domain) return
    setForm((prev) =>
      prev[list].includes(domain)
        ? prev
        : { ...prev, [list]: [...prev[list], domain] }
    )
  }

  const removeDomain = (list: 'ban_domains' | 'allow_domains', domain: string) => {
    setForm((prev) => ({ ...prev, [list]: prev[list].filter((d) => d !== domain) }))
  }

  const togglePreset = (key: PresetKey, checked: boolean) => {
    setForm((prev) => ({ ...prev, presets: { ...prev.presets, [key]: checked } }))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Routing Rules</h2>
          <p className="text-muted-foreground">
            Control how your users&apos; traffic is routed (sing-box clients)
          </p>
        </div>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Traffic Routing</CardTitle>
          <CardDescription>
            When enabled, banned domains are blocked and allowed domains bypass the proxy.
            These rules apply to sing-box configs generated for your users.
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
                  <Label htmlFor="rr-enabled">Enabled</Label>
                  <p className="text-xs text-muted-foreground">
                    Toggle routing rules on or off for all your users.
                  </p>
                </div>
                <Switch
                  id="rr-enabled"
                  checked={form.is_enabled}
                  onCheckedChange={(checked) => setForm({ ...form, is_enabled: checked })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="rr-ban">Ban domains (blocked)</Label>
                <div className="flex gap-2">
                  <Input
                    id="rr-ban"
                    placeholder="e.g. example.com"
                    value={banInput}
                    onChange={(e) => setBanInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addDomain('ban_domains', banInput)
                        setBanInput('')
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      addDomain('ban_domains', banInput)
                      setBanInput('')
                    }}
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {form.ban_domains.length === 0 ? (
                    <span className="text-xs text-muted-foreground">No banned domains.</span>
                  ) : (
                    form.ban_domains.map((domain) => (
                      <span
                        key={domain}
                        className="inline-flex items-center gap-1 rounded-full bg-red-100 px-3 py-1 text-xs text-red-800 dark:bg-red-900 dark:text-red-300"
                      >
                        {domain}
                        <button
                          type="button"
                          aria-label={`Remove ${domain}`}
                          onClick={() => removeDomain('ban_domains', domain)}
                          className="rounded-full hover:bg-red-200 dark:hover:bg-red-800"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="rr-allow">Allow domains (direct)</Label>
                <div className="flex gap-2">
                  <Input
                    id="rr-allow"
                    placeholder="e.g. bank.ir"
                    value={allowInput}
                    onChange={(e) => setAllowInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addDomain('allow_domains', allowInput)
                        setAllowInput('')
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      addDomain('allow_domains', allowInput)
                      setAllowInput('')
                    }}
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {form.allow_domains.length === 0 ? (
                    <span className="text-xs text-muted-foreground">No allowed domains.</span>
                  ) : (
                    form.allow_domains.map((domain) => (
                      <span
                        key={domain}
                        className="inline-flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-xs text-green-800 dark:bg-green-900 dark:text-green-300"
                      >
                        {domain}
                        <button
                          type="button"
                          aria-label={`Remove ${domain}`}
                          onClick={() => removeDomain('allow_domains', domain)}
                          className="rounded-full hover:bg-green-200 dark:hover:bg-green-800"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))
                  )}
                </div>
              </div>

              <div className="space-y-3">
                <Label>Presets</Label>
                <div className="space-y-3">
                  {PRESET_KEYS.map((key) => (
                    <div key={key} className="flex items-center gap-3">
                      <Checkbox
                        id={`rr-preset-${key}`}
                        checked={form.presets[key] ?? false}
                        onCheckedChange={(checked) => togglePreset(key, checked === true)}
                      />
                      <Label htmlFor={`rr-preset-${key}`} className="font-normal">
                        {PRESET_LABELS[key]}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-2">
                <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
