import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { formatRelativeTime } from '@/lib/utils'
import {
  UserPlus,
  CreditCard,
  AlertCircle,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react'

interface Activity {
  id: string
  type: 'user_registered' | 'payment_completed' | 'payment_failed' | 'subscription_expired' | 'support_ticket'
  message: string
  timestamp: string
  status?: 'success' | 'warning' | 'error' | 'info'
}

interface RecentActivityFeedProps {
  activities: Activity[]
  loading?: boolean
}

const activityIcons = {
  user_registered: UserPlus,
  payment_completed: CreditCard,
  payment_failed: XCircle,
  subscription_expired: Clock,
  support_ticket: AlertCircle,
}

const activityColors = {
  success: 'text-green-600',
  warning: 'text-yellow-600',
  error: 'text-red-600',
  info: 'text-blue-600',
}

export function RecentActivityFeed({ activities, loading = false }: RecentActivityFeedProps) {
  if (loading) {
    return (
      <Card className="col-span-1">
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Latest system events and user actions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-start gap-4">
                <Skeleton className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/4" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="col-span-1">
      <CardHeader>
        <CardTitle>Recent Activity</CardTitle>
        <CardDescription>Latest system events and user actions</CardDescription>
      </CardHeader>
      <CardContent>
        {activities.length === 0 ? (
          <div className="flex h-[300px] items-center justify-center text-muted-foreground">
            No recent activity
          </div>
        ) : (
          <ScrollArea className="h-[400px] pr-4">
            <div className="space-y-4">
              {activities.map((activity) => {
                const Icon = activityIcons[activity.type] || CheckCircle
                const colorClass = activity.status
                  ? activityColors[activity.status]
                  : 'text-muted-foreground'

                return (
                  <div key={activity.id} className="flex items-start gap-4">
                    <div
                      className={`flex h-8 w-8 items-center justify-center rounded-full bg-muted ${colorClass}`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 space-y-1">
                      <p className="text-sm font-medium leading-none">
                        {activity.message}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatRelativeTime(activity.timestamp)}
                      </p>
                    </div>
                    {activity.status && (
                      <Badge
                        variant={
                          activity.status === 'success'
                            ? 'success'
                            : activity.status === 'error'
                            ? 'destructive'
                            : activity.status === 'warning'
                            ? 'warning'
                            : 'default'
                        }
                      >
                        {activity.status}
                      </Badge>
                    )}
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}
