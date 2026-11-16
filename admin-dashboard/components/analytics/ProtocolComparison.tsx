'use client'

import React from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { ProtocolStats } from '@/types/api'
import { formatCurrency } from '@/lib/utils'

interface ProtocolComparisonProps {
  data?: ProtocolStats[]
  loading?: boolean
}

export function ProtocolComparison({ data, loading }: ProtocolComparisonProps) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Protocol Comparison</CardTitle>
          <CardDescription>Active subscriptions and revenue by protocol</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[350px] w-full" />
        </CardContent>
      </Card>
    )
  }

  // Transform data for chart
  const chartData = data.map((protocol) => ({
    name: protocol.protocol_name,
    subscriptions: protocol.active_subscriptions,
    revenue: parseFloat(protocol.revenue),
    health: protocol.avg_health_score,
  }))

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg border bg-background p-3 shadow-sm">
          <p className="text-sm font-medium mb-2">{payload[0].payload.name}</p>
          <p className="text-sm text-muted-foreground">
            Subscriptions: {payload[0].value}
          </p>
          <p className="text-sm text-muted-foreground">
            Revenue: ${formatCurrency(payload[0].payload.revenue)}
          </p>
          <p className="text-sm text-muted-foreground">
            Health: {payload[0].payload.health.toFixed(1)}%
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Protocol Comparison</CardTitle>
        <CardDescription>Active subscriptions and revenue by protocol</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Bar dataKey="subscriptions" fill="#8884d8" name="Active Subscriptions" />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
