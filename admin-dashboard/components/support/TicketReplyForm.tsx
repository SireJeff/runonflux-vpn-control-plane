'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Loader2, Send } from 'lucide-react'

interface TicketReplyFormProps {
  onSubmit: (message: string, isInternal: boolean) => Promise<void>
  loading?: boolean
  ticketId: number
}

export function TicketReplyForm({ onSubmit, loading = false, ticketId }: TicketReplyFormProps) {
  const [message, setMessage] = React.useState('')
  const [isInternal, setIsInternal] = React.useState(false)

  // Load draft from localStorage
  React.useEffect(() => {
    const draft = localStorage.getItem(`ticket-draft-${ticketId}`)
    if (draft) {
      setMessage(draft)
    }
  }, [ticketId])

  // Save draft to localStorage
  React.useEffect(() => {
    if (message) {
      localStorage.setItem(`ticket-draft-${ticketId}`, message)
    } else {
      localStorage.removeItem(`ticket-draft-${ticketId}`)
    }
  }, [message, ticketId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!message.trim()) return

    try {
      await onSubmit(message, isInternal)
      setMessage('')
      setIsInternal(false)
      localStorage.removeItem(`ticket-draft-${ticketId}`)
    } catch (error) {
      // Error handling done by parent
      console.error('Reply submission error:', error)
    }
  }

  const characterCount = message.length
  const maxCharacters = 5000

  return (
    <Card>
      <form onSubmit={handleSubmit}>
        <CardContent className="pt-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="message">Reply to ticket</Label>
              <Textarea
                id="message"
                placeholder="Type your message here..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="min-h-[120px] resize-y"
                maxLength={maxCharacters}
                disabled={loading}
              />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-4">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="internal"
                      checked={isInternal}
                      onCheckedChange={(checked) => setIsInternal(!!checked)}
                      disabled={loading}
                    />
                    <label
                      htmlFor="internal"
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                    >
                      Internal note (admin only)
                    </label>
                  </div>
                </div>
                <span className={characterCount > maxCharacters - 500 ? 'text-orange-500' : ''}>
                  {characterCount} / {maxCharacters}
                </span>
              </div>
            </div>
          </div>
        </CardContent>

        <CardFooter className="flex justify-between">
          <div className="text-xs text-muted-foreground">
            {message && !loading && (
              <span>Draft saved automatically</span>
            )}
          </div>
          <Button
            type="submit"
            disabled={loading || !message.trim() || characterCount > maxCharacters}
          >
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            <Send className="mr-2 h-4 w-4" />
            {isInternal ? 'Add Internal Note' : 'Send Reply'}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
