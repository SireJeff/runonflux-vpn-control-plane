'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProtocolConnections } from '@/lib/api/endpoints/admin-api'
import {
  ArrowLeft,
  Copy,
  Check,
  Server,
  Send,
  Key,
  RefreshCw,
  MessageCircle,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import toast from 'react-hot-toast'

const COUNTRY_NAMES: Record<string, string> = {
  US: 'United States', CA: 'Canada', MX: 'Mexico',
  NL: 'Netherlands', CH: 'Switzerland', DE: 'Germany', FR: 'France',
  GB: 'United Kingdom', PL: 'Poland', SE: 'Sweden', FI: 'Finland',
  NO: 'Norway', DK: 'Denmark', IT: 'Italy', ES: 'Spain', PT: 'Portugal',
  IE: 'Ireland', AT: 'Austria', BE: 'Belgium', CZ: 'Czech Republic',
  RO: 'Romania', UA: 'Ukraine', JP: 'Japan', SG: 'Singapore',
  IN: 'India', KR: 'South Korea', AU: 'Australia', BR: 'Brazil',
}

function countryFlag(code: string): string {
  return String.fromCodePoint(
    ...[...code.toUpperCase()].map((c) => 0x1f1e5 + c.charCodeAt(0))
  )
}

function countryLabel(code: string): string {
  return `${countryFlag(code)} ${COUNTRY_NAMES[code] || code}`
}

const PROTOCOL_LABELS: Record<string, { label: string; color: string }> = {
  ssh: { label: 'SSH', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300' },
  shadowsocks: { label: 'Shadowsocks', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300' },
  vless: { label: 'VLESS', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300' },
  trojan: { label: 'Trojan', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300' },
  outline: { label: 'Outline', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300' },
  http_proxy: { label: 'HTTP Proxy', color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300' },
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Copied to clipboard')
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Failed to copy')
    }
  }

  return (
    <Button
      variant="outline"
      size="icon"
      className="h-8 w-8 shrink-0"
      onClick={handleCopy}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  )
}

const ConnectionField = ({ protocol, connections }: { protocol: string; connections: ProtocolConnections }) => {
  const label = PROTOCOL_LABELS[protocol] || { label: protocol, color: 'bg-gray-100 text-gray-800' }
  const [showFallbacks, setShowFallbacks] = useState(false)

  return (
    <div className="py-2 border rounded-lg p-3 space-y-1">
      <div className="flex items-center gap-2">
        <Badge className={`${label.color} text-xs shrink-0`}>{label.label}</Badge>
        <span className="text-xs text-muted-foreground shrink-0">Primary</span>
        <code className="text-xs bg-muted px-2 py-1 rounded flex-1 overflow-hidden whitespace-nowrap text-ellipsis">
          {connections.primary}
        </code>
        <CopyButton text={connections.primary} />
      </div>
      {connections.fallbacks.length > 0 && (
        <>
          <button
            onClick={() => setShowFallbacks(!showFallbacks)}
            className="text-xs text-muted-foreground hover:text-foreground ml-2"
          >
            {showFallbacks ? '▾' : '▸'} Fallbacks ({connections.fallbacks.length})
          </button>
          {showFallbacks && connections.fallbacks.map((fb, i) => (
            <div key={i} className="flex items-center gap-2 ml-2">
              <span className="text-xs text-muted-foreground w-20 shrink-0">Fallback {i + 1}</span>
              <code className="text-xs bg-muted px-2 py-1 rounded flex-1 overflow-hidden whitespace-nowrap text-ellipsis">
                {fb}
              </code>
              <CopyButton text={fb} />
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function RegionCard({
  regionCode,
  connections,
  username,
}: {
  regionCode: string
  connections: Record<string, ProtocolConnections>
  username: string
}) {
  const protocols = Object.keys(connections).sort()

  const handleCopyAll = async () => {
    const lines: string[] = []
    protocols.forEach((p) => {
      const meta = PROTOCOL_LABELS[p] || { label: p }
      const conn = connections[p]
      lines.push(`${meta.label}:`)
      lines.push(conn.primary)
      lines.push('')
    })

    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      toast.success('All connections copied')
    } catch {
      toast.error('Failed to copy')
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">{countryLabel(regionCode)}</CardTitle>
          <Badge variant="outline" className="text-xs">
            {protocols.length} protocols
          </Badge>
        </div>
        <Button variant="outline" size="sm" onClick={handleCopyAll}>
          <Copy className="mr-1 h-3 w-3" />
          Copy All
        </Button>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {protocols.map((protocol) => (
            <ConnectionField
              key={protocol}
              protocol={protocol}
              connections={connections[protocol]}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export default function UserConnectionsPage({
  params,
}: {
  params: { id: string }
}) {
  const userId = parseInt(params.id, 10)

  const { data: user, isLoading: userLoading } = useQuery({
    queryKey: ['admin', 'user', userId],
    queryFn: () => api.adminNew.getUser(userId),
    enabled: !isNaN(userId),
  })

  const { data: connectionsData, isLoading: connLoading, refetch: refetchConnections } = useQuery({
    queryKey: ['admin', 'user', userId, 'connections'],
    queryFn: () => api.adminNew.getUserConnections(userId),
    enabled: !isNaN(userId),
    refetchInterval: 30000,
  })

  const [refreshing, setRefreshing] = useState(false)
  const [sending, setSending] = useState(false)
  const [revealedPassword, setRevealedPassword] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await api.adminNew.refreshUserConnections(userId)
      refetchConnections()
      toast.success('Connections refreshed')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const handleResetPassword = async () => {
    setResetting(true)
    try {
      const res = await api.adminNew.resetUserPassword(userId)
      setRevealedPassword(res.password)
      toast.success('New password generated')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to reset password')
    } finally {
      setResetting(false)
    }
  }

  const handleSendTelegram = async () => {
    setSending(true)
    try {
      const res = await api.adminNew.sendConnectionsToTelegram(userId)
      setRevealedPassword(res.new_password)
      toast.success('Sent to Telegram (new password generated)')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Failed to send')
    } finally {
      setSending(false)
    }
  }

  const isLoading = userLoading || connLoading
  const regions = connectionsData?.connections || {}
  const telegramProxies = connectionsData?.telegram_proxies || {}

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href={`/dashboard/users/${userId}`}>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h2 className="text-2xl font-bold tracking-tight">Connection Strings</h2>
          <p className="text-muted-foreground">
            {user?.username || `User #${userId}`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? 'Refreshing...' : 'Refresh Connections'}
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-96" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Login Credentials Card */}
          <Card className="max-w-md">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Key className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-base">Website Login</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground w-20 shrink-0">Username</span>
                <code className="flex-1 text-sm bg-muted px-3 py-1.5 rounded break-all">
                  {user?.username}
                </code>
                <CopyButton text={user?.username || ''} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground w-20 shrink-0">Password</span>
                {revealedPassword ? (
                  <>
                    <code className="flex-1 text-sm bg-muted px-3 py-1.5 rounded font-mono break-all">
                      {revealedPassword}
                    </code>
                    <CopyButton text={revealedPassword} />
                  </>
                ) : (
                  <span className="text-sm text-muted-foreground italic">
                    Hidden - click Reset to generate
                  </span>
                )}
              </div>
              {revealedPassword && (
                <p className="text-xs text-muted-foreground">
                  Copy this password now. It will not be shown again.
                </p>
              )}
              <div className="flex gap-2 pt-1">
                <Button variant="outline" size="sm" onClick={handleResetPassword} disabled={resetting}>
                  <RefreshCw className="mr-1 h-3 w-3" />
                  {resetting ? 'Generating...' : 'Reset Password'}
                </Button>
                <Button variant="outline" size="sm" onClick={handleSendTelegram} disabled={sending}>
                  <Send className="mr-1 h-3 w-3" />
                  {sending ? 'Sending...' : 'Send to Telegram'}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Telegram Proxy Card */}
          {Object.keys(telegramProxies).length > 0 && (
            <Card className="max-w-md">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <MessageCircle className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-base">Telegram Proxy</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Click to auto-configure in Telegram. Uses SOCKS5 proxy with your credentials.
                </p>
                {Object.entries(telegramProxies).map(([countryCode, link]) => (
                  <div key={countryCode} className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground w-24 shrink-0">{countryLabel(countryCode)}</span>
                    <a
                      href={link}
                      className="flex-1 text-sm text-blue-600 hover:text-blue-800 break-all"
                    >
                      {link}
                    </a>
                    <CopyButton text={link} />
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Subscription Link Card */}
          {user?.subscription_url && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Subscription Links</CardTitle>
                <CardDescription>
                  Import connections into VPN clients automatically
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Standard (v2rayNG, V2Box, NetMod) — SS, VLESS, Trojan
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs bg-muted p-2 rounded break-all">
                      {user.subscription_url}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(user.subscription_url!)
                        toast.success('Standard link copied')
                      }}
                    >
                      Copy
                    </Button>
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Sing-box (Throne, Hiddify) — All 6 protocols incl. SSH, HTTP
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs bg-muted p-2 rounded break-all">
                      {user.subscription_url}?format=singbox
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(`${user.subscription_url}?format=singbox`)
                        toast.success('Sing-box link copied')
                      }}
                    >
                      Copy
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Region connection cards */}
          {Object.keys(regions).length === 0 ? (
            <Card>
              <CardContent className="text-center py-12">
                <Server className="mx-auto h-10 w-10 text-muted-foreground/50" />
                <p className="mt-3 text-sm text-muted-foreground">
                  No connection strings available.
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  This user needs at least one assigned macro region to have connection strings.
                </p>
                <Link href={`/dashboard/users/${userId}`}>
                  <Button variant="outline" size="sm" className="mt-4">
                    Manage Regions
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-1 lg:grid-cols-2">
              {Object.entries(regions)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([regionCode, conns]) => (
                  <RegionCard
                    key={regionCode}
                    regionCode={regionCode}
                    connections={conns}
                    username={user?.username || `User #${userId}`}
                  />
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
