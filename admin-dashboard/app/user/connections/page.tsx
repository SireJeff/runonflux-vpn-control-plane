'use client'

/**
 * End-user connections page (T15 redesign).
 *
 * Layout: hero (sub link + dashboard login + reset) → toolbar (refresh,
 * copy-all, language toggle) → country grid → guide link.
 *
 * Replaces the URI-dump + tab layout from the prior version. Country grid
 * uses expand-on-click cards so all countries are visible at once; the old
 * tab UI hid non-default countries behind a click.
 */

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Wifi, BookOpen, ClipboardList, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useI18n } from '@/lib/i18n/user-portal'
import { SubscriptionHero } from '@/components/user/SubscriptionHero'
import { CountryCard } from '@/components/user/CountryCard'
import { LangToggle } from '@/components/user/LangToggle'

function RefreshButton({
  canRefresh,
  refreshAvailableAt,
  onRefresh,
  refreshing,
  labels,
}: {
  canRefresh: boolean
  refreshAvailableAt: string | null
  onRefresh: () => void
  refreshing: boolean
  labels: { refresh: string; refreshing: string; next_refresh_in: string }
}) {
  const [remaining, setRemaining] = useState('')

  useEffect(() => {
    if (canRefresh || !refreshAvailableAt) return
    const update = () => {
      const diff = new Date(refreshAvailableAt).getTime() - Date.now()
      if (diff <= 0) {
        setRemaining('')
        return
      }
      const h = Math.floor(diff / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      setRemaining(`${h}h ${m}m`)
    }
    update()
    const interval = setInterval(update, 60000)
    return () => clearInterval(interval)
  }, [canRefresh, refreshAvailableAt])

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={onRefresh}
        disabled={!canRefresh || refreshing}
      >
        <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        {refreshing ? labels.refreshing : labels.refresh}
      </Button>
      {!canRefresh && remaining && (
        <span className="text-xs text-muted-foreground">
          {labels.next_refresh_in} {remaining}
        </span>
      )}
    </div>
  )
}

export default function EndUserConnectionsPage() {
  const queryClient = useQueryClient()
  const { t, lang } = useI18n()

  const { data: connectionsData, isLoading } = useQuery({
    queryKey: ['endUser', 'connections'],
    queryFn: () => api.endUser.getConnections(),
    refetchInterval: 30000,
  })
  const [refreshing, setRefreshing] = useState(false)
  const [resetting, setResetting] = useState(false)

  const countries = connectionsData?.countries || []
  const canRefresh = connectionsData?.can_refresh ?? false
  const refreshAvailableAt = connectionsData?.refresh_available_at ?? null

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const result = await api.endUser.refreshConnections()
      queryClient.setQueryData(['endUser', 'connections'], result)
      toast.success(t('copied'))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const handleReset = async () => {
    setResetting(true)
    try {
      await api.endUser.resetCredentials()
      // Refetch connections to pick up new password + sub URL
      await queryClient.invalidateQueries({ queryKey: ['endUser', 'connections'] })
      toast.success(lang === 'fa' ? 'رمز و لینک بازنشانی شد' : 'Password and link reset')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || t('reset_password_failed'))
    } finally {
      setResetting(false)
    }
  }

  const handleCopyAll = async () => {
    if (!countries.length) return
    const lines: string[] = []
    countries.forEach((country) => {
      const protocols = Object.entries(country.connections).sort(([a], [b]) =>
        a.localeCompare(b)
      )
      protocols.forEach(([protocol, conn]) => {
        lines.push(`${protocol.toUpperCase()}:`)
        lines.push(conn.primary)
        lines.push('')
      })
    })
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      toast.success(lang === 'fa' ? 'همه اتصالات کپی شد' : 'All connections copied')
    } catch {
      toast.error(t('failed_to_copy'))
    }
  }

  const heroLabels = {
    subscription_link: t('subscription_link'),
    subscription_link_help: t('subscription_link_help'),
    singbox_link: t('singbox_link'),
    singbox_link_help: t('singbox_link_help'),
    user_portal: t('user_portal'),
    portal_address: t('portal_address'),
    username: t('username'),
    password: t('password'),
    reset_password: t('reset_password'),
    reset_password_confirm: t('reset_password_confirm'),
    expires_on: t('expires_on'),
    days_left: t('days_left'),
    copied: t('copied'),
  }

  const protocolLabels = {
    primary: t('primary'),
    fallbacks: t('fallbacks'),
    fallback: t('fallback'),
    sshFieldsTitle: t('ssh_fields_for_putty'),
    host: t('host'),
    port: t('port'),
    username: t('username'),
    password: t('password'),
    copied: t('copied'),
  }

  return (
    <div className="space-y-6" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t('your_connections')}</h2>
          <p className="text-muted-foreground text-sm">{t('copy_to_client')}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <LangToggle />
          {!isLoading && countries.length > 0 && (
            <RefreshButton
              canRefresh={canRefresh}
              refreshAvailableAt={refreshAvailableAt}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              labels={{
                refresh: t('refresh'),
                refreshing: t('refreshing'),
                next_refresh_in: t('next_refresh_in'),
              }}
            />
          )}
          {!isLoading && countries.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={handleCopyAll}
            >
              <ClipboardList className="h-3.5 w-3.5" />
              {t('copy_all')}
            </Button>
          )}
          <Link href="/user/guide">
            <Button variant="outline" size="sm" className="gap-1.5">
              <BookOpen className="h-3.5 w-3.5" />
              {t('setup_guides')}
            </Button>
          </Link>
        </div>
      </div>

      {/* Hero */}
      {!isLoading && (
        <SubscriptionHero
          subUrl={connectionsData?.subscription_url}
          username={connectionsData?.username}
          password={connectionsData?.password}
          dashboardUrl={connectionsData?.dashboard_url}
          expiresAt={connectionsData?.expires_at}
          onReset={handleReset}
          resetting={resetting}
          labels={heroLabels}
        />
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full rounded-lg" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && countries.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Wifi className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-medium">{t('no_connections')}</h3>
            <p className="mt-1 text-sm text-muted-foreground text-center max-w-sm">
              {t('no_connections_help')}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Country grid */}
      {!isLoading && countries.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            {t('available_countries')} ({countries.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {countries.map((country) => (
              <CountryCard
                key={country.country_code}
                country={country}
                labels={protocolLabels}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
