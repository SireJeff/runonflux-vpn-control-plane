'use client'

import React from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TopUser } from '@/types/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { useRouter } from 'next/navigation'
import { TrendingUp } from 'lucide-react'

interface TopUsersTableProps {
  data?: TopUser[]
  loading?: boolean
}

export function TopUsersTable({ data, loading }: TopUsersTableProps) {
  const router = useRouter()

  if (loading || !data) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            <CardTitle>Top Users</CardTitle>
          </div>
          <CardDescription>Highest spending users on the platform</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          <CardTitle>Top Users</CardTitle>
        </div>
        <CardDescription>Highest spending users on the platform</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60px]">Rank</TableHead>
              <TableHead>Username</TableHead>
              <TableHead className="text-right">Total Spent</TableHead>
              <TableHead className="text-center">Active Subs</TableHead>
              <TableHead className="text-center">Referrals</TableHead>
              <TableHead>Joined</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.length > 0 ? (
              data.map((user, index) => (
                <TableRow
                  key={user.user_id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => router.push(`/dashboard/users?search=${user.user_id}`)}
                >
                  <TableCell>
                    <Badge
                      variant={index < 3 ? 'default' : 'secondary'}
                      className={
                        index === 0
                          ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                          : index === 1
                          ? 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                          : index === 2
                          ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
                          : ''
                      }
                    >
                      #{index + 1}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-medium">
                    {user.username || `User #${user.user_id}`}
                  </TableCell>
                  <TableCell className="text-right font-mono font-bold">
                    ${formatCurrency(parseFloat(user.total_spent))}
                  </TableCell>
                  <TableCell className="text-center">{user.active_subscriptions}</TableCell>
                  <TableCell className="text-center">{user.referrals}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(user.joined_date)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  No users found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
