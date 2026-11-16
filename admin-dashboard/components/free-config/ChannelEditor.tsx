'use client'

import { useState } from 'react'
import type { ChannelOut } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Trash2 } from 'lucide-react'

interface ChannelEditorProps {
  channels: ChannelOut[]
  onAdd: (identifier: string, inviteUrl?: string) => void
  onDelete: (id: number) => void
  title?: string
}

/**
 * Controlled editor for required Telegram channels.
 * Parent owns all data fetching; this component only renders rows and
 * emits onAdd / onDelete callbacks.
 */
export function ChannelEditor({ channels, onAdd, onDelete, title }: ChannelEditorProps) {
  const [identifier, setIdentifier] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')

  const handleAdd = () => {
    const trimmed = identifier.trim()
    if (!trimmed) return
    const url = inviteUrl.trim()
    onAdd(trimmed, url || undefined)
    setIdentifier('')
    setInviteUrl('')
  }

  return (
    <div className="space-y-3">
      {title ? <Label>{title}</Label> : null}

      {channels.length === 0 ? (
        <p className="text-xs text-muted-foreground">No channels configured yet.</p>
      ) : (
        <ul className="space-y-2">
          {channels.map((ch) => (
            <li
              key={ch.id}
              className="flex items-center justify-between rounded-md border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{ch.title}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {ch.username ?? (ch.chat_id != null ? String(ch.chat_id) : '')}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete channel ${ch.title}`}
                onClick={() => onDelete(ch.id)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Input
          placeholder="@channel or -100..."
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
        />
        <Input
          placeholder="Invite URL (optional)"
          value={inviteUrl}
          onChange={(e) => setInviteUrl(e.target.value)}
        />
      </div>
      <Button type="button" variant="outline" onClick={handleAdd}>
        Add channel
      </Button>
    </div>
  )
}

export default ChannelEditor
