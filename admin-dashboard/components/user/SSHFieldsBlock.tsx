'use client'

/**
 * SSH connection-details block (field-wise).
 *
 * Renders {host, port, username, password} from `parsed_fields` returned
 * by GET /user/connections. Each field has its own copy button — PuTTY and
 * Termius users need them separately for form input.
 */

import { Copy, Check, Globe, Plug, User, Key } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { SSHParsedFields } from '@/lib/api/endpoints/end-user'

interface Props {
  fields: SSHParsedFields
  labels: {
    title: string
    host: string
    port: string
    username: string
    password: string
    copied: string
  }
}

function FieldRow({
  icon: Icon,
  label,
  value,
  copiedLabel,
}: {
  icon: typeof Globe
  label: string
  value: string | number
  copiedLabel: string
}) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore — clipboard may be blocked in some browsers
    }
  }
  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs text-muted-foreground shrink-0">{label}:</span>
        <code className="text-xs font-mono break-all select-all">{value}</code>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0"
        onClick={handleCopy}
        aria-label={`${copiedLabel} ${label}`}
      >
        {copied ? (
          <Check className="h-3 w-3 text-green-600" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </Button>
    </div>
  )
}

export function SSHFieldsBlock({ fields, labels }: Props) {
  return (
    <div className="mt-2 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground mb-1">
        📋 {labels.title}
      </div>
      <FieldRow icon={Globe} label={labels.host} value={fields.host} copiedLabel={labels.copied} />
      <FieldRow icon={Plug} label={labels.port} value={fields.port} copiedLabel={labels.copied} />
      <FieldRow icon={User} label={labels.username} value={fields.username} copiedLabel={labels.copied} />
      <FieldRow icon={Key} label={labels.password} value={fields.password} copiedLabel={labels.copied} />
    </div>
  )
}
