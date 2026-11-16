'use client'

/**
 * Single-protocol row in a country card. Shows protocol badge + primary URI
 * + copy button. For SSH, conditionally renders SSHFieldsBlock below when
 * parsed_fields is populated (older connections may not have it).
 */

import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SSHFieldsBlock } from './SSHFieldsBlock'
import type { ProtocolConnections } from '@/lib/api/endpoints/end-user'

const PROTOCOL_META: Record<string, { label: string; dotColor: string; badgeClass: string }> = {
  ssh: {
    label: 'SSH',
    dotColor: 'bg-blue-500',
    badgeClass: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  },
  ss: {
    label: 'SS',
    dotColor: 'bg-green-500',
    badgeClass: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  },
  shadowsocks: {
    label: 'Shadowsocks',
    dotColor: 'bg-green-500',
    badgeClass: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  },
  vless: {
    label: 'VLESS',
    dotColor: 'bg-purple-500',
    badgeClass: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  },
  trojan: {
    label: 'Trojan',
    dotColor: 'bg-red-500',
    badgeClass: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  },
  outline: {
    label: 'Outline',
    dotColor: 'bg-orange-500',
    badgeClass: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  },
  http_proxy: {
    label: 'HTTP',
    dotColor: 'bg-gray-500',
    badgeClass: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  },
}

function getMeta(protocol: string) {
  return (
    PROTOCOL_META[protocol] || {
      label: protocol.toUpperCase(),
      dotColor: 'bg-gray-500',
      badgeClass: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    }
  )
}

interface Props {
  protocol: string
  connections: ProtocolConnections
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

export function ProtocolRow({ protocol, connections, labels }: Props) {
  const meta = getMeta(protocol)
  const [showFallbacks, setShowFallbacks] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(connections.primary)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  return (
    <div className="py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${meta.dotColor}`} />
          <Badge className={meta.badgeClass}>{meta.label}</Badge>
          <span className="text-xs text-muted-foreground font-medium">★ {labels.primary}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={handleCopy}
          aria-label={`Copy ${meta.label}`}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-600" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
      <code className="block w-full rounded-md bg-muted px-3 py-2 text-xs font-mono break-all leading-relaxed select-all mt-1">
        {connections.primary}
      </code>

      {/* SSH: field-wise block */}
      {protocol.toLowerCase() === 'ssh' && connections.parsed_fields && (
        <SSHFieldsBlock
          fields={connections.parsed_fields}
          labels={{
            title: labels.sshFieldsTitle,
            host: labels.host,
            port: labels.port,
            username: labels.username,
            password: labels.password,
            copied: labels.copied,
          }}
        />
      )}

      {/* Fallbacks */}
      {connections.fallbacks.length > 0 && (
        <div className="mt-1">
          <button
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
            onClick={() => setShowFallbacks(!showFallbacks)}
          >
            <span className={`transition-transform ${showFallbacks ? 'rotate-90' : ''}`}>&#9654;</span>
            <span>
              {labels.fallbacks} ({connections.fallbacks.length})
            </span>
          </button>
          {showFallbacks && (
            <div className="ml-2 border-l-2 border-border pl-3 mt-1 space-y-2">
              {connections.fallbacks.map((fallback, index) => (
                <div key={index}>
                  <div className="text-xs text-muted-foreground font-medium mb-1">
                    {labels.fallback} {index + 1}
                  </div>
                  <code className="block w-full rounded-md bg-muted px-3 py-2 text-xs font-mono break-all leading-relaxed select-all">
                    {fallback}
                  </code>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
