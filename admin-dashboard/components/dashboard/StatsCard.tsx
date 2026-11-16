import { LucideIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'

interface StatsCardProps {
  title: string
  value: string | number
  change?: number | null
  icon: LucideIcon
  format?: 'currency' | 'number' | 'text'
  loading?: boolean
}

export function StatsCard({
  title,
  value,
  change,
  icon: Icon,
  format = 'text',
  loading = false,
}: StatsCardProps) {
  const formattedValue = () => {
    if (loading) return null

    switch (format) {
      case 'currency':
        return formatCurrency(Number(value))
      case 'number':
        return formatNumber(Number(value))
      default:
        return value
    }
  }

  const changeData = change !== undefined ? formatPercentage(change) : null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-24" />
            {change !== undefined && <Skeleton className="h-4 w-16" />}
          </div>
        ) : (
          <>
            <div className="text-2xl font-bold">{formattedValue()}</div>
            {changeData && (
              <p className={`text-xs ${changeData.color}`}>
                {changeData.text} from last month
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function StatsCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-4" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-24 mb-2" />
        <Skeleton className="h-4 w-16" />
      </CardContent>
    </Card>
  )
}
