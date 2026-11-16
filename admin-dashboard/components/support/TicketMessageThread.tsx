'use client'

import React from 'react'
import { TicketMessageResponse } from '@/types/api'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { formatDistanceToNow } from 'date-fns'
import { User, Shield, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'

interface TicketMessageThreadProps {
  messages: TicketMessageResponse[]
  loading?: boolean
}

export function TicketMessageThread({ messages, loading }: TicketMessageThreadProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (loading) {
    return (
      <div className="space-y-4 p-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex gap-3">
            <div className="h-8 w-8 rounded-full bg-muted animate-pulse" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-32 bg-muted animate-pulse rounded" />
              <div className="h-16 bg-muted animate-pulse rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <div className="text-center">
          <MessageSquare className="h-12 w-12 mx-auto mb-3 text-muted-foreground/50" />
          <p>No messages yet</p>
        </div>
      </div>
    )
  }

  return (
    <ScrollArea className="h-[500px] pr-4" ref={scrollRef}>
      <div className="space-y-4">
        {messages.map((message) => {
          const isStaff = message.is_staff
          const isInternal = message.is_internal

          return (
            <div
              key={message.id}
              className={cn(
                'flex gap-3',
                isStaff && !isInternal && 'flex-row-reverse'
              )}
            >
              {/* Avatar */}
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                  isStaff
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
                )}
              >
                {isStaff ? (
                  <Shield className="h-4 w-4" />
                ) : (
                  <User className="h-4 w-4" />
                )}
              </div>

              {/* Message Content */}
              <div className={cn('flex-1 space-y-1', isStaff && !isInternal && 'items-end')}>
                {/* Header */}
                <div className={cn('flex items-center gap-2', isStaff && !isInternal && 'justify-end')}>
                  <span className="text-sm font-medium">
                    {message.user_name || 'Unknown User'}
                  </span>
                  {isStaff && <Badge variant="secondary">Staff</Badge>}
                  {isInternal && (
                    <Badge className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
                      Internal Note
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(message.created_at), {
                      addSuffix: true,
                    })}
                  </span>
                </div>

                {/* Message Body */}
                <div
                  className={cn(
                    'rounded-lg px-4 py-3 text-sm',
                    isInternal
                      ? 'bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800'
                      : isStaff
                      ? 'bg-primary/10 border border-primary/20'
                      : 'bg-muted'
                  )}
                >
                  <p className="whitespace-pre-wrap break-words">{message.message}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </ScrollArea>
  )
}

