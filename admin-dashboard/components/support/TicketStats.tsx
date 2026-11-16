'use client'

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TicketStats as TicketStatsType } from '@/types/api'
import { MessageSquare, Clock, AlertCircle, CheckCircle2, XCircle } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'

interface TicketStatsProps {
  stats: TicketStatsType | undefined
  loading?: boolean
}

export function TicketStats({ stats, loading }: TicketStatsProps) {
  if (loading || !stats) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        {[...Array(5)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const statsConfig = [
    {
      title: 'Total Tickets',
      value: stats.total_tickets,
      icon: MessageSquare,
      color: 'text-primary',
    },
    {
      title: 'Open Tickets',
      value: stats.open_tickets,
      icon: AlertCircle,
      color: 'text-orange-500',
    },
    {
      title: 'In Progress',
      value: stats.in_progress_tickets,
      icon: Clock,
      color: 'text-blue-500',
    },
    {
      title: 'Resolved',
      value: stats.resolved_tickets,
      icon: CheckCircle2,
      color: 'text-green-500',
    },
    {
      title: 'Closed',
      value: stats.closed_tickets,
      icon: XCircle,
      color: 'text-gray-500',
    },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      {statsConfig.map((stat) => {
        const Icon = stat.icon
        return (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <Icon className={`h-4 w-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              {stat.title === 'In Progress' && stats.avg_resolution_time_hours && (
                <p className="text-xs text-muted-foreground mt-1">
                  Avg: {Math.round(stats.avg_resolution_time_hours)}h resolution
                </p>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
