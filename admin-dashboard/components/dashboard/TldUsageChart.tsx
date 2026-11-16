'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { TldAnalyticsSeries } from '@/lib/api/endpoints/super-admin'

interface Props {
  purpose: string
  data?: TldAnalyticsSeries
  loading?: boolean
}

// Distinct colors per domain line (recharts needs an explicit stroke per series).
const PALETTE = [
  'hsl(var(--primary))',
  '#2563eb', '#16a34a', '#db2777', '#ea580c', '#9333ea', '#0891b2',
]

export function TldUsageChart({ purpose, data, loading }: Props) {
  const title = purpose[0].toUpperCase() + purpose.slice(1)

  // Pivot each day's `values` map to top-level keys so each domain becomes a
  // flat series column (e.g. { date, "a.com": 3, "b.com": 1 }). recharts reliably
  // plots flat dataKeys; nested "values.<domain>" dot-paths render nothing.
  const chartData = (data?.series || []).map((day) => ({ date: day.date, ...day.values }))

  if (loading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title} — active users by TLD</CardTitle>
          <CardDescription>Last {data?.days ?? 30} days</CardDescription>
        </CardHeader>
        <CardContent><Skeleton className="h-[300px] w-full" /></CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title} — active users by TLD</CardTitle>
        <CardDescription>Last {data.days} days (daily snapshot)</CardDescription>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <div className="flex h-[300px] items-center justify-center text-muted-foreground">
            No analytics history yet — the daily snapshot runs at 03:17 UTC.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: 'currentColor' }} />
              <YAxis className="text-xs" tick={{ fill: 'currentColor' }} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                }}
              />
              <Legend />
              {data.domains.map((domain, i) => (
                <Line
                  key={domain}
                  type="monotone"
                  dataKey={domain}
                  stroke={PALETTE[i % PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                  name={domain}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
