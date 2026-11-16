'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import { Skeleton } from '@/components/ui/skeleton'
import { Server, Globe, Activity, AlertCircle, Users, TrendingUp } from 'lucide-react'
import { api } from '@/lib/api'
import type { ServerInstance, ServerStats } from '@/lib/api/endpoints/servers'

// Country flag emoji mapping
const COUNTRY_FLAGS: Record<string, string> = {
  US: '🇺🇸',
  GB: '🇬🇧',
  SG: '🇸🇬',
  DE: '🇩🇪',
  JP: '🇯🇵',
  CA: '🇨🇦',
  AU: '🇦🇺',
  FR: '🇫🇷',
  NL: '🇳🇱',
  SE: '🇸🇪',
}

// Health badge component
function HealthBadge({ status, score }: { status: string; score: number }) {
  const variants = {
    healthy: 'default',
    degraded: 'secondary',
    unhealthy: 'destructive',
  } as const

  const colors = {
    healthy: 'text-green-600',
    degraded: 'text-yellow-600',
    unhealthy: 'text-red-600',
  } as const

  return (
    <div className="flex items-center gap-2">
      <Badge variant={variants[status as keyof typeof variants] || 'default'}>
        {status}
      </Badge>
      <span className={`text-sm font-medium ${colors[status as keyof typeof colors] || ''}`}>
        {score}%
      </span>
    </div>
  )
}

function getHealthScore(status: string): number {
  const scores: Record<string, number> = {
    healthy: 100,
    degraded: 50,
    unhealthy: 0,
    unknown: 0,
  }
  return scores[status] ?? 0
}

// Stats card component
function StatsCard({
  title,
  value,
  icon: Icon,
  description,
  trend,
}: {
  title: string
  value: string | number
  icon: React.ElementType
  description?: string
  trend?: string
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
        {trend && (
          <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
            <TrendingUp className="h-3 w-3" />
            {trend}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default function ServersPage() {
  const [instances, setInstances] = useState<ServerInstance[]>([])
  const [stats, setStats] = useState<ServerStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [protocolFilter, setProtocolFilter] = useState<string>('all')
  const [countryFilter, setCountryFilter] = useState<string>('all')
  const [healthFilter, setHealthFilter] = useState<string>('all')

  // Load data
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      setError(null)

      try {
        const [instancesData, statsData] = await Promise.all([
          api.servers.listInstances(),
          api.servers.getInstanceStats(),
        ])

        setInstances(instancesData)
        setStats(statsData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load server data')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [protocolFilter, countryFilter, healthFilter])

  // Extract unique values for filters
  const protocols = ['all', ...new Set(instances.map(i => i.protocol_name))]
  const countries = ['all', ...new Set(instances.map(i => i.country_code))]

  const filteredInstances = instances.filter(instance => {
    if (protocolFilter !== 'all' && instance.protocol_name !== protocolFilter) {
      return false
    }
    if (countryFilter !== 'all' && instance.country_code !== countryFilter) {
      return false
    }
    if (healthFilter !== 'all' && instance.health_status !== healthFilter) {
      return false
    }
    return true
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Server Management</h1>
        <p className="text-muted-foreground">
          Monitor and manage FluxCloud VPN server instances
        </p>
      </div>

      {/* Stats Cards */}
      {loading && !stats ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="space-y-0 pb-2">
                <Skeleton className="h-4 w-[120px]" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-[80px]" />
                <Skeleton className="h-3 w-[140px] mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : stats ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <StatsCard
            title="Total Instances"
            value={stats.total_instances}
            icon={Server}
            description="Active server instances"
          />
          <StatsCard
            title="Healthy Servers"
            value={stats.healthy_instances}
            icon={Activity}
            description={`${Math.round((stats.healthy_instances / stats.total_instances) * 100)}% operational`}
            trend="+2 from yesterday"
          />
          <StatsCard
            title="Unhealthy Servers"
            value={stats.unhealthy_instances}
            icon={AlertCircle}
            description={stats.degraded_instances > 0 ? `${stats.degraded_instances} degraded` : 'All stable'}
          />
          <StatsCard
            title="Countries"
            value={stats.total_countries}
            icon={Globe}
            description="Geographic coverage"
          />
          <StatsCard
            title="Active Connections"
            value={stats.total_connections}
            icon={Users}
            description="Current user connections"
          />
          <StatsCard
            title="Avg Health Score"
            value={`${stats.avg_health_score}%`}
            icon={TrendingUp}
            description="Overall system health"
          />
        </div>
      ) : null}

      {/* Server Instances Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Server Instances</CardTitle>
              <CardDescription>
                View and filter all VPN server instances across protocols and regions
              </CardDescription>
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-4 pt-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Protocol:</label>
              <Select value={protocolFilter} onValueChange={setProtocolFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All protocols" />
                </SelectTrigger>
                <SelectContent>
                  {protocols.map(protocol => (
                    <SelectItem key={protocol} value={protocol}>
                      {protocol === 'all' ? 'All Protocols' : protocol}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Country:</label>
              <Select value={countryFilter} onValueChange={setCountryFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All countries" />
                </SelectTrigger>
                <SelectContent>
                  {countries.map(country => (
                    <SelectItem key={country} value={country}>
                      {country === 'all' ? 'All Countries' : `${COUNTRY_FLAGS[country] || ''} ${country}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Health:</label>
              <Select value={healthFilter} onValueChange={setHealthFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="healthy">Healthy</SelectItem>
                  <SelectItem value="degraded">Degraded</SelectItem>
                  <SelectItem value="unhealthy">Unhealthy</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="flex items-center justify-center h-64 text-destructive">
              <AlertCircle className="h-5 w-5 mr-2" />
              {error}
            </div>
          ) : loading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filteredInstances.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
              <Server className="h-12 w-12 mb-4 opacity-50" />
              <p className="text-lg font-medium">No servers found</p>
              <p className="text-sm">Try adjusting your filters</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Protocol</TableHead>
                  <TableHead>Country</TableHead>
                  <TableHead>IP Address</TableHead>
                  <TableHead>Port</TableHead>
                  <TableHead>Health Status</TableHead>
                  <TableHead>Connections</TableHead>
                  <TableHead>Active</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredInstances.map(instance => (
                  <TableRow
                    key={instance.id}
                    className="cursor-pointer"
                    onClick={() => {
                      // TODO: Navigate to instance details page
                      console.log('View details for instance:', instance.id)
                    }}
                  >
                    <TableCell className="font-medium">#{instance.id}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{instance.protocol_name}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{COUNTRY_FLAGS[instance.country_code] || '🏳️'}</span>
                        <div className="flex flex-col">
                          <span className="text-sm font-medium">{instance.country_name}</span>
                          <span className="text-xs text-muted-foreground">{instance.country_code}</span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{instance.public_ip}</TableCell>
                    <TableCell className="font-mono text-sm">{instance.port}</TableCell>
                    <TableCell>
                      <HealthBadge
                        status={instance.health_status}
                        score={getHealthScore(instance.health_status)}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="text-sm font-medium">{instance.active_connections}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={instance.is_active ? 'default' : 'secondary'}>
                        {instance.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* TODO: Add instance details modal/page when clicked */}
      {/* TODO: Add server actions (restart, disable, enable) */}
      {/* TODO: Add real-time health monitoring */}
    </div>
  )
}
