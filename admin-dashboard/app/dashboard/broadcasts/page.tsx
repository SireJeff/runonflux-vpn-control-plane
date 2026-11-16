'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { BroadcastSegment } from '@/lib/api/endpoints/broadcasts'
import { formatDate } from '@/lib/utils'
import { Send, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import toast from 'react-hot-toast'
import { isAxiosError } from 'axios'

const SEGMENTS: { value: BroadcastSegment; label: string }[] = [
  { value: 'all', label: 'Everyone who started the bot' },
  { value: 'lang_fa', label: 'Persian speakers' },
  { value: 'lang_en', label: 'English speakers' },
  { value: 'active_paid', label: 'Active paid subscribers' },
  { value: 'expired_free', label: 'Expired / free (win-back)' },
]

export default function BroadcastsPage() {
  const queryClient = useQueryClient()
  const [segment, setSegment] = useState<BroadcastSegment>('all')
  const [messageText, setMessageText] = useState('')
  const [buttonLabel, setButtonLabel] = useState('')
  const [buttonUrl, setButtonUrl] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const { data: history } = useQuery({
    queryKey: ['broadcasts'],
    queryFn: () => api.broadcasts.list(),
    refetchInterval: (query) => {
      const rows = query.state.data
      const active = rows?.some((b) => b.status === 'queued' || b.status === 'sending')
      return active ? 4000 : false
    },
  })

  const { data: audienceCount, isFetching: countLoading } = useQuery({
    queryKey: ['broadcast-audience', segment],
    queryFn: () => api.broadcasts.audienceCount(segment),
  })

  const sendMutation = useMutation({
    mutationFn: () =>
      api.broadcasts.create({
        message_text: messageText,
        button_label: buttonLabel || undefined,
        button_url: buttonUrl || undefined,
        segment,
      }),
    onSuccess: () => {
      toast.success('Broadcast queued')
      setMessageText('')
      setButtonLabel('')
      setButtonUrl('')
      queryClient.invalidateQueries({ queryKey: ['broadcasts'] })
    },
    onError: (err) => {
      if (isAxiosError(err) && err.response?.status === 429) {
        toast.error('Daily broadcast limit reached')
      } else if (isAxiosError(err) && err.response?.status === 409) {
        toast.error('Broadcasting is disabled or a broadcast is already in progress')
      } else if (isAxiosError(err) && err.response?.status === 422) {
        toast.error(`Invalid message: ${err.response?.data?.detail ?? ''}`)
      } else {
        toast.error('Failed to send broadcast')
      }
    },
    onSettled: () => setConfirmOpen(false),
  })

  const canSend = messageText.trim().length > 0 && messageText.length <= 4096

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Send className="h-5 w-5" /> New Broadcast</CardTitle>
          <CardDescription>Message the end-users who started your bot.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Audience</Label>
            <Select value={segment} onValueChange={(v) => setSegment(v as BroadcastSegment)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {SEGMENTS.map((s) => (
                  <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">
              {countLoading ? 'Counting…' : `${audienceCount ?? 0} recipient(s)`}
            </p>
          </div>

          <div className="space-y-2">
            <Label>Message (HTML: &lt;b&gt; &lt;i&gt; &lt;a&gt; …)</Label>
            <Textarea
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              rows={6}
              maxLength={4096}
              placeholder="Your announcement…"
            />
            <p className="text-xs text-muted-foreground text-right">{messageText.length}/4096</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Button label (optional)</Label>
              <Input value={buttonLabel} onChange={(e) => setButtonLabel(e.target.value)} maxLength={64} />
            </div>
            <div className="space-y-2">
              <Label>Button URL (optional)</Label>
              <Input value={buttonUrl} onChange={(e) => setButtonUrl(e.target.value)} placeholder="https://…" />
            </div>
          </div>

          <Button disabled={!canSend} onClick={() => setConfirmOpen(true)}>
            <Send className="h-4 w-4 mr-2" /> Send Broadcast
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>History</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(history ?? []).map((b) => (
              <div key={b.id} className="flex items-center justify-between border-b py-2 text-sm">
                <div className="flex flex-col">
                  <span className="font-medium">{SEGMENTS.find((s) => s.value === b.segment)?.label ?? b.segment}</span>
                  <span className="text-muted-foreground">{formatDate(b.created_at)}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span>{b.sent_count}✓ {b.blocked_count}🚫 {b.failed_count}✗ / {b.audience_count}</span>
                  <Badge variant={b.status === 'completed' ? 'default' : b.status === 'failed' ? 'destructive' : 'secondary'}>
                    {b.status}
                  </Badge>
                </div>
              </div>
            ))}
            {(history ?? []).length === 0 && <p className="text-sm text-muted-foreground">No broadcasts yet.</p>}
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Send this broadcast?</AlertDialogTitle>
            <AlertDialogDescription>
              This will message {audienceCount ?? 0} user(s). This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              {sendMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
