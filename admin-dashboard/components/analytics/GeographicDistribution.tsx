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
import { CountryStats } from '@/types/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Globe, Server, Activity } from 'lucide-react'

interface GeographicDistributionProps {
  data?: CountryStats[]
  loading?: boolean
}

export function GeographicDistribution({ data, loading }: GeographicDistributionProps) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            <CardTitle>Geographic Distribution</CardTitle>
          </div>
          <CardDescription>Server instances and connections by country</CardDescription>
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

  // Sort by active instances descending
  const sortedData = [...data].sort((a, b) => b.active_instances - a.active_instances)

  const getHealthBadge = (health: number) => {
    if (health >= 90) {
      return <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Excellent</Badge>
    } else if (health >= 70) {
      return <Badge className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">Good</Badge>
    } else if (health >= 50) {
      return <Badge className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">Fair</Badge>
    } else {
      return <Badge className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">Poor</Badge>
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5" />
          <CardTitle>Geographic Distribution</CardTitle>
        </div>
        <CardDescription>Server instances and connections by country</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Country</TableHead>
              <TableHead className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <Server className="h-3 w-3" />
                  <span>Instances</span>
                </div>
              </TableHead>
              <TableHead className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <Activity className="h-3 w-3" />
                  <span>Connections</span>
                </div>
              </TableHead>
              <TableHead className="text-center">Health</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedData.length > 0 ? (
              sortedData.map((country) => (
                <TableRow key={country.country_code}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{getFlagEmoji(country.country_code)}</span>
                      <span className="font-medium">{country.country_name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-center font-medium">
                    {country.active_instances}
                  </TableCell>
                  <TableCell className="text-center font-medium">
                    {country.total_connections.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-center">
                    <div className="flex items-center justify-center gap-2">
                      {getHealthBadge(country.avg_health)}
                      <span className="text-sm text-muted-foreground">
                        {country.avg_health.toFixed(0)}%
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                  No geographic data available
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

// Helper function to get flag emoji from country code
function getFlagEmoji(countryCode: string): string {
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map((char) => 127397 + char.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}
