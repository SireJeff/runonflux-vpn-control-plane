'use client'

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { TicketMessageThread } from '@/components/support/TicketMessageThread'
import { TicketReplyForm } from '@/components/support/TicketReplyForm'
import {
  ArrowLeft,
  Loader2,
  User,
  Calendar,
  Tag,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { formatDate } from '@/lib/utils'
import toast from 'react-hot-toast'
import { CheckCircle2 } from 'lucide-react'

export default function TicketDetailPage({ params }: { params: { id: string } }) {
  const ticketId = parseInt(params.id)
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  // Redirect if not authenticated
  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch ticket details
  const { data: ticketDetail, isLoading } = useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => api.support.getTicket(ticketId),
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 10000, // Refresh every 10s for real-time updates
  })

  // Assign ticket mutation
  const assignMutation = useMutation({
    mutationFn: () => api.support.assignTicket(ticketId, user?.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      toast.success('Ticket assigned to you')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to assign ticket')
    },
  })

  // Resolve ticket mutation
  const resolveMutation = useMutation({
    mutationFn: () => api.support.resolveTicket(ticketId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      toast.success('Ticket marked as resolved')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to resolve ticket')
    },
  })

  // Add message mutation
  const addMessageMutation = useMutation({
    mutationFn: (data: { message: string; is_internal: boolean }) =>
      api.support.addMessage(ticketId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      toast.success('Message sent')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to send message')
    },
  })

  const handleAddMessage = async (message: string, isInternal: boolean) => {
    await addMessageMutation.mutateAsync({ message, is_internal: isInternal })
  }

  // Loading state
  if (authLoading || isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">Loading ticket...</p>
        </div>
      </div>
    )
  }

  // Access denied
  if (!user?.is_admin) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Access Denied</h1>
          <p className="text-muted-foreground">Admin privileges required</p>
        </div>
      </div>
    )
  }

  if (!ticketDetail) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Ticket Not Found</h1>
          <Button onClick={() => router.push('/dashboard/support')}>
            Back to Tickets
          </Button>
        </div>
      </div>
    )
  }

  const { ticket, messages } = ticketDetail

  const getStatusBadge = (status: string) => {
    const variants = {
      open: { variant: 'default' as const, label: 'Open' },
      in_progress: { variant: 'default' as const, label: 'In Progress' },
      waiting_customer: { variant: 'secondary' as const, label: 'Waiting Customer' },
      resolved: { variant: 'secondary' as const, label: 'Resolved' },
      closed: { variant: 'secondary' as const, label: 'Closed' },
    }
    const config = variants[status as keyof typeof variants] || variants.open
    return <Badge variant={config.variant}>{config.label}</Badge>
  }

  const getPriorityBadge = (priority: string) => {
    const colors = {
      low: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
      medium: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
      high: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
      urgent: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    }
    return (
      <Badge className={colors[priority as keyof typeof colors] || colors.low}>
        {priority.toUpperCase()}
      </Badge>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Button
          variant="ghost"
          onClick={() => router.push('/dashboard/support')}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to tickets
        </Button>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h1 className="text-3xl font-bold tracking-tight">{ticket.ticket_number}</h1>
              {getStatusBadge(ticket.status)}
              {getPriorityBadge(ticket.priority)}
            </div>
            <h2 className="text-xl text-muted-foreground">{ticket.subject}</h2>
          </div>
          <div className="flex gap-2">
            {!ticket.assigned_to && (
              <Button
                onClick={() => assignMutation.mutate()}
                disabled={assignMutation.isPending}
                size="sm"
              >
                {assignMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                Assign to Me
              </Button>
            )}
            {ticket.status !== 'resolved' && ticket.status !== 'closed' && (
              <Button
                onClick={() => resolveMutation.mutate()}
                disabled={resolveMutation.isPending}
                variant="outline"
                size="sm"
              >
                {resolveMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                Mark Resolved
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Main Content - 2/3 width */}
        <div className="md:col-span-2 space-y-6">
          {/* Messages */}
          <Card>
            <CardHeader>
              <CardTitle>Conversation</CardTitle>
              <CardDescription>
                {messages.length} message{messages.length !== 1 ? 's' : ''} in this thread
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TicketMessageThread messages={messages} loading={isLoading} />
            </CardContent>
          </Card>

          {/* Reply Form */}
          <TicketReplyForm
            onSubmit={handleAddMessage}
            loading={addMessageMutation.isPending}
            ticketId={ticketId}
          />
        </div>

        {/* Sidebar - 1/3 width */}
        <div className="space-y-6">
          {/* Ticket Info */}
          <Card>
            <CardHeader>
              <CardTitle>Ticket Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-start gap-3">
                <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium">User ID</p>
                  <p className="text-sm text-muted-foreground">#{ticket.user_id}</p>
                </div>
              </div>

              <Separator />

              <div className="flex items-start gap-3">
                <Tag className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium">Category</p>
                  <p className="text-sm text-muted-foreground capitalize">
                    {ticket.category.replace('_', ' ')}
                  </p>
                </div>
              </div>

              <Separator />

              <div className="flex items-start gap-3">
                <Calendar className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium">Created</p>
                  <p className="text-sm text-muted-foreground">
                    {formatDate(ticket.created_at)}
                  </p>
                </div>
              </div>

              <Separator />

              <div className="flex items-start gap-3">
                <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium">Last Updated</p>
                  <p className="text-sm text-muted-foreground">
                    {formatDate(ticket.updated_at)}
                  </p>
                </div>
              </div>

              {ticket.assigned_to_name && (
                <>
                  <Separator />
                  <div className="flex items-start gap-3">
                    <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium">Assigned To</p>
                      <p className="text-sm text-muted-foreground">
                        {ticket.assigned_to_name}
                      </p>
                    </div>
                  </div>
                </>
              )}

              {ticket.resolved_at && (
                <>
                  <Separator />
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium">Resolved</p>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(ticket.resolved_at)}
                      </p>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button variant="outline" className="w-full justify-start" size="sm" disabled>
                Change Status
              </Button>
              <Button variant="outline" className="w-full justify-start" size="sm" disabled>
                Change Priority
              </Button>
              <Button variant="outline" className="w-full justify-start" size="sm" disabled>
                Reassign Ticket
              </Button>
              <Button
                variant="outline"
                className="w-full justify-start"
                size="sm"
                onClick={() => router.push(`/dashboard/users?search=${ticket.user_id}`)}
              >
                View User Profile
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
