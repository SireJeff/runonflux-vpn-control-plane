'use client'

/**
 * Country card with expand/collapse. When expanded, shows one ProtocolRow
 * per protocol (sorted alphabetically).
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { ProtocolRow } from './ProtocolRow'
import type { ConnectionCountry, ProtocolConnections } from '@/lib/api/endpoints/end-user'

interface Props {
  country: ConnectionCountry
  labels: {
    primary: string
    fallbacks: string
    fallback: string
    sshFieldsTitle: string
    host: string
    port: string
    username: string
    password: string
    copied: string
  }
}

export function CountryCard({ country, labels }: Props) {
  const [expanded, setExpanded] = useState(false)
  const protocols = Object.entries(country.connections).sort(([a], [b]) =>
    a.localeCompare(b)
  )

  return (
    <Card>
      <CardHeader
        className="flex flex-row items-center justify-between pb-3 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="text-base font-semibold">
          {country.flag} {country.country_name}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </CardHeader>
      {expanded && (
        <CardContent>
          <div className="divide-y divide-border">
            {protocols.map(([protocol, connections]) => (
              <ProtocolRow
                key={protocol}
                protocol={protocol}
                connections={connections as ProtocolConnections}
                labels={labels}
              />
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
