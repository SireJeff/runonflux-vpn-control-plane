'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  FileText,
  Search,
  Filter,
  Download,
  AlertCircle,
  Calendar as CalendarIcon,
  AlertTriangle,
  Info,
  XCircle,
  Bug,
} from 'lucide-react'
import { api, LogLevel, LogSource, LogEntry, LogStats } from '@/lib/api'
import { format } from 'date-fns'
import { cn } from '@/lib/utils'

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    level: 'all' as string,
    source: 'all' as string,
    search: '',
  })

  const isFilterActive = (v: string) => v && v !== 'all'
  const [dateRange, setDateRange] = useState<{
    from: Date | undefined
    to: Date | undefined
  }>({
    from: undefined,
    to: undefined,
  })

  useEffect(() => {
    loadLogs()
    loadStats()
  }, [filters, dateRange])

  const loadLogs = async () => {
    try {
      setLoading(true)
      const params: any = {}

      if (isFilterActive(filters.level)) params.level = filters.level
      if (isFilterActive(filters.source)) params.source = filters.source
      if (filters.search) params.search = filters.search
      if (dateRange.from) params.start_date = format(dateRange.from, 'yyyy-MM-dd')
      if (dateRange.to) params.end_date = format(dateRange.to, 'yyyy-MM-dd')

      const data = await api.logs.listLogs(params)
      setLogs(data)
    } catch (error) {
      console.error('Failed to load logs:', error)
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const data = await api.logs.getLogStats()
      setStats(data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleExport = async () => {
    try {
      const params: any = {}
      if (isFilterActive(filters.level)) params.level = filters.level
      if (isFilterActive(filters.source)) params.source = filters.source
      if (filters.search) params.search = filters.search
      if (dateRange.from) params.start_date = format(dateRange.from, 'yyyy-MM-dd')
      if (dateRange.to) params.end_date = format(dateRange.to, 'yyyy-MM-dd')

      const blob = await api.logs.exportLogs(params)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `system-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Failed to export logs:', error)
    }
  }

  const getLevelBadgeVariant = (level: LogLevel) => {
    switch (level) {
      case 'DEBUG':
        return 'secondary'
      case 'INFO':
        return 'default'
      case 'WARNING':
        return 'outline'
      case 'ERROR':
        return 'destructive'
      case 'CRITICAL':
        return 'destructive'
      default:
        return 'secondary'
    }
  }

  const getLevelIcon = (level: LogLevel) => {
    switch (level) {
      case 'DEBUG':
        return <Bug className="h-4 w-4" />
      case 'INFO':
        return <Info className="h-4 w-4" />
      case 'WARNING':
        return <AlertTriangle className="h-4 w-4" />
      case 'ERROR':
        return <XCircle className="h-4 w-4" />
      case 'CRITICAL':
        return <AlertCircle className="h-4 w-4" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">System Logs</h1>
        <p className="text-muted-foreground">
          Monitor and analyze system activity and errors
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Logs Today</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="text-2xl font-bold">{stats.total_today.toLocaleString()}</div>
            ) : (
              <Skeleton className="h-8 w-20" />
            )}
            <p className="text-xs text-muted-foreground mt-1">Total log entries</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Errors Today</CardTitle>
            <XCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="text-2xl font-bold text-red-600">{stats.errors_today.toLocaleString()}</div>
            ) : (
              <Skeleton className="h-8 w-20" />
            )}
            <p className="text-xs text-muted-foreground mt-1">Critical & errors</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Warnings Today</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="text-2xl font-bold text-yellow-600">{stats.warnings_today.toLocaleString()}</div>
            ) : (
              <Skeleton className="h-8 w-20" />
            )}
            <p className="text-xs text-muted-foreground mt-1">Warning messages</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Primary Source</CardTitle>
            <Info className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="text-2xl font-bold capitalize">{stats.most_common_source}</div>
            ) : (
              <Skeleton className="h-8 w-20" />
            )}
            <p className="text-xs text-muted-foreground mt-1">Most active component</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Filters</CardTitle>
          </div>
          <CardDescription>Filter logs by level, source, date range, or search</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {/* Log Level Filter */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Log Level</label>
              <Select
                value={filters.level}
                onValueChange={(value) =>
                  setFilters({ ...filters, level: value  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="All levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="DEBUG">DEBUG</SelectItem>
                  <SelectItem value="INFO">INFO</SelectItem>
                  <SelectItem value="WARNING">WARNING</SelectItem>
                  <SelectItem value="ERROR">ERROR</SelectItem>
                  <SelectItem value="CRITICAL">CRITICAL</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Source Filter */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Source</label>
              <Select
                value={filters.source}
                onValueChange={(value) =>
                  setFilters({ ...filters, source: value  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="All sources" />
                </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sources</SelectItem>
                    <SelectItem value="connection">Connection</SelectItem>
                    <SelectItem value="auth">Auth</SelectItem>
                  </SelectContent>
              </Select>
            </div>

            {/* Date Range */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Start Date</label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      'w-full justify-start text-left font-normal',
                      !dateRange.from && 'text-muted-foreground'
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {dateRange.from ? format(dateRange.from, 'PPP') : 'Pick a date'}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={dateRange.from}
                    onSelect={(date) => setDateRange({ ...dateRange, from: date })}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">End Date</label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      'w-full justify-start text-left font-normal',
                      !dateRange.to && 'text-muted-foreground'
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {dateRange.to ? format(dateRange.to, 'PPP') : 'Pick a date'}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={dateRange.to}
                    onSelect={(date) => setDateRange({ ...dateRange, to: date })}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

            {/* Search */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Search</label>
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search messages..."
                  value={filters.search}
                  onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                  className="pl-8"
                />
              </div>
            </div>
          </div>

          <div className="flex gap-2 mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setFilters({ level: 'all', source: 'all', search: '' })
                setDateRange({ from: undefined, to: undefined })
              }}
            >
              Clear Filters
            </Button>
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4 mr-2" />
              Export CSV
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Logs Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Log Entries</CardTitle>
          </div>
          <CardDescription>Recent system logs and events</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="rounded-full bg-muted p-3 mb-4">
                <FileText className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">No logs found</h3>
              <p className="text-sm text-muted-foreground mb-6 max-w-sm">
                No log entries match your current filters. Try adjusting your search criteria or check
                back later.
              </p>
              <div className="bg-muted/50 border border-muted rounded-lg p-4 max-w-md">
                <p className="text-sm text-muted-foreground">
                  No log entries matched your current filters.
                </p>
              </div>
            </div>
          ) : (
            <div className="relative overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[180px]">Timestamp</TableHead>
                    <TableHead className="w-[120px]">Level</TableHead>
                    <TableHead className="w-[120px]">Source</TableHead>
                    <TableHead>Message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="font-mono text-xs">
                        {format(new Date(log.timestamp), 'MMM dd, yyyy HH:mm:ss')}
                      </TableCell>
                      <TableCell>
                        <Badge variant={getLevelBadgeVariant(log.level)} className="gap-1">
                          {getLevelIcon(log.level)}
                          {log.level}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {log.source}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-md">
                        <div className="truncate" title={log.message}>
                          {log.message}
                        </div>
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
