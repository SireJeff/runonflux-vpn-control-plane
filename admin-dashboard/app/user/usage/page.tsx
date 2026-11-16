'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Activity, Wifi, HardDrive } from 'lucide-react'
import { formatTraffic } from '@/lib/utils'
import type { ProtocolBreakdown, RegionBreakdown } from '@/lib/api/endpoints/end-user'

// Protocol color mapping - matches connections page
const PROTOCOL_COLORS: Record<string, { barColor: string; badgeClass: string }> = {
  ssh: {
    barColor: 'bg-blue-500',
    badgeClass: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  },
  shadowsocks: {
    barColor: 'bg-green-500',
    badgeClass: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  },
  vless: {
    barColor: 'bg-purple-500',
    badgeClass: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  },
  trojan: {
    barColor: 'bg-red-500',
    badgeClass: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  },
  outline: {
    barColor: 'bg-orange-500',
    badgeClass: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  },
  http_proxy: {
    barColor: 'bg-gray-500',
    badgeClass: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  },
}

function getProtocolColor(protocol: string) {
  return PROTOCOL_COLORS[protocol] || {
    barColor: 'bg-gray-500',
    badgeClass: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  }
}

function formatRegionLabel(code: string): string {
  return code
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function UsageBar({ label, gb, maxGb, barColor, badgeClass }: {
  label: string
  gb: number
  maxGb: number
  barColor: string
  badgeClass: string
}) {
  const pct = maxGb > 0 ? Math.min((gb / maxGb) * 100, 100) : 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Badge className={badgeClass}>{label}</Badge>
        <span className="text-sm font-mono font-medium">{formatTraffic(gb)}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function EndUserUsagePage() {
  const { data: usageData, isLoading } = useQuery({
    queryKey: ['endUser', 'usage'],
    queryFn: () => api.endUser.getUsage(),
    refetchInterval: 60000,
  })

  const totalGb = usageData?.total_gb || 0
  const protocolBreakdown = usageData?.protocol_breakdown || []
  const regionBreakdown = usageData?.region_breakdown || []

  // Max GB for bar scaling (within each breakdown section)
  const maxProtocolGb = protocolBreakdown.reduce(
    (max, p) => Math.max(max, p.gb_total),
    0
  )
  const maxRegionGb = regionBreakdown.reduce(
    (max, r) => Math.max(max, r.gb_total),
    0
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Usage</h2>
        <p className="text-muted-foreground">Monitor your bandwidth consumption</p>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {!isLoading && (
        <>
          {/* Total Traffic Card */}
          <Card className="border-2">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Total Traffic</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold">
                {formatTraffic(totalGb).replace(' GB', '').replace(' MB', '')}{' '}
                <span className="text-lg font-normal text-muted-foreground">{formatTraffic(totalGb).includes('MB') ? 'MB' : 'GB'}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {totalGb === 0
                  ? 'No traffic recorded yet'
                  : `Across ${protocolBreakdown.length} protocol${protocolBreakdown.length !== 1 ? 's' : ''}`}
              </p>
            </CardContent>
          </Card>

          {/* Protocol Breakdown */}
          {protocolBreakdown.length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-base">By Protocol</CardTitle>
                </div>
                <CardDescription>
                  Traffic consumption per VPN protocol
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {protocolBreakdown
                    .sort((a, b) => b.gb_total - a.gb_total)
                    .map((p: ProtocolBreakdown) => {
                      const colors = getProtocolColor(p.protocol)
                      return (
                        <UsageBar
                          key={p.protocol}
                          label={p.protocol}
                          gb={p.gb_total}
                          maxGb={maxProtocolGb}
                          barColor={colors.barColor}
                          badgeClass={colors.badgeClass}
                        />
                      )
                    })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Region Breakdown */}
          {regionBreakdown.length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Wifi className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-base">By Region</CardTitle>
                </div>
                <CardDescription>
                  Traffic consumption per server region
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {regionBreakdown
                    .sort((a, b) => b.gb_total - a.gb_total)
                    .map((r: RegionBreakdown) => (
                      <UsageBar
                        key={r.region_code}
                        label={formatRegionLabel(r.region_code)}
                        gb={r.gb_total}
                        maxGb={maxRegionGb}
                        barColor="bg-primary"
                        badgeClass="bg-primary/10 text-primary dark:bg-primary/20"
                      />
                    ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* No Data State */}
          {protocolBreakdown.length === 0 && regionBreakdown.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16">
                <Activity className="h-12 w-12 text-muted-foreground/40" />
                <h3 className="mt-4 text-lg font-medium">No usage data yet</h3>
                <p className="mt-1 text-sm text-muted-foreground text-center max-w-sm">
                  Your bandwidth usage will appear here once you start using your VPN connections.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
