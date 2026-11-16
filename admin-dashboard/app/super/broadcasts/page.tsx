'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Radio } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

const STATUS_VARIANT: Record<string, 'default' | 'destructive' | 'secondary'> = {
  completed: 'default',
  failed: 'destructive',
  queued: 'secondary',
  sending: 'secondary',
}

export default function SuperBroadcastsPage() {
  const { data: broadcasts, isLoading } = useQuery({
    queryKey: ['super', 'broadcasts'],
    queryFn: () => api.superAdmin.listBroadcasts(),
    refetchInterval: (query) => {
      const rows = query.state.data
      const active = rows?.some((b) => b.status === 'queued' || b.status === 'sending')
      return active ? 5000 : false
    },
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Radio className="h-6 w-6" /> Broadcasts
        </h2>
        <p className="text-muted-foreground">Read-only view of every reseller broadcast.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Broadcasts</CardTitle>
          <CardDescription>Newest first, across all resellers.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (broadcasts ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-10">No broadcasts yet.</p>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Admin</TableHead>
                    <TableHead>Segment</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Progress</TableHead>
                    <TableHead className="hidden sm:table-cell">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(broadcasts ?? []).map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="font-mono text-xs">#{b.id}</TableCell>
                      <TableCell className="text-sm">#{b.admin_id}</TableCell>
                      <TableCell className="text-xs">{b.segment}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[b.status] ?? 'secondary'}>{b.status}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {b.sent_count}✓ {b.blocked_count}🚫 {b.failed_count}✗ / {b.audience_count}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                        {b.created_at ? formatDate(b.created_at, true) : '-'}
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
